#!/usr/bin/env python3
"""Review 2/3: is the 4-agents-per-vCPU limit only a worst case of identical agents
started at the same moment? Compare, on M0 set 2 (4 vCPU, t3):

  together   r_density + r_density_more: all agents start at once (5 groups per level)
  staggered  r_density_stagger: agents 2..N start at a random moment within 60 s
             (meta/stagger.json), 5 groups per level

Per agent: wall = its own start to its final result (the delay is taken off).
Per group: throughput = N / (last finish - first start), agents per minute;
CPU seconds per agent = group CPU / N; the agents alive at once, from the starts
and ends, as a median over the group's busy time and as a peak.

  python rev/a12_stagger.py -> rev/a12.txt, rev/a12.csv
"""
import csv, json, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import REV, wilson    # noqa: E402
from predict import intervals     # noqa: E402

CAMPS = {'together': ['r_density', 'r_density_more'], 'staggered': ['r_density_stagger']}
VCPU = 4
out = []


def p(*a):
    out.append(' '.join(str(x) for x in a))
    print(*a, flush=True)


def group(run):
    spec = json.loads((run / 'spec.json').read_text())
    res = json.loads((run / 'result.json').read_text())
    t0 = json.loads(open(run / 'meta' / 'clock_anchors.jsonl').readline())['realtime']
    n = spec['agents']
    delays = json.loads((run / 'meta' / 'stagger.json').read_text()) if (run / 'meta' / 'stagger.json').exists() else [0.0] * n
    starts, ends, walls, oks = [], [], [], []
    for a, d in zip(res['agents'], delays):
        turns, tools, _, t_res, _ = intervals(run, a['agent'])
        end = t_res or max([b for _, b in turns + tools], default=t0)
        starts.append(t0 + d)
        ends.append(end)
        walls.append(end - (t0 + d))
        oks.append(a['agent_exit'] == 0 and a['task_check_exit'] == 0)
    s = [json.loads(l) for l in open(run / 'samples.jsonl')]
    cpu = (s[-1]['group']['cpu_usage_usec'] - s[0]['group']['cpu_usage_usec']) / 1e6
    span = max(ends) - min(starts)
    # agents alive at once: step through the starts and ends
    ev = sorted([(t, 1) for t in starts] + [(t, -1) for t in ends])
    alive, peak, area, last = 0, 0, 0.0, ev[0][0]
    for t, d in ev:
        area += alive * (t - last)
        alive += d
        peak = max(peak, alive)
        last = t
    return n, walls, oks, cpu, span, peak, area / span


rows = []
for kind, camps in CAMPS.items():
    by = defaultdict(list)
    for camp in camps:
        for r in sorted((REV / camp).glob('*/result.json')):
            n, walls, oks, cpu, span, peak, avg_alive = group(r.parent)
            by[n].append((walls, oks, cpu, span, peak, avg_alive))
    p(f'\n== {kind} (M0 set 2, 4 vCPU, t3)')
    p(f"{'N':>4}{'groups':>7}{'solved':>10}{'agent wall med':>15}{'p95':>7}{'agents/min':>11}{'CPU-s/agent':>12}"
      f"{'alive avg':>10}{'alive peak':>11}{'span s':>8}")
    for n in sorted(by):
        g = by[n]
        walls = [w for x in g for w in x[0]]
        ok = sum(o for x in g for o in x[1])
        thr = st.median(n / x[3] * 60 for x in g)
        cpa = st.median(x[2] / n for x in g)
        p(f'{n:>4}{len(g):>7}{ok:>6}/{len(walls):<4}{st.median(walls):>14.1f}{sorted(walls)[int(.95 * (len(walls) - 1))]:>7.1f}'
          f'{thr:>11.1f}{cpa:>12.1f}{st.median(x[5] for x in g):>10.1f}{st.median(x[4] for x in g):>11.0f}'
          f'{st.median(x[3] for x in g):>8.0f}')
        rows.append(dict(kind=kind, n=n, groups=len(g), agents=len(walls), solved=ok, wall_med=round(st.median(walls), 2),
                         agents_per_min=round(thr, 2), cpu_s_per_agent=round(cpa, 2),
                         alive_avg=round(st.median(x[5] for x in g), 2), alive_peak=round(st.median(x[4] for x in g)),
                         span_s=round(st.median(x[3] for x in g), 1)))
with open(HERE / 'a12.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
(HERE / 'a12.txt').write_text('\n'.join(out).lstrip() + '\n')
