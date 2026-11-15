#!/usr/bin/env python3
"""RQ4: N agents on one 4-vCPU machine, all started at once, same small coding
task (t3_implement), Opus, no limits. One row per agent, then one line per N.

  OSNOISE_RUNS=<runs root> python rq4/agents.py   (writes rq4/agents.csv, rq4/table.txt)

Per agent, from its own event log: wall = run start to the agent's final
result; start-up = run start to its first model request; model and tool time
as in rq1/split.py (10 ms steps, model wins where both overlap). Local = wall
minus model. Waits come from the trace, per agent process tree
(density/diag_agents.jsonl): busy = ready to run while all CPUs were busy.
Throughput = agents finished per minute = N / (time until the last agent
finished). Memory peak is for the whole group of agents (meta/memory.peak);
cost is each agent's own reported cost. Slowdown = median per-agent value / median at N=1.
"""
import csv, json, os, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
P2 = HERE.parent
sys.path.insert(0, str(P2 / 'rq1'))
os.environ.setdefault('OSNOISE_RUNS', 'C:/workplace/microservice-trace-dataset/agentic-runs-phase2/runs')
from split import events, intervals, ROOT, STEP  # noqa: E402

diag = {(d['run'], d['pidfile'].split('/')[0]): d for d in map(json.loads, open(P2 / 'density' / 'diag_agents.jsonl'))}


def busy(iv, t0, n):
    on = bytearray(n)
    for a, b in iv:
        for i in range(max(0, int((a - t0) / STEP)), min(n, int((b - t0) / STEP) + 1)):
            on[i] = 1
    return on


rows = []
for run in sorted((ROOT / 'density').glob('density_*_r*')):
    spec = json.loads((run / 'spec.json').read_text())
    res = json.loads((run / 'result.json').read_text())
    t0 = json.loads(open(run / 'meta' / 'clock_anchors.jsonl').readline())['realtime']
    for a in res['agents']:
        turns, tools, t_first, t_result, main = intervals(run, a['agent'])
        end = t_result or max(b for _, b in turns + tools)
        n = int((end - t0) / STEP) + 1
        m, tl = busy(turns, t0, n), busy(tools, t0, n)
        d = diag.get((run.name, a['agent']), {})
        rows.append(dict(run=run.name, n_agents=spec['agents'], agent=a['agent'],
                         ok=a['agent_exit'] == 0 and a['task_check_exit'] == 0 and not a['test_file_tampered'],
                         wall_s=round(end - t0, 2), startup_s=round(min(s for s, _ in turns) - t0, 2),
                         model_s=round(sum(m) * STEP, 2), tool_s=round(sum(t and not mm for t, mm in zip(tl, m)) * STEP, 2),
                         turns=main, tool_calls=len(tools),
                         cost_usd=next((e.get('total_cost_usd') for _, e in events(run, a['agent']) if e.get('type') == 'result'), None),
                         group_mem_peak_mb=round(int((run / 'meta' / 'memory.peak').read_text()) / 2**20), on_cpu_s=d.get('on_cpu_s'),
                         wait_busy_s=d.get('wait_busy_s'), wait_idle_s=d.get('wait_idle_s'), wait_disk_s=d.get('d_io_s')))
with open(HERE / 'agents.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)

f = lambda r, k: float(r[k] or 0)
local = lambda r: f(r, 'wall_s') - f(r, 'model_s')
by = defaultdict(list)
for r in rows:
    by[r['n_agents']].append(r)
med = lambda v, k: st.median(k(r) if callable(k) else f(r, k) for r in v)
b1 = by[1]
out = [f"{'N':>3}{'agents':>7}{'ok':>5}{'wall':>7}{'p90':>7}{'max':>7}{'x wall':>7}{'local':>7}{'x local':>8}{'startup':>8}"
       f"{'model':>7}{'tool':>7}{'onCPU':>7}{'waitCPU':>8}{'waitDisk':>9}{'turns':>6}{'agents/min':>11}{'memPeakMB':>10}{'$/agent':>8}"]
for N in sorted(by):
    v = by[N]
    walls = sorted(f(r, 'wall_s') for r in v)
    runs = sorted({r['run'] for r in v})
    thr = st.median(N / max(f(r, 'wall_s') for r in v if r['run'] == x) * 60 for x in runs)
    out.append(f"{N:>3}{len(v):>7}{sum(r['ok'] for r in v):>5}{st.median(walls):>7.1f}{walls[int(0.9 * (len(walls) - 1))]:>7.1f}"
               f"{walls[-1]:>7.1f}{st.median(walls) / med(b1, 'wall_s'):>7.2f}{med(v, local):>7.1f}{med(v, local) / med(b1, local):>8.2f}"
               f"{med(v, 'startup_s'):>8.1f}{med(v, 'model_s'):>7.1f}{med(v, 'tool_s'):>7.1f}{med(v, 'on_cpu_s'):>7.1f}"
               f"{med(v, 'wait_busy_s'):>8.1f}{med(v, 'wait_disk_s'):>9.1f}{med(v, 'turns'):>6.0f}{thr:>11.1f}"
               f"{med(v, 'group_mem_peak_mb'):>10.0f}{med(v, 'cost_usd'):>8.3f}")
(HERE / 'table.txt').write_text('\n'.join(out) + '\n')
print('\n'.join(out))
