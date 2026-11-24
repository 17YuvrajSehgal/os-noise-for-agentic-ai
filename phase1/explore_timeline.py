#!/usr/bin/env python3
"""Exploration: one merged timeline of a run.

Rows: outgoing writes on port-443 sockets (>= MIN bytes), bursts of incoming
reads per socket (reads closer than GAP seconds are one burst), and every
exec in the agent subtree.

  python explore_timeline.py <run_dir> [MIN=300] [GAP=0.3]
"""
import gzip, re, sys
from pathlib import Path

TS = re.compile(r'^\[(\d\d):(\d\d):(\d\d)\.(\d{9})\]')
CTX = re.compile(r'pid = (\d+), tid = (\d+), procname = "([^"]*)"')
EVT = re.compile(r' ([a-z0-9_]+): \{ cpu_id')
FD = re.compile(r'\{ fd = (\d+)')
RET = re.compile(r'\{ ret = (-?\d+)')
DPORT = re.compile(r'dport = (\d+)')
FORK = re.compile(r'parent_pid = (\d+),.*child_pid = (\d+)')
FN = re.compile(r'filename = "([^"]*)"')
IN = {'read', 'recvfrom', 'recvmsg', 'readv'}
OUT = {'write', 'sendto', 'sendmsg', 'writev'}

run = Path(sys.argv[1])
MIN = int(sys.argv[2]) if len(sys.argv) > 2 else 300
GAP = float(sys.argv[3]) if len(sys.argv) > 3 else 0.3
root = int((run / 'meta/root.pid').read_text().split()[0])
subtree = {root}


def tsec(m):
    h, mi, s, f = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(f) / 1e9


conn, nconn, pend, rows, burst = {}, 0, {}, [], {}
t0 = None


def flush(k):
    b = burst.pop(k, None)
    if b:
        rows.append((b[0], f'  IN  conn {k:>2} {b[2]:>8} B in {b[3]:>3} reads over {b[1] - b[0]:.2f}s'))


for line in gzip.open(run / 'trace.txt.gz', 'rt', errors='replace'):
    m = TS.match(line)
    if not m:
        continue
    ev, c = EVT.search(line), CTX.search(line)
    if not ev or not c:
        continue
    t = tsec(m)
    t0 = t0 if t0 is not None else t
    t -= t0
    name = ev.group(1)
    pid, tid, comm = int(c.group(1)), int(c.group(2)), c.group(3)
    if name == 'sched_process_fork':
        f = FORK.search(line)
        if f and int(f.group(1)) in subtree:
            subtree.add(int(f.group(2)))
    elif name == 'sched_process_exec' and pid in subtree:
        fn = FN.search(line)
        rows.append((t, f'EXEC pid {pid} {fn.group(1) if fn else comm}'))
    elif name == 'syscall_entry_connect':
        dp, fd = DPORT.search(line), FD.search(line)
        if dp and fd and dp.group(1) == '443' and pid in subtree:
            conn[(pid, int(fd.group(1)))] = nconn
            nconn += 1
    elif name == 'syscall_entry_close':
        fd = FD.search(line)
        if fd:
            k = conn.pop((pid, int(fd.group(1))), None)
            if k is not None:
                flush(k)
    elif name.startswith('syscall_entry_'):
        s = name[14:]
        if s in IN or s in OUT:
            fd = FD.search(line)
            if fd:
                pend[tid] = (s, int(fd.group(1)))
    elif name.startswith('syscall_exit_'):
        p = pend.pop(tid, None)
        if not p or p[0] != name[13:]:
            continue
        k = conn.get((pid, p[1]))
        r = RET.search(line)
        if k is None or not r or int(r.group(1)) <= 0:
            continue
        n = int(r.group(1))
        if p[0] in OUT:
            flush(k)
            if n >= MIN:
                rows.append((t, f'OUT   conn {k:>2} {n:>8} B'))
        else:
            b = burst.get(k)
            if b and t - b[1] > GAP:
                flush(k)
                b = None
            if b:
                b[1] = t; b[2] += n; b[3] += 1
            else:
                burst[k] = [t, t, n, 1]
for k in list(burst):
    flush(k)
for t, s in sorted(rows):
    print(f'{t:8.2f}  {s}')
