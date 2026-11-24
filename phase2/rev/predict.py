#!/usr/bin/env python3
"""A1-A3: predict the wall time under a limit from the UNLIMITED run only.

The unlimited run's timeline is cut into the sampler's slices (about 0.2 s).
A slice inside a model turn keeps its length: the machine does not change how
long the model takes to answer. A local slice that used d CPU-seconds and read
b bytes needs at least d/q seconds under a quota of q cores and b/r seconds
under a read rate of r bytes/s, so it becomes max(dt, d/q, b/r). Predicted
wall = sum of all slices. No parameter is fitted: the inputs are the
unlimited run's samples and the limit's setting.

  OSNOISE_RUNS=<root> python rev/predict.py

Modes for the model/local cut (A4):
  model  a slice that overlaps a model turn is model time (as in the paper)
  tool   a slice where a tool runs is local even while the model streams
"""
import json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'rq1'))
os.environ.setdefault('OSNOISE_RUNS', 'C:/workplace/microservice-trace-dataset/agentic-runs-phase2/runs')  # split.py reads it on import
from split import intervals                      # noqa: E402  same model/tool timeline as RQ1


def samples(run):
    out = []
    for line in open(run / 'samples.jsonl'):
        s = json.loads(line)
        g = s.get('group') or {}
        if 'cpu_usage_usec' in g:
            out.append((s['realtime'], g['cpu_usage_usec'] / 1e6, (g.get('io') or {}).get('rbytes', 0)))
    return out


def covered(iv, t):
    return any(a <= t <= b for a, b in iv)


def slices(run, mode='model'):
    """-> list of (dt, cpu_s, read_bytes, is_model) and the wall time of the run."""
    anchors = [json.loads(l) for l in open(run / 'meta' / 'clock_anchors.jsonl')]
    t0, t1 = anchors[0]['realtime'], anchors[-1]['realtime']
    turns, tools, *_ = intervals(run)
    s = samples(run)
    out = []
    for (ta, ca, ba), (tb, cb, bb) in zip(s, s[1:]):
        a, b = max(ta, t0), min(tb, t1)
        if b <= a:
            continue
        k = (b - a) / (tb - ta)
        mid = (a + b) / 2
        model = covered(turns, mid) and not (mode == 'tool' and covered(tools, mid))
        out.append((b - a, (cb - ca) * k, (bb - ba) * k, model))
    seen = sum(x[0] for x in out)
    out.append((max(0.0, (t1 - t0) - seen), 0.0, 0.0, False))    # time outside the samples: local, unchanged
    return out, t1 - t0


def predict(sl, q=None, r=None):
    """Predicted wall seconds under a CPU quota q (cores) and a read rate r (bytes/s)."""
    tot = 0.0
    for dt, cpu, rb, model in sl:
        if model:
            tot += dt
            continue
        need = dt
        if q:
            need = max(need, cpu / q)
        if r:
            need = max(need, rb / r)
        tot += need
    return tot


def split_times(sl):
    model = sum(dt for dt, _, _, m in sl if m)
    return model, sum(dt for dt, *_ in sl) - model


if __name__ == '__main__':
    root = Path(os.environ['OSNOISE_RUNS'])
    for run in sorted((root / 'cpu').glob('cpu_claude_t3_implement_max_r*')):
        sl, wall = slices(run)
        m, l = split_times(sl)
        print(run.name, f'wall {wall:.1f} model {m:.1f} local {l:.1f}',
              ' '.join(f'q{q}:{predict(sl, q=q):.1f}' for q in (1, .75, .5, .375, .25)))
