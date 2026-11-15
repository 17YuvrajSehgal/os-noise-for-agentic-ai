#!/usr/bin/env python3
"""P1b: lost-event check from the decoded text alone.

On one CPU, the thread a sched_switch switches IN must be the thread the
next sched_switch on that CPU switches OUT. A break in that chain means
switch events are missing there. Used for runs whose raw trace (and so the
index with its lost-event counters) is not available.

  OSNOISE_RUNS=<runs root> python p1b_switch_chain.py > results/p1b_switch_chain.csv
"""
import csv, gzip, os, re, sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(os.environ['OSNOISE_RUNS'])
SW = re.compile(r'sched_switch: \{ cpu_id = (\d+) \}.*prev_tid = (\d+),.*next_tid = (\d+)')


def check(run):
    cur = {}                  # cpu -> tid switched in last
    n = breaks = 0
    with gzip.open(run / 'trace.txt.gz', 'rt', errors='replace') as f:
        for line in f:
            if 'sched_switch:' not in line:
                continue
            m = SW.search(line)
            cpu, prev, nxt = m.group(1), m.group(2), m.group(3)
            n += 1
            if cpu in cur and cur[cpu] != prev:
                breaks += 1
            cur[cpu] = nxt
    return {'family': run.parent.relative_to(ROOT).as_posix(), 'run': run.name,
            'switches': n, 'chain_breaks': breaks}


if __name__ == '__main__':
    runs = sorted(p.parent for p in ROOT.glob('**/trace.txt.gz'))
    with Pool(12) as pool:
        rows = pool.map(check, runs)
    w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]), lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
