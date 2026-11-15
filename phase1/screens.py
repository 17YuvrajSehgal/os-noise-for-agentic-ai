#!/usr/bin/env python3
"""P16 / P17: run the lock-wait screen and the slow-system-call screen on
every run and keep their verdict lines.

The two screens are existing scripts (futex_wait.py, syscall_stall.py) that
read a plain-text trace, so each trace is unzipped to a temp file first.

  OSNOISE_RUNS=<runs root> SCREEN_TOOLS=<folder with the two scripts> \
      python screens.py results/screens.csv

Slow (the screens take minutes on the largest traces). Rows are appended as
runs finish, and runs already in the file are skipped, so an interrupted
run can simply be started again.
"""
import csv, gzip, json, os, shutil, subprocess, sys, tempfile
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(os.environ['OSNOISE_RUNS'])
TOOLS = Path(os.environ['SCREEN_TOOLS'])


def verdict(out, prefixes):
    for line in out.splitlines():
        if line.startswith(prefixes):
            return line[:400]
    return 'NO VERDICT LINE'


def one(run):
    a = [json.loads(l) for l in (run / 'meta/clock_anchors.jsonl').read_text().splitlines()]
    secs = int(a[-1]['realtime'] - a[0]['realtime']) + 8
    gt = json.loads((run / 'meta/ground_truth.json').read_text())
    with tempfile.TemporaryDirectory() as d:
        txt = Path(d) / 'trace.txt'
        with gzip.open(run / 'trace.txt.gz', 'rb') as src, open(txt, 'wb') as dst:
            shutil.copyfileobj(src, dst)
        py = lambda *args: subprocess.run([sys.executable, *map(str, args)], capture_output=True,
                                          text=True, errors='replace').stdout
        lock = py(TOOLS / 'futex_wait.py', txt, secs, '--top', 3)
        stall = py(TOOLS / 'syscall_stall.py', txt, '--min-ms', 10, '--top', 5)
    return dict(family=run.parent.relative_to(ROOT).as_posix(), run=run.name,
                agent=gt.get('agent', 'claude'), cpu_max=gt['cpu_max'],
                mem_limit=gt.get('mem_limit', ''), io_limit=gt.get('io_limit', ''),
                lock=verdict(lock, ('VERDICT:', 'NO LONG FUTEX', 'NO LOCK', 'FUTEX WAITS')),
                stall=verdict(stall, ('STALL:', 'NO WORK-CLASS')))


FIELDS = ['family', 'run', 'agent', 'cpu_max', 'mem_limit', 'io_limit', 'lock', 'stall']

if __name__ == '__main__':
    out = Path(sys.argv[1])
    done = set()
    if out.exists():
        done = {(r['family'], r['run']) for r in csv.DictReader(open(out, newline=''))}
    runs = sorted(p.parent for p in ROOT.glob('**/trace.txt.gz'))
    runs = [r for r in runs if (r.parent.relative_to(ROOT).as_posix(), r.name) not in done]
    with open(out, 'a', newline='') as f, Pool(10) as pool:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator='\n')
        if not done:
            w.writeheader()
        for row in pool.imap_unordered(one, runs):
            w.writerow(row)
            f.flush()
