#!/usr/bin/env python3
"""RQ2: how each limit changes the time split. One curve per experiment, per
model and task: every limit level against the baseline of the same model and
task.

  python curves.py          (reads rq1/runs.csv; writes rq2/curves.txt, rq2/curves.csv)

Baseline: the unlimited cell of the experiment; if it has none, its loosest
level. pids_mid is joined to pids (same task, pids has the unlimited cell).
Slowdown = median wall / median baseline wall, with a 95% bootstrap interval
(both groups resampled, 2000 times, fixed seed). Local = wall minus model time:
the time spent on the machine, where limits act; the model's answer time
varies by run and hides small effects in the wall time. The breaking point is
the loosest level whose interval lies above 1.10 (wall, and local). Deltas are medians of the part
minus the baseline median of that part, in seconds. Waits are medians of the
agent process tree (trace). A run that did not solve the task is counted in
"failed" and kept in the time medians.
"""
import csv, json, random, statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
P2 = HERE.parent
RUNS = Path(__import__('os').environ.get('OSNOISE_RUNS', 'C:/workplace/microservice-trace-dataset/agentic-runs-phase2/runs'))
EXPS = ['cpu', 'cpu_model2', 'memory_soft', 'memory_hard_file', 'memory_cliff', 'e2e_memory', 'disk', 'e2e_disk',
        'network', 'pids', 'threads', 'neighbour']
KNEE = 1.10
rows = list(csv.DictReader(open(P2 / 'rq1' / 'runs.csv')))
f = lambda r, k: float(r[k] or 0)
rng = random.Random(7)


def level(r):
    """The one thing the experiment varies, as a short label."""
    if r['campaign'] == 'threads':
        return f"{r['task_arg']} workers"
    if r['net']:
        return r['net'] if r['net'] != '{}' else 'none'
    if r['neighbour']:
        return r['neighbour']
    lim = json.loads(r['limits']) if r['limits'] else {}
    return ' '.join(f'{k}={v}' for k, v in lim.items()) or 'none'


def order(camp):
    """Levels from loose to tight, in the order of the campaign grid."""
    d = json.loads((RUNS / camp / 'campaign.json').read_text())
    key, vals = next((k, v) for k, v in d['grid'].items() if k not in ('agent', 'task', 'model'))
    return key, vals


def boot_ratio(a, b, n=2000):
    rs = sorted(st.median(rng.choices(a, k=len(a))) / st.median(rng.choices(b, k=len(b))) for _ in range(n))
    return rs[int(0.025 * n)], rs[int(0.975 * n)]


PARTS = [('startup', ['startup_s']), ('model', ['model_only_s', 'model_tool_s']), ('tool', ['tool_only_s']),
         ('other', ['agent_only_s', 'shutdown_s'])]
WAITS = [('cpuQuota', 'wait_cpu_quota_s'), ('cpuBusy', 'wait_cpu_busy_s'), ('disk', 'wait_disk_s'),
         ('dOther', 'wait_d_other_s'), ('reclaim', 'reclaim_s')]
out, table = [], []
for exp in EXPS:
    camps = ['pids', 'pids_mid'] if exp == 'pids' else [exp]
    key, vals = order(exp)
    if exp == 'pids':
        vals = vals[:5] + [23, 22, 21, 20, 19, 18, 17] + vals[5:]      # down to 24, the middle levels, then 16, 12
    labels = []
    for v in vals:                     # the level label each grid value produces
        fake = dict(campaign=exp, task_arg=str(v), net='', neighbour='', limits='')
        if key == 'net':
            fake['net'] = json.dumps(v) if v != {} else '{}'
        elif key == 'neighbour':
            fake['neighbour'] = json.dumps(v) if v else ''
        elif key.startswith('limits.'):
            lk = key.split('.', 1)[1]
            fake['limits'] = json.dumps({lk: v}, sort_keys=True) if v not in ('max', None) else ''
        labels.append(level(fake))
    g = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r['campaign'] in camps:
            g[(r['model'].replace('claude-', ''), r['task'])][level(r)].append(r)
    for (model, task), cells in sorted(g.items()):
        levels = [l for l in labels if l in cells]
        base = cells[levels[0]]
        bw = [f(r, 'wall_s') for r in base]
        local = lambda r: f(r, 'wall_s') - f(r, 'model_only_s') - f(r, 'model_tool_s')
        bl = [local(r) for r in base]
        out.append(f'\n== {exp}  {model}  {task}  (baseline: {levels[0]}, n={len(base)}, wall {st.median(bw):.1f} s)')
        out.append(f"{'level':<34}{'n':>3}{'fail':>5}{'wall':>7}{'slowdown [95%]':>21}"
                   + ''.join(f'{"+" + p:>9}' for p, _ in PARTS) + ''.join(f'{w:>9}' for w, _ in WAITS) + '  turns   local  local slowdown')
        knee = knee_l = None
        for l in levels:
            v = cells[l]
            w = [f(r, 'wall_s') for r in v]
            ratio = st.median(w) / st.median(bw)
            lo, hi = boot_ratio(w, bw) if l != levels[0] else (1.0, 1.0)
            if knee is None and lo > KNEE:
                knee = l
            lw = [local(r) for r in v]
            lr = st.median(lw) / st.median(bl)
            llo, lhi = boot_ratio(lw, bl) if l != levels[0] else (1.0, 1.0)
            if knee_l is None and llo > KNEE:
                knee_l = l
            d = {p: st.median(sum(f(r, k) for k in ks) for r in v) - st.median(sum(f(r, k) for k in ks) for r in base)
                 for p, ks in PARTS}
            wt = {w_: st.median(f(r, k) for r in v) for w_, k in WAITS}
            fail = sum(r['ok'] != 'True' for r in v)
            out.append(f'{l[:33]:<34}{len(v):>3}{fail:>5}{st.median(w):>7.1f}{ratio:>8.2f} [{lo:.2f}-{hi:.2f}]'
                       + ''.join(f'{d[p]:>+9.1f}' for p, _ in PARTS) + ''.join(f'{wt[x]:>9.1f}' for x, _ in WAITS)
                       + f"  {st.median(f(r, 'turns_log') for r in v):>5.0f}{st.median(lw):>8.1f}{lr:>7.2f} [{llo:.2f}-{lhi:.2f}]")
            table.append(dict(experiment=exp, model=model, task=task, level=l, n=len(v), failed=fail,
                              wall_med=round(st.median(w), 2), slowdown=round(ratio, 3), ci_lo=round(lo, 3),
                              ci_hi=round(hi, 3), **{f'd_{p}_s': round(d[p], 2) for p, _ in PARTS},
                              **{f'{x}_s': round(wt[x], 2) for x, _ in WAITS},
                              turns_med=st.median(f(r, 'turns_log') for r in v), local_med=round(st.median(lw), 2),
                              local_slowdown=round(lr, 3), local_ci_lo=round(llo, 3), local_ci_hi=round(lhi, 3)))
        out.append(f'breaking point (interval above {KNEE:.2f}): wall {knee or "none in range"}; '
                   f'local {knee_l or "none in range"}')
(HERE / 'curves.txt').write_text('\n'.join(out).lstrip() + '\n')
with open(HERE / 'curves.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(table[0]))
    w.writeheader(); w.writerows(table)
print('\n'.join(out))
