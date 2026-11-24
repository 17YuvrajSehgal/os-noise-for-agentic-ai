#!/usr/bin/env python3
"""RQ1 table: the time split of runs with no limit, per model, task and runtime.

  python table.py          (reads rq1/runs.csv from split.py; writes rq1/table.txt)

Shares are medians over runs of (part / wall time), in percent. Model = model
only + model with a tool running at the same time (sub-agents, background
tools). Waits are seconds of the agent's process tree from the trace.
"""
import csv, statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = [r for r in csv.DictReader(open(HERE / 'runs.csv')) if r['unlimited'] == 'True']
f = lambda r, k: float(r[k] or 0)
med = lambda v: st.median(v) if v else float('nan')
g = defaultdict(list)
for r in rows:
    g[(r['model'].replace('claude-', ''), r['task'] + ('' if r['task'] != 'swe' else ':' + r['task_arg'].split('__')[0]),
       r['runtime'])].append(r)

cols = ['n', 'wall', 'startup%', 'model%', 'tool%', 'agent%', 'end%', 'turns', 'tools',
        'agentCPU', 'toolCPU', 'cpuWait', 'diskWait']
out = [f"{'model':<10}{'task':<16}{'runtime':<8}" + ''.join(f'{c:>9}' for c in cols)]
for k in sorted(g):
    v = g[k]
    pct = lambda *ks: med([100 * sum(f(r, x) for x in ks) / f(r, 'wall_s') for r in v])
    vals = [len(v), med([f(r, 'wall_s') for r in v]), pct('startup_s'), pct('model_only_s', 'model_tool_s'),
            pct('tool_only_s'), pct('agent_only_s'), pct('shutdown_s'), med([f(r, 'turns_log') for r in v]),
            med([f(r, 'tool_calls') for r in v]), med([f(r, 'agent_cpu_s') for r in v]),
            med([f(r, 'tool_cpu_s') for r in v]),
            med([f(r, 'wait_cpu_quota_s') + f(r, 'wait_cpu_busy_s') for r in v]), med([f(r, 'wait_disk_s') for r in v])]
    out.append(f'{k[0]:<10}{k[1]:<16}{k[2]:<8}' + ''.join(f'{x:>9.1f}' if isinstance(x, float) else f'{x:>9}' for x in vals))

# one line per model over all coding tasks (toy tasks t2, t3, t9, t10 and the real tasks)
out.append('')
coding = lambda r: r['task'] in ('t2_medium', 't3_implement', 't9_implement_quiet', 't10_expr', 'swe')
for m in sorted({r['model'] for r in rows}):
    v = [r for r in rows if r['model'] == m and coding(r)]
    if v:
        share = [100 * (f(r, 'model_only_s') + f(r, 'model_tool_s')) / f(r, 'wall_s') for r in v]
        tool = [100 * f(r, 'tool_only_s') / f(r, 'wall_s') for r in v]
        out.append(f'{m}: {len(v)} coding runs, model share median {med(share):.0f}% '
                   f'(range {min(share):.0f}-{max(share):.0f}), tool share median {med(tool):.0f}%')
(HERE / 'table.txt').write_text('\n'.join(out) + '\n')
print('\n'.join(out))
