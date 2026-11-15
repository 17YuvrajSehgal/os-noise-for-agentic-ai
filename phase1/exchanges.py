#!/usr/bin/env python3
"""Request/response exchanges on the agent's HTTPS sockets, from the trace.

An exchange on one socket = the bytes the agent writes (the request) and the
bytes it then reads (the response), until it writes the next request or
closes the socket. Small writes while a response is arriving (HTTP/2 control
frames, under CTRL bytes) do not start a new exchange.

Also returns, on the same clock: the agent subtree's exec events and process
lifetimes, and per-process CPU use in BIN-second bins (on-CPU and
ready-but-waiting), from the same per-thread state machine as analyze_run.py.

  from exchanges import parse_run
  python exchanges.py <run_dir>          # prints the exchanges
"""
import gzip, re, sys
from pathlib import Path

TS = re.compile(r'^\[(\d\d):(\d\d):(\d\d)\.(\d{9})\]')
CTX = re.compile(r'pid = (\d+), tid = (\d+), procname = "([^"]*)"')
EVT = re.compile(r' ([a-z0-9_]+): \{ cpu_id')
FD = re.compile(r'\{ fd = (\d+)')
RET = re.compile(r'\{ ret = (-?\d+)')
DPORT = re.compile(r'dport = (\d+)')
V4 = re.compile(r'v4addr = \[ \[0\] = (\d+), \[1\] = (\d+), \[2\] = (\d+), \[3\] = (\d+)')
FORK = re.compile(r'parent_pid = (\d+),.*child_pid = (\d+)')
FN = re.compile(r'filename = "([^"]*)"')
IN = {'read', 'recvfrom', 'recvmsg', 'readv', 'recvmmsg'}
OUT = {'write', 'sendto', 'sendmsg', 'writev', 'sendmmsg'}
PORTS = {'443', '53'}   # HTTPS and DNS: the sockets whose traffic we follow
SW = re.compile(r'prev_tid = (\d+), prev_prio = -?\d+, prev_state = (\d+), '
                r'next_comm = "[^"]*", next_tid = (\d+)')
WAKE = re.compile(r'\{ comm = "[^"]*", tid = (\d+),')
CTRL = 200      # bytes; a smaller write during a response is not a new request
BIN = 0.01      # seconds; width of the CPU-use bins


def tsec(m):
    h, mi, s, f = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(f) / 1e9


def parse_run(run_dir):
    """-> dict(t0, t_end, root, exchanges, execs, procs, connects, cpu)
    Times are seconds since the first trace event (t0 is its time of day).
    cpu = {pid: [[bin_index, on_cpu_s, ready_s], ...]} for subtree pids."""
    run = Path(run_dir)
    root = int((run / 'meta/root.pid').read_text().split()[0])
    subtree = {root}
    conn = {}       # (pid, fd) -> open connection record
    cur = {}        # (pid, fd) -> exchange being built
    pend = {}       # tid -> (syscall, fd)
    exchanges, execs, connects = [], [], []
    procs = {}      # pid -> [t_fork, t_exit, comm]
    t0 = t = None
    tid2pid, state = {}, {}    # tid -> pid ; tid -> (kind, since)
    cpu = {}                   # pid -> {bin: [run_s, rdy_s]}

    def close_state(tid, now):
        st = state.get(tid)
        if not st or st[0] == 'BLK':
            return
        pid = tid2pid.get(tid)
        if pid not in subtree:
            return
        col = 0 if st[0] == 'RUN' else 1
        bins = cpu.setdefault(pid, {})
        a = st[1]
        while a < now:                      # spread the interval over its bins
            i = int(a / BIN)
            if (i + 1) * BIN <= a:          # float rounding put a on a bin edge
                i += 1
            b = min(now, (i + 1) * BIN)
            bins.setdefault(i, [0.0, 0.0])[col] += b - a
            a = b

    def close_x(key):
        x = cur.pop(key, None)
        if x and x['in_bytes']:
            exchanges.append(x)

    with gzip.open(run / 'trace.txt.gz', 'rt', errors='replace') as f:
        for line in f:
            m = TS.match(line)
            if not m:
                continue
            ev, c = EVT.search(line), CTX.search(line)
            if not ev or not c:
                continue
            t = tsec(m)
            if t0 is None:
                t0 = t
            t -= t0
            name = ev.group(1)
            pid, tid, comm = int(c.group(1)), int(c.group(2)), c.group(3)
            tid2pid[tid] = pid
            if name == 'sched_switch':
                s = SW.search(line)
                if s:
                    prev, pst, nxt = int(s.group(1)), int(s.group(2)), int(s.group(3))
                    close_state(prev, t)
                    state[prev] = ('RDY' if pst == 0 or pst & 0x100 else 'BLK', t)
                    close_state(nxt, t)
                    state[nxt] = ('RUN', t)
            elif name == 'sched_wakeup':
                w = WAKE.search(line)
                if w:
                    wt = int(w.group(1))
                    st = state.get(wt)
                    if not st or st[0] == 'BLK':
                        state[wt] = ('RDY', t)
            elif name == 'sched_process_fork':
                fk = FORK.search(line)
                if fk and int(fk.group(1)) in subtree:
                    child = int(fk.group(2))
                    subtree.add(child)
                    procs.setdefault(child, [t, None, comm])
            elif name == 'sched_process_exec':
                if pid in subtree:
                    fn = FN.search(line)
                    execs.append((t, pid, fn.group(1) if fn else comm))
                    if pid in procs:
                        procs[pid][2] = (fn.group(1) if fn else comm).rsplit('/', 1)[-1]
            elif name == 'sched_process_exit':
                if pid in procs and pid == tid:
                    procs[pid][1] = t
            elif name == 'syscall_entry_connect':
                if pid not in subtree:
                    continue
                dp, fd, a = DPORT.search(line), FD.search(line), V4.search(line)
                if not dp or not fd or dp.group(1) == '0':    # 0 = unix socket / address probe
                    continue
                rec = dict(id=len(connects), ip='.'.join(a.groups()) if a else 'v6',
                           dport=int(dp.group(1)), comm=comm, pid=pid, t_open=t, t_close=None,
                           out_bytes=0, in_bytes=0)
                connects.append(rec)
                if dp.group(1) in PORTS:
                    key = (pid, int(fd.group(1)))
                    close_x(key)
                    conn[key] = rec
            elif name == 'syscall_entry_close':
                fd = FD.search(line)
                if fd:
                    key = (pid, int(fd.group(1)))
                    rec = conn.pop(key, None)
                    if rec is not None:
                        rec['t_close'] = t
                        close_x(key)
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
                key = (pid, p[1])
                cn = conn.get(key)
                r = RET.search(line)
                if cn is None or not r or int(r.group(1)) <= 0:
                    continue
                n = int(r.group(1))
                x = cur.get(key)
                cn['out_bytes' if p[0] in OUT else 'in_bytes'] += n
                if p[0] in OUT:
                    if x and x['in_bytes'] and n < CTRL:
                        continue                      # control frame during a response
                    if x is None or x['in_bytes']:
                        close_x(key)
                        x = cur[key] = dict(conn=cn['id'], ip=cn['ip'], dport=cn['dport'],
                                            comm=cn['comm'], pid=pid, t_conn=cn['t_open'],
                                            t_req=t, t_req_end=t, out_bytes=0, t_first_in=None,
                                            t_last_in=None, in_bytes=0, n_reads=0, max_gap=0.0)
                    x['out_bytes'] += n
                    x['t_req_end'] = t
                elif x:
                    if x['t_first_in'] is None:
                        x['t_first_in'] = t
                    else:
                        x['max_gap'] = max(x['max_gap'], t - x['t_last_in'])   # longest pause in the stream
                    x['t_last_in'] = t
                    x['in_bytes'] += n
                    x['n_reads'] += 1
    for key in list(cur):
        close_x(key)
    for tid in list(state):
        close_state(tid, t)
    exchanges.sort(key=lambda x: x['t_req'])
    return dict(t0=t0, t_end=t, root=root, exchanges=exchanges, execs=execs,
                procs=procs, connects=connects,
                cpu={p: [[i, round(v[0], 6), round(v[1], 6)] for i, v in sorted(b.items())]
                     for p, b in cpu.items()})


if __name__ == '__main__':
    r = parse_run(sys.argv[1])
    print(f"{'t_req':>7}{'conn':>5} {'ip':<16}{'out B':>8}{'ttfb':>7}{'dur':>7}{'in B':>8}{'reads':>6}")
    for x in r['exchanges']:
        print(f"{x['t_req']:>7.2f}{x['conn']:>5} {x['ip']:<16}{x['out_bytes']:>8}"
              f"{x['t_first_in'] - x['t_req_end']:>7.2f}{x['t_last_in'] - x['t_req']:>7.2f}"
              f"{x['in_bytes']:>8}{x['n_reads']:>6}")
