#!/usr/bin/env python3
"""Review 3, point 6: why does the kernel kill the agent instead of the 700 MB test?

The kernel's OOM report (printk) is in the trace: a table of every task in the memory
cgroup (rss, oom_score_adj, name) and the line "Killed process <pid> (<name>) anon-rss".
For every OOM kill in t12 at memory.max 768M with no fix (r_cutout), list the victim and
the largest tasks in the table at that moment.

  python rev/oom_victims.py -> rev/oom_victims.txt
"""
import gzip, re, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import REV   # noqa: E402

MSG = re.compile(r'printk_console: .*?msg = "(.*)" \}\s*$')
ROW = re.compile(r'^\[\s*(\d+)\]\s+\d+\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(\S+)')
KILL = re.compile(r'Killed process (\d+) \((.*?)\).*?anon-rss:(\d+)kB')
out = []


def p(*a):
    out.append(' '.join(str(x) for x in a))
    print(*a)


def kills(run):
    """[(victim name, victim anon MB, [(name, rss MB) of the 3 largest tasks])] per OOM kill."""
    res, table = [], []
    with gzip.open(run / 'trace.txt.gz', 'rt', errors='ignore') as f:
        for line in f:
            if 'printk_console' not in line:
                continue
            m = MSG.search(line)
            if not m:
                continue
            msg = m.group(1)
            if 'invoked oom-killer' in msg:
                table = []
            r = ROW.match(msg.strip())
            if r:   # rss is in pages of 4 kB
                table.append((r.group(11), int(r.group(4)) * 4 / 1024))
            k = KILL.search(msg)
            if k:
                top = sorted(table, key=lambda t: -t[1])[:3]
                res.append((k.group(2), int(k.group(3)) / 1024, top))
    return res


victims, agent_cases = Counter(), []
for run in sorted((REV / 'r_cutout').glob('*memory_max768M*')):
    agent_dead = (run / 'a1' / 'exit_code').read_text().strip() == '137'
    ks = kills(run)
    for name, mb, top in ks:
        victims[name] += 1
    if agent_dead:
        agent_cases.append((run.name, ks))
p('OOM victims in all t12 runs at 768M with no fix:', dict(victims))
p(f'\nruns where the agent was killed: {len(agent_cases)}')
for name, ks in agent_cases:
    p(f'  {name}')
    for v, mb, top in ks:
        p(f'     killed {v} ({mb:.0f} MB anon); largest tasks then: ' + ', '.join(f'{n} {m:.0f} MB' for n, m in top))
(HERE / 'oom_victims.txt').write_text('\n'.join(out) + '\n')
