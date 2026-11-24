#!/usr/bin/env python3
"""feedback + feedback_extra campaigns: per cell, what the agent did (from its own event log).

  OSNOISE_RUNS=<runs root> python feedback_cells.py     (tests also to rq5/feedback_tests.txt)
"""
import csv, json, os, re, statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(os.environ['OSNOISE_RUNS'])
CAMPS = ('feedback', 'feedback_extra')   # extra: 10 more Haiku runs of t3 and t9 at 25%
SPEED = re.compile(r'slow|optimi[sz]|faster|speed up|performance', re.I)
C = {r['run']: dict(r, camp=c) for c in CAMPS for r in csv.DictReader(open(Path(__file__).parent / c / 'counters.csv'))}
g = defaultdict(list)
for run, c in C.items():
    s = json.loads(c['spec'])
    tools = edits = after = out_tok = 0
    said = passed = False
    for line in open(ROOT / c['camp'] / run / 'a1' / 'events.jsonl', encoding='utf-8'):
        try: e = json.loads(json.loads(line)['line'])
        except (ValueError, KeyError): continue
        out_tok = e.get('usage', {}).get('output_tokens', out_tok) if 'total_cost_usd' in e else out_tok
        for b in (e.get('message') or {}).get('content') or []:
            if not isinstance(b, dict): continue
            if b.get('type') == 'tool_use':
                tools += 1; after += passed
                edits += b['name'] in ('Edit', 'Write', 'MultiEdit')
            elif b.get('type') == 'text' and SPEED.search(b['text']):
                said = True
            elif b.get('type') == 'tool_result' and 'ALL PASS' in json.dumps(b.get('content')) and 'print(' not in json.dumps(b.get('content')):
                passed = True
    timed = s['task_arg'] or ('timed' if s['task'].startswith('t3') else 'quiet')
    g[(s['model'].replace('claude-', ''), s['task'][:3].strip('_') + ' ' + timed, s['limits']['cpu_max'].split()[0])].append(
        dict(turns=float(c['turns']), cost=float(c['cost_usd']), cpu=float(c['cpu_s']), wall=float(c['wall_s']),
             api=float(c['api_s']), tools=tools, edits=edits, after=after, said=said, out=out_tok))
print(f"{'model':<10}{'task':<10}{'cpu':>6} | turns med (min-max) | tools | edits | tools after 1st pass | out_tok | cost$ | cpu_s | api_s | wall_s | runs that talk about speed")
for k in sorted(g, key=lambda k: (k[0], k[1], -1 if k[2] == 'max' else -int(k[2]))):
    v = g[k]; m = lambda f: st.median(r[f] for r in v)
    print(f"{k[0]:<10}{k[1]:<10}{k[2]:>6} | {m('turns'):4.0f} ({min(r['turns'] for r in v):2.0f}-{max(r['turns'] for r in v):2.0f})"
          f"{'':8}| {m('tools'):5.0f} | {m('edits'):5.0f} | {m('after'):3.0f} (max {max(r['after'] for r in v):2.0f}){'':8}| {m('out'):7.0f} | {m('cost'):.3f} | {m('cpu'):5.1f} | {m('api'):5.1f} | {m('wall'):6.1f} | {sum(r['said'] for r in v)}/{len(v)}")

# RQ5 tests: one-sided rank-sum test (mid-ranks for ties): p = share of splits of the runs
# whose rank sum for group a is at least the observed one. All splits when there are at most
# 1e5, else 200000 random splits (seed 7). Holm correction over the tests of one model.
import math, random
from itertools import combinations


def rank_p(a, b):
    v = sorted(a + b)
    rank = {x: st.mean(i + 1 for i, y in enumerate(v) if y == x) for x in v}
    r = [rank[x] for x in a + b]
    obs = sum(r[:len(a)])
    if math.comb(len(r), len(a)) <= 1e5:
        sums = [sum(r[i] for i in c) for c in combinations(range(len(r)), len(a))]
    else:
        rng = random.Random(7)
        sums = [sum(rng.sample(r, len(a))) for _ in range(200000)]
    return sum(s >= obs - 1e-9 for s in sums) / len(sums)


def holm(ps):
    order, adj, run = sorted(range(len(ps)), key=ps.__getitem__), [0] * len(ps), 0
    for k, i in enumerate(order):
        run = max(run, min(1, (len(ps) - k) * ps[i])); adj[i] = run
    return adj


tests = [('printed vs not printed, t3/t9 at 25%', ('t3 timed', '25000'), ('t9 quiet', '25000')),
         ('printed vs not printed, t3/t9 at 50%', ('t3 timed', '50000'), ('t9 quiet', '50000')),
         ('25% vs no limit, t3 printed', ('t3 timed', '25000'), ('t3 timed', 'max')),
         ('25% vs no limit, t9 not printed', ('t9 quiet', '25000'), ('t9 quiet', 'max')),
         ('printed vs not printed, t10 at 25%', ('t10 timed', '25000'), ('t10 quiet', '25000'))]
out = []
for model in ('haiku-5-5', 'opus-5-5'):
    rows = []
    for name, a, b in tests:
        A, B = g[(model, *a)], g[(model, *b)]
        rows.append((f'{model:<10}{name:<38} n={len(A)}/{len(B)}', [(f, st.median(r[f] for r in A), st.median(r[f] for r in B),
                     rank_p([r[f] for r in A], [r[f] for r in B])) for f in ('after', 'turns', 'out', 'wall')]))
    adj = holm([p for _, cells in rows for *_, p in cells])
    for i, (head, cells) in enumerate(rows):
        out.append(head + ''.join(f"  {f}: {x:.0f} vs {y:.0f} p={p:.3f} (holm {adj[4 * i + j]:.3f})"
                                  for j, (f, x, y, p) in enumerate(cells)))
(Path(__file__).parent / 'rq5' / 'feedback_tests.txt').write_text('\n'.join(out) + '\n')
print('\n'.join(out))
