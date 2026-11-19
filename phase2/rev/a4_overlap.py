#!/usr/bin/env python3
"""A4: how much machine work does the event log count as model time?

The paper's local time is wall minus model time, where model time is any
moment a model answer is open in the agent's event log. A tool that runs
while the model still streams is then counted as model time, so local time
is a lower bound. Here the kernel trace decides instead: every process the
run started (from the trace's exec list) except the agent binary and the
collector's wrappers is machine work. Its lifetime and its CPU (10 ms steps)
that fall inside model time (any open model answer) are the hidden part.

Trace and event clocks agree to about 20 ms (a Bash process starts 20-200 ms
after its tool_use event), so no offset is applied.

  python rev/a4_overlap.py <phase2 campaign dirs...>   -> rev/a4.txt, rev/a4_runs.csv
"""
import csv, json, os, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
P2 = HERE.parent
sys.path.insert(0, str(HERE))
from predict import intervals      # noqa: E402  (also sets OSNOISE_RUNS)
from common import FIRST, REV      # noqa: E402

WRAPPERS = ('/usr/bin/bash', '/usr/bin/sudo', '/usr/bin/tee', '/usr/bin/timeout')
STEP = 0.01


def union(iv):
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def inter_len(iv, other):
    tot, j = 0.0, 0
    for a, b in iv:
        for c, d in other:
            tot += max(0.0, min(b, d) - max(a, c))
    return tot


def one(d, run):
    a0 = d['anchors'][0]['realtime']
    turns, tools, *_ = intervals(run)
    turns = union([(a - a0, b - a0) for a, b in turns])
    tools = union([(a - a0, b - a0) for a, b in tools])
    model_time = turns          # the paper counts every moment a model answer is open as model time
    wall = d['anchors'][1]['realtime'] - a0
    # not tool work: wrappers, the agent, Docker's init, and anything alive for most of the run
    # (network shaper, busy neighbour, container shell); a pid can exec several of these in turn
    infra = {pid for _, pid, path in d['execs'] if path in WRAPPERS or '/claude' in path or 'docker' in path}
    work = {pid for _, pid, path in d['execs']} - infra
    work = {p for p in work if str(p) in d['procs']
            and d['procs'][str(p)][1] - d['procs'][str(p)][0] < 0.9 * wall}
    life = union([d['procs'][str(p)][:2] for p in work])
    hidden = inter_len(life, model_time)
    cpu_all = cpu_hidden = 0.0
    for p in work:
        for b, on, *_ in d['cpu'].get(str(p), []):
            cpu_all += on
            t = b * STEP
            if any(a <= t < e for a, e in model_time):
                cpu_hidden += on
    model = sum(b - a for a, b in turns)
    return dict(wall=wall, local=wall - model, hidden_s=hidden, work_cpu_s=cpu_all, hidden_cpu_s=cpu_hidden)


if __name__ == '__main__':
    rows = []
    for c in sys.argv[1:]:
        root = REV if c.startswith(('r_', 'm1_', 'm2_')) else FIRST
        for line in open(P2 / c / 'parsed_all.jsonl'):
            d = json.loads(line)
            run = root / c / d['run']
            spec = json.loads((run / 'spec.json').read_text())
            if spec.get('agents', 1) != 1 or spec.get('agent', 'claude') != 'claude':
                continue
            try:
                r = one(d, run)
            except Exception as e:
                print('skip', d['run'], type(e).__name__, e)
                continue
            lim = {k: v for k, v in (spec.get('limits') or {}).items() if v not in (None, 'max', '')}
            rows.append(dict(campaign=c, run=d['run'], limits=json.dumps(lim, sort_keys=True),
                             **{k: round(v, 3) for k, v in r.items()}))
    with open(HERE / 'a4_runs.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    by = defaultdict(list)
    for r in rows:
        by[r['campaign']].append(r)
    share = lambda r: r['hidden_s'] / (r['local'] + r['hidden_s']) if r['local'] + r['hidden_s'] > 0 else 0
    lines = [f"{'campaign':18} {'runs':>4} {'hidden s (med / max)':>21} {'share of local (med / p90 / max)':>34} {'hidden CPU share':>17}"]
    for c, v in by.items():
        sh = sorted(share(r) for r in v)
        cs = [r['hidden_cpu_s'] / r['work_cpu_s'] for r in v if r['work_cpu_s'] > 0]
        lines.append(f"{c:18} {len(v):4d} {st.median(r['hidden_s'] for r in v):10.2f} / {max(r['hidden_s'] for r in v):6.2f}"
                     f"   {st.median(sh):10.1%} / {sh[int(.9 * len(sh))]:6.1%} / {sh[-1]:6.1%}   {st.median(cs) if cs else 0:12.1%}")
    sh = sorted(share(r) for r in rows)
    lines.append(f"\nall {len(rows)} runs: hidden share of local time median {st.median(sh):.1%}, "
                 f"p90 {sh[int(.9 * len(sh))]:.1%}, max {sh[-1]:.1%}")

    # Sensitivity: move the hidden time from model to local time and redo f, s and Eq. 1 per cell.
    cells = defaultdict(list)
    for r in rows:
        cells[(r['campaign'], r['limits'])].append(r)
    lines += ['', 'Eq. 1 per cell, as in the paper (local) and with the hidden time moved to local (local+):',
              f"{'campaign':16} {'limit':44} {'n':>2} {'hidden':>6} {'f':>5} {'f+':>5} {'s':>5} {'s+':>5} "
              f"{'wall':>5} {'err':>6} {'err+':>6}"]
    errs, errs2 = [], []
    for (c, lim), v in sorted(cells.items()):
        base = cells.get((c, '{}'))
        if lim == '{}' or not base:
            continue
        m = lambda xs, k: st.median(x[k] for x in xs)
        m2 = lambda xs: st.median(x['local'] + x['hidden_s'] for x in xs)
        f, f2 = m(base, 'local') / m(base, 'wall'), m2(base) / m(base, 'wall')
        s, s2 = m(v, 'local') / m(base, 'local'), m2(v) / m2(base)
        obs = m(v, 'wall') / m(base, 'wall')
        e, e2 = (1 + f * (s - 1)) / obs - 1, (1 + f2 * (s2 - 1)) / obs - 1
        errs.append(abs(e)); errs2.append(abs(e2))
        lines.append(f"{c:16} {lim[:44]:44} {len(v):2d} {m(v, 'hidden_s'):6.2f} {f:5.2f} {f2:5.2f} {s:5.2f} {s2:5.2f} "
                     f"{obs:5.2f} {e:+6.1%} {e2:+6.1%}")
    lines.append(f'\n{len(errs)} cells: median |err| {st.median(errs):.1%} as in the paper, '
                 f'{st.median(errs2):.1%} with hidden time as local; within 10%: '
                 f'{sum(x <= .1 for x in errs)} vs {sum(x <= .1 for x in errs2)}')
    (HERE / 'a4.txt').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))
