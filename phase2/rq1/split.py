#!/usr/bin/env python3
"""RQ1 (and the base of RQ2-RQ5): where each run's wall-clock time goes,
from the agent's own event log, plus CPU and waiting times from the trace.

  OSNOISE_RUNS=<runs root> python split.py [<campaign> ...]   (default: all in phase2/)

Model turns and tool calls come from a1/events.jsonl, which time-stamps every
line the agent prints. The agent prints each content block of a model answer
when that block is complete, and a tool result when the tool is done. So:
  model turn  = from the last event before the answer's first block (session
                start or a tool result of the same agent) to its last block
  tool call   = from the tool_use block to its tool_result
This covers tools that run inside the agent process (Read, Edit, Grep), which
the trace sees as the agent's own work, and sub-agents (their events carry
parent_tool_use_id). Wall time (start to end anchor) is split in 10 ms steps
into startup, model+tool, model only, tool only, agent only, shutdown.

Writes phase2/rq1/runs.csv: one row per single-agent run, with the split, the
turn count, the trace CPU (agent and tool processes, step1_runs.csv) and the
waits of the agent's process tree (diag_all.jsonl).
"""
import csv, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
P2 = HERE.parent
ROOT = Path(os.environ['OSNOISE_RUNS'])
STEP = 0.01
CATS = ('startup', 'model_tool', 'model_only', 'tool_only', 'agent_only', 'shutdown')


def events(run, agent='a1'):
    for line in open(run / agent / 'events.jsonl', encoding='utf-8'):
        try:
            w = json.loads(line)
            e = json.loads(w['line'])
        except (ValueError, KeyError):
            continue
        if isinstance(e, dict):
            yield w['realtime'], e


def intervals(run, agent='a1'):
    """-> model turns [(start, end)], tool calls [(start, end)], first event time,
    end of the agent's final result, number of main-agent turns."""
    boundary = {}                   # parent id (None = main agent) -> time of last request trigger
    msgs = {}                       # message id -> [start, first block, last block, parent]
    uses, tools = {}, []
    t_first = t_result = None
    for t, e in events(run, agent):
        t_first = t if t_first is None else t_first
        typ, parent = e.get('type'), e.get('parent_tool_use_id')
        if typ == 'system' and e.get('subtype') == 'init':
            boundary[None] = t
        elif typ == 'assistant':
            m = e.get('message') or {}
            mid = m.get('id')
            if mid not in msgs:
                msgs[mid] = [boundary.get(parent, t), t, t, parent]
            msgs[mid][2] = t
            for b in m.get('content') or []:
                if isinstance(b, dict) and b.get('type') == 'tool_use':
                    uses[b['id']] = t
                    if b.get('name') in ('Task', 'Agent'):       # a sub-agent's first request
                        boundary[b['id']] = t
        elif typ == 'user':
            for b in (e.get('message') or {}).get('content') or []:
                if isinstance(b, dict) and b.get('type') == 'tool_result' and b.get('tool_use_id') in uses:
                    tools.append((uses.pop(b['tool_use_id']), t))
            boundary[parent] = t
        elif typ == 'result':
            t_result = t
    turns = [(s, e) for s, _, e, _ in msgs.values()]
    main = sum(1 for v in msgs.values() if v[3] is None)
    return turns, tools, t_first, t_result, main


def split(run):
    anchors = [json.loads(l) for l in open(run / 'meta' / 'clock_anchors.jsonl')]
    t0, t1 = anchors[0]['realtime'], anchors[-1]['realtime']
    turns, tools, t_first, t_result, main = intervals(run)
    n = int((t1 - t0) / STEP) + 1
    def cover(iv):
        out = bytearray(n)
        for a, b in iv:
            for i in range(max(0, int((a - t0) / STEP)), min(n, int((b - t0) / STEP) + 1)):
                out[i] = 1
        return out
    m, tl = cover(turns), cover(tools)
    first = min((a for a, _ in turns), default=t1)
    last = max([b for _, b in turns + tools] + ([t_result] if t_result else []), default=t1)
    acc = dict.fromkeys(CATS, 0.0)
    for i in range(n):
        t = t0 + i * STEP
        c = ('startup' if t < first else 'shutdown' if t > last else
             'model_tool' if m[i] and tl[i] else 'model_only' if m[i] else
             'tool_only' if tl[i] else 'agent_only')
        acc[c] += STEP
    row = {f'{c}_s': round(v, 2) for c, v in acc.items()}
    row.update(wall_s=round(t1 - t0, 2), turns_log=main, turns_all=len(turns), tool_calls=len(tools),
               model_s=round(sum(m) * STEP, 2), tool_s=round(sum(tl) * STEP, 2),
               first_event_s=round(t_first - t0, 2) if t_first else None)
    return row


def spec_cols(s):
    lim = {k: v for k, v in (s.get('limits') or {}).items() if v not in ('max', '', None)}
    return dict(model=s.get('model'), task=s['task'].replace('.sh', ''), task_arg=s.get('task_arg', ''),
                runtime=s.get('runtime', 'host'), limits=json.dumps(lim, sort_keys=True) if lim else '',
                net=json.dumps(s['net']) if s.get('net') is not None else '',
                neighbour=json.dumps(s['neighbour']) if s.get('neighbour') else '',
                unlimited=not lim and s.get('net') is None and not s.get('neighbour'))


if __name__ == '__main__':
    camps = sys.argv[1:] or sorted(p.parent.name for p in P2.glob('*/diag_all.jsonl'))
    rows = []
    for c in camps:
        diag = {r['run']: r for r in map(json.loads, open(P2 / c / 'diag_all.jsonl'))}
        s1 = {r['run']: r for r in csv.DictReader(open(P2 / c / 'step1_runs.csv'))}
        for run in sorted((ROOT / c).glob('*/spec.json')):
            run = run.parent
            s = json.loads((run / 'spec.json').read_text())
            if s.get('agents', 1) != 1 or not (run / 'a1' / 'events.jsonl').exists():
                continue
            res = json.loads((run / 'result.json').read_text())
            d, t = diag.get(run.name, {}), s1.get(run.name, {})
            row = dict(campaign=c, run=run.name, ok=res['ok'], **spec_cols(s), **split(run),
                       turns_net=t.get('n_turns'), agent_cpu_s=t.get('agent_cpu_s'), tool_cpu_s=t.get('tool_cpu_s'),
                       on_cpu_s=d.get('on_cpu_s'), wait_cpu_quota_s=d.get('wait_idle_s'),
                       wait_cpu_busy_s=d.get('wait_busy_s'), wait_disk_s=d.get('d_io_s'),
                       wait_d_other_s=d.get('d_noio_s'), reclaim_s=d.get('reclaim_s'), reclaim_n=d.get('reclaim_n'))
            rows.append(row)
        print(c, sum(r['campaign'] == c for r in rows), 'runs', flush=True)
    with open(HERE / 'runs.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print(len(rows), 'runs ->', HERE / 'runs.csv')
