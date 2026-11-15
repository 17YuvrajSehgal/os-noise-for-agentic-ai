#!/usr/bin/env python3
"""Exploration: per-socket traffic of the agent subtree on port 443.

Prints one summary row per connection, then a timeline of every outgoing
write of at least MIN_OUT bytes (candidate "request" starts).

  python explore_sockets.py <run_dir> [MIN_OUT=1000]
"""
import gzip, re, sys
from collections import defaultdict
from pathlib import Path

TS = re.compile(r'^\[(\d\d):(\d\d):(\d\d)\.(\d{9})\]')
CTX = re.compile(r'pid = (\d+), tid = (\d+), procname = "([^"]*)"')
EVT = re.compile(r' ([a-z0-9_]+): \{ cpu_id')
FD = re.compile(r'\{ fd = (\d+)')
RET = re.compile(r'\{ ret = (-?\d+)')
DPORT = re.compile(r'dport = (\d+)')
V4 = re.compile(r'v4addr = \[ \[0\] = (\d+), \[1\] = (\d+), \[2\] = (\d+), \[3\] = (\d+)')
IN = {'read', 'recvfrom', 'recvmsg', 'readv'}
OUT = {'write', 'sendto', 'sendmsg', 'writev'}

run = Path(sys.argv[1])
MIN_OUT = int(sys.argv[2]) if len(sys.argv) > 2 else 1000


def tsec(m):
    h, mi, s, f = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(f) / 1e9


conn = {}          # (pid, fd) -> conn id currently open
info = []          # conn id -> dict
pend = {}          # tid -> (syscall, fd)
t0 = None
big = []
for line in gzip.open(run / 'trace.txt.gz', 'rt', errors='replace'):
    m = TS.match(line)
    if not m:
        continue
    ev = EVT.search(line)
    c = CTX.search(line)
    if not ev or not c:
        continue
    t = tsec(m)
    t0 = t0 if t0 is not None else t
    name = ev.group(1)
    pid, tid, comm = int(c.group(1)), int(c.group(2)), c.group(3)
    if name == 'syscall_entry_connect':
        dp, fd, a = DPORT.search(line), FD.search(line), V4.search(line)
        if dp and fd and dp.group(1) == '443':
            conn[(pid, int(fd.group(1)))] = len(info)
            info.append(dict(pid=pid, comm=comm, fd=int(fd.group(1)),
                             ip='.'.join(a.groups()) if a else 'v6', t_open=t - t0, t_close=None,
                             n_out=0, b_out=0, n_in=0, b_in=0, t_first_out=None, t_last_in=None))
    elif name == 'syscall_entry_close':
        fd = FD.search(line)
        if fd:
            k = conn.pop((pid, int(fd.group(1))), None)
            if k is not None:
                info[k]['t_close'] = t - t0
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
        i = info[k]
        if p[0] in OUT:
            i['n_out'] += 1; i['b_out'] += n
            i['t_first_out'] = i['t_first_out'] if i['t_first_out'] is not None else t - t0
            if n >= MIN_OUT:
                big.append((t - t0, k, n, comm))
        else:
            i['n_in'] += 1; i['b_in'] += n; i['t_last_in'] = t - t0

print(f"{'id':>3} {'pid':>6} {'comm':<16}{'ip':<16}{'open':>7}{'close':>8}{'#out':>6}{'KB out':>8}{'#in':>6}{'KB in':>8}")
for k, i in enumerate(info):
    cl = f"{i['t_close']:.2f}" if i['t_close'] is not None else '-'
    print(f"{k:>3} {i['pid']:>6} {i['comm']:<16}{i['ip']:<16}{i['t_open']:>7.2f}{cl:>8}"
          f"{i['n_out']:>6}{i['b_out'] / 1024:>8.1f}{i['n_in']:>6}{i['b_in'] / 1024:>8.1f}")
print(f'\noutgoing writes >= {MIN_OUT} bytes:')
for t, k, n, comm in big:
    print(f'  t={t:7.2f}s conn {k:>2} {n:>7} B  {comm}')
