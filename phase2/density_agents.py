#!/usr/bin/env python3
"""Density campaign: the diagnosis signals per agent, not for the whole group.

  OSNOISE_RUNS=<runs root> python density_agents.py > density/diag_agents.jsonl
"""
import json, os, sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'phase1'))
from diag_pass import one

ROOT = Path(os.environ['OSNOISE_RUNS']) / 'density'


def work(job):
    return json.dumps(one(*job))


if __name__ == '__main__':
    jobs = [(p.parents[1], f'{p.parent.name}/root.pid') for p in sorted(ROOT.glob('*/a*/root.pid'))]
    jobs.sort(key=lambda j: -(j[0] / 'trace.txt.gz').stat().st_size)
    with Pool(16) as pool:
        for line in pool.imap_unordered(work, jobs):
            print(line, flush=True)
