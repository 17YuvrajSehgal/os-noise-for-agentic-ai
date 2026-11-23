#!/usr/bin/env python3
"""Review 3, points 2 and 3: is the replay skilful on the part of the run it changes?

For every held-out setting of a1_eval.py (same cells, same unlimited runs):
  - error on LOCAL time and on the LOCAL slowdown, not only on wall time
    (the replay copies the model slices, so wall error is diluted by f);
  - a whole-run baseline: the same max rule on the whole local part,
    local' = max(local, local CPU / q, local bytes / r), model time unchanged.
    This tests whether cutting the run into 0.2 s slices adds anything;
  - paired comparisons with one result per group of settings that share the same
    unlimited runs (the settings are not independent), two-sided.

  python rev/a1_local.py -> rev/a1_local.txt
"""
import json, random, statistics as st, sys
from collections import defaultdict
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from predict import slices, predict, split_times   # noqa: E402

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


def whole(sl, q, r):
    """Whole-run baseline: model time unchanged, local part as one block under the max rule."""
    m, l = split_times(sl)
    cpu = sum(c for dt, c, b, mod in sl if not mod)
    rb = sum(b for dt, c, b, mod in sl if not mod)
    need = l
    if q:
        need = max(need, cpu / q)
    if r:
        need = max(need, rb / r)
    return m + need, need


def sign_p(k, m):
    """Two-sided exact sign test."""
    tail = sum(comb(m, i) for i in range(max(k, m - k), m + 1)) / 2 ** m
    return min(1.0, 2 * tail)


rows = []
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
            if not base:
                continue
            design = dset == 'M0 first pass' and camp == 'cpu' and key[1] == 't3_implement'
            if design:
                continue
            bl = st.median(split_times(sl)[1] for sl, _, _ in base)
            bw = st.median(w for _, w, _ in base)
            for lk, v in cs.items():
                lim = v[0][2]
                if lk == '{}' or set(lim) - {'cpu_max', 'io_max', 'memory_max'} or not set(lim) & {'cpu_max', 'io_max'}:
                    continue
                q = int(lim['cpu_max'].split()[0]) / int(lim['cpu_max'].split()[1]) if 'cpu_max' in lim else None
                r = lim['io_max'].get('rbps') if isinstance(lim.get('io_max'), dict) else None
                obs_w = st.median(w for _, w, _ in v)
                obs_l = st.median(split_times(sl)[1] for sl, _, _ in v)
                d_model = st.median(split_times(sl)[0] for sl, _, _ in v) - st.median(split_times(sl)[0] for sl, _, _ in base)
                rep_w = st.median(predict(sl, q, r) for sl, _, _ in base)
                rep_l = st.median(predict(sl, q, r) - split_times(sl)[0] for sl, _, _ in base)
                who_w = st.median(whole(sl, q, r)[0] for sl, _, _ in base)
                who_l = st.median(whole(sl, q, r)[1] for sl, _, _ in base)
                naive = max(1.0, 1 / q) if q else 1.0
                rows.append(dict(group=(dset, camp) + key, obs_w=obs_w, obs_l=obs_l, rep_w=rep_w, rep_l=rep_l,
                                 who_w=who_w, who_l=who_l, naive_l=bl * naive, bl=bl, bw=bw, stable=abs(d_model) < 2,
                                 q=q, r=r))
        p(dset, camp, 'done')

e = lambda a, b: abs(a / b - 1)
p(f'\n{len(rows)} held-out settings, {len({r["group"] for r in rows})} groups of settings that share unlimited runs')
p(f"{'error of':<34}{'median':>8}{'mean':>8}{'p90':>8}{'within 10%':>12}")
for name, f in (('wall time, replay', lambda r: e(r['rep_w'], r['obs_w'])),
                ('wall time, whole-run max rule', lambda r: e(r['who_w'], r['obs_w'])),
                ('local time, replay', lambda r: e(r['rep_l'], r['obs_l'])),
                ('local time, whole-run max rule', lambda r: e(r['who_l'], r['obs_l'])),
                ('local time, s = 1/q', lambda r: e(r['naive_l'], r['obs_l'])),
                ('local slowdown, replay', lambda r: e(r['rep_l'] / r['bl'], r['obs_l'] / r['bl'])),
                ('local time, replay, model stable', None)):
    sel = rows if f else [r for r in rows if r['stable']]
    f = f or (lambda r: e(r['rep_l'], r['obs_l']))
    v = sorted(f(r) for r in sel)
    p(f'{name:<34}{st.median(v):>8.3f}{st.mean(v):>8.3f}{v[int(.9 * len(v))]:>8.3f}{sum(x <= .1 for x in v):>7}/{len(v)}')

p('\npaired: replay against an alternative, on local time (positive = replay closer)')
for name, alt in (('whole-run max rule', 'who_l'), ('s = 1/q', 'naive_l')):
    d = [e(r[alt], r['obs_l']) - e(r['rep_l'], r['obs_l']) for r in rows]
    k, m = sum(x > 0 for x in d), sum(x != 0 for x in d)
    g = defaultdict(list)
    for r, x in zip(rows, d):
        g[r['group']].append(x)
    gm = [st.mean(v) for v in g.values()]
    gk, gn = sum(x > 0 for x in gm), sum(x != 0 for x in gm)
    p(f'  vs {name}: settings closer {k} of {m}, sign test two-sided p={sign_p(k, m):.4f}; '
      f'per group of shared runs: closer in {gk} of {gn} groups, two-sided p={sign_p(gk, gn):.4f}; '
      f'median gain {100 * st.median(d):.1f} points')
(HERE / 'a1_local.txt').write_text('\n'.join(out) + '\n')


# --- by kind of limit, and the wall-time comparison per group (review 3, point 3) -------------
def kind(r):
    if r['r'] and not r['q']:
        return 'disk'
    return 'q<1' if r['q'] and r['q'] < 1 else 'q>=1'


p('\nby kind of limit')
for k in ('q<1', 'q>=1', 'disk'):
    sel = [r for r in rows if kind(r) == k]
    for name, a, b in (('local', 'rep_l', 'obs_l'), ('local, s=1/q', 'naive_l', 'obs_l'), ('wall', 'rep_w', 'obs_w')):
        v = sorted(e(r[a], r[b]) for r in sel)
        p(f'  {k:<5}{name:<14} n={len(v):>3} median {st.median(v):.3f} mean {st.mean(v):.3f} p90 {v[int(.9 * len(v))]:.3f}')
    d = [e(r['naive_l'], r['obs_l']) - e(r['rep_l'], r['obs_l']) for r in sel]
    k_, m_ = sum(x > 0 for x in d), sum(x != 0 for x in d)
    p(f'  {k:<5}replay closer than s=1/q on local time in {k_} of {m_} (two-sided p={sign_p(k_, m_):.4f})')
# read limits only: the simple estimate from the total bytes read, max(t, B/r), which is the
# whole-run rule (reviewer M., 2026-11-22). Also split by task: t8 is the plain file read.
sel = [r for r in rows if kind(r) == 'disk']
v = sorted(e(r['who_l'], r['obs_l']) for r in sel)
d = [e(r['who_l'], r['obs_l']) - e(r['rep_l'], r['obs_l']) for r in sel]
p(f"\nread limits, local time, max(t, B/r): n={len(v)} median {st.median(v):.3f} mean {st.mean(v):.3f} max {v[-1]:.3f}; "
  f"replay closer in {sum(x > 0 for x in d)} of {len(d)} (ties {sum(x == 0 for x in d)}), "
  f"two-sided p={sign_p(sum(x > 0 for x in d), sum(x != 0 for x in d)):.4f}")
for r in sel:
    p(f"  {r['group'][0]:<14}{r['group'][3]:<14} r={r['r'] / 1e6:>5.0f} MB/s  obs {r['obs_l']:>6.1f}  replay {r['rep_l']:>6.1f} ({100 * e(r['rep_l'], r['obs_l']):>4.1f}%)  "
      f"max(t,B/r) {r['who_l']:>6.1f} ({100 * e(r['who_l'], r['obs_l']):>4.1f}%)  1/q {r['naive_l']:>6.1f}")
d = [e(1 + (r['naive_l'] - r['bl']) / r['bw'], r['obs_w'] / r['bw']) - e(r['rep_w'], r['obs_w']) for r in rows]
g = defaultdict(list)
for r, x in zip(rows, d):
    g[r['group']].append(x)
gm = [st.mean(v) for v in g.values()]
gk, gn = sum(x > 0 for x in gm), sum(x != 0 for x in gm)
k, m = sum(x > 0 for x in d), sum(x != 0 for x in d)
p(f'\nwall time, replay vs Eq. 1 with s=1/q: settings {k} of {m} (two-sided p={sign_p(k, m):.4f}); '
  f'groups {gk} of {gn} (two-sided p={sign_p(gk, gn):.4f})')
(HERE / 'a1_local.txt').write_text('\n'.join(out) + '\n')
