#!/usr/bin/env python3
"""A8: two limits at once. Is the combined slowdown the sum of the single ones
(additive: S_ab - 1 = (S_a - 1) + (S_b - 1)), their product (S_ab = S_a * S_b),
more, or less?

Slowdown = median time / median time of the unlimited runs of the same task
on the same data set. Done for wall and local time.

  python rev/a8_pairs.py   -> rev/a8.txt
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import FIRST, REV, load, med, boot_ratio   # noqa: E402

CPU5 = '{"cpu_max": "50000 100000"}'
# (name, task, unlimited cells, single a, single b, pair); a cell = (root, campaign, limits json)
PAIRS = [
    ('CPU 0.5 + memory 256 MB (first pass)', 't3_implement',
     [(FIRST, 'cpu', '{}'), (FIRST, 'e2e_memory', '{}')],
     (FIRST, 'cpu', CPU5), (FIRST, 'e2e_memory', '{"memory_max": "256M"}'),
     (FIRST, 'two_limits', '{"cpu_max": "50000 100000", "memory_max": "256M"}')),
    ('CPU 0.5 + disk 20 MB/s (revision)', 't3_implement',
     [(REV, 'r_cpu', '{}')],
     (REV, 'r_cpu', CPU5), (REV, 'r_interact', '{"io_max": {"rbps": 20971520}}'),
     (REV, 'r_interact', '{"cpu_max": "50000 100000", "io_max": {"rbps": 20971520}}')),
    ('memory 192 MB + 20 processes (revision)', 't3_implement',
     [(REV, 'r_cpu', '{}')],
     (REV, 'r_interact', '{"memory_max": "192M"}'), (REV, 'r_pids', '{"pids_max": 20}'),
     (REV, 'r_interact', '{"memory_max": "192M", "pids_max": 20}')),
    # only one of the two single limits was measured on these tasks
    ('CPU 0.5 + soft memory 768 MB (t6, single CPU missing)', 't6_memtouch',
     [(FIRST, 'memory_soft', '{}')],
     None, (FIRST, 'memory_soft', '{"memory_high": "768M"}'),
     (FIRST, 'two_limits', '{"cpu_max": "50000 100000", "memory_high": "768M"}')),
    ('CPU 0.5 + disk 50 MB/s (t8, single CPU missing)', 't8_ioread',
     [(FIRST, 'disk', '{}')],
     None, (FIRST, 'disk', '{"io_max": {"rbps": 52428800}}'),
     (FIRST, 'two_limits', '{"cpu_max": "50000 100000", "io_max": {"rbps": 52428800}}')),
    ('soft memory 768 MB + disk 50 MB/s (t6, single disk missing)', 't6_memtouch',
     [(FIRST, 'memory_soft', '{}')],
     (FIRST, 'memory_soft', '{"memory_high": "768M"}'), None,
     (FIRST, 'two_limits', '{"io_max": {"rbps": 52428800}, "memory_high": "768M"}')),
]


def cell(c, task):
    root, camp, lim = c
    v = [r for r in load(root, camp) if r['task'] == task and r['limits'] == lim and r['model'] == 'opus-5-5']
    if not v:
        raise SystemExit(f'empty cell {camp} {lim}')
    return v


def verdict(a, b, ci):
    """Which prediction lies inside the pair's 95% interval."""
    add, mul = a + b - 1, a * b
    inside = lambda x: ci[0] <= x <= ci[1]
    if inside(add) and inside(mul):
        return 'additive or multiplying (cannot tell apart)'
    if inside(add):
        return 'additive'
    if inside(mul):
        return 'multiplying'
    if inside(max(a, b)):
        return 'same as the stronger limit alone (the other adds nothing)'
    if ci[0] > max(add, mul):
        return 'more than multiplying'
    if ci[1] < min(add, mul):
        return 'less than additive'
    return 'between additive and multiplying'


lines = []
for name, task, bases, ca, cb, cab in PAIRS:
    base = [r for c in bases for r in cell(c, task)]
    lines.append(f'\n== {name}  (unlimited n={len(base)})')
    for part in ('wall', 'local'):
        b0 = [r[part] for r in base if r[part] is not None]
        sd = {}
        for tag, c in (('a', ca), ('b', cb), ('pair', cab)):
            if c is None:
                continue
            v = cell(c, task)
            x = [r[part] for r in v if r[part] is not None]
            ci = boot_ratio(x, b0)
            sd[tag] = (med(x) / med(b0), ci, len(v), sum(not r['ok'] for r in v))
        row = '  '.join(f'{t}: {s:.2f} [{lo:.2f}-{hi:.2f}] n={n}' + (f' fail={fl}' if fl else '')
                        for t, (s, (lo, hi), n, fl) in sd.items())
        if 'a' in sd and 'b' in sd:
            a, b, (s, ci, *_ ) = sd['a'][0], sd['b'][0], sd['pair']
            row += f'   sum {a + b - 1:.2f}  product {a * b:.2f}  -> {verdict(a, b, ci)}'
        else:
            one = sd.get('a') or sd.get('b')
            row += f'   pair / single = {sd["pair"][0] / one[0]:.2f}'
        lines.append(f'  {part:5} {row}')
(HERE / 'a8.txt').write_text('\n'.join(lines).lstrip() + '\n')
print('\n'.join(lines))
