#!/usr/bin/env python3
"""RQ3, like with like: the time of the same shell command in different
settings. The agent picks different tests per run, so per-run tool time mixes
the setting's effect with the agent's choice. Here every Bash tool call of the
real-task runs is keyed by (task, its test runs: the test-runner part of the
command, without pipes or paths). A key run in the no-limit cell and in
another setting gives a ratio of medians; the summary uses keys with at least
2 runs on both sides.

  OSNOISE_RUNS=<runs root> python rq3/commands.py      (writes rq3/commands.txt)
"""
import json, os, re, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'rq1'))
os.environ.setdefault('OSNOISE_RUNS', 'C:/workplace/microservice-trace-dataset/agentic-runs-phase2/runs')
from split import events, ROOT  # noqa: E402

SETTING = {'{}': 'none', '{"cpu_max": "200000 100000", "memory_max": "8G"}': '2 CPU / 8 GB',
           '{"cpu_max": "200000 100000", "memory_max": "512M"}': '2 CPU / 512 MB',
           '{"cpu_max": "100000 100000", "memory_max": "512M"}': '1 CPU / 512 MB',
           '{"cpu_max": "25000 100000", "memory_max": "512M"}': '0.25 CPU / 512 MB'}
NAMES = ['host', 'none', '2 CPU / 8 GB', '2 CPU / 512 MB', '1 CPU / 512 MB', '0.25 CPU / 512 MB']

TEST = re.compile(r'(pytest|bin/test|runtests\.py)')


def key(cmd):
    """The test runs of a shell command, without pipes, redirects and paths, in order;
    None if the command runs no test or also runs other Python code."""
    tests = []
    for seg in re.split(r'&&|;|\n', cmd):
        seg = re.sub(r'\d?>&\d|\|.*', '', seg).replace('../', '').strip()   # drop 2>&1 and everything after a pipe
        if 'python' in seg and TEST.search(seg):
            tests.append(' '.join(seg.split()))
        elif 'python' in seg:
            return None
    return ' ; '.join(tests) or None


calls = defaultdict(lambda: defaultdict(list))        # (task, test runs) -> setting -> [seconds]
for camp in ('real', 'real_host', 'real_quarter'):
    for run in sorted((ROOT / camp).glob(f'{camp}_*_r*')):
        spec = json.loads((run / 'spec.json').read_text())
        name = 'host' if camp == 'real_host' else SETTING[json.dumps(spec.get('limits') or {})]
        task = spec['task_arg'].split('__')[1]
        uses = {}
        for t, e in events(run):
            for b in (e.get('message') or {}).get('content') or []:
                if not isinstance(b, dict):
                    continue
                if b.get('type') == 'tool_use' and b.get('name') == 'Bash' and e.get('type') == 'assistant':
                    uses[b['id']] = (t, key(b['input'].get('command', '')))
                elif b.get('type') == 'tool_result' and b.get('tool_use_id') in uses:
                    t0, cmd = uses.pop(b['tool_use_id'])
                    if cmd:
                        calls[(task, cmd)][name].append(t - t0)

out = [f"{'task':<15}{'n per setting (' + ', '.join(NAMES) + ')':<46}{'none s':>8}"
       + ''.join(f'{n:>19}' for n in NAMES if n != 'none') + '  command']
ratios = defaultdict(list)
for (task, cmd), by in sorted(calls.items(), key=lambda kv: (kv[0][0], -sum(map(len, kv[1].values())))):
    if not by.get("none") or len(by) < 2 or st.median(by['none']) < 0.5:
        continue                       # needs a no-limit reference of at least 0.5 s
    base = st.median(by['none'])
    cells = []
    for n in NAMES:
        if n == 'none':
            continue
        if by.get(n):
            r = st.median(by[n]) / base
            if len(by[n]) >= 2 and len(by['none']) >= 2:
                ratios[n].append(r)
            cells.append(f'{r:>19.2f}')
        else:
            cells.append(f'{"-":>19}')
    out.append(f"{task:<15}{'/'.join(str(len(by.get(n, []))) for n in NAMES):<44}{base:>8.1f}" + ''.join(cells)
               + '  ' + cmd[:90])
out.append('')
for n in NAMES:
    if ratios[n]:
        out.append(f'{n}: {len(ratios[n])} commands with 2+ runs each side, median ratio to no limit {st.median(ratios[n]):.2f} '
                   f'(range {min(ratios[n]):.2f}-{max(ratios[n]):.2f})')
(HERE / 'commands.txt').write_text('\n'.join(out) + '\n', encoding='utf-8')
print('\n'.join(out))
