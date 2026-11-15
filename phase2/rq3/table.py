#!/usr/bin/env python3
"""RQ3: real coding tasks (SWE-bench Verified, Docker, Opus) at platform
settings, each against the same task with no limit.

  python rq3/table.py [campaign ...]   (default real real_quarter -> rq3/table.txt;
                                        others -> rq3/table_<first>.txt)

Slowdown and local slowdown as in rq2/curves.py (median ratio, 95% bootstrap,
2000 resamples, seed 7). "all tasks" = mean of the six per-task median ratios,
bootstrapped by resampling runs inside each task. Throttled = time the cgroup
was held back by its CPU quota (cpu.stat); mem peak = memory.peak of the
agent's cgroup, which includes file cache.
"""
import csv, json, random, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
P2 = HERE.parent
SETTINGS = [('none', {}), ('2 CPU / 8 GB', {'cpu_max': '200000 100000', 'memory_max': '8G'}),
            ('2 CPU / 512 MB', {'cpu_max': '200000 100000', 'memory_max': '512M'}),
            ('1 CPU / 512 MB', {'cpu_max': '100000 100000', 'memory_max': '512M'}),
            ('0.25 CPU / 512 MB', {'cpu_max': '25000 100000', 'memory_max': '512M'})]
f = lambda r, k: float(r[k] or 0)
local = lambda r: f(r, 'wall_s') - f(r, 'model_only_s') - f(r, 'model_tool_s')
rng = random.Random(7)

CAMPS = sys.argv[1:] or ['real', 'real_quarter']
cnt = {r['run']: r for c in CAMPS for r in csv.DictReader(open(P2 / c / 'counters.csv'))}
g = defaultdict(list)
for r in csv.DictReader(open(P2 / 'rq1' / 'runs.csv')):
    if r['campaign'] in CAMPS:
        lim = json.loads(r['limits']) if r['limits'] else {}
        name = next(n for n, l in SETTINGS if l == lim)
        g[(r['task_arg'].split('__')[1], name)].append({**r, **{k: cnt[r['run']][k] for k in
                                                                 ('throttled_s', 'mem_peak_mb', 'oom_kill', 'psi_mem_s')}})
tasks = sorted({t for t, _ in g})


def boot(fn, pairs, n=2000):
    """pairs: list of (runs, base runs); returns the mean over pairs of median(fn) ratios, with a 95% interval."""
    est = st.mean(st.median(map(fn, a)) / st.median(map(fn, b)) for a, b in pairs)
    rs = sorted(st.mean(st.median(map(fn, rng.choices(a, k=len(a)))) / st.median(map(fn, rng.choices(b, k=len(b))))
                        for a, b in pairs) for _ in range(n))
    return est, rs[int(0.025 * n)], rs[int(0.975 * n)]


cols = f"{'task':<15}{'setting':<19}{'n':>3}{'ok':>4}{'wall':>7}{'slowdown [95%]':>21}{'local':>7}{'local slowdown':>21}" \
       f"{'throttled':>10}{'cpuWait':>8}{'memPeak':>8}{'reclaim':>8}{'diskWait':>9}{'toolCPU':>8}{'turns':>6}"
out = [cols]
for t in tasks + ['all tasks']:
    for name, _ in SETTINGS:
        if not g[(tasks[0], name)]:
            continue                            # setting not in these campaigns
        ts = tasks if t == 'all tasks' else [t]
        pairs = [(g[(x, name)], g[(x, 'none')]) for x in ts]
        v = [r for a, _ in pairs for r in a]
        md = lambda k: st.median(f(r, k) for r in v)
        if name == 'none':
            s = ls = (1.0, 1.0, 1.0)
        else:
            s, ls = boot(lambda r: f(r, 'wall_s'), pairs), boot(local, pairs)
        out.append(f"{t:<15}{name:<19}{len(v):>3}{sum(r['ok'] == 'True' for r in v):>4}{md('wall_s'):>7.1f}"
                   f"{s[0]:>8.2f} [{s[1]:.2f}-{s[2]:.2f}]{st.median(map(local, v)):>7.1f}{ls[0]:>8.2f} [{ls[1]:.2f}-{ls[2]:.2f}]"
                   f"{md('throttled_s'):>10.1f}{st.median(f(r, 'wait_cpu_quota_s') + f(r, 'wait_cpu_busy_s') for r in v):>8.1f}"
                   f"{md('mem_peak_mb'):>8.0f}{md('reclaim_n'):>8.0f}{md('wait_disk_s'):>9.1f}{md('tool_cpu_s'):>8.1f}{md('turns_log'):>6.0f}")
    out.append('')
oom = sum(int(r['oom_kill'] or 0) for v in g.values() for r in v)
at_limit = sorted((t, n, r['run'].rsplit('_', 1)[1]) for (t, n), v in g.items() if '512' in n
                  for r in v if f(r, 'mem_peak_mb') >= 511)
out.append(f'memory kills: {oom}; runs whose memory reached the 512 MB limit: {len(at_limit)} {at_limit}')
(HERE / ('table.txt' if sys.argv[1:] in ([], ['real', 'real_quarter']) else f'table_{CAMPS[0]}.txt')).write_text('\n'.join(out) + '\n')
print('\n'.join(out))
