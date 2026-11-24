#!/usr/bin/env python3
"""A6: does a breaking point move if "slower" means 5% or 20% instead of 10%?

Breaking point = the loosest level whose 95% interval of the slowdown lies
above 1 + threshold (as in rq2/curves.py). Reads a curves.csv (rows are in
loose-to-tight order per experiment, model and task).

  python rev/a6_thresholds.py [curves.csv]   -> rev/a6.txt
"""
import csv, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / 'rq2' / 'curves.csv'
TH = (0.05, 0.10, 0.20)
curves = defaultdict(list)
for r in csv.DictReader(open(src)):   # rq2/curves.csv (per model, task) or rev/machines.csv (per machine)
    r.setdefault('ci_lo', r.get('wall_lo'))
    r['local_ci_lo'] = r.get('local_ci_lo') or r.get('local_lo')
    curves[(r['experiment'][:16], r.get('machine') or r.get('model'), r.get('task', '')[:14])].append(r)


def knee(levels, col, th):
    return next((r['level'] for r in levels if float(r[col]) > 1 + th), '-')


lines = [f"{'experiment':16} {'model':10} {'task':14} {'part':5} " + ' '.join(f'{f"{t:.0%}":>22}' for t in TH) + '  same?']
moved = total = far = 0
for (exp, model, task), levels in curves.items():
    for part, col in (('wall', 'ci_lo'), ('local', 'local_ci_lo')):
        ks = [knee(levels, col, t) for t in TH]
        names = [r['level'] for r in levels] + ['-']           # '-' = none in range, one step past the tightest
        steps = max(names.index(k) for k in ks) - min(names.index(k) for k in ks)
        total += 1
        moved += steps > 0
        far += steps > 1
        lines.append(f'{exp:16} {model:10} {task:14} {part:5} ' + ' '.join(f'{k[:22]:>22}' for k in ks)
                     + ('  same' if not steps else f'  moves {steps} level' + 's' * (steps > 1)))
lines.append(f'\n{total - moved} of {total} breaking points are the same at 5%, 10% and 20%; '
             f'{moved - far} move by one level; {far} move by more.')
(HERE / ('a6.txt' if 'curves' in src.name else f'a6_{src.stem}.txt')).write_text('\n'.join(lines) + '\n')
print('\n'.join(lines))
