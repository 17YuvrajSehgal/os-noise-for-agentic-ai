#!/usr/bin/env python3
"""Step 3 trace pass: local work of the agent subtree.

Per run, one JSON line with:
  syscalls   {pid: {name: [count, seconds inside the call]}}   (subtree pids)
  errors     {pid: {"name:ret": count}}                        (calls that returned < 0)
  spawns     {pid: {kind: [count, total_s, max_s]}}            kind = vfork | clone3 | clone:<flags>
  dsleep     {pid: seconds in uninterruptible (disk-type) sleep}
  idle       {cpu: seconds the CPU ran the idle task}
  irq        {hard_s, soft_s, hard_on_agent_s, soft_on_agent_s, soft_by_vec}
  block      {read_bytes, write_bytes, read_n, write_n, sub_read_bytes, sub_write_bytes}
  span_s     seconds between first and last event

  OSNOISE_RUNS=<runs root> python local_pass.py > results/local_all.jsonl
"""
import gzip, json, os, re, sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exchanges import TS, CTX, EVT, RET, FORK, SW, WAKE, tsec

ROOT = Path(os.environ.get('OSNOISE_RUNS', '.'))
CPU = re.compile(r'\{ cpu_id = (\d+) \}')
FLAGS = re.compile(r'\{ flags = (0x[0-9A-Fa-f]+)')
VEC = re.compile(r'name = \( "([A-Z_]+)"')
BLK = re.compile(r'bytes = (\d+), tid = \d+, rwbs = (\d+)')


def one(run):
    root = int((run / 'meta/root.pid').read_text().split()[0])
    subtree = {root}
    tid2pid = {}
    sysc = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    errs = defaultdict(lambda: defaultdict(int))
    spawns = defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0.0]))
    dsleep = defaultdict(float)
    pend = {}                 # tid -> (name, t_entry, spawn kind or None)
    dstart = {}               # tid -> t it went into D sleep
    cur = {}                  # cpu -> tid on it
    idle_since, idle = {}, defaultdict(float)
    irq_open, sirq_open = {}, {}          # cpu -> (t, on_agent[, vec])
    irq = dict(hard_s=0.0, soft_s=0.0, hard_on_agent_s=0.0, soft_on_agent_s=0.0)
    soft_by_vec = defaultdict(float)
    block = dict(read_bytes=0, write_bytes=0, read_n=0, write_n=0, sub_read_bytes=0, sub_write_bytes=0)
    t0 = t = None
    with gzip.open(run / 'trace.txt.gz', 'rt', errors='replace') as f:
        for line in f:
            m = TS.match(line)
            if not m:
                continue
            ev, c, cp = EVT.search(line), CTX.search(line), CPU.search(line)
            if not ev or not c or not cp:
                continue
            t = tsec(m)
            if t0 is None:
                t0 = t
            name, cpu = ev.group(1), cp.group(1)
            pid, tid = int(c.group(1)), int(c.group(2))
            tid2pid[tid] = pid
            if name.startswith('syscall_entry_'):
                if pid in subtree:
                    s = name[14:]
                    kind = None
                    if s == 'clone':
                        fl = FLAGS.search(line)
                        kind = 'clone:' + (fl.group(1) if fl else '?')
                    elif s in ('vfork', 'fork', 'clone3'):
                        kind = s
                    pend[tid] = (s, t, kind)
            elif name.startswith('syscall_exit_'):
                p = pend.pop(tid, None)
                if p and p[0] == name[13:]:
                    d = t - p[1]
                    v = sysc[pid][p[0]]
                    v[0] += 1; v[1] += d
                    r = RET.search(line)
                    if r and r.group(1)[0] == '-':
                        errs[pid][f'{p[0]}:{r.group(1)}'] += 1
                    elif p[2]:                         # in the parent a spawn returns the child pid
                        sp = spawns[pid][p[2]]
                        sp[0] += 1; sp[1] += d; sp[2] = max(sp[2], d)
            elif name == 'sched_switch':
                s = SW.search(line)
                if not s:
                    continue
                prev, pst, nxt = int(s.group(1)), int(s.group(2)), int(s.group(3))
                cur[cpu] = nxt
                if prev == 0 and cpu in idle_since:
                    idle[cpu] += t - idle_since.pop(cpu)
                if nxt == 0:
                    idle_since[cpu] = t
                if pst & 2:
                    dstart[prev] = t
                if nxt in dstart:                      # D sleep ends when it runs again
                    dp = tid2pid.get(nxt)
                    d = t - dstart.pop(nxt)
                    if dp in subtree:
                        dsleep[dp] += d
            elif name == 'sched_process_fork':
                fk = FORK.search(line)
                if fk and int(fk.group(1)) in subtree:
                    subtree.add(int(fk.group(2)))
            elif name == 'irq_handler_entry':
                irq_open[cpu] = (t, tid2pid.get(cur.get(cpu)) in subtree)
            elif name == 'irq_handler_exit':
                o = irq_open.pop(cpu, None)
                if o:
                    irq['hard_s'] += t - o[0]
                    if o[1]:
                        irq['hard_on_agent_s'] += t - o[0]
            elif name == 'irq_softirq_entry':
                v = VEC.search(line)
                sirq_open[cpu] = (t, tid2pid.get(cur.get(cpu)) in subtree, v.group(1) if v else '?')
            elif name == 'irq_softirq_exit':
                o = sirq_open.pop(cpu, None)
                if o:
                    irq['soft_s'] += t - o[0]
                    soft_by_vec[o[2]] += t - o[0]
                    if o[1]:
                        irq['soft_on_agent_s'] += t - o[0]
            elif name == 'block_rq_issue':
                b = BLK.search(line)
                if b:
                    n, w = int(b.group(1)), int(b.group(2)) & 1
                    block['write_bytes' if w else 'read_bytes'] += n
                    block['write_n' if w else 'read_n'] += 1
                    if pid in subtree:
                        block['sub_write_bytes' if w else 'sub_read_bytes'] += n
    for cpu, since in idle_since.items():
        idle[cpu] += t - since
    irq['soft_by_vec'] = {k: round(v, 4) for k, v in soft_by_vec.items()}
    rnd = lambda d: {str(p): {k: [v[0], round(v[1], 5)] + [round(x, 5) for x in v[2:]] for k, v in s.items()}
                     for p, s in d.items()}
    return dict(family=run.parent.relative_to(ROOT).as_posix(), run=run.name, span_s=round(t - t0, 3),
                syscalls=rnd(sysc), spawns=rnd(spawns),
                errors={str(p): dict(e) for p, e in errs.items()},
                dsleep={str(p): round(v, 4) for p, v in dsleep.items()},
                idle={c: round(v, 3) for c, v in idle.items()},
                irq={k: (round(v, 4) if isinstance(v, float) else v) for k, v in irq.items()},
                block=block)


if __name__ == '__main__':
    runs = sorted(p.parent for p in ROOT.glob('**/trace.txt.gz'))
    with Pool(12) as pool:
        for r in pool.imap(one, runs):
            print(json.dumps(r), flush=True)
