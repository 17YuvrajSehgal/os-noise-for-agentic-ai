#!/usr/bin/env python3
"""One campaign: validation of the trace numbers, medians per setting, and
the diagnosis verdicts (thresholds frozen from Phase 1).

  python report.py <campaign> <spec keys, comma separated, dotted for nested>

Reads phase2/<campaign>/{analyze_all,diag_all}.jsonl, step1_runs.csv (from
run_passes.py) and counters.csv (from collector/summarize.py --csv).
"""
import csv, json, statistics as st, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
camp, keys = sys.argv[1], sys.argv[2].split(',')
d = HERE / camp
load = lambda n: {r['run']: r for r in map(json.loads, open(d / n))}
A, D = load('analyze_all.jsonl'), load('diag_all.jsonl')
S1 = {r['run']: r for r in csv.DictReader(open(d / 'step1_runs.csv'))}
C = {r['run']: r for r in csv.DictReader(open(d / 'counters.csv'))}
num = lambda v: float(v) if v not in ('', None, 'None') else None
med = lambda v: st.median(v) if v else float('nan')


def dig(x, dotted):
    for k in dotted.split('.'):
        x = x.get(k) if isinstance(x, dict) else None
    return json.dumps(x, separators=(',', ':')) if isinstance(x, (dict, list)) else str(x)


def verdict(r):
    if r['reclaim_n'] >= 50: return 'memory'
    if r['d_noio_s'] >= 1.0: return 'disk'
    if r['wait_idle_s'] >= 0.3: return 'cpu-quota'
    if r['wait_busy_s'] >= 1.0: return 'cpu-compete'
    return 'nothing'


rows = []
for run, c in sorted(C.items()):
    if run not in A or run not in D:
        print('MISSING trace pass for', run)
        continue
    a, dg, s = A[run], D[run], S1.get(run, {})
    f = lambda k: num(s.get(k)) or 0.0
    model = f('model_only_s') + f('model_tool_s')
    usage = a['cpu_stat']['usage_s']
    rows.append(dict(
        label=' / '.join(dig(json.loads(c['spec']), k) for k in keys), ok=c['ok'] == 'True',
        wall=num(c['wall_s']), startup=f('startup_s'), model=model, tool=f('tool_only_s'),
        agent_only=f('agent_only_s'), turns_trace=int(s.get('n_turns') or 0), turns_agent=num(c['turns']),
        api=num(c['api_s']), on_cpu=dg['on_cpu_s'], usage=usage,
        gap=100 * (a['subtree_cpu_seconds']['on_cpu'] - usage) / usage if usage else None,
        throttled=num(c['throttled_s']), wait_idle=dg['wait_idle_s'], wait_busy=dg['wait_busy_s'],
        d_io=dg['d_io_s'], d_noio=dg['d_noio_s'], reclaim_n=dg['reclaim_n'], reclaim_s=dg['reclaim_s'],
        psi_io=num(c['psi_io_s']), psi_mem=num(c['psi_mem_s']), killed=len(dg['killed']),
        oom_kill=num(c['oom_kill']) or 0, verdict=verdict(dg)))

print(f'== {camp}: {len(rows)} runs')
gap = [abs(r['gap']) for r in rows if r['gap'] is not None]
print(f'trace CPU vs cpu.stat (a1 or group): median gap {med(gap):.2f}%, worst {max(gap):.1f}%')
dt = Counter(r['turns_trace'] - int(r['turns_agent']) for r in rows if r['turns_agent'] is not None)
print('model turns, trace minus agent report:', dict(sorted(dt.items())))
ratio = [r['model'] / r['api'] for r in rows if r['api']]
if ratio:
    print(f'model time, trace / agent API time: median {med(ratio):.2f}, range {min(ratio):.2f}-{max(ratio):.2f}')

cols = ['wall', 'startup', 'model', 'tool', 'agent_only', 'on_cpu', 'throttled', 'wait_idle', 'wait_busy',
        'd_io', 'd_noio', 'reclaim_n', 'reclaim_s', 'psi_io', 'psi_mem', 'oom_kill']
g = defaultdict(list)
for r in rows:
    g[r['label']].append(r)
w = max(len(k) for k in g) + 1
print(f"{'setting':<{w}}{'n':>3}{'ok':>4}" + ''.join(f'{c:>11}' for c in cols) + '  verdicts')
for label in sorted(g):
    v = g[label]
    print(f"{label:<{w}}{len(v):>3}{sum(r['ok'] for r in v):>4}"
          + ''.join(f"{med([r[c] for r in v if r[c] is not None]):>11.2f}" for c in cols)
          + '  ' + str(dict(Counter(r['verdict'] for r in v))))
