#!/usr/bin/env python3
"""feedback campaign: per cell, what the agent did (from its own event log).

  OSNOISE_RUNS=<runs root> python feedback_cells.py     (tests also to rq5/feedback_tests.txt)
"""
import csv, json, os, re, statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(os.environ['OSNOISE_RUNS']) / 'feedback'
SPEED = re.compile(r'slow|optimi[sz]|faster|speed up|performance', re.I)
C = {r['run']: r for r in csv.DictReader(open(Path(__file__).parent / 'feedback' / 'counters.csv'))}
g = defaultdict(list)
for run, c in C.items():
    s = json.loads(c['spec'])
    tools = edits = after = out_tok = 0
    said = passed = False
    for line in open(ROOT / run / 'a1' / 'events.jsonl', encoding='utf-8'):
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

# RQ5 tests: exact one-sided rank-sum test (all splits of the 10 runs, mid-ranks for ties):
# p = share of splits whose rank sum for group a is at least the observed one.
from itertools import combinations


def rank_p(a, b):
    v = sorted(a + b)
    rank = {x: st.mean(i + 1 for i, y in enumerate(v) if y == x) for x in v}
    r = [rank[x] for x in a + b]
    obs = sum(r[:len(a)])
    sums = [sum(r[i] for i in c) for c in combinations(range(len(r)), len(a))]
    return sum(s >= obs - 1e-9 for s in sums) / len(sums)


tests = [('printed vs not printed, t3/t9 at 25%', ('t3 timed', '25000'), ('t9 quiet', '25000')),
         ('printed vs not printed, t3/t9 at 50%', ('t3 timed', '50000'), ('t9 quiet', '50000')),
         ('25% vs no limit, t3 printed', ('t3 timed', '25000'), ('t3 timed', 'max')),
         ('25% vs no limit, t9 not printed', ('t9 quiet', '25000'), ('t9 quiet', 'max')),
         ('printed vs not printed, t10 at 25%', ('t10 timed', '25000'), ('t10 quiet', '25000'))]
out = []
for model in ('haiku-5-5', 'opus-5-5'):
    for name, a, b in tests:
        A, B = g[(model, *a)], g[(model, *b)]
        out.append(f'{model:<10}{name:<38}' + ''.join(
            f"  {f}: {st.median(r[f] for r in A):.0f} vs {st.median(r[f] for r in B):.0f} p={rank_p([r[f] for r in A], [r[f] for r in B]):.3f}"
            for f in ('after', 'turns', 'out', 'wall')))
(Path(__file__).parent / 'rq5' / 'feedback_tests.txt').write_text('\n'.join(out) + '\n')
print('\n'.join(out))
