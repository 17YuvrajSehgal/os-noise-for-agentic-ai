#!/usr/bin/env python3
"""Review priority 4: limits change what the agent does. From each run's event log.

Part 1, printed run time (r_feedback, r_feedback_ref, first-pass feedback):
  per cell: turns, tool calls, edits, tool calls after the tests first print
  ALL PASS ("after"), runs whose text talks about speed, wall. Tests: one-sided
  exact rank-sum (as rq5), Holm over the tests of this file.
Part 2, silent test kill (r_cutout, t12): did the agent notice that the kernel
  killed its test? noticed = its final report names a kill, exit 137, OOM, the
  memory limit or the cgroup;
  test runs = Bash calls that run the tests; untee = a test run without tee.

  python rev/behaviour.py   -> rev/behaviour.txt
"""
import json, math, random, re, statistics as st, sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import FIRST, REV, lim_key   # noqa: E402

SPEED = re.compile(r'slow|optimi[sz]|faster|speed up|performance', re.I)
NOTICE = re.compile(r'killed|\b137\b|sigkill|\boom\b|out of memory|memory limit|memory\.max|cgroup', re.I)


def blocks(run):
    for line in open(run / 'a1' / 'events.jsonl', encoding='utf-8'):
        try:
            e = json.loads(json.loads(line)['line'])
        except (ValueError, KeyError):
            continue
        if isinstance(e, dict):
            for b in (e.get('message') or {}).get('content') or []:
                if isinstance(b, dict):
                    yield e.get('type'), b


def feedback(run):
    tools = edits = after = turns = 0
    said = passed = False
    for typ, b in blocks(run):
        if b.get('type') == 'tool_use':
            tools += 1
            after += passed
            edits += b.get('name') in ('Edit', 'Write', 'MultiEdit')
        elif b.get('type') == 'text' and SPEED.search(b.get('text', '')):
            said = True
        elif b.get('type') == 'tool_result':
            c = json.dumps(b.get('content'))
            if 'ALL PASS' in c and 'print(' not in c:
                passed = True
    return dict(tools=tools, edits=edits, after=after, said=said)


def cutout(run):
    tests = untee = 0
    noticed = False
    for typ, b in blocks(run):
        if b.get('type') == 'tool_use' and b.get('name') == 'Bash':
            cmd = (b.get('input') or {}).get('command', '')
            if 'run_tests' in cmd or 'tests.py' in cmd:
                tests += 1
                untee += 'run_tests' not in cmd and 'tee' not in cmd
    report = False
    for line in open(run / 'a1' / 'events.jsonl', encoding='utf-8'):   # the final report to the user
        try:
            e = json.loads(json.loads(line)['line'])
        except (ValueError, KeyError):
            continue
        if isinstance(e, dict) and e.get('type') == 'result':
            report = True
            noticed = bool(NOTICE.search(str(e.get('result', ''))))
    # the memory limit covers the agent too: the kernel may kill the agent instead of the test
    agent_killed = (run / 'a1' / 'exit_code').read_text().strip() == '137'
    return dict(tests=tests, untee=untee, noticed=noticed, report=report, agent_killed=agent_killed)


def cells(root, camp, fn):
    g = defaultdict(list)
    for sp in sorted((root / camp).glob('*/spec.json')):
        run = sp.parent
        s = json.loads(sp.read_text())
        if not (run / 'result.json').exists() or s.get('agent', 'claude') != 'claude':
            continue
        res = json.loads((run / 'result.json').read_text())
        variant = s['task'].replace('.sh', '').split('_')[0] + (f" {s['task_arg']}" if s.get('task_arg') else '')
        lim = json.loads(lim_key(s))
        lim_s = 'none' if not lim else ' '.join(f'{k}={v}' for k, v in lim.items())
        g[((s.get('model') or 'opus').replace('claude-', ''), variant, lim_s)].append(
            dict(fn(run), wall=res['wall_s'], ok=res['ok']))
    return g


def rank_p(a, b):
    """One-sided: are the values of a larger than those of b? Exact (or 200000 random splits)."""
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
        run = max(run, min(1, (len(ps) - k) * ps[i]))
        adj[i] = run
    return adj


fb = defaultdict(list)
for root, camp in ((FIRST, 'feedback'), (FIRST, 'feedback_extra'), (REV, 'r_feedback_ref'), (REV, 'r_feedback')):
    for k, v in cells(root, camp, feedback).items():
        fb[(('rev ' if root == REV else 'first ') + k[0],) + k[1:]] += v
Q = 'cpu_max=25000 100000'
lines = ['Part 1: printed run time', f"{'set model':16}{'task':18}{'limit':22}{'n':>3}{'tools':>7}{'edits':>7}"
                                     f"{'after':>7}{'max':>5}{'speed talk':>12}{'wall':>7}{'solved':>8}"]
for k in sorted(fb):
    v = fb[k]
    m = lambda f: st.median(r[f] for r in v)
    lines.append(f'{k[0]:16}{k[1]:18}{k[2][:21]:22}{len(v):>3}{m("tools"):>7.0f}{m("edits"):>7.0f}{m("after"):>7.0f}'
                 f'{max(r["after"] for r in v):>5}{sum(r["said"] for r in v):>8}/{len(v):<3}{m("wall"):>7.1f}'
                 f'{sum(r["ok"] for r in v):>5}/{len(v)}')

TESTS = [  # name, cell a, cell b: is a's "after" (and tools) larger than b's?
    ('Haiku, new disk: printed vs silent at 0.25 core', ('rev haiku-5-5', 't3', Q), ('rev haiku-5-5', 't9', Q)),
    ('Haiku, new disk: printed at 0.25 vs no limit', ('rev haiku-5-5', 't3', Q), ('rev haiku-5-5', 't3', 'none')),
    ('Haiku: printed slow (0.25) vs printed fixed fast number (0.25)', ('rev haiku-5-5', 't3', Q),
     ('rev haiku-5-5', 't11 const_fast', Q)),
    ('Haiku: fixed slow number, no limit vs printed, no limit', ('rev haiku-5-5', 't11 const_slow', 'none'),
     ('rev haiku-5-5', 't3', 'none')),
    ('Haiku: printed at 0.25 vs same + "run time is not a goal"', ('rev haiku-5-5', 't3', Q),
     ('rev haiku-5-5', 't11 instruct', Q)),
    ('Fable: printed vs silent at 0.25 core', ('rev fable-5-1', 't3', Q), ('rev fable-5-1', 't9', Q)),
]
res = []
for name, a, b in TESTS:
    A, B = fb.get(a, []), fb.get(b, [])
    if not A or not B:
        res.append((name, None))
        continue
    res.append((name, [(f, st.median(r[f] for r in A), st.median(r[f] for r in B), rank_p([r[f] for r in A], [r[f] for r in B]))
                       for f in ('after', 'tools', 'wall')], len(A), len(B)))
adj = holm([p for x in res if x[1] for *_, p in x[1]])
lines += ['', 'tests (one-sided: first cell larger; Holm over all tests here)']
i = 0
for x in res:
    if not x[1]:
        lines.append(f'  {x[0]}: missing cell')
        continue
    name, cs, na, nb = x
    lines.append(f'  {name}  n={na}/{nb}: ' + '  '.join(f'{f} {a:.0f} vs {b:.0f} p={p:.3f} (holm {adj[i + j]:.3f})'
                                                     for j, (f, a, b, p) in enumerate(cs)))
    i += len(cs)

cut = cells(REV, 'r_cutout', cutout)
lines += ['', 'Part 2: silent test kill (t12, test output piped through tee, 700 MB fixture)',
          '(solved: the code passes the check outside the limit; agent killed: exit 137, no final report;',
          ' report names a kill: of the reports given; without a limit these are warnings in advance)',
          f"{'model':12}{'limit':16}{'n':>3}{'solved':>8}{'agent killed':>14}{'report names kill':>19}"
          f"{'test runs med (max)':>21}{'runs w/o tee':>14}{'wall':>7}"]
for k in sorted(cut):
    v = cut[k]
    rep = [r for r in v if r['report']]
    lines.append(f'{k[0]:12}{k[2][:15]:16}{len(v):>3}{sum(r["ok"] for r in v):>5}/{len(v):<3}'
                 f'{sum(r["agent_killed"] for r in v):>10}/{len(v):<3}{sum(r["noticed"] for r in rep):>15}/{len(rep):<3}'
                 f'{st.median(r["tests"] for r in v):>14.0f} ({max(r["tests"] for r in v):>2}){sum(r["untee"] > 0 for r in v):>10}/{len(v):<3}'
                 f'{st.median(r["wall"] for r in v):>7.1f}')
(HERE / 'behaviour.txt').write_text('\n'.join(lines) + '\n')
print('\n'.join(lines))
