#!/usr/bin/env python3
"""Every table of the workshop paper (research-paper/paper.tex, OXAI 2026,
arXiv only) recomputed on the old runs (Phase 1: Claude and Codex) and on the
new runs (Phase 2: Claude), side by side.

  python workshop/replicate.py     (from phase2/; writes workshop/tables.txt)

Inputs are the outputs of the same analyzer (analyze_run.py) on both sets:
phase1/results/analyze_all.jsonl (old) and phase2/<campaign>/analyze_all.jsonl
(new), plus step1_runs.csv (model share by the turn rule) and, for new runs,
rq1/runs.csv (model share from the agent's own log). Cells: median [min-max].
"""
import csv, json, re, statistics as st
from collections import defaultdict
from pathlib import Path

P2 = Path(__file__).resolve().parents[1]
P1 = P2.parent / 'phase1' / 'results'
C = 4                                                  # vCPUs on both VMs


def load(path, src):
    for l in open(path):
        a = json.loads(l)
        g = a['ground_truth']
        a['src'] = f"{src} {g.get('agent') or 'claude'}"
        yield a


OLD = list(load(P1 / 'analyze_all.jsonl', 'old'))
NEW = {c: list(load(P2 / c / 'analyze_all.jsonl', 'new')) for c in
       ('cpu', 'cpu_model2', 'threads', 'subagents', 'memory_soft', 'memory_hard_file', 'memory_cliff', 'disk',
        'e2e_memory', 'e2e_disk')}
gt = lambda a, k: a['ground_truth'].get(k) or ''
mem = lambda a: a.get('memory') or {}
wk = lambda a: a.get('workers') or {}


def cell(v, nd=1):
    v = [x for x in v if x is not None]
    if not v:
        return '-'
    return f'{st.median(v):.{nd}f} [{min(v):.{nd}f}-{max(v):.{nd}f}]'


def num(s):
    m = re.findall(r'\d+', s)
    return int(m[0]) if m else 10 ** 12                # 'max' / '' = unlimited, sorts first when reversed


out = []
def table(title, runs, key, cols, order):
    """runs: list of analyze rows; key(a) -> level label; cols: [(name, fn, digits)]."""
    out.append(f'\n== {title}')
    g = defaultdict(list)
    for a in runs:
        g[(a['src'], gt(a, 'task').replace('.sh', ''), key(a))].append(a)
    out.append(f"{'source':<12}{'task':<16}{'level':<14}{'n':>3}  " + ''.join(f'{n:<24}' for n, _, _ in cols))
    for k in sorted(g, key=lambda k: (k[0], k[1], order(k[2]))):
        v = g[k]
        out.append(f'{k[0]:<12}{k[1]:<16}{k[2]:<14}{len(v):>3}  ' + ''.join(f'{cell([f(a) for a in v], d):<24}' for _, f, d in cols))


cap = lambda a: 'unlimited' if gt(a, 'cpu_max') in ('max', '') else f"{int(gt(a, 'cpu_max').split()[0]) / 100000:g} core"
cap_order = lambda l: -10 if l == 'unlimited' else -float(l.split()[0])

# --- model share (workshop: 84% by all-HTTPS rule; Phase 1 turn rule; new: agent log)
s1 = [dict(r, src=f"old {r['agent']}") for r in csv.DictReader(open(P1 / 'step1_runs.csv'))]
for c in ('cpu', 'cpu_model2'):
    s1 += [dict(r, src=f"new {r['agent']}") for r in csv.DictReader(open(P2 / c / 'step1_runs.csv'))]
log = {r['run']: r for r in csv.DictReader(open(P2 / 'rq1' / 'runs.csv'))}
out.append('== Model share of wall time by CPU cap (workshop Sec. 3 baseline and LLM-SHARE-RESULT)')
out.append('   turn = trace turn rule (Phase 1); log = agent event log (new runs only)')
g = defaultdict(list)
for r in s1:
    if r['task'] in ('t2_medium.sh', 't3_implement.sh') and not r['mem_limit'] and not r['io_limit']:
        lv = 'unlimited' if r['cpu_max'] == 'max' else f"{int(r['cpu_max'].split()[0]) / 100000:g} core"
        model = log.get(r['run'], {}).get('model', '').replace('claude-', '') if r['src'].startswith('new') else ''
        g[(r['src'], model, r['task'].replace('.sh', ''), lv)].append(r)
for k in sorted(g, key=lambda k: (k[0], k[1], k[2], cap_order(k[3]))):
    v = g[k]
    lg = [100 * (float(log[r['run']]['model_only_s']) + float(log[r['run']]['model_tool_s'])) / float(log[r['run']]['wall_s'])
          for r in v if r['run'] in log]
    out.append(f"{k[0]:<12}{k[1]:<10}{k[2]:<14}{k[3]:<11}{len(v):>3}  turn {cell([float(r['model_pct']) for r in v], 0):<16}"
               f"log {cell(lg, 0)}")

# --- Problem 1: CPU cap (Table II)
table('Problem 1, CPU cap (Table II): wall, on-CPU, throttled (cpu.stat), throttled % of wall',
      [a for a in OLD if a['family'].startswith('1_svc') and gt(a, 'task') in ('t2_medium.sh', 't3_implement.sh')]
      + [a for a in NEW['cpu']] + [dict(a, src='new ' + a['run'].split('_')[2].replace('claude-', '').split('-')[0]) for a in NEW['cpu_model2']],
      cap, [('wall s', lambda a: a['wall_s'], 1), ('on-CPU s', lambda a: a['subtree_cpu_seconds']['on_cpu'], 1),
            ('throttled s', lambda a: a['cpu_stat']['throttled_s'], 1),
            ('throttled %', lambda a: 100 * a['cpu_stat']['throttled_s'] / a['wall_s'], 0)], cap_order)

# --- Problem 2: threads vs cores (Table III) + sub-agents
W = lambda a: int(gt(a, 'task_arg'))
table('Problem 2, threads vs cores (Table III): phase, wait fraction (runnable/phase), predicted (W-C)/W, stalls',
      [a for a in OLD if gt(a, 'task') == 't4_parallel.sh'] + NEW['threads'], lambda a: f'W={W(a)}',
      [('phase s', lambda a: wk(a).get('phase_wall_s'), 2), ('on-CPU/worker', lambda a: wk(a).get('worker_on_cpu_s_med'), 2),
       ('wait fraction', lambda a: wk(a)['worker_runnable_s_med'] / wk(a)['phase_wall_s'] if wk(a).get('phase_wall_s') else None, 2),
       ('predicted', lambda a: max(0, (W(a) - C) / W(a)), 2), ('stalls>=1ms', lambda a: a['sched_latency']['ge_1ms'], 0),
       ('stalls>=10ms', lambda a: a['sched_latency']['ge_10ms'], 0)], lambda l: int(l[2:]))
table('Problem 2, sub-agents (Sec. IV text): N sub-agents each running one worker',
      [a for a in OLD if gt(a, 'task') == 't5_subagents.sh'] + NEW['subagents'], lambda a: f'N={W(a)}',
      [('phase s', lambda a: wk(a).get('phase_wall_s'), 2), ('on-CPU/worker', lambda a: wk(a).get('worker_on_cpu_s_med'), 2),
       ('runnable/worker', lambda a: wk(a).get('worker_runnable_s_med'), 2), ('stalls>=1ms', lambda a: a['sched_latency']['ge_1ms'], 0),
       ('wall s', lambda a: a['wall_s'], 1)], lambda l: int(l[2:]))

# --- Problem 3A: memory.high on the file workload (Table IV), and memory.max on the same workload (text)
lim = lambda a: gt(a, 'mem_limit') or 'unlimited'
lim_order = lambda l: -num(l)
mcols = [('phase s', lambda a: wk(a).get('phase_wall_s'), 1),
         ('refaults', lambda a: mem(a).get('stat_delta', {}).get('workingset_refault_file', 0), 0),
         ('high events', lambda a: mem(a).get('events', {}).get('high', 0), 0),
         ('oom kills', lambda a: mem(a).get('events', {}).get('oom_kill', 0), 0),
         ('reclaim stall s', lambda a: mem(a).get('reclaim_stall_s'), 2)]
t6 = [a for a in OLD if gt(a, 'task') == 't6_memtouch.sh']
table('Problem 3A, memory.high, 1 GB file workload (Table IV)',
      [a for a in t6 if not lim(a).startswith('max')] + NEW['memory_soft'], lim, mcols, lim_order)
table('Problem 3B part 1, memory.max, same file workload (text: no OOM kill, same refault cost)',
      [a for a in t6 if lim(a).startswith('max')] + NEW['memory_hard_file'], lim, mcols, lim_order)

# --- Problem 3B: anonymous-memory cliff; who is killed (agent exit 137 = the agent itself)
out.append('\n== Problem 3B, memory.max cliff, 512 MB anonymous workload (text)')
out.append(f"{'source':<12}{'memory.max':<12}{'n':>3}{'OOM kill':>10}{'task fail':>11}{'agent killed':>14}")
g = defaultdict(list)
for a in [a for a in OLD if gt(a, 'task') == 't7_memhog.sh'] + NEW['memory_cliff']:
    g[(a['src'], lim(a))].append(a)
for k in sorted(g, key=lambda k: (k[0], -num(k[1]))):
    v = g[k]
    out.append(f"{k[0]:<12}{k[1]:<12}{len(v):>3}{sum(mem(a).get('events', {}).get('oom_kill', 0) > 0 for a in v):>10}"
               f"{sum(a['ground_truth'].get('task_check_exit') != 0 for a in v):>11}"
               f"{sum(a['ground_truth'].get('agent_exit') == 137 for a in v):>14}")

# --- Problem 4: disk read cap (Table V)
rb = lambda a: 'unlimited' if not gt(a, 'io_limit') else f"{int(gt(a, 'io_limit').split(':')[1]) // 2 ** 20} MB/s"
table('Problem 4, io.max rbps, cold 1 GB read (Table V): phase, bytes read (io.stat), device MB/s = bytes / phase',
      [a for a in OLD if gt(a, 'task') == 't8_ioread.sh'] + NEW['disk'], rb,
      [('phase s', lambda a: wk(a).get('phase_wall_s'), 2), ('read MB', lambda a: (a.get('io') or {}).get('rbytes', 0) / 1e6, 0),
       ('device MB/s', lambda a: (a.get('io') or {}).get('rbytes', 0) / 1e6 / wk(a)['phase_wall_s'] if wk(a).get('phase_wall_s') else None, 0)],
      lambda l: -num(l))

# --- Realistic task (Table VI): new only; old end-to-end runs have no traces
table('Realistic task t3_implement end to end (Table VI), new runs: wall, OOM kills, solved = 1',
      NEW['e2e_memory'] + NEW['e2e_disk'] + [a for a in NEW['cpu'] if gt(a, 'task') == 't3_implement.sh'],
      lambda a: (lim(a) if gt(a, 'mem_limit') else rb(a) if gt(a, 'io_limit') else cap(a)),
      [('wall s', lambda a: a['wall_s'], 0), ('oom kills', lambda a: mem(a).get('events', {}).get('oom_kill', 0), 0),
       ('solved', lambda a: int(a['ground_truth'].get('task_check_exit') == 0), 0),
       ('peak MB', lambda a: mem(a).get('peak_bytes', 0) / 2 ** 20, 0)], lambda l: (l[:3], -num(l)))

# --- Validation: trace on-CPU vs cpu.stat (Sec. III)
out.append('\n== Trace on-CPU against cpu.stat usage, |gap| % (workshop: ~2% throttled, ~18% unthrottled)')
g = defaultdict(list)
for a in OLD + [a for v in NEW.values() for a in v]:
    u = a['cpu_stat']['usage_s']
    if u > 0.5:
        g[(a['src'], 'throttled' if a['cpu_stat']['throttled_s'] > 0 else 'not throttled')].append(
            100 * abs(a['subtree_cpu_seconds']['on_cpu'] - u) / u)
for k in sorted(g):
    out.append(f'{k[0]:<12}{k[1]:<15}{len(g[k]):>4} runs  median {st.median(g[k]):.1f}%  90th pct '
               f'{sorted(g[k])[int(0.9 * (len(g[k]) - 1))]:.1f}%  max {max(g[k]):.1f}%')

(Path(__file__).parent / 'tables.txt').write_text('\n'.join(out) + '\n')
print('\n'.join(out))
