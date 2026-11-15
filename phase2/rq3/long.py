#!/usr/bin/env python3
"""RQ3, longer tasks (real_long): mean slowdown over the tasks that fit in
512 MB, and the hidden-cost model of rq2/hidden.py checked on these new cells.

  python rq3/long.py      (reads rq1/runs.csv; writes rq3/long.txt)

Same method as rq3/table.py (median ratios, mean over tasks, 95% bootstrap,
2000 resamples, seed 7). Model: wall slowdown = 1 + f (s - 1), f = local/wall
of the no-limit runs (medians), s = local slowdown.
"""
import csv, json, random, statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
rng = random.Random(7)
f = lambda r, k: float(r[k] or 0)
wall = lambda r: f(r, 'wall_s')
local = lambda r: wall(r) - f(r, 'model_only_s') - f(r, 'model_tool_s')
NAME = {'{}': 'none', '{"cpu_max": "100000 100000", "memory_max": "512M"}': '1 CPU / 512 MB',
        '{"cpu_max": "25000 100000", "memory_max": "512M"}': '0.25 CPU / 512 MB'}
g = defaultdict(list)
for r in csv.DictReader(open(HERE.parent / 'rq1' / 'runs.csv')):
    if r['campaign'] == 'real_long':
        lim = json.dumps(json.loads(r['limits']) if r['limits'] else {}, sort_keys=True)
        g[(r['task_arg'].split('__')[1], NAME[lim])].append(r)
med = lambda fn, v: st.median(map(fn, v))


def boot(fn, pairs, n=2000):
    est = st.mean(med(fn, a) / med(fn, b) for a, b in pairs)
    rs = sorted(st.mean(med(fn, rng.choices(a, k=len(a))) / med(fn, rng.choices(b, k=len(b))) for a, b in pairs)
                for _ in range(n))
    return f'{est:.2f} [{rs[int(0.025 * n)]:.2f}-{rs[int(0.975 * n)]:.2f}]'


out = []
fit = ['django-15957', 'pytest-10356', 'sympy-14248']      # xarray needs ~810 MB, killed under 512 MB
for name in ('1 CPU / 512 MB', '0.25 CPU / 512 MB'):
    pairs = [(g[(t, name)], g[(t, 'none')]) for t in fit]
    out.append(f'mean of {len(fit)} tasks that fit, {name:<18} wall {boot(wall, pairs)}  local {boot(local, pairs)}')
out.append('')
out.append(f"{'task':<14}{'setting':<19}{'f':>6}{'s':>7}{'pred':>7}{'obs':>7}{'err':>7}")
errs = []
for t in sorted({t for t, _ in g}):
    b = g[(t, 'none')]
    fr = med(local, b) / med(wall, b)
    for name in ('1 CPU / 512 MB', '0.25 CPU / 512 MB'):
        a = g[(t, name)]
        s, obs = med(local, a) / med(local, b), med(wall, a) / med(wall, b)
        pred = 1 + fr * (s - 1)
        errs.append((pred - obs) / obs)
        out.append(f'{t:<14}{name:<19}{fr:6.2f}{s:7.2f}{pred:7.2f}{obs:7.2f}{errs[-1]:+7.1%}')
out.append(f'within 10%: {sum(abs(e) <= 0.10 for e in errs)} of {len(errs)}; median |err| {st.median(map(abs, errs)):.1%}')
(HERE / 'long.txt').write_text('\n'.join(out) + '\n')
print('\n'.join(out))
