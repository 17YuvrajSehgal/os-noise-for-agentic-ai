#!/usr/bin/env python3
"""Step 4 (P21-P25): the limits, looked at again.

P21  where the CPU-cap wait lands (which part of the run, agent or tools)
P22  which parts of a run each limit slows
P23  how stable each metric is across repetitions
P24  a fixed procedure names the limit from the trace alone; compared with
     the limit that was really set
P25  what the cgroup counters alone would have said

Inputs: results/parsed_all.jsonl, diag_all.jsonl, analyze_all.jsonl,
step1_runs.csv, step2_turns.csv. Writes results/step4_diagnosis.csv.
"""
import csv, json, statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from step1 import roles, STEP

HERE = Path(__file__).resolve().parent
CAP = {'max': 'unlimited', '100000 100000': '1 core', '50000 100000': '0.5 core',
       '25000 100000': '0.25 core'}

# ---- the procedure (P24). Trace signals only, agent process tree only. ----
RECLAIM_MIN = 50      # memory-cgroup reclaim episodes started by the tree
D_NOIO_MIN = 1.0      # s of disk-type sleep with no block request in flight
WAIT_IDLE_MIN = 0.3   # s ready-to-run while a CPU was idle
WAIT_BUSY_MIN = 1.0   # s ready-to-run while all CPUs were busy


def diagnose(d):
    """First check that fires decides. Order matters: reclaim also causes
    disk sleep, and a CPU quota also causes a little no-I/O sleep."""
    if d['reclaim_n'] >= RECLAIM_MIN:
        return 'memory limit' + (' + kill' if d['killed'] else '')
    if d['d_noio_s'] >= D_NOIO_MIN:
        return 'disk limit'
    if d['wait_idle_s'] >= WAIT_IDLE_MIN:
        return 'CPU quota'
    if d['wait_busy_s'] >= WAIT_BUSY_MIN:
        return 'CPU competition'
    return 'nothing found'


def truth(gt):
    """What was really done to the run, and whether it could bite at all."""
    mem, io, cpu, task = gt.get('mem_limit', ''), gt.get('io_limit', ''), gt['cpu_max'], gt['task']
    if cpu != 'max':
        return 'CPU quota', CAP[cpu]
    if task.startswith('t4'):
        w = int(gt['task_arg'])
        return ('CPU competition' if w > 4 else 'none'), f'{w} workers on 4 CPUs'
    if io:
        mb = int(io.split(':')[1]) // 1048576
        return ('disk limit' if mb < 200 else 'none'), f'disk {mb} MB/s' + ('' if mb < 200 else ' (above disk speed)')
    if mem and mem != 'high:max':
        val = mem.split(':')[1]
        size = int(val[:-1]) * (1024 if val.endswith('G') else 1)
        need = 762 if task.startswith('t7') else 1380        # MB, footprint from the workshop paper
        loose = size > need + 100
        return ('none' if loose else 'memory limit'), f'memory {mem}' + (' (above footprint)' if loose else '')
    return 'none', 'no limit'


def counters(a, gt):
    """P25: verdict from the cgroup counters that were saved with the run."""
    if a['cpu_stat']['nr_throttled'] > 0:
        return 'CPU quota'
    ev = (a.get('memory') or {}).get('events') or {}
    if ev.get('oom_kill', 0) > 0:
        return 'memory limit + kill'
    if ev.get('high', 0) > 0 or ev.get('max', 0) > 0:
        return 'memory limit'
    return 'nothing found'


def load(name):
    return {(r['family'], r['run']): r for r in map(json.loads, open(HERE / 'results' / name))}


def med(v, nd=2):
    v = [float(x) for x in v if x not in ('', None)]
    return round(st.median(v), nd) if v else ''


if __name__ == '__main__':
    P, D, A = load('parsed_all.jsonl'), load('diag_all.jsonl'), load('analyze_all.jsonl')
    S1 = list(csv.DictReader(open(HERE / 'results/step1_runs.csv')))
    T2 = list(csv.DictReader(open(HERE / 'results/step2_turns.csv')))
    coding = lambda x: (x['task'] in ('t2_medium.sh', 't3_implement.sh')
                        and x['run'] not in ('t2_nocap_r1', 't2_cap100_r1'))

    # ---------------- P21 ----------------
    print('=== P21: where the CPU-cap wait lands (coding runs, median seconds of ready-wait) ===')
    parts = ('startup', 'model_only', 'model_tool', 'tool_only', 'agent_only', 'shutdown')
    acc = defaultdict(list)
    for k, r in P.items():
        gt = r['ground_truth']
        if gt['task'] not in ('t2_medium.sh', 't3_implement.sh') or r['run'] in ('t2_nocap_r1', 't2_cap100_r1'):
            continue
        ro = roles(r)
        turns = ro['turns']
        first, last = turns[0]['t_req'], max(x['t_last_in'] for x in turns)
        miv = [(x['t_req'], x['t_last_in']) for x in turns]
        tiv = [(ro['procs'][p][0], ro['procs'][p][1]) for p in ro['tools']]
        inside = lambda t, iv: any(a <= t <= b for a, b in iv)
        w = defaultdict(float)
        for p, bins in r['cpu'].items():
            who = 'tool' if int(p) in ro['tools'] else 'agent'
            for i, _, rdy in bins:
                if not rdy:
                    continue
                t = i * STEP
                if t < ro['t_start'] or t > ro['t_end']:
                    continue
                if t < first:
                    c = 'startup'
                elif t > last:
                    c = 'shutdown'
                else:
                    m_, t_ = inside(t, miv), inside(t, tiv)
                    c = 'model_tool' if m_ and t_ else 'model_only' if m_ else 'tool_only' if t_ else 'agent_only'
                w[c] += rdy
                w[who] += rdy
        acc[(gt.get('agent', 'claude'), CAP[gt['cpu_max']])].append((w, A[k]['cpu_stat']['throttled_s']))
    print(f"{'agent':<7}{'cpu':<10}{'n':<4}" + ''.join(f'{p:>11}' for p in parts)
          + f"{'by agent':>10}{'by tools':>10}{'total':>8}{'cpu.stat':>9}")
    for agent in ('claude', 'codex'):
        for cap in CAP.values():
            v = acc[(agent, cap)]
            print(f"{agent:<7}{cap:<10}{len(v):<4}" + ''.join(f"{med([w[p] for w, _ in v]):>11}" for p in parts)
                  + f"{med([w['agent'] for w, _ in v]):>10}{med([w['tool'] for w, _ in v]):>10}"
                  + f"{med([w['agent'] + w['tool'] for w, _ in v]):>8}{med([t for _, t in v]):>9}")

    # ---------------- P22 ----------------
    print('\n=== P22: which part of the run each limit slows (median seconds) ===')
    grp = defaultdict(list)
    for r in S1:
        gt_like = dict(cpu_max=r['cpu_max'], mem_limit=r['mem_limit'], io_limit=r['io_limit'],
                       task=r['task'], task_arg=r['task_arg'])
        grp[(r['agent'], r['task'][:9], truth(gt_like)[1])].append(r)
    tt = defaultdict(list)
    for t in T2:
        tt[(t['family'], t['run'])].append(float(t['ttfb_s']))
    print(f"{'agent':<7}{'task':<10}{'condition':<34}{'n':<3}{'wall':>7}{'startup':>8}{'model':>7}{'tool only':>10}"
          f"{'turns':>6}{'ttfb':>6}")
    for k in sorted(grp):
        if k[1] in ('t2_medium', 't3_implem'):
            continue                                   # CPU caps on coding runs are in Step 1
        v = grp[k]
        ttfb = [st.median(tt[(r['family'], r['run'])]) for r in v if tt[(r['family'], r['run'])]]
        print(f"{k[0]:<7}{k[1]:<10}{k[2]:<34}{len(v):<3}{med([r['wall_s'] for r in v]):>7}"
              f"{med([r['startup_s'] for r in v]):>8}"
              f"{med([float(r['model_only_s']) + float(r['model_tool_s']) for r in v]):>7}"
              f"{med([r['tool_only_s'] for r in v]):>10}{med([r['n_turns'] for r in v], 0):>6}{med(ttfb):>6}")

    # ---------------- P23 ----------------
    print('\n=== P23: spread across repetitions, per metric ===')
    print('    spread of a cell = (max - min) / median over its repetitions; shown: median over cells, worst cell')
    metrics = {}
    cells = defaultdict(list)
    for r in S1:
        key = (r['agent'], r['task'], r['cpu_max'], r['mem_limit'], r['io_limit'], r['task_arg'])
        cells[key].append(r)
    def spread(get, sel=lambda k: True):
        out = []
        for k, v in cells.items():
            if len(v) < 3 or not sel(k):
                continue
            x = [get(r) for r in v]
            x = [y for y in x if y is not None]
            if len(x) >= 3 and st.median(x) > 0:
                out.append((max(x) - min(x)) / st.median(x))
        return (round(100 * st.median(out)), round(100 * max(out)), len(out)) if out else None
    fl = lambda name: (lambda r: float(r[name]) if r.get(name) not in ('', None) else None)
    is_coding = lambda k: k[1] in ('t2_medium.sh', 't3_implement.sh')
    key_of = lambda r: (r['family'], r['run'])
    dget = lambda name: (lambda r: D[key_of(r)][name])
    aget = lambda f_: (lambda r: f_(A[key_of(r)]))
    rows = [
        ('wall time, coding runs', spread(fl('wall_s'), is_coding)),
        ('number of model turns, coding runs', spread(fl('n_turns'), is_coding)),
        ('model time, coding runs', spread(lambda r: float(r['model_only_s']) + float(r['model_tool_s']), is_coding)),
        ('start-up time, all runs', spread(fl('startup_s'))),
        ('tool-only time, coding runs', spread(fl('tool_only_s'), is_coding)),
        ('agent CPU, all runs', spread(fl('agent_cpu_s'))),
        ('tool CPU, coding runs', spread(fl('tool_cpu_s'), is_coding)),
        ('throttled time (cpu.stat), capped runs', spread(aget(lambda a: a['cpu_stat']['throttled_s']),
                                                          lambda k: k[2] not in ('max', '100000 100000'))),
        ('ready-wait with idle CPU, capped runs', spread(dget('wait_idle_s'),
                                                         lambda k: k[2] not in ('max', '100000 100000'))),
        ('worker phase time, synthetic runs', spread(aget(lambda a: (a['workers'] or {}).get('phase_wall_s')),
                                                     lambda k: not is_coding(k))),
        ('disk-type sleep, disk and memory runs', spread(lambda r: D[key_of(r)]['d_io_s'] + D[key_of(r)]['d_noio_s'],
                                                         lambda k: k[1].startswith(('t6', 't8')))),
        ('reclaim episodes, binding memory runs', spread(dget('reclaim_n'), lambda k: k[1].startswith('t6'))),
    ]
    for name, s in rows:
        if s:
            print(f'    {name:<44} {s[0]:>4}%   worst {s[1]:>4}%   ({s[2]} cells)')

    # ---------------- P24 / P25 ----------------
    out = []
    for k, d in D.items():
        gt = P[k]['ground_truth']
        tr, detail = truth(gt)
        out.append(dict(family=k[0], run=k[1], agent=gt.get('agent', 'claude'), truth=tr, condition=detail,
                        trace_verdict=diagnose(d), counter_verdict=counters(A[k], gt),
                        has_mem_counters=int(A[k].get('memory') is not None),
                        **{s: d[s] for s in ('wait_idle_s', 'wait_busy_s', 'd_noio_s', 'd_io_s', 'reclaim_n')},
                        killed=';'.join(d['killed']),
                        oom_kill_counter=((A[k].get('memory') or {}).get('events') or {}).get('oom_kill', '')))
    with open(HERE / 'results/step4_diagnosis.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader(); w.writerows(out)

    base = lambda v: v.replace(' + kill', '')
    labels = ['CPU quota', 'CPU competition', 'memory limit', 'disk limit', 'nothing found']
    for title, col in (('P24: verdict from the TRACE', 'trace_verdict'), ('P25: verdict from the COUNTERS', 'counter_verdict')):
        print(f'\n=== {title} (rows: what was really done; columns: what the procedure said) ===')
        tab = defaultdict(Counter)
        for r in out:
            tab[r['truth']][base(r[col])] += 1
        print(f"{'truth':<18}{'n':>4}" + ''.join(f'{l:>17}' for l in labels) + f"{'correct':>9}")
        ok = tot = 0
        for tr in ('CPU quota', 'CPU competition', 'memory limit', 'disk limit', 'none'):
            want = 'nothing found' if tr == 'none' else tr
            n = sum(tab[tr].values())
            ok += tab[tr][want]; tot += n
            print(f"{tr:<18}{n:>4}" + ''.join(f'{tab[tr][l]:>17}' for l in labels) + f"{100 * tab[tr][want] / n:>8.0f}%")
        print(f'overall: {ok} of {tot} runs named correctly ({100 * ok / tot:.1f}%)')
        if col == 'trace_verdict':
            wrong = [r for r in out if base(r[col]) != ('nothing found' if r['truth'] == 'none' else r['truth'])]
            print('  runs the trace procedure got wrong:')
            for r in wrong:
                print(f"    {r['agent']:<7}{r['run']:<26}{r['condition']:<30} said: {r[col]:<18}"
                      f" wait_idle={r['wait_idle_s']} wait_busy={r['wait_busy_s']} d_noio={r['d_noio_s']} reclaim={r['reclaim_n']}")
    print('\n=== kill detection (trace: a process exits within 1 ms of its own reclaim) vs oom_kill counter ===')
    c = Counter()
    for r in out:
        if r['oom_kill_counter'] == '':
            continue
        c[('kill said' if r['killed'] else 'no kill said', 'really killed' if int(r['oom_kill_counter']) > 0 else 'not killed')] += 1
    for k, n in sorted(c.items()):
        print('   ', k, n)
    print('    runs with no memory counters saved (cannot check):', sum(1 for r in out if r['oom_kill_counter'] == ''))
