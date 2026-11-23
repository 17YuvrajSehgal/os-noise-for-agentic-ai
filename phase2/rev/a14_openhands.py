#!/usr/bin/env python3
"""A second agent: OpenHands CLI (Haiku through the API) on t3 under a CPU quota.

Small check that the CPU results do not belong to Claude Code only (campaign r_oh_cpu,
5 runs per step). The OpenHands event log is different from Claude Code's, so the split
into model wait and local time is done here:

  - every JSON event carries its own timestamp (UTC). The output is buffered, so the
    arrival time that the collector stamps is not used.
  - a model turn opens at the user message, or when the last pending tool call returns.
    It closes at the first event of the model's next answer (an action or a message).
  - a tool call runs from its action event to its observation event.
  - local time = wall time minus model wait, as for Claude Code. Start-up is the time
    from the start of the run to the user message; it is local time.

For each step: wall and local slowdown against no limit (medians, 95% bootstrap), the
local share f, Equation 1 with the measured s and with s = 1/q, and from cpu.stat the CPU
time used and the time throttled (does the quota add work or waiting?).

  python rev/a14_openhands.py [runs dir] -> rev/a14.txt
"""
import json, statistics as st, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import boot_ratio   # noqa: E402
from predict import samples, predict   # noqa: E402

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else
            'C:/workplace/microservice-trace-dataset/agentic-runs-phase2/runs-oh/r_oh_cpu')
out = []


def p(*a):
    out.append(' '.join(str(x) for x in a))
    print(*a)


def events(run):
    ev = []
    for line in open(run / 'a1' / 'events.jsonl', encoding='utf-8'):
        x = json.loads(line)['line']
        if x.startswith('{'):
            try:
                d = json.loads(x)
            except ValueError:
                continue
            if 'timestamp' in d and 'kind' in d:
                d['t'] = datetime.fromisoformat(d['timestamp']).replace(tzinfo=timezone.utc).timestamp()
                ev.append(d)
    return sorted(ev, key=lambda d: d['t'])


def split(run):
    """-> dict(wall, model, local, startup, tool, turns, tools) in seconds / counts."""
    an = [json.loads(l) for l in open(run / 'meta' / 'clock_anchors.jsonl')]
    t0, t1 = an[0]['realtime'], an[-1]['realtime']
    ev = events(run)
    model = tool = 0.0
    iv = []
    turn_open, pending, turns, tools, first = None, {}, 0, 0, None
    for d in ev:
        k, src = d['kind'], d.get('source')
        if k == 'MessageEvent' and src == 'user':
            turn_open, first = d['t'], first or d['t']
        elif src == 'agent' and k in ('ActionEvent', 'MessageEvent'):
            if turn_open is not None:          # first event of a new answer closes the model turn
                model += d['t'] - turn_open
                iv.append((turn_open, d['t']))
                turns += 1
                turn_open = None
            if k == 'ActionEvent':
                pending[d.get('tool_call_id') or d['id']] = d['t']
                tools += 1
        elif k in ('ObservationEvent', 'AgentErrorEvent', 'UserRejectObservation'):
            a = pending.pop(d.get('tool_call_id'), None)
            if a is not None:
                tool += d['t'] - a
            if not pending:
                turn_open = d['t']             # all results are back: the model is asked again
    wall = t1 - t0
    return dict(wall=wall, model=model, local=wall - model, startup=(first - t0) if first else None,
                tool=tool, turns=turns, tools=tools, iv=iv, t0=t0, t1=t1)


def slices(run, r):
    """The run cut into the sampler's slices: (dt, cpu s, bytes read, inside a model turn), as predict.slices."""
    sm, sl = samples(run), []
    for (ta, ca, ba), (tb, cb, bb) in zip(sm, sm[1:]):
        a, b = max(ta, r['t0']), min(tb, r['t1'])
        if b <= a:
            continue
        k, mid = (b - a) / (tb - ta), (a + b) / 2
        sl.append((b - a, (cb - ca) * k, (bb - ba) * k, any(x <= mid <= y for x, y in r['iv'])))
    sl.append((max(0.0, r['wall'] - sum(x[0] for x in sl)), 0.0, 0.0, False))
    return sl


def cpu_stat(run, tag):
    f = run / 'meta' / f'cpu.stat.{tag}'
    return {k: int(v) for k, v in (l.split() for l in f.read_text().splitlines())} if f.exists() else {}


by = {}
for sp in sorted(ROOT.glob('*/spec.json')):
    run = sp.parent
    s = json.loads(sp.read_text())
    if not (run / 'result.json').exists():
        continue
    res = json.loads((run / 'result.json').read_text())
    q = s['limits'].get('cpu_max')
    q = None if q in (None, 'max') else int(q.split()[0]) / int(q.split()[1])
    r = split(run)
    r['sl'] = slices(run, r)
    a, b = cpu_stat(run, 'before'), cpu_stat(run, 'after')
    r.update(ok=res['ok'], cpu=(b.get('usage_usec', 0) - a.get('usage_usec', 0)) / 1e6,
             thr=(b.get('throttled_usec', 0) - a.get('throttled_usec', 0)) / 1e6, run=run.name)
    by.setdefault(q, []).append(r)

m = lambda rs, k: st.median(r[k] for r in rs)
base = by[None]
f = m(base, 'local') / m(base, 'wall')
p(f'OpenHands CLI, Haiku, t3_implement, M0. Runs with no limit: {len(base)}; local share f = {f:.2f}')
p(f"{'quota':>6} {'n':>2} {'solved':>6} {'wall s':>7} {'model s':>8} {'local s':>8} {'startup':>8} {'turns':>5} {'tools':>5} "
  f"{'CPU s':>6} {'throttled s':>11}   {'wall x [95%]':<18} {'local x [95%]':<18} {'Eq.1 measured s':>15} {'Eq.1 s=1/q':>11}")
for q in sorted(by, key=lambda x: -(x or 9)):
    rs = by[q]
    w = (m(rs, 'wall') / m(base, 'wall'),) + tuple(boot_ratio([r['wall'] for r in rs], [r['wall'] for r in base]))
    l = (m(rs, 'local') / m(base, 'local'),) + tuple(boot_ratio([r['local'] for r in rs], [r['local'] for r in base]))
    e1 = 1 + f * (l[0] - 1)
    e2 = 1 + f * (max(1, 1 / q) - 1) if q else 1.0
    p(f"{q or 'none':>6} {len(rs):>2} {sum(r['ok'] for r in rs):>3}/{len(rs):<2} {m(rs, 'wall'):>7.1f} {m(rs, 'model'):>8.1f} "
      f"{m(rs, 'local'):>8.1f} {m(rs, 'startup'):>8.1f} {m(rs, 'turns'):>5.0f} {m(rs, 'tools'):>5.0f} {m(rs, 'cpu'):>6.1f} "
      f"{m(rs, 'thr'):>11.1f}   {w[0]:.2f} [{w[1]:.2f}-{w[2]:.2f}]   {l[0]:.2f} [{l[1]:.2f}-{l[2]:.2f}]   "
      f"{e1:>6.2f} ({100 * (e1 / w[0] - 1):+.0f}%) {e2:>6.2f} ({100 * (e2 / w[0] - 1):+.0f}%)")
p('\nreplay of the runs with no limit (median over the 5 runs), against the measured medians')
for q in sorted((x for x in by if x), reverse=True):
    rs = by[q]
    pw = st.median(predict(r['sl'], q) for r in base)
    pl = st.median(predict(r['sl'], q) - r['model'] for r in base)
    nl = m(base, 'local') * max(1, 1 / q)
    p(f"  {q:>5}: wall predicted {pw:.1f} measured {m(rs, 'wall'):.1f} ({100 * (pw / m(rs, 'wall') - 1):+.1f}%); "
      f"local predicted {pl:.1f} measured {m(rs, 'local'):.1f} ({100 * (pl / m(rs, 'local') - 1):+.1f}%); "
      f"s = 1/q gives local {nl:.1f} ({100 * (nl / m(rs, 'local') - 1):+.1f}%)")
p('\nper run')
for q in sorted(by, key=lambda x: -(x or 9)):
    for r in by[q]:
        p(f"  {q or 'none':>6} {r['run'][-12:]:<12} ok={r['ok']!s:<5} wall {r['wall']:>6.1f} model {r['model']:>6.1f} local {r['local']:>6.1f} "
          f"turns {r['turns']:>2} tools {r['tools']:>2} cpu {r['cpu']:>5.1f} thr {r['thr']:>6.1f}")
(HERE / 'a14.txt').write_text('\n'.join(out) + '\n', encoding='utf-8')
