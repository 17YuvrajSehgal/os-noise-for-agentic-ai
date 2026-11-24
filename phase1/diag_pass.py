#!/usr/bin/env python3
"""Step 4 trace pass: the signals the diagnosis procedure needs.

Everything here comes from the trace alone and is restricted to the agent's
process tree. Nothing reads the limit that was set.

Per run:
  wait_idle_s    time tree threads were ready to run while at least one CPU
                 was idle (CPU was available but not given: a quota)
  wait_busy_s    time tree threads were ready while every CPU was busy
                 (competition for cores)
  long_idle_waits / long_busy_waits   single waits of 50 ms or more, by the
                 class that covers most of the wait
  on_cpu_s       tree on-CPU time
  d_io_s         disk-type sleep while a block request was in flight
  d_noio_s       disk-type sleep with NO block request in flight (the I/O is
                 being held back before it reaches the device: a throttle)
  reclaim_n      memory-cgroup reclaim episodes started by tree processes
  reclaim_s      time inside those episodes
  killed         processes that exited within KILL_MS of their own reclaim

  OSNOISE_RUNS=<runs root> python diag_pass.py > results/diag_all.jsonl
"""
import gzip, json, os, re, sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exchanges import TS, CTX, EVT, FORK, SW, WAKE, tsec

ROOT = Path(os.environ.get('OSNOISE_RUNS', '.'))
CPU = re.compile(r'\{ cpu_id = (\d+) \}')
RQ = re.compile(r'\{ dev = (\d+), sector = (\d+), nr_sector = (\d+)')
LONG = 0.05         # a "long" wait, seconds
KILL_MS = 1.0       # exit this close to the process's own reclaim = killed


def one(run, pidfile='meta/root.pid'):
    # pidfile: 'a<i>/root.pid' limits the pass to one agent of a multi-agent run
    root = int((run / pidfile).read_text().split()[0])
    subtree = {root}
    tid2pid, comm = {}, {}
    state = {}            # tid -> (kind, since, idle_integral_at_start, noio_integral_at_start)
    idle_cpus = set()
    inflight = set()
    I = J = 0.0           # integrals: time with >=1 idle CPU ; time with no block request in flight
    last = None
    out = dict(wait_idle_s=0.0, wait_busy_s=0.0, long_idle_waits=0, long_busy_waits=0,
               on_cpu_s=0.0, d_io_s=0.0, d_noio_s=0.0, reclaim_n=0, reclaim_s=0.0)
    rec_open, rec_last, killed = {}, {}, []

    def close(tid, t):
        st = state.pop(tid, None)
        if not st or tid2pid.get(tid) not in subtree:
            return
        kind, since, i0, j0 = st
        d = t - since
        if kind == 'RUN':
            out['on_cpu_s'] += d
        elif kind == 'RDY':
            idle = I - i0
            out['wait_idle_s'] += idle
            out['wait_busy_s'] += d - idle
            if d >= LONG:
                out['long_idle_waits' if idle >= d / 2 else 'long_busy_waits'] += 1
        elif kind == 'D':
            noio = J - j0
            out['d_noio_s'] += noio
            out['d_io_s'] += d - noio

    with gzip.open(run / 'trace.txt.gz', 'rt', errors='replace') as f:
        for line in f:
            m = TS.match(line)
            if not m:
                continue
            ev, c, cp = EVT.search(line), CTX.search(line), CPU.search(line)
            if not ev or not c or not cp:
                continue
            t = tsec(m)
            if last is not None:
                if idle_cpus:
                    I += t - last
                if not inflight:
                    J += t - last
            last = t
            name, cpu = ev.group(1), cp.group(1)
            pid, tid = int(c.group(1)), int(c.group(2))
            tid2pid[tid] = pid
            comm[pid] = c.group(3)
            if name == 'sched_switch':
                s = SW.search(line)
                if not s:
                    continue
                prev, pst, nxt = int(s.group(1)), int(s.group(2)), int(s.group(3))
                close(prev, t)
                if pst == 0 or pst & 0x100:
                    state[prev] = ('RDY', t, I, J)
                elif pst & 2:
                    state[prev] = ('D', t, I, J)
                close(nxt, t)
                state[nxt] = ('RUN', t, I, J)
                if nxt == 0:
                    idle_cpus.add(cpu)
                else:
                    idle_cpus.discard(cpu)
            elif name == 'sched_wakeup':
                w = WAKE.search(line)
                if w:
                    wt = int(w.group(1))
                    st = state.get(wt)
                    if not st or st[0] == 'D':
                        close(wt, t)
                        state[wt] = ('RDY', t, I, J)
            elif name == 'sched_process_fork':
                fk = FORK.search(line)
                if fk and int(fk.group(1)) in subtree:
                    subtree.add(int(fk.group(2)))
            elif name == 'block_rq_issue':
                r = RQ.search(line)
                if r and r.group(3) != '0':        # a flush has no sectors and never pairs up
                    inflight.add(r.groups())
            elif name == 'block_rq_complete':
                r = RQ.search(line)
                if r:
                    inflight.discard(r.groups())
            elif name == 'mm_vmscan_memcg_reclaim_begin':
                if pid in subtree:
                    out['reclaim_n'] += 1
                    rec_open[tid] = t
            elif name == 'mm_vmscan_memcg_reclaim_end':
                t0 = rec_open.pop(tid, None)
                if t0 is not None:
                    out['reclaim_s'] += t - t0
                    rec_last[pid] = t
            elif name == 'sched_process_exit':
                if pid == tid and pid in rec_last and (t - rec_last[pid]) * 1000 <= KILL_MS:
                    killed.append(comm.get(pid, '?'))
    for tid in list(state):
        close(tid, last)
    res = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}
    res.update(family=run.parent.relative_to(ROOT).as_posix(), run=run.name, killed=killed, pidfile=pidfile)
    return res


if __name__ == '__main__':
    runs = sorted(p.parent for p in ROOT.glob('**/trace.txt.gz'))
    with Pool(12) as pool:
        for r in pool.imap(one, runs):
            print(json.dumps(r), flush=True)
