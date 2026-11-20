#!/usr/bin/env python3
"""Review 2: do the two fixes keep the OOM killer away from the agent?

t12 (700 MB test) under memory.max 768M: r_cutout (no fix) against r_oomfix
(tool_guard oom_adj: tool shells raise their oom_score_adj; tool_guard cgroup:
tool shells move to a child cgroup with memory.max 448M).
Per run: agent killed (exit 137), solved, kernel OOM kills in the agent's group
(memory.events, which counts the child cgroups too), tool shells that the guard
reached, the agent's final report names a kill, test runs without tee, wall.

  python rev/oomfix.py -> rev/oomfix.txt
"""
import json, re, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import REV, wilson   # noqa: E402

NOTICE = re.compile(r'killed|\b137\b|sigkill|\boom\b|out of memory|memory limit|memory\.max|cgroup', re.I)


def events(run):
    """(final report text or None, test runs, test runs without tee)"""
    report, tests, untee = None, 0, 0
    for line in open(run / 'a1' / 'events.jsonl', encoding='utf-8'):
        try:
            e = json.loads(json.loads(line)['line'])
        except (ValueError, KeyError):
            continue
        if not isinstance(e, dict):
            continue
        if e.get('type') == 'result':
            report = str(e.get('result', ''))
        for b in (e.get('message') or {}).get('content') or []:
            if isinstance(b, dict) and b.get('type') == 'tool_use' and b.get('name') == 'Bash':
                cmd = (b.get('input') or {}).get('command', '')
                if 'run_tests' in cmd or 'tests.py' in cmd:
                    tests += 1
                    untee += 'run_tests' not in cmd and 'tee' not in cmd
    return report, tests, untee


def oom_kills(run):
    f = run / 'meta' / 'after' / 'a1' / 'memory.events'
    if not f.exists():
        return 0
    return int(dict(l.split() for l in f.read_text().split('\n') if l.strip()).get('oom_kill', 0))


g = defaultdict(list)
for camp in ('r_cutout', 'r_oomfix'):
    for sp in sorted((REV / camp).glob('*/spec.json')):
        run, s = sp.parent, json.loads(sp.read_text())
        if not (run / 'result.json').exists() or (s.get('limits') or {}).get('memory_max') != '768M':
            continue
        res = json.loads((run / 'result.json').read_text())
        report, tests, untee = events(run)
        guard = run / 'meta' / 'tool_guard.log'
        g[(s.get('tool_guard') or 'none', (s.get('model') or '').replace('claude-', ''))].append(dict(
            killed=(run / 'a1' / 'exit_code').read_text().strip() == '137', ok=res['ok'], wall=res['wall_s'],
            ooms=oom_kills(run), guarded=len(guard.read_text().split()) if guard.exists() else 0,
            report=report, noticed=bool(report and NOTICE.search(report)), tests=tests, untee=untee > 0))

lines = ['t12, 700 MB test, memory.max 768M',
         f"{'fix':<9}{'model':<11}{'n':>3}{'agent killed [95%]':>21}{'solved':>8}{'OOM kills':>11}"
         f"{'guarded shells':>16}{'report names kill':>19}{'reran w/o tee':>15}{'wall s':>8}"]
tot = defaultdict(lambda: [0, 0])
for k in sorted(g, key=lambda k: (['none', 'oom_adj', 'cgroup'].index(k[0]), k[1])):
    v = g[k]
    kl = sum(r['killed'] for r in v)
    lo, hi = wilson(kl, len(v))
    rep = [r for r in v if r['report'] is not None]
    tot[k[0]][0] += kl
    tot[k[0]][1] += len(v)
    lines.append(f'{k[0]:<9}{k[1]:<11}{len(v):>3}{kl:>6}/{len(v):<3}[{lo:.2f}-{hi:.2f}]{sum(r["ok"] for r in v):>5}/{len(v):<3}'
                 f'{st.median(r["ooms"] for r in v):>8.0f}{st.median(r["guarded"] for r in v):>14.0f}'
                 f'{sum(r["noticed"] for r in rep):>14}/{len(rep):<4}{sum(r["untee"] for r in v):>11}/{len(v):<3}'
                 f'{st.median(r["wall"] for r in v):>8.1f}')
lines.append('')
for fix, (kl, n) in tot.items():
    lo, hi = wilson(kl, n)
    lines.append(f'{fix:<9} agent killed in {kl} of {n} runs [95% Wilson {lo:.2f}-{hi:.2f}]')
# one-sided Fisher exact test: is the kill rate lower with each fix than with none?
from math import comb
def fisher(a, n1, b, n2):
    """P(X <= a) for X kills in group 1 given the total, hypergeometric."""
    k, n = a + b, n1 + n2
    return sum(comb(k, i) * comb(n - k, n1 - i) for i in range(0, a + 1)) / comb(n, n1)
for fix in ('oom_adj', 'cgroup'):
    if fix in tot:
        lines.append(f'{fix}: Fisher exact, one-sided, fewer agent kills than no fix: '
                     f'p={fisher(tot[fix][0], tot[fix][1], tot["none"][0], tot["none"][1]):.5f}')
(HERE / 'oomfix.txt').write_text('\n'.join(lines) + '\n')
print('\n'.join(lines))
