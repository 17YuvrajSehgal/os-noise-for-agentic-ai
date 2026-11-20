#!/usr/bin/env python3
"""Review 3, point 5: which threads make up the agent's peak number of tasks?

From the kernel trace of runs with no limit on M1 (2 vCPU), M0 set 2 (4) and M2 (8):
follow every task (thread or process) created under the agent's launcher with
sched_process_fork, drop it at sched_process_exit, and record the largest number
alive at once. At that moment, list the live tasks by their thread name
(procname of their last event). Also compare with the cgroup's pids.peak.

  python rev/pids_threads.py -> rev/pids_threads.txt
"""
import gzip, re, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import REV   # noqa: E402

CTX = re.compile(r'\{ pid = (\d+), tid = (\d+), procname = "([^"]*)"')
FORK = re.compile(r'sched_process_fork: .*?parent_pid = (\d+).*?child_comm = "([^"]*)", child_tid = (\d+).*?child_pid = (\d+)')
EXIT = re.compile(r'sched_process_exit: .*?\{ comm = "[^"]*", tid = (\d+)')
SETS = [('M1, 2 vCPU', 'm1_cpu'), ('M0 set 2, 4 vCPU', 'r_cpu'), ('M2, 8 vCPU', 'm2_cpu')]
out = []


def p(*a):
    out.append(' '.join(str(x) for x in a))
    print(*a, flush=True)


def one(run):
    root = int((run / 'meta' / 'root.pid').read_text())
    alive, procs, name, best, best_set = {root}, {root}, {}, 1, {root}
    with gzip.open(run / 'trace.txt.gz', 'rt', errors='ignore') as f:
        for line in f:
            c = CTX.search(line)
            if c and int(c.group(2)) in alive:
                name[int(c.group(2))] = c.group(3)
            if 'sched_process_fork' in line:
                m = FORK.search(line)
                if m and int(m.group(1)) in procs:
                    t = int(m.group(3))
                    alive.add(t)
                    name.setdefault(t, m.group(2))
                    if m.group(4) == m.group(3):       # a new process (pid = tid): its threads belong to the tree too
                        procs.add(t)
                    if len(alive) > best:
                        best, best_set = len(alive), set(alive)
            elif 'sched_process_exit' in line:
                m = EXIT.search(line)
                if m:
                    alive.discard(int(m.group(1)))
    peak_f = run / 'meta' / 'after' / 'a1' / 'pids.peak'
    peak = peak_f.read_text().strip() if peak_f.exists() else '?'
    return best, peak, Counter(name.get(t, '?') for t in best_set if t != root)


for label, camp in SETS:
    runs = [d for d in (REV / camp).glob('*_max_r*') if (d / 'trace.txt.gz').exists()][:3]
    p(f'\n== {label} ({camp}), {len(runs)} runs with no limit')
    for run in runs:
        best, peak, names = one(run)
        p(f'  {run.name}: most tasks alive at once in the trace {best}, cgroup pids.peak {peak}')
        p('     ' + ', '.join(f'{n} x{k}' for n, k in names.most_common()))
(HERE / 'pids_threads.txt').write_text('\n'.join(out) + '\n')
