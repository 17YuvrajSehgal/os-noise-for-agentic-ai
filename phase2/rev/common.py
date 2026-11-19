"""Shared loader for the revision analyses: one record per run, from the run
folder only (spec, result, event log, samples). No trace pass needed.

wall/model/local use the same cut as RQ1 (predict.slices, mode 'model').
Multi-agent runs get one record per agent (wall = that agent's own time).
"""
import json, random, statistics as st
from pathlib import Path

from predict import slices, split_times

DATA = Path('C:/workplace/microservice-trace-dataset/agentic-runs-phase2')
FIRST, REV = DATA / 'runs', DATA / 'runs-rev'
_cache = {}


def lim_key(spec):
    lim = {k: v for k, v in (spec.get('limits') or {}).items() if v not in (None, 'max', '')}
    return json.dumps(lim, sort_keys=True)


def load(root, camp, agents=False):
    """Single-agent runs of a campaign (or every agent of every run, if agents=True)."""
    k = (str(root), camp, agents)
    if k in _cache:
        return _cache[k]
    out = []
    for sp in sorted((Path(root) / camp).glob('*/spec.json')):
        run = sp.parent
        s = json.loads(sp.read_text())
        if s.get('agent', 'claude') != 'claude' or not (run / 'result.json').exists():
            continue
        n = s.get('agents', 1)
        if (n != 1) != agents:
            continue
        res = json.loads((run / 'result.json').read_text())
        rec = dict(campaign=camp, run=run.name, model=(s.get('model') or '').replace('claude-', ''),
                   task=s['task'].replace('.sh', ''), task_arg=str(s.get('task_arg', '')),
                   runtime=s.get('runtime', 'host'), limits=lim_key(s), trace=s.get('trace', 'full'),
                   agents=n, ok=res['ok'], wall=res.get('wall_s'))
        if not agents:
            try:
                sl, wall = slices(run)
                m, l = split_times(sl)
                rec.update(wall=wall, model_s=m, local=l, exit=(run / 'a1' / 'exit_code').read_text().strip()
                           if (run / 'a1' / 'exit_code').exists() else '')
            except Exception as e:              # a run with a broken event log keeps wall from result.json
                rec.update(model_s=None, local=None, exit='', err=f'{type(e).__name__}: {e}')
            out.append(rec)
        else:
            for a in res.get('agents', []):
                out.append(dict(rec, agent=a['agent'], ok=a['task_check_exit'] == 0, exit=a.get('agent_exit')))
    _cache[k] = out
    return out


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def boot_ratio(a, b, n=2000, seed=7):
    """95% bootstrap interval of median(a) / median(b)."""
    rng = random.Random(seed)
    rs = sorted(st.median(rng.choices(a, k=len(a))) / st.median(rng.choices(b, k=len(b))) for _ in range(n))
    return rs[int(.025 * n)], rs[int(.975 * n)]


def cliffs_delta(a, b):
    """P(a > b) - P(a < b): effect size, -1..1. |d| < .147 negligible, < .33 small, < .474 medium, else large."""
    gt = sum(x > y for x in a for y in b)
    lt = sum(x < y for x in a for y in b)
    return (gt - lt) / (len(a) * len(b))


def wilson(k, n, z=1.96):
    """95% Wilson interval of a rate k/n."""
    if not n:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** .5
    return max(0.0, (c - h) / d), min(1.0, (c + h) / d)
