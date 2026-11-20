#!/usr/bin/env python3
"""Review 2, point 3: how much does the replay depend on the unlimited run it starts from,
and is it better than the naive guess in a paired test?

a1_eval.py predicts from the median over all unlimited runs of a cell (5 to 15).
Here each unlimited run predicts alone: error = replay(run) / median measured wall - 1.

  python rev/a1_single.py   -> rev/a1_single.txt   (reads rev/a1_cells.csv for the paired tests)
"""
import csv, json, random, statistics as st, sys
from collections import defaultdict, Counter
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from predict import slices, predict   # noqa: E402

DATA = Path('C:/workplace/microservice-trace-dataset/agentic-runs-phase2')
SETS = {   # as in a1_eval.py
    'M0 first pass': (DATA / 'runs', ['cpu', 'cpu_model2', 'disk', 'e2e_disk', 'real', 'real_quarter', 'real_long']),
    'M0 revision': (DATA / 'runs-rev', ['r_cpu', 'r_feedback_ref', 'r_real', 'r_interact']),
    'M1': (DATA / 'runs-rev', ['m1_cpu', 'm1_disk', 'm1_real']),
    'M2': (DATA / 'runs-rev', ['m2_cpu', 'm2_disk', 'm2_real']),
}
out = []


def p(*a):
    out.append(' '.join(str(x) for x in a))
    print(*a, flush=True)


# --- paired tests on the cells of a1_eval ----------------------------------------------
cells = [r for r in csv.DictReader(open(HERE / 'a1_cells.csv')) if r['role'] == 'held-out']
err = lambda r, k: abs(float(r[k]) / float(r['obs']) - 1)
p('held-out cells by task:', dict(Counter('real' if r['task'] == 'swe' else r['task'] for r in cells)))
for name, sel in (('all held-out', cells), ('without t3', [r for r in cells if r['task'] != 't3_implement'])):
    d = [err(r, 'eq1_quota') - err(r, 'replay') for r in sel]
    k, m = sum(x > 0 for x in d), sum(x != 0 for x in d)
    sign = sum(comb(m, i) for i in range(k, m + 1)) / 2 ** m
    rng = random.Random(1)
    n = 20000
    hits = sum(st.mean(x * rng.choice((1, -1)) for x in d) >= st.mean(d) for _ in range(n))
    p(f'{name}: n={len(sel)}  replay {st.median(err(r, "replay") for r in sel):.3f}  naive Eq.1 '
      f'{st.median(err(r, "eq1_quota") for r in sel):.3f}  replay closer in {k} of {m}  '
      f'sign test p={sign:.4f}  mean gain {st.mean(d):.3f} (sign-flip p={(hits + 1) / (n + 1):.4f})')

# --- one unlimited run at a time ---------------------------------------------------------
design = lambda dset, camp, task: dset == 'M0 first pass' and camp == 'cpu' and task == 't3_implement'
single, spread, worst, nb, slow, slow_worst = [], [], [], [], [], []
for dset, (root, camps) in SETS.items():
    for camp in camps:
        by = defaultdict(lambda: defaultdict(list))
        for sp in sorted((root / camp).glob('*/spec.json')):
            run = sp.parent
            s = json.loads(sp.read_text())
            if s.get('agents', 1) != 1 or s.get('agent') != 'claude' or s.get('trace') == 'none':
                continue
            if not (run / 'samples.jsonl').exists() or not (run / 'result.json').exists():
                continue
            try:
                sl, wall = slices(run)
            except Exception:
                continue
            lim = {k: v for k, v in (s.get('limits') or {}).items() if v not in (None, 'max', '')}
            key = (s.get('model') or '', s['task'].replace('.sh', ''), str(s.get('task_arg', '')), s.get('runtime', 'host'))
            by[key][json.dumps(lim, sort_keys=True)].append((sl, wall, lim))
        for key, cs in by.items():
            base = cs.get('{}')
            if not base or design(dset, camp, key[1]):
                continue
            for lk, v in cs.items():
                lim = v[0][2]
                if lk == '{}' or set(lim) - {'cpu_max', 'io_max', 'memory_max'} or not set(lim) & {'cpu_max', 'io_max'}:
                    continue
                q = int(lim['cpu_max'].split()[0]) / int(lim['cpu_max'].split()[1]) if 'cpu_max' in lim else None
                r = lim['io_max'].get('rbps') if isinstance(lim.get('io_max'), dict) else None
                if q is None and r is None:
                    continue
                obs = st.median(w for _, w, _ in v)
                preds = [predict(sl, q, r) for sl, _, _ in base]
                e = [abs(x / obs - 1) for x in preds]
                bw = st.median(w for _, w, _ in base)      # slowdown of the run itself against the measured slowdown
                es = [abs((x / w) / (obs / bw) - 1) for x, (_, w, _) in zip(preds, base)]
                slow.append(st.median(es))
                slow_worst.append(max(es))
                single.append(st.median(e))
                worst.append(max(e))
                spread.append((max(preds) - min(preds)) / st.median(preds))
                nb.append(len(base))
        p(dset, camp, 'done')
p(f'\none unlimited run at a time: {len(single)} held-out cells, {min(nb)} to {max(nb)} unlimited runs per cell')
p(f'  error of a typical single run (median over cells of the per-cell median): {st.median(single):.3f}')
p(f'  cells where the typical single run is within 10%: {sum(x <= 0.10 for x in single)} of {len(single)}')
p(f'  error of the worst single run of a cell, median over cells: {st.median(worst):.3f}; '
  f'cells where even the worst run is within 10%: {sum(x <= 0.10 for x in worst)}')
p(f'  spread of the predictions inside a cell ((max - min) / median), median over cells: {st.median(spread):.3f}')
p(f'  slowdown predicted by a single run (its replay / its own wall) against the measured slowdown: typical run '
  f'{st.median(slow):.3f}, within 10% in {sum(x <= 0.10 for x in slow)} cells; worst run {st.median(slow_worst):.3f}, '
  f'within 10% in {sum(x <= 0.10 for x in slow_worst)} cells')
(HERE / 'a1_single.txt').write_text('\n'.join(out) + '\n')
