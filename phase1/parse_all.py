#!/usr/bin/env python3
"""Run exchanges.parse_run() on every run, in parallel. One JSON per line.

  OSNOISE_RUNS=<runs root> python parse_all.py > results/parsed_all.jsonl
"""
import json, os, sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exchanges import parse_run

ROOT = Path(os.environ['OSNOISE_RUNS'])


def one(run):
    r = parse_run(run)
    r['family'] = run.parent.relative_to(ROOT).as_posix()
    r['run'] = run.name
    r['ground_truth'] = json.loads((run / 'meta/ground_truth.json').read_text())
    r['anchors'] = [json.loads(l) for l in (run / 'meta/clock_anchors.jsonl').read_text().splitlines()]
    return r


if __name__ == '__main__':
    runs = sorted(p.parent for p in ROOT.glob('**/trace.txt.gz'))
    with Pool(12) as pool:
        for r in pool.imap(one, runs):
            print(json.dumps(r), flush=True)
