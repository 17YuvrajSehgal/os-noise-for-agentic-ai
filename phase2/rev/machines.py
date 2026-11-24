#!/usr/bin/env python3
"""Results across machines (new Section 7) and A5 statistics.

For each core experiment and machine: every level with n, wall and local
slowdown against the machine's own unlimited (or loosest) level with a 95%
bootstrap interval, Cliff's delta of the wall times against that baseline,
the solve rate and the rate of abnormal agent exits (crash or kill) with 95%
Wilson intervals. Breaking point = loosest level whose interval lies above
1.10 (as in RQ2).

  python rev/machines.py   -> rev/machines.txt, rev/machines.csv
"""
import csv, json, statistics as st, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import FIRST, REV, load, med, boot_ratio, cliffs_delta, wilson   # noqa: E402

KNEE = 1.10
VCPU = {'M0 first pass': 4, 'M0 revision': 4, 'M1': 2, 'M2': 8}


def cpu_q(lim):
    l = json.loads(lim)
    return int(l['cpu_max'].split()[0]) / 100000 if 'cpu_max' in l else 99


def mem_mb(lim, key):
    v = json.loads(lim).get(key)
    return 1e9 if v is None else (int(v[:-1]) * (1024 if v.endswith('G') else 1))


def rate(lim):
    v = json.loads(lim).get('io_max')
    return 1e12 if v is None else v['rbps']


def pids(lim):
    return json.loads(lim).get('pids_max', 1e9)


# name, task, [(machine, root, campaigns)], level(record) -> label, tightness(label) -> sort key (loose first)
EXPS = [
    ('CPU quota (t3, Opus)', 't3_implement',
     [('M0 first pass', FIRST, ['cpu']), ('M0 revision', REV, ['r_cpu']), ('M1', REV, ['m1_cpu']), ('M2', REV, ['m2_cpu'])],
     lambda r: r['limits'], lambda l: -cpu_q(l)),
    ('Threads (t4, W workers per vCPU)', 't4_parallel',
     [('M0 first pass', FIRST, ['threads']), ('M1', REV, ['m1_threads']), ('M2', REV, ['m2_threads'])],
     None, lambda l: float(l.split()[0])),
    ('Soft memory limit (t6, 1 GB file)', 't6_memtouch',
     [('M0 first pass', FIRST, ['memory_soft']), ('M1', REV, ['m1_memory']), ('M2', REV, ['m2_memory'])],
     lambda r: r['limits'], lambda l: -mem_mb(l, 'memory_high')),
    ('Hard memory limit (t7, 512 MB tool)', 't7_memhog',
     [('M0 first pass', FIRST, ['memory_cliff']), ('M0 revision', REV, ['r_mem']), ('M1', REV, ['m1_memory']),
      ('M2', REV, ['m2_memory'])],
     lambda r: r['limits'], lambda l: -mem_mb(l, 'memory_max')),
    ('Disk read rate (t8, 1 GB)', 't8_ioread',
     [('M0 first pass', FIRST, ['disk']), ('M1', REV, ['m1_disk']), ('M2', REV, ['m2_disk'])],
     lambda r: r['limits'], lambda l: -rate(l)),
    ('Process limit (t3, Opus)', 't3_implement',
     [('M0 first pass', FIRST, ['pids', 'pids_mid']), ('M0 revision', REV, ['r_cpu', 'r_pids']),
      ('M1', REV, ['m1_cpu', 'm1_pids', 'm1_pids_lo']), ('M2', REV, ['m2_cpu', 'm2_pids', 'm2_pids_hi'])],
     lambda r: r['limits'], lambda l: -pids(l)),
]


def threads_level(r, machine):
    return f"{int(r['task_arg']) / VCPU[machine]:g} per vCPU ({r['task_arg']} workers)"


def keep(exp, r):
    if r['model'] not in ('opus-5-5', '') or r['trace'] == 'none':
        return False
    if exp.startswith('Process'):           # only unlimited and process-limit cells
        return r['limits'] == '{}' or 'pids_max' in r['limits']
    if exp.startswith('CPU'):
        return 'pids_max' not in r['limits']
    if exp.startswith('Soft'):
        return 'memory_max' not in r['limits']
    if exp.startswith('Hard'):
        return 'memory_high' not in r['limits']
    return True


rows, lines = [], []
knees = []     # (experiment, machine, part, breaking point with medians, with means)
for exp, task, sets, lev, tight in EXPS:
    lines.append(f'\n#### {exp}')
    for machine, root, camps in sets:
        recs = [r for c in camps if (root / c).exists() for r in load(root, c) if r['task'] == task and keep(exp, r)]
        if not recs:
            continue
        label = (lambda r: threads_level(r, machine)) if lev is None else lev
        cells = {}
        for r in recs:
            cells.setdefault(label(r), []).append(r)
        order = sorted(cells, key=tight)
        base = cells[order[0]]
        bw = [r['wall'] for r in base]
        bl = [r['local'] for r in base if r['local'] is not None]
        lines.append(f'\n== {machine} ({VCPU[machine]} vCPU)  baseline: {order[0]}  n={len(base)}  wall {med(bw):.1f} s')
        lines.append(f"{'level':40}{'n':>4}{'wall slowdown [95%]':>23}{'local slowdown [95%]':>23}{'delta':>7}"
                     f"{'solved [95%]':>21}{'abnormal exit [95%]':>24}")
        knee = knee_l = knee_m = knee_lm = None
        for l in order:
            v = cells[l]
            w = [r['wall'] for r in v]
            lw = [r['local'] for r in v if r['local'] is not None]
            sw, (lo, hi) = med(w) / med(bw), ((1, 1) if v is base else boot_ratio(w, bw))
            sl, (llo, lhi) = med(lw) / med(bl), ((1, 1) if v is base else boot_ratio(lw, bl))
            if knee is None and lo > KNEE:
                knee = l
            if knee_l is None and llo > KNEE:
                knee_l = l
            # the same with means instead of medians (robustness check)
            mw, (mlo, _) = st.mean(w) / st.mean(bw), ((1, 1) if v is base else boot_ratio(w, bw, stat=st.mean))
            ml, (mllo, _) = st.mean(lw) / st.mean(bl), ((1, 1) if v is base else boot_ratio(lw, bl, stat=st.mean))
            if knee_m is None and mlo > KNEE:
                knee_m = l
            if knee_lm is None and mllo > KNEE:
                knee_lm = l
            d = 0.0 if v is base else cliffs_delta(w, bw)
            ok = sum(r['ok'] for r in v)
            bad = sum(r['exit'] not in ('0', '') for r in v)
            s_lo, s_hi = wilson(ok, len(v))
            b_lo, b_hi = wilson(bad, len(v))
            lines.append(f'{l[:39]:40}{len(v):>4}{sw:>8.2f} [{lo:.2f}-{hi:.2f}]{"":>2}{sl:>8.2f} [{llo:.2f}-{lhi:.2f}]{"":>2}'
                         f'{d:>+7.2f}{ok:>5}/{len(v):<3}[{s_lo:.2f}-{s_hi:.2f}]{bad:>6}/{len(v):<3}[{b_lo:.2f}-{b_hi:.2f}]')
            rows.append(dict(experiment=exp, machine=machine, vcpu=VCPU[machine], level=l, n=len(v),
                             wall_slowdown=round(sw, 3), wall_lo=round(lo, 3), wall_hi=round(hi, 3),
                             local_slowdown=round(sl, 3), local_lo=round(llo, 3), local_hi=round(lhi, 3),
                             wall_mean_ratio=round(mw, 3), local_mean_ratio=round(ml, 3),
                             local_min=round(min(lw), 2), local_max=round(max(lw), 2),
                             cliffs_delta=round(d, 3), solved=ok, abnormal_exit=bad,
                             exit_codes=' '.join(sorted({r['exit'] for r in v if r['exit'] not in ('0', '')}))))
        lines.append(f'breaking point (interval above {KNEE:.2f}): wall {knee or "none"}; local {knee_l or "none"}')
        lines.append(f'  with means instead of medians: wall {knee_m or "none"}; local {knee_lm or "none"}')
        knees += [(exp, machine, 'wall', knee, knee_m), (exp, machine, 'local', knee_l, knee_lm)]

same = [k for k in knees if k[3] == k[4]]
lines.append('')
lines.append(f'#### Means instead of medians: {len(same)} of {len(knees)} breaking points are the same; '
             f'local: {sum(k[2] == "local" for k in same)} of {sum(k[2] == "local" for k in knees)}')
for k in knees:
    if k[3] != k[4]:
        lines.append(f'  differs: {k[0]} / {k[1]} / {k[2]}: median {k[3] or "none"} -> mean {k[4] or "none"}')
d = [abs(r['local_mean_ratio'] / r['local_slowdown'] - 1) for r in rows if r['local_slowdown'] > 0 and r['n'] and r['abnormal_exit'] == 0]
lines.append(f'local slowdown, mean ratio against median ratio (cells with no aborted run): median difference '
             f'{100 * st.median(d):.1f}%, 90th percentile {100 * sorted(d)[int(.9 * len(d))]:.1f}%')
with open(HERE / 'machines.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
(HERE / 'machines.txt').write_text('\n'.join(lines).lstrip() + '\n')
print('\n'.join(lines))
