#!/usr/bin/env python3
"""Review 2: the headline numbers with other summaries than the median.

  1. Replay error: median, mean and 90th percentile of the absolute error (a1_cells.csv).
  2. Real tasks (set 1): slowdown with per-task means instead of per-task medians.
  (Breaking points with means: machines.py.)

  python rev/robust.py -> rev/robust.txt
"""
import csv, json, statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
P2 = HERE.parent
out = []


def p(*a):
    out.append(' '.join(str(x) for x in a))
    print(*a)


cells = [r for r in csv.DictReader(open(HERE / 'a1_cells.csv')) if r['role'] == 'held-out']
p(f'1. Replay, {len(cells)} held-out settings: absolute error of the predicted wall time')
p(f"{'method':<28}{'median':>8}{'mean':>8}{'p90':>8}{'max':>8}{'within 20%':>12}")
for name, k in (('replay', 'replay'), ('Eq. 1 with s = 1/q', 'eq1_quota'), ('wall unchanged', 'unchanged'),
                ('wall = 1/q', 'quota'), ('Eq. 1 with measured s', 'eq1_measured')):
    e = sorted(abs(float(r[k]) / float(r['obs']) - 1) for r in cells)
    p(f'{name:<28}{st.median(e):>8.3f}{st.mean(e):>8.3f}{e[int(.9 * len(e))]:>8.3f}{e[-1]:>8.3f}{sum(x <= .2 for x in e):>12}')
stable = [r for r in cells if abs(float(r['d_model_s'] or 0)) < 2]
e = sorted(abs(float(r['replay']) / float(r['obs']) - 1) for r in stable)
p(f'replay where the model time changed by less than 2 s ({len(e)} settings): median {st.median(e):.3f}  '
  f'mean {st.mean(e):.3f}  p90 {e[int(.9 * len(e))]:.3f}  max {e[-1]:.3f}')

p('\n2. Real tasks, set 1, six short tasks: geometric mean over tasks of the per-task ratio')
f = lambda r, k: float(r[k] or 0)
local = lambda r: f(r, 'wall_s') - f(r, 'model_only_s') - f(r, 'model_tool_s')
g = defaultdict(list)
for r in csv.DictReader(open(P2 / 'rq1' / 'runs.csv')):
    if r['campaign'] in ('real', 'real_quarter'):
        lim = json.loads(r['limits']) if r['limits'] else {}
        g[(r['task_arg'], lim.get('cpu_max', 'none') + ' ' + lim.get('memory_max', ''))].append(r)
tasks = sorted({t for t, _ in g})
p(f"{'size':<24}{'wall, medians':>15}{'wall, means':>13}{'local, medians':>16}{'local, means':>14}")
for size in sorted({s for _, s in g} - {'none '}):
    row = []
    for fn in (lambda r: f(r, 'wall_s'), local):
        for stat in (st.median, st.mean):
            row.append(st.geometric_mean(stat(map(fn, g[(t, size)])) / stat(map(fn, g[(t, 'none ')])) for t in tasks))
    p(f'{size:<24}{row[0]:>15.2f}{row[1]:>13.2f}{row[2]:>16.2f}{row[3]:>14.2f}')
(HERE / 'robust.txt').write_text('\n'.join(out) + '\n')
