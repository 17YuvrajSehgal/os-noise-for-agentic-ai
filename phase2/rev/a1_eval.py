#!/usr/bin/env python3
"""A1-A3: how well does the replay prediction (predict.py) match measured wall
times, against simple baselines, on data it was not designed on.

  python rev/a1_eval.py [--mode model|tool]   -> rev/a1_cells.csv, rev/a1.txt

Cells: single-agent runs whose limit is a CPU quota and/or a read rate
(cpu_max, io_max), in the same campaign as an unlimited cell of the same
model, task and runtime. Real-task cells that also cap memory (platform
sizes) are kept but marked: the replay ignores memory.

Per cell: pred = median over the unlimited runs of their replayed wall under
the cell's limit; obs = median measured wall. Slowdowns are against the
median unlimited wall. Error = pred / obs - 1. 95% interval of the error:
bootstrap over the runs of both sides (1000, fixed seed).

Methods (all use only the unlimited runs and the limit setting, except eq1-measured):
  replay        this method
  unchanged     wall slowdown 1
  quota         wall slowdown max(1, 1/q) (no dilution by model time)
  eq1-quota     1 + f (max(1, 1/q) - 1) (dilution, naive local slowdown)
  eq1-measured  1 + f (s - 1) with s measured under the limit (consistency check, NOT a prediction)
Design set: the first-pass M0 t3 CPU cells (the only ones looked at while writing predict.py).
Everything else is held out.
"""
import csv, json, random, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from predict import slices, predict, split_times   # noqa: E402

DATA = Path('C:/workplace/microservice-trace-dataset/agentic-runs-phase2')
SETS = {   # data set -> (root, campaigns)
    'M0 first pass': (DATA / 'runs', ['cpu', 'cpu_model2', 'disk', 'e2e_disk', 'real', 'real_quarter', 'real_long']),
    'M0 revision': (DATA / 'runs-rev', ['r_cpu', 'r_feedback_ref', 'r_real', 'r_interact']),
    'M1': (DATA / 'runs-rev', ['m1_cpu', 'm1_disk', 'm1_real']),
    'M2': (DATA / 'runs-rev', ['m2_cpu', 'm2_disk', 'm2_real']),
}
MODE = sys.argv[sys.argv.index('--mode') + 1] if '--mode' in sys.argv else 'model'
rng = random.Random(11)


def limit_of(spec):
    lim = {k: v for k, v in (spec.get('limits') or {}).items() if v not in (None, 'max', '')}
    q = r = None
    if 'cpu_max' in lim:
        a, b = lim['cpu_max'].split()
        q = int(a) / int(b)
    if 'io_max' in lim:
        r = lim['io_max'].get('rbps') if isinstance(lim['io_max'], dict) else None
    other = sorted(set(lim) - {'cpu_max', 'io_max'})
    return q, r, other, lim


def load(root, camp):
    runs = []
    for sp in sorted((root / camp).glob('*/spec.json')):
        run = sp.parent
        s = json.loads(sp.read_text())
        if s.get('agents', 1) != 1 or s.get('agent') != 'claude' or s.get('trace') == 'none':
            continue
        if not (run / 'samples.jsonl').exists() or not (run / 'result.json').exists():
            continue
        try:
            sl, wall = slices(run, MODE)
        except Exception as e:                  # a broken run must not stop the table
            print('skip', run.name, type(e).__name__, e)
            continue
        q, r, other, lim = limit_of(s)
        key = (s.get('model') or '', s['task'].replace('.sh', ''), str(s.get('task_arg', '')), s.get('runtime', 'host'))
        runs.append(dict(run=run.name, key=key, q=q, r=r, other=other, lim=json.dumps(lim, sort_keys=True),
                         sl=sl, wall=wall, ok=json.loads((run / 'result.json').read_text())['ok']))
    return runs


def boot(fn, a, b, n=1000):
    vals = sorted(fn(rng.choices(a, k=len(a)), rng.choices(b, k=len(b))) for _ in range(n))
    return vals[int(.025 * n)], vals[int(.975 * n)]


rows = []
for dset, (root, camps) in SETS.items():
    for camp in camps:
        if not (root / camp).exists():
            print('missing', root / camp)
            continue
        runs = load(root, camp)
        by = defaultdict(lambda: defaultdict(list))
        for x in runs:
            by[x['key']][x['lim']].append(x)
        for key, cells in by.items():
            base = cells.get('{}')
            if not base:
                continue
            bw = st.median(x['wall'] for x in base)
            f = st.median(split_times(x['sl'])[1] / x['wall'] for x in base)
            bl = st.median(split_times(x['sl'])[1] for x in base)
            for lim, v in cells.items():
                if lim == '{}':
                    continue
                q, r, other = v[0]['q'], v[0]['r'], v[0]['other']
                if q is None and r is None:
                    continue
                if other and other != ['memory_max']:
                    continue
                pw = lambda bs: st.median(predict(x['sl'], q, r) for x in bs)
                obs = st.median(x['wall'] for x in v)
                pred = pw(base)
                lo, hi = boot(lambda bs, vs: pw(bs) / st.median(x['wall'] for x in vs) - 1, base, v)
                naive = max(1.0, 1 / q) if q else 1.0
                s_meas = st.median(split_times(x['sl'])[1] for x in v) / bl
                d_model = st.median(split_times(x['sl'])[0] for x in v) - st.median(split_times(x['sl'])[0] for x in base)
                design = dset == 'M0 first pass' and camp == 'cpu' and key[1] == 't3_implement'
                rows.append(dict(set=dset, campaign=camp, model=key[0].replace('claude-', ''), task=key[1],
                                 task_arg=key[2], runtime=key[3], limit=lim, with_memory=bool(other),
                                 role='design' if design else 'held-out', n_base=len(base), n=len(v),
                                 failed=sum(not x['ok'] for x in v), f=round(f, 3),
                                 obs=round(obs / bw, 3), replay=round(pred / bw, 3),
                                 err_lo=round(lo, 3), err_hi=round(hi, 3),
                                 unchanged=1.0, quota=round(naive, 3), eq1_quota=round(1 + f * (naive - 1), 3),
                                 eq1_measured=round(1 + f * (s_meas - 1), 3), d_model_s=round(d_model, 2)))
        print(dset, camp, 'done', flush=True)

out = HERE / ('a1_cells.csv' if MODE == 'model' else f'a1_cells_{MODE}.csv')
with open(out, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)

METHODS = ['replay', 'unchanged', 'quota', 'eq1_quota', 'eq1_measured']


def summary(sel, title):
    if not sel:
        return []
    lines = [f'\n{title}: {len(sel)} cells']
    for m in METHODS:
        e = [abs(float(r[m]) / float(r['obs']) - 1) for r in sel]
        meds = sorted(st.median(rng.choices(e, k=len(e))) for _ in range(1000))
        lines.append(f'  {m:13} median |err| {st.median(e):6.1%} [{meds[25]:.1%}-{meds[975]:.1%}]  '
                     f'within 10% {sum(x <= .10 for x in e):3d}/{len(e)}  max {max(e):6.1%}')
    return lines


lines = [f'mode={MODE} (how a slice that is both model and tool time is counted)']
held = [r for r in rows if r['role'] == 'held-out']
lines += summary([r for r in rows if r['role'] == 'design'], 'design set (M0 first pass, t3, CPU)')
lines += summary(held, 'all held-out cells')
for dset in SETS:
    lines += summary([r for r in held if r['set'] == dset], f'held-out, {dset}')
lines += summary([r for r in held if r['task'] != 'swe'], 'held-out, small tasks')
lines += summary([r for r in held if r['task'] == 'swe'], 'held-out, real tasks')
lines += summary([r for r in held if r['limit'].count('io_max') and 'cpu_max' not in r['limit']], 'held-out, disk only')
lines += summary([r for r in held if r['with_memory']], 'held-out, CPU + memory platform sizes')
lines += summary([r for r in held if not r['failed']], 'held-out, cells where every run solved the task')

# Why the replay misses: the agent changed what it does (model time moved by 2 s or more,
# the test the paper uses for Eq. 1), or runs failed (memory kills), or neither.
miss = [r for r in held if abs(r['replay'] / r['obs'] - 1) > .10]
behav = [r for r in miss if abs(r['d_model_s']) >= 2]
fail = [r for r in miss if r not in behav and r['failed']]
same_dir = sum((r['replay'] < r['obs']) == (r['d_model_s'] > 0) for r in behav)
lines += ['', f'held-out replay misses (> 10%): {len(miss)}',
          f'  model time moved >= 2 s: {len(behav)} (the miss has the same sign as the model-time change in {same_dir})',
          f'  failed runs (no model-time change): {len(fail)}',
          f'  neither: {len(miss) - len(behav) - len(fail)}']
for r in [r for r in miss if r not in behav and r not in fail]:
    lines.append(f"    {r['set']} {r['campaign']} {r['model']} {r['task_arg']} {r['limit']} obs {r['obs']} replay {r['replay']}")
ok = [r for r in held if abs(r['d_model_s']) < 2 and not r['failed']]
lines += summary(ok, 'held-out, model time stable (< 2 s) and every run solved')
e = lambda r, m: abs(r[m] / r['obs'] - 1)
lines.append(f"\npaired, all held-out: replay closer than eq1_quota in {sum(e(r, 'replay') < e(r, 'eq1_quota') for r in held)} "
             f"cells, farther in {sum(e(r, 'replay') > e(r, 'eq1_quota') for r in held)}")
txt = HERE / ('a1.txt' if MODE == 'model' else f'a1_{MODE}.txt')
txt.write_text('\n'.join(lines) + '\n')
print('\n'.join(lines))
