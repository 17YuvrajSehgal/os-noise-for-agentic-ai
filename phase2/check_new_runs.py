#!/usr/bin/env python3
"""Do the new traces give sound numbers? Run after the Phase 1 passes
(analyze_all, parse_all, step1, diag_pass) on a campaign of the new collector.

  python3 check_new_runs.py <phase1 results dir> <campaign dir>

Compares, per run:
  - trace on-CPU time against cpu.stat                 (accounting is complete)
  - trace ready-wait with idle CPUs against throttled time  (throttle is visible)
  - model turns from the trace against the agent's own turn count
  - model time from the trace against the agent's own API time
and prints the wall-clock split per CPU setting and the diagnosis verdicts.
"""
import csv, json, statistics as st, sys
from collections import Counter, defaultdict
from pathlib import Path

res, camp = Path(sys.argv[1]), Path(sys.argv[2])
load = lambda n: {r['run']: r for r in map(json.loads, open(res / n))}
A, D = load('analyze_all.jsonl'), load('diag_all.jsonl')
S1 = {r['run']: r for r in csv.DictReader(open(res / 'step1_runs.csv'))}
med = lambda v: round(st.median(v), 2) if v else float('nan')


def agent_report(run):
    rep, n_asst = {}, 0
    for line in open(camp / run / 'a1/events.jsonl'):
        try:
            ev = json.loads(json.loads(line)['line'])
        except (ValueError, KeyError):
            continue
        if ev.get('type') == 'result':
            rep = ev
    return rep


rows = []
for run, a in sorted(A.items()):
    rep, s, d = agent_report(run), S1[run], D[run]
    usage = a['cpu_stat']['usage_s']
    model_s = float(s['model_only_s']) + float(s['model_tool_s'])
    rows.append(dict(run=run, cap=a['ground_truth']['cpu_max'], task=a['ground_truth']['task'],
                     cpu_gap_pct=100 * (a['subtree_cpu_seconds']['on_cpu'] - usage) / usage,
                     throttled=a['cpu_stat']['throttled_s'], wait_idle=d['wait_idle_s'],
                     turns_trace=int(s['n_turns']), turns_agent=rep.get('num_turns'),
                     model_trace=model_s, api_agent=rep.get('duration_api_ms', 0) / 1000,
                     startup=float(s['startup_s']), tool=float(s['tool_only_s']), model=model_s,
                     wall=float(s['wall_s']), reclaim=d['reclaim_n'], d_noio=d['d_noio_s'],
                     wait_busy=d['wait_busy_s']))

gap = [abs(r['cpu_gap_pct']) for r in rows]
print(f'trace CPU vs cpu.stat: median gap {med(gap)}%, worst {max(gap):.1f}%')
thr = [(r['wait_idle'], r['throttled']) for r in rows if r['throttled'] > 1]
print(f'ready-wait with idle CPU vs throttled time (capped runs): median ratio '
      f'{med([w / t for w, t in thr])}, range {min(w / t for w, t in thr):.2f}-{max(w / t for w, t in thr):.2f}')
dt = Counter(r['turns_trace'] - r['turns_agent'] for r in rows if r['turns_agent'] is not None)
print('model turns, trace minus agent report:', dict(sorted(dt.items())))
ratio = [r['model_trace'] / r['api_agent'] for r in rows if r['api_agent']]
print(f'model time, trace / agent API time: median {med(ratio)}, range {min(ratio):.2f}-{max(ratio):.2f}')

print('\nwall-clock split per CPU setting (median s):')
print(f"{'task':<16}{'cpu.max':<16}{'n':>3}{'wall':>7}{'startup':>9}{'model':>7}{'tool':>7}{'throttled':>10}{'wait_idle':>10}")
g = defaultdict(list)
for r in rows:
    g[(r['task'], r['cap'])].append(r)
order = ['max', '100000 100000', '75000 100000', '50000 100000', '37500 100000', '25000 100000']
for (task, cap), v in sorted(g.items(), key=lambda kv: (kv[0][0], order.index(kv[0][1]))):
    m = lambda k: med([r[k] for r in v])
    print(f"{task:<16}{cap:<16}{len(v):>3}{m('wall'):>7}{m('startup'):>9}{m('model'):>7}{m('tool'):>7}"
          f"{m('throttled'):>10}{m('wait_idle'):>10}")

print('\ndiagnosis from the trace alone (thresholds frozen from Phase 1):')
def verdict(r):
    if r['reclaim'] >= 50: return 'memory limit'
    if r['d_noio'] >= 1.0: return 'disk limit'
    if r['wait_idle'] >= 0.3: return 'CPU quota'
    if r['wait_busy'] >= 1.0: return 'CPU competition'
    return 'nothing found'
tab = defaultdict(Counter)
for r in rows:
    tab[r['cap']][verdict(r)] += 1
for cap in order:
    print(f'  {cap:<16}', dict(tab[cap]))
