"""What does the tracing itself cost? no trace vs core profile vs full profile.

    OSNOISE_RUNS=... python overhead/analyze.py      # -> overhead/overhead.txt

Per run: wall, model, local (= wall - model), start-up, tool time from the
agent's event log (rq1/split.py), CPU time of the agent's group (cpu.stat),
task check, and events the tracer discarded. Ratio of medians against no
trace, 95% bootstrap interval, exact one-sided rank-sum p (traced slower).
"""
import json
import random
import re
import statistics as st
import sys
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'rq1'))
from split import ROOT, split  # noqa: E402

rng = random.Random(7)


def cpu_s(run):
    def usage(when):
        txt = (run / 'meta' / when / 'a1' / 'cpu.stat').read_text()
        return int(re.search(r'usage_usec (\d+)', txt).group(1))
    return (usage('after') - usage('before')) / 1e6


def discarded(run):
    f = run / 'meta' / 'lttng_stats.txt'
    if not f.exists():
        return 0
    return sum(int(x) for x in re.findall(r'[Dd]iscarded[^\d]*(\d+)', f.read_text()))


def boot(a, b, n=2000):
    rs = sorted(st.median(rng.choices(a, k=len(a))) / st.median(rng.choices(b, k=len(b))) for _ in range(n))
    return rs[int(0.025 * n)], rs[int(0.975 * n)]


def rank_p(a, b):
    v = sorted(a + b)
    rank = {x: st.mean(i + 1 for i, y in enumerate(v) if y == x) for x in v}
    r = [rank[x] for x in a + b]
    obs = sum(r[:len(a)])
    sums = [sum(r[i] for i in c) for c in combinations(range(len(r)), len(a))]
    return sum(s >= obs - 1e-9 for s in sums) / len(sums)


MEASURES = ['wall_s', 'model_s', 'local_s', 'startup_s', 'tool_s', 'cpu_s']
lines = []
for camp in ('overhead', 'overhead_real'):
    cells = {}
    for run in sorted((ROOT / camp).iterdir()):
        if not (run / 'result.json').exists():
            continue
        res = json.loads((run / 'result.json').read_text())
        row = split(run)
        row.update(local_s=row['wall_s'] - row['model_s'], cpu_s=cpu_s(run),
                   ok=res['agents'][0]['task_check_exit'] == 0, lost=discarded(run))
        cells.setdefault(res['spec']['trace'], []).append(row)
    lines.append(f'== {camp}')
    for prof in ('none', 'core', 'full'):
        rs = cells[prof]
        lines.append(f"{prof:5} n={len(rs)} solved={sum(r['ok'] for r in rs)} discarded events={sum(r['lost'] for r in rs)}  "
                     + '  '.join(f"{m[:-2]} {st.median(r[m] for r in rs):.2f}" for m in MEASURES))
    for prof in ('core', 'full'):
        lines.append(f'{prof} vs none:')
        for m in MEASURES:
            a, b = [r[m] for r in cells[prof]], [r[m] for r in cells['none']]
            lo, hi = boot(a, b)
            lines.append(f'  {m[:-2]:8} x{st.median(a) / st.median(b):.3f} [{lo:.3f}-{hi:.3f}]  '
                         f'{st.median(a) - st.median(b):+.2f} s  p={rank_p(a, b):.3f}')
    lines.append('')
(HERE / 'overhead.txt').write_text('\n'.join(lines) + '\n')
print('\n'.join(lines))
