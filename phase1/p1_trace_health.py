#!/usr/bin/env python3
"""P1: trace health for every run.

Per run: lost events / time gaps / packet gaps from the raw trace index, and
whether the decoded trace covers the whole run (first event before the start
anchor, last event after the end anchor).

  OSNOISE_RUNS=<runs root> IDX_SUMMARY=<path to idx_summary.py> \
      python p1_trace_health.py > results/p1_trace_health.csv
"""
import csv, gzip, json, os, re, subprocess, sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(os.environ['OSNOISE_RUNS'])
IDX = os.environ['IDX_SUMMARY']
TS = re.compile(r'^\[(\d\d):(\d\d):(\d\d)\.(\d{9})\]')
DAY = 86400.0


def tod(line):
    m = TS.match(line)
    h, mi, s, frac = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(frac) / 1e9


def check(run):
    row = {'family': run.parent.relative_to(ROOT).as_posix(), 'run': run.name}
    out = subprocess.run([sys.executable, IDX, str(run / 'trace/kernel')],
                         capture_output=True, text=True).stdout
    for key in ('lost events', 'time gaps', 'seq gaps', 'file sizes', 'duration'):
        m = re.search(rf'^{key}\s*: (.*)$', out, re.M)
        row[key.replace(' ', '_')] = m.group(1).split('. Listed')[0] if m else 'NO RAW TRACE'
    first = last = None
    n = 0
    with gzip.open(run / 'trace.txt.gz', 'rt', errors='replace') as f:
        for line in f:
            if line[0] == '[':
                if first is None:
                    first = line
                last = line
                n += 1
    a = [json.loads(l) for l in (run / 'meta/clock_anchors.jsonl').read_text().splitlines()]
    # anchors are epoch seconds, trace text is UTC time of day; compare modulo a day
    lead = (a[0]['realtime'] - tod(first)) % DAY     # trace starts this long before the agent
    tail = (tod(last) - a[-1]['realtime']) % DAY     # trace ends this long after the agent
    row.update(events=n, wall_s=round(a[-1]['realtime'] - a[0]['realtime'], 2),
               lead_s=round(lead if lead < DAY / 2 else lead - DAY, 3),
               tail_s=round(tail if tail < DAY / 2 else tail - DAY, 3))
    return row


if __name__ == '__main__':
    runs = sorted(p.parent for p in ROOT.glob('**/trace.txt.gz'))
    with Pool(12) as pool:
        rows = pool.map(check, runs)
    w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]), lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
