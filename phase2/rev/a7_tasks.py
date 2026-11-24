#!/usr/bin/env python3
"""A7 + A9: per-task results of the real SWE-bench tasks, every size and machine.

Three outcomes kept apart (A9):
  speed      wall and local slowdown against the same task with no limit, same data set
  success    solve rate with a 95% Wilson interval (xarray-6992 is never solved, even
             unlimited, and pytest-10356 only 1 of 5: kept for speed, marked, and left out
             of every success claim)
  behaviour  median model turns and tool calls (from the event log)

  python rev/a7_tasks.py   -> rev/a7.txt, rev/a7.csv
"""
import csv, json, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import FIRST, REV, load, med, boot_ratio, wilson   # noqa: E402
sys.path.insert(0, str(HERE.parent / 'rq1'))
from split import intervals                                  # noqa: E402

SETS = [('M0 first pass', FIRST, ['real', 'real_quarter', 'real_long']), ('M0 revision', REV, ['r_real']),
        ('M1', REV, ['m1_real']), ('M2', REV, ['m2_real'])]
NEVER = {'pydata__xarray-6992': ' *never solved', 'pytest-dev__pytest-10356': ' *rarely solved'}


def size(lim):
    l = json.loads(lim)
    if not l:
        return 'none'
    cpu = int(l['cpu_max'].split()[0]) / 100000 if 'cpu_max' in l else None
    return f"{cpu:g} CPU / {l.get('memory_max', 'no cap')}"


def turns_tools(r, root):
    t, tools, *_ = intervals(root / r['campaign'] / r['run'])
    return len(t), len(tools)


rows, lines = [], []
for machine, root, camps in SETS:
    recs = [r for c in camps if (root / c).exists() for r in load(root, c) if r['task'] == 'swe']
    by = defaultdict(lambda: defaultdict(list))
    for r in recs:
        by[r['task_arg']][size(r['limits'])].append(r)
    lines.append(f'\n== {machine}')
    lines.append(f"{'task':28}{'size':20}{'n':>3}{'wall s':>8}{'wall slowdown [95%]':>22}{'local slowdown [95%]':>23}"
                 f"{'solved [95%]':>20}{'turns':>7}{'tools':>7}")
    for task in sorted(by):
        cells = by[task]
        base = cells.get('none')
        for sz in sorted(cells, key=lambda s: (s != 'none', s)):
            v = cells[sz]
            w = [r['wall'] for r in v]
            lw = [r['local'] for r in v if r['local'] is not None]
            if base and v is not base:
                bw, bl = [r['wall'] for r in base], [r['local'] for r in base if r['local'] is not None]
                sw, ci = med(w) / med(bw), boot_ratio(w, bw)
                sl, cil = med(lw) / med(bl), boot_ratio(lw, bl)
            else:
                sw, ci, sl, cil = 1.0, (1.0, 1.0), 1.0, (1.0, 1.0)
            ok = sum(r['ok'] for r in v)
            lo, hi = wilson(ok, len(v))
            tt = [turns_tools(r, root) for r in v]
            nt, nl = med(x[0] for x in tt), med(x[1] for x in tt)
            mark = NEVER.get(task, '')
            lines.append(f'{task[:27]:28}{sz:20}{len(v):>3}{med(w):>8.1f}{sw:>8.2f} [{ci[0]:.2f}-{ci[1]:.2f}]{"":>2}'
                         f'{sl:>8.2f} [{cil[0]:.2f}-{cil[1]:.2f}]{"":>2}{ok:>4}/{len(v):<3}[{lo:.2f}-{hi:.2f}]{nt:>7.0f}{nl:>7.0f}{mark}')
            rows.append(dict(machine=machine, task=task, size=sz, n=len(v), wall_med=round(med(w), 2),
                             wall_slowdown=round(sw, 3), wall_lo=round(ci[0], 3), wall_hi=round(ci[1], 3),
                             local_slowdown=round(sl, 3), local_lo=round(cil[0], 3), local_hi=round(cil[1], 3),
                             solved=ok, solve_lo=round(lo, 3), solve_hi=round(hi, 3), turns=nt, tools=nl,
                             never_solved=task in NEVER, has_baseline=bool(base)))
with open(HERE / 'a7.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
(HERE / 'a7.txt').write_text('\n'.join(lines).lstrip() + '\n')
print('\n'.join(lines))
