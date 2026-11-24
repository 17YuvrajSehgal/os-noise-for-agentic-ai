#!/usr/bin/env python3
"""Run the Phase 1 trace passes on campaigns of the new collector.

  OSNOISE_RUNS=<runs root> python run_passes.py <campaign> [<campaign> ...]

Per campaign writes phase2/<campaign>/{analyze_all,parsed_all,diag_all}.jsonl
and step1_runs.csv / step1_turns.csv. A pass whose output exists is skipped,
so the script can be started again after a stop.
"""
import csv, json, os, sys
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'phase1'))
ROOT = Path(os.environ['OSNOISE_RUNS'])
PASSES = {'analyze_all': 'analyze_all', 'parsed_all': 'parse_all', 'diag_all': 'diag_pass'}


def work(job):
    name, run = job
    one = __import__(PASSES[name]).one
    try:
        return name, run.parent.name, json.dumps(one(run)), None
    except Exception as e:                      # one broken run must not stop the campaign
        return name, run.parent.name, None, f'{run.name}: {type(e).__name__}: {e}'


if __name__ == '__main__':
    jobs, outs = [], {}
    for c in sys.argv[1:]:
        (HERE / c).mkdir(exist_ok=True)
        runs = sorted(p.parent for p in (ROOT / c).glob('*/trace.txt.gz'))
        for name in PASSES:
            if not (HERE / c / f'{name}.jsonl').exists():
                jobs += [(name, r) for r in runs]
    # largest traces first, so the pool is not left with one giant at the end
    jobs.sort(key=lambda j: -(j[1] / 'trace.txt.gz').stat().st_size)
    with Pool(int(os.environ.get('OSN_PROCS', 12))) as pool:
        for name, c, line, err in pool.imap_unordered(work, jobs):
            if err:
                print('ERROR', name, c, err, flush=True)
                continue
            f = outs.get((c, name)) or outs.setdefault((c, name), open(HERE / c / f'{name}.jsonl.part', 'w'))
            f.write(line + '\n')
    for (c, name), f in outs.items():
        f.close()
        os.replace(HERE / c / f'{name}.jsonl.part', HERE / c / f'{name}.jsonl')

    import step1
    for c in sys.argv[1:]:
        rows, turns = [], []
        for line in open(HERE / c / 'parsed_all.jsonl'):
            row, t = step1.analyze(json.loads(line))
            rows.append(row); turns += t
        with open(HERE / c / 'step1_runs.csv', 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(max(rows, key=len)), restval='')
            w.writeheader(); w.writerows(rows)
        if turns:
            with open(HERE / c / 'step1_turns.csv', 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(turns[0]))
                w.writeheader(); w.writerows(turns)
        print(c, len(rows), 'runs,', len(turns), 'turns,', sum(1 for r in rows if not r['n_turns']), 'with no model turn', flush=True)
