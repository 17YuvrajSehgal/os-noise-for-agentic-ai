#!/usr/bin/env python3
"""Step 1 (P3, P4, P5): the shape of a run.

Reads results/parsed_all.jsonl (from parse_all.py) and writes one row per run
to results/step1_runs.csv and one row per model turn to
results/step1_turns.csv.

Definitions
- agent process: the process in the agent subtree with the most HTTPS exchanges.
- model turn: an exchange of the agent process with a request of at least
  REQ_MIN bytes whose response is still arriving DUR_MIN seconds after the
  request. (Other exchanges are start-up configuration calls and telemetry
  uploads: small or answered at once.)
- tool process: a process started after the agent process that has exited
  by the end of the last model response. The launcher chain and helpers that
  outlive the last response count as the agent.
- wall clock = start anchor to end anchor, split in STEP-second steps into:
  startup (before the first model request), shutdown (after the last model
  response), and in between: model+tool, model only, tool only, agent only.
"""
import csv, json, statistics, sys
from pathlib import Path

REQ_MIN = 2000
DUR_MIN = 0.7
STEP = 0.01          # must equal exchanges.BIN
DAY = 86400.0
HERE = Path(__file__).resolve().parent


def rel(anchor, t0):
    d = (anchor['realtime'] % DAY - t0) % DAY
    return d if d < DAY / 2 else d - DAY


def covered(intervals, n, t_start):
    """bool list over steps: is step i inside any interval?"""
    out = [False] * n
    for a, b in intervals:
        i0 = max(0, int((a - t_start) / STEP))
        i1 = min(n, int((b - t_start) / STEP) + 1)
        for i in range(i0, i1):
            out[i] = True
    return out


def roles(r):
    """Who is who in a parsed run: the agent process, its model turns, its
    tool processes, and the run's start and end on the trace clock."""
    t_start, t_end = rel(r['anchors'][0], r['t0']), rel(r['anchors'][-1], r['t0'])
    xs = [x for x in r['exchanges'] if x['dport'] == 443]
    by_pid = {}
    for x in xs:
        by_pid[x['pid']] = by_pid.get(x['pid'], 0) + 1
    agent = max(by_pid, key=by_pid.get) if by_pid else None
    turns = [x for x in xs if x['pid'] == agent and x['out_bytes'] >= REQ_MIN
             and x['t_last_in'] - x['t_req'] >= DUR_MIN]
    procs = {int(p): v for p, v in r['procs'].items()}
    tools = set()
    if turns:
        last = max(x['t_last_in'] for x in turns)
        # not tools: the launcher chain (started before the agent) and helpers
        # the agent keeps for the session (e.g. codex-code-mode-host). A tool has
        # finished before the last model response ends; a helper is still alive.
        tools = {p for p in procs if p != agent and procs[p][0] > procs[agent][0]
                 and procs[p][1] is not None and procs[p][1] <= last}
    return dict(t_start=t_start, t_end=t_end, xs=xs, agent=agent, turns=turns,
                procs=procs, tools=tools)


def analyze(r):
    gt = r['ground_truth']
    ro = roles(r)
    t_start, t_end, xs, agent, turns = ro['t_start'], ro['t_end'], ro['xs'], ro['agent'], ro['turns']
    procs, tools = ro['procs'], ro['tools']
    wall = t_end - t_start
    row = dict(family=r['family'], run=r['run'], agent=gt.get('agent', 'claude'),
               task=gt['task'], cpu_max=gt['cpu_max'], mem_limit=gt.get('mem_limit', ''),
               io_limit=gt.get('io_limit', ''), task_arg=gt.get('task_arg', ''),
               wall_s=round(wall, 2), n_turns=len(turns), n_exchanges=len(xs),
               n_connects=sum(1 for c in r['connects'] if c['dport'] == 443))
    if not turns:
        return row, []
    first, last = turns[0]['t_req'], max(x['t_last_in'] for x in turns)
    n = int(wall / STEP) + 1
    model = covered([(x['t_req'], x['t_last_in']) for x in turns], n, t_start)
    tool = covered([(procs[p][0], procs[p][1] if procs[p][1] is not None else t_end)
                    for p in tools], n, t_start)
    cat = {}        # category -> [wall_s, agent_cpu_s, tool_cpu_s, ready_s]
    cpu_bins = {}   # step -> [agent_on, tool_on, ready]
    for p, bins in r['cpu'].items():
        col = 1 if int(p) in tools else 0
        for i, on, rdy in bins:
            j = int(round((i * STEP - t_start) / STEP))
            if 0 <= j < n:
                v = cpu_bins.setdefault(j, [0.0, 0.0, 0.0])
                v[col] += on
                v[2] += rdy
    for j in range(n):
        t = t_start + j * STEP
        if t < first:
            c = 'startup'
        elif t > last:
            c = 'shutdown'
        elif model[j] and tool[j]:
            c = 'model_tool'
        elif model[j]:
            c = 'model_only'
        elif tool[j]:
            c = 'tool_only'
        else:
            c = 'agent_only'
        v = cat.setdefault(c, [0.0, 0.0, 0.0, 0.0])
        v[0] += STEP
        b = cpu_bins.get(j)
        if b:
            v[1] += b[0]; v[2] += b[1]; v[3] += b[2]
    for c in ('startup', 'model_only', 'model_tool', 'tool_only', 'agent_only', 'shutdown'):
        v = cat.get(c, [0, 0, 0, 0])
        row[f'{c}_s'] = round(v[0], 2)
        row[f'{c}_agent_cpu'] = round(v[1], 3)
        row[f'{c}_tool_cpu'] = round(v[2], 3)
        row[f'{c}_ready'] = round(v[3], 3)
    row['model_pct'] = round(100 * sum(model) * STEP / wall, 1)
    row['n_tool_procs'] = len(tools)
    row['agent_cpu_s'] = round(sum(v[0] for v in cpu_bins.values()), 2)
    row['tool_cpu_s'] = round(sum(v[1] for v in cpu_bins.values()), 2)
    row['ttfb_med'] = round(statistics.median(x['t_first_in'] - x['t_req_end'] for x in turns), 2)
    row['turn_dur_med'] = round(statistics.median(x['t_last_in'] - x['t_req'] for x in turns), 2)
    row['out_kb_total'] = round(sum(x['out_bytes'] for x in turns) / 1024, 1)
    row['in_kb_total'] = round(sum(x['in_bytes'] for x in turns) / 1024, 1)
    trows = []
    for k, x in enumerate(turns):
        nxt = turns[k + 1]['t_req'] if k + 1 < len(turns) else None
        trows.append(dict(family=r['family'], run=r['run'], agent=row['agent'], turn=k + 1,
                          t_req=round(x['t_req'] - t_start, 2), out_bytes=x['out_bytes'],
                          ttfb_s=round(x['t_first_in'] - x['t_req_end'], 3),
                          stream_s=round(x['t_last_in'] - x['t_first_in'], 3),
                          in_bytes=x['in_bytes'], n_reads=x['n_reads'],
                          gap_to_next_s=round(nxt - x['t_last_in'], 3) if nxt is not None else ''))
    return row, trows


if __name__ == '__main__':
    rows, turns = [], []
    for line in open(HERE / 'results/parsed_all.jsonl'):
        row, t = analyze(json.loads(line))
        rows.append(row)
        turns += t
    keys = max(rows, key=len).keys()
    with open(HERE / 'results/step1_runs.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(keys), restval='')
        w.writeheader(); w.writerows(rows)
    with open(HERE / 'results/step1_turns.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(turns[0]))
        w.writeheader(); w.writerows(turns)
    print(len(rows), 'runs,', len(turns), 'turns;', sum(1 for r in rows if not r['n_turns']), 'runs with no model turn')
