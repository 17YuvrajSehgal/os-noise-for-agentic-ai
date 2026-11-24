#!/usr/bin/env python3
"""P2 debug: where is the CPU time that cpu.stat sees and the trace misses?

Rebuilds on-CPU time per tid for EVERY thread (not only the agent subtree),
then prints: subtree total, top non-subtree pids, time on tids never mapped
to a pid, and RUN time lost because a thread was already RUN when it was
switched in again (a missed switch-out).

  python p2_gap_debug.py <run_dir>
"""
import gzip, json, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / 'latency/1_svc_cpu_cap/agentic-os-noise/analysis'))
from analyze_run import TS, CTX, SW, FORK, EVT, ts_ns, read_stat

run = Path(sys.argv[1])
root = int((run / 'meta/root.pid').read_text().split()[0])
subtree = {root}
tid2pid, names = {}, {}
on = {}                        # tid -> switch-in ts
run_ns = defaultdict(int)      # tid -> on-CPU ns
cpu_cur = {}                   # cpu -> tid currently on it
double_in = 0                  # switch-in of a tid that was already on a CPU
first_seen_running = defaultdict(int)   # tid switched OUT without a switch-in seen
fork_parent = {}
t_first = t_last = None
CPU = __import__('re').compile(r'cpu_id = (\d+)')

for line in gzip.open(run / 'trace.txt.gz', 'rt', errors='replace'):
    m = TS.match(line)
    if not m:
        continue
    t = ts_ns(*m.groups())
    t_first = t_first or t
    t_last = t
    c = CTX.search(line)
    if c:
        tid2pid[int(c.group(2))] = int(c.group(1))
        names[int(c.group(1))] = c.group(3)
    ev = EVT.search(line)
    name = ev.group(1) if ev else ''
    if name == 'sched_process_fork':
        f = FORK.search(line)
        if f:
            fork_parent[int(f.group(2))] = int(f.group(1))
            if int(f.group(1)) in subtree:
                subtree.add(int(f.group(2)))
    elif name == 'sched_switch':
        s = SW.search(line)
        if not s:
            print('UNPARSED sched_switch:', line[:200])
            continue
        prev, nxt = int(s.group(1)), int(s.group(3))
        if prev in on:
            run_ns[prev] += t - on.pop(prev)
        elif prev != 0:
            # was running before we ever saw it switched in: time since trace start is lost
            first_seen_running[prev] = t - t_first
        if nxt in on:
            double_in += 1
        on[nxt] = t

for tid, since in on.items():
    run_ns[tid] += t_last - since

b, a = read_stat(run / 'meta/cpu.stat.before'), read_stat(run / 'meta/cpu.stat.after')
usage = (a['usage_usec'] - b['usage_usec']) / 1e6
per_pid = defaultdict(int)
unmapped = 0
for tid, ns in run_ns.items():
    if tid == 0:
        continue
    pid = tid2pid.get(tid)
    if pid is None:
        unmapped += ns
    else:
        per_pid[pid] += ns
sub = sum(v for p, v in per_pid.items() if p in subtree) / 1e9
print(f'run {run.name}: cpu.stat usage {usage:.2f}s, trace subtree on-CPU {sub:.2f}s, missing {usage - sub:.2f}s')
print(f'unmapped tids on-CPU: {unmapped / 1e9:.3f}s; double switch-ins: {double_in}')
lost = sum(v for tid, v in first_seen_running.items() if tid2pid.get(tid) in subtree) / 1e9
print(f'subtree threads first seen already running (upper bound on lost time): {lost:.3f}s')
print('top non-subtree pids by on-CPU:')
for p, v in sorted(((p, v) for p, v in per_pid.items() if p not in subtree), key=lambda x: -x[1])[:12]:
    print(f'  pid {p:<7} {names.get(p, "?"):<18} {v / 1e9:7.3f}s  parent={fork_parent.get(p)}'
          f' ({names.get(fork_parent.get(p), "?")})')
