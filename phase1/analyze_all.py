#!/usr/bin/env python3
"""Run analyze_run.analyze() on every run under OSNOISE_RUNS, in parallel.
One JSON object per line, with the run family added.

  OSNOISE_RUNS=<runs root> python analyze_all.py > results/analyze_all.jsonl
"""
import json, os, sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / 'latency/1_svc_cpu_cap/agentic-os-noise/analysis'))
from analyze_run import analyze

ROOT = Path(os.environ['OSNOISE_RUNS'])


def one(run):
    a = dict(analyze(run))
    a['family'] = run.parent.relative_to(ROOT).as_posix()
    a['ground_truth'] = json.loads((run / 'meta/ground_truth.json').read_text())
    return a


if __name__ == '__main__':
    runs = sorted(p.parent for p in ROOT.glob('**/trace.txt.gz'))
    with Pool(12) as pool:
        for a in pool.imap(one, runs):
            print(json.dumps(a), flush=True)
