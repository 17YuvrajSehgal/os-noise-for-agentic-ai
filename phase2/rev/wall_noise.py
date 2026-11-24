"""How large a change in wall or local time can five runs detect?

For every group of runs with no limit that has at least 10 runs (same task, model,
campaign), draw 5 runs against 5 other runs 4,000 times and take the ratio of the two
medians. The 95th percentile of |ratio - 1| is the change that pure run-to-run variation
produces in 1 of 20 comparisons. Uses rq1/runs.csv (set 1). Seeded.
"""
import csv, random, statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = [r for r in csv.DictReader(open(HERE.parent / 'rq1' / 'runs.csv')) if r['unlimited'] == 'True']
f = lambda r, k: float(r[k] or 0)
groups = defaultdict(list)
for r in rows:
    wall = f(r, 'wall_s')
    model = f(r, 'model_only_s') + f(r, 'model_tool_s')
    if wall > 0:
        groups[(r['task'], r['model'], r['task_arg'][:30])].append((wall, wall - model))
rng = random.Random(7)
print(f"{'group':52} {'n':>3} {'wall p95':>9} {'local p95':>10}")
allw, alll = [], []
for g, v in sorted(groups.items()):
    if len(v) < 10:
        continue
    dw, dl = [], []
    for _ in range(4000):
        s = rng.sample(v, 10)
        a, b = s[:5], s[5:]
        dw.append(abs(st.median(x[0] for x in a) / st.median(x[0] for x in b) - 1))
        dl.append(abs(st.median(x[1] for x in a) / st.median(x[1] for x in b) - 1))
    q = lambda d: sorted(d)[int(0.95 * len(d))]
    allw.append(q(dw)); alll.append(q(dl))
    print(f"{' '.join(g):52} {len(v):>3} {100 * q(dw):>8.0f}% {100 * q(dl):>9.0f}%")
print(f"groups {len(allw)}: wall p95 {100 * min(allw):.0f} to {100 * max(allw):.0f}%, "
      f"local p95 {100 * min(alll):.0f} to {100 * max(alll):.0f}%")
