#!/usr/bin/env python3
"""A11: many agents on one machine, every machine and both tasks.

Per agent (own event log): wall = run start to its final result. Per level N:
median and p95 agent wall, throughput = N / time until the last agent
finished (agents per minute, median over groups), CPU seconds per agent =
group CPU (sampler) / N, group memory peak, solve rate with a 95% Wilson
interval. Capacity from one agent = vCPUs / (CPU seconds per agent at N=1 /
agent wall at N=1) * 60 / (agent wall at N=1): the throughput a naive
estimate expects if agents only add CPU demand.

  python rev/a11_density.py   -> rev/a11.txt, rev/a11.csv
"""
import csv, json, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import FIRST, REV, wilson   # noqa: E402
from predict import intervals           # noqa: E402

SETS = [('M0 first pass', 4, FIRST, ['density']), ('M0 revision', 4, REV, ['r_density', 'r_density_more']),
        ('M1', 2, REV, ['m1_density']), ('M2', 8, REV, ['m2_density']),
        ('M0 revision, Requests in Docker', 4, REV, ['r_density_real'])]


def group(run):
    spec = json.loads((run / 'spec.json').read_text())
    res = json.loads((run / 'result.json').read_text())
    t0 = json.loads(open(run / 'meta' / 'clock_anchors.jsonl').readline())['realtime']
    walls, oks = [], []
    for a in res['agents']:
        turns, tools, _, t_res, _ = intervals(run, a['agent'])
        end = t_res or max([b for _, b in turns + tools], default=t0)
        walls.append(end - t0)
        oks.append(a['agent_exit'] == 0 and a['task_check_exit'] == 0)
    s = [json.loads(l) for l in open(run / 'samples.jsonl')]
    cpu = (s[-1]['group']['cpu_usage_usec'] - s[0]['group']['cpu_usage_usec']) / 1e6
    peak = int((run / 'meta' / 'memory.peak').read_text()) / 2**20
    return spec['agents'], walls, oks, cpu, peak


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


rows, lines = [], []
for name, vcpu, root, camps in SETS:
    by = defaultdict(list)
    for run in sorted(r for camp in camps for r in (root / camp).glob('*/result.json')):
        if json.loads((run.parent / 'spec.json').read_text()).get('trace') == 'none':
            continue
        n, walls, oks, cpu, peak = group(run.parent)
        by[n].append((walls, oks, cpu, peak))
    if 1 not in by:
        continue
    w1 = st.median(w for g in by[1] for w in g[0])
    c1 = st.median(g[2] for g in by[1])
    naive = vcpu / (c1 / w1) * 60 / w1          # agents per minute if each agent only adds its CPU demand
    lines.append(f'\n== {name} ({vcpu} vCPU)   one agent: wall {w1:.1f} s, {c1:.1f} CPU-s; '
                 f'capacity from one agent: {naive:.0f} agents/min')
    lines.append(f"{'N':>4}{'groups':>7}{'agents':>7}{'solved [95%]':>20}{'wall med':>9}{'p95':>7}{'max':>7}"
                 f"{'x med':>7}{'x p95':>7}{'agents/min':>11}{'CPU-s/agent':>12}{'mem peak MB':>12}{'MB/agent':>9}")
    for n in sorted(by):
        g = by[n]
        walls = [w for x in g for w in x[0]]
        ok = sum(o for x in g for o in x[1])
        lo, hi = wilson(ok, len(walls))
        thr = st.median(n / max(x[0]) * 60 for x in g)
        cpa = st.median(x[2] / n for x in g)
        peak = st.median(x[3] for x in g)
        lines.append(f'{n:>4}{len(g):>7}{len(walls):>7}{ok:>6}/{len(walls):<4}[{lo:.2f}-{hi:.2f}]{st.median(walls):>9.1f}'
                     f'{pct(walls, .95):>7.1f}{max(walls):>7.1f}{st.median(walls) / w1:>7.2f}{pct(walls, .95) / w1:>7.2f}'
                     f'{thr:>11.1f}{cpa:>12.1f}{peak:>12.0f}{peak / n:>9.0f}')
        rows.append(dict(set=name, vcpu=vcpu, n=n, groups=len(g), agents=len(walls), solved=ok,
                         wall_med=round(st.median(walls), 2), wall_p95=round(pct(walls, .95), 2), wall_max=round(max(walls), 2),
                         agents_per_min=round(thr, 2), cpu_s_per_agent=round(cpa, 2), mem_peak_mb=round(peak),
                         naive_capacity=round(naive, 1)))
with open(HERE / 'a11.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
(HERE / 'a11.txt').write_text('\n'.join(lines).lstrip() + '\n')
print('\n'.join(lines))
