#!/usr/bin/env python3
"""Per-run tables for two paper figures (paper-icpe/figures/make_figures.py reads them).

  fig_timeline.csv  one typical t3 run with no limit and one at 0.25 core (set 2,
                    the run with the median wall time), as model/local segments.
  fig_feedback.csv  every Haiku run of the printed-run-time controls (set 2):
                    tool calls after the tests first pass, and wall time.

  python rev/fig_data.py
"""
import csv, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import REV, load          # noqa: E402
from predict import slices            # noqa: E402
import behaviour                      # noqa: E402  (its per-run records: behaviour.fb)

# --- timeline -----------------------------------------------------------------------------
rows = []
for name, lim in (('no limit', '{}'), ('0.25 core', json.dumps({'cpu_max': '25000 100000'}))):
    runs = sorted((r for r in load(REV, 'r_cpu') if r['limits'] == lim and r['local'] is not None),
                  key=lambda r: r['wall'])
    r = runs[len(runs) // 2]
    sl, wall = slices(REV / 'r_cpu' / r['run'])
    t, seg = 0.0, []
    for dt, _cpu, _rd, model in sl:
        kind = 'model' if model else 'local'
        if seg and seg[-1][2] == kind:
            seg[-1][1] += dt
        else:
            seg.append([t, dt, kind])
        t += dt
    rows += [dict(cond=name, run=r['run'], start=round(a, 3), dur=round(d, 3), kind=k) for a, d, k in seg]
with open(HERE / 'fig_timeline.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['cond', 'run', 'start', 'dur', 'kind'])
    w.writeheader()
    w.writerows(rows)

# --- feedback controls ----------------------------------------------------------------------
Q = behaviour.Q
CELLS = [('time printed', 't3', Q), ('no time printed', 't9', Q), ('fixed fast time printed', 't11 const_fast', Q),
         ('time printed + "not a goal"', 't11 instruct', Q), ('time printed', 't3', 'none'),
         ('fixed slow time printed', 't11 const_slow', 'none')]
with open(HERE / 'fig_feedback.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['label', 'limit', 'after', 'wall'])
    for label, task, lim in CELLS:
        for r in behaviour.fb[('rev haiku-5-5', task, lim)]:
            w.writerow([label, '0.25 core' if lim == Q else 'no limit', r['after'], r['wall']])
print('wrote fig_timeline.csv, fig_feedback.csv')
