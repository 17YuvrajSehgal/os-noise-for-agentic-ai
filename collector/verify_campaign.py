#!/usr/bin/env python3
"""Is every run of a campaign complete and usable?

  python3 verify_campaign.py ~/osn-runs/cpu

Checks each run folder for the things that were lost or missing in the
workshop study: the raw trace, discarded events, the decoded trace, the
agent's event stream, the counters, the time series, the checksums. Prints
one line per problem and a summary. Exit code 1 if any run has a problem.

A failed TASK is not a problem here: under a tight limit the agent is
expected to fail. A run is a problem when the MEASUREMENT is incomplete.
"""
import gzip, json, sys
from pathlib import Path


def problems(run):
    out = []
    res = run / 'result.json'
    if not res.exists():
        return ['no result.json (run did not finish)']
    spec = json.loads(res.read_text())['spec']
    meta = run / 'meta'
    if spec['trace'] != 'none':
        if not any((run / 'trace').rglob('metadata')):
            out.append('raw trace missing')
        stats = meta / 'lttng_stats.txt'
        if not stats.exists():
            out.append('no tracer statistics')
        else:
            lost = sum(int(l.rsplit(':', 1)[1]) for l in stats.read_text().splitlines()
                       if 'Discarded event' in l or 'Lost packets' in l)
            if lost:
                out.append(f'{lost} events or packets lost by the tracer')
        txt = run / 'trace.txt.gz'
        if not txt.exists() or txt.stat().st_size < 10000:
            out.append('decoded trace missing or tiny')
        else:
            try:                                   # the gzip must be complete, not cut off
                with gzip.open(txt, 'rb') as f:
                    while f.read(1 << 22):
                        pass
            except (OSError, EOFError):
                out.append('decoded trace is truncated')
        err = meta / 'babeltrace_stderr.txt'
        if err.exists() and err.stat().st_size:
            out.append('decoder printed warnings: ' + err.read_text()[:120].replace('\n', ' '))
    for i in range(1, spec['agents'] + 1):
        a = run / f'a{i}'
        ev = a / 'events.jsonl'
        code = (a / 'exit_code').read_text().strip() if (a / 'exit_code').exists() else ''
        # an agent killed by its limit before its first line is a result, not a lost measurement
        if (not ev.exists() or not ev.stat().st_size) and code in ('', '0'):
            out.append(f'a{i}: no agent events')
        if not (a / 'exit_code').exists():
            out.append(f'a{i}: no exit code')
        if not (a / 'root.pid').exists():
            out.append(f'a{i}: agent never entered its cgroup')
        for tag in ('before', 'after'):
            for f in ('cpu.stat', 'memory.events', 'io.stat', 'cpu.pressure', 'pids.peak'):
                if not (meta / tag / f'a{i}' / f).exists():
                    out.append(f'a{i}: {tag}/{f} missing')
    if spec['sample_hz'] and (not (run / 'samples.jsonl').exists() or not (run / 'samples.jsonl').stat().st_size):
        out.append('no time series')
    anchors = meta / 'clock_anchors.jsonl'
    if not anchors.exists() or len(anchors.read_text().splitlines()) != 2:
        out.append('clock anchors missing')
    for f in ('versions.json', 'launcher.sh', 'root.pid', 'ground_truth.json'):
        if not (meta / f).exists():
            out.append(f'meta/{f} missing')
    if not (run / 'SHA256SUMS').exists():
        out.append('no checksums')
    return out


if __name__ == '__main__':
    root = Path(sys.argv[1])
    runs = sorted(p for p in root.iterdir() if p.is_dir())
    bad = 0
    for run in runs:
        p = problems(run)
        if p:
            bad += 1
            print(f'{run.name}: ' + '; '.join(p))
    kernels = {json.loads((r / 'meta/versions.json').read_text())['kernel'] for r in runs
               if (r / 'meta/versions.json').exists()}
    print(f'{len(runs)} runs, {bad} with a measurement problem, kernels: {sorted(kernels)}')
    sys.exit(1 if bad else 0)
