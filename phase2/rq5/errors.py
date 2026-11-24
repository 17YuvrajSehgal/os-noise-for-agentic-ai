#!/usr/bin/env python3
"""RQ5: what the agent does when the system returns an error.

  OSNOISE_RUNS=<runs root> python rq5/errors.py    (writes rq5/errors.csv, rq5/errors.txt)

Runs: memory_cliff (a tool that needs 512 MB, memory.max 1024M down to 512M)
and pids + pids_mid (process limit), Claude only. Per run, from the agent's
event log:
  error_seen  a tool result shows the system error (memory: a "Killed" line
              or exit 137 / out of memory; process limit: fork "Resource
              temporarily unavailable")
  ended       the log has the agent's final result (no = the agent itself died)
  mentions    the final message names the cause (memory / killed / OOM, or
              fork / process / resource)
  after       tool calls after the first error
"""
import csv, json, os, re, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'rq1'))
os.environ.setdefault('OSNOISE_RUNS', 'C:/workplace/microservice-trace-dataset/agentic-runs-phase2/runs')
from split import events, ROOT  # noqa: E402

ERR = {'memory': re.compile(r'\bKilled\b|exit=137|exit code 137|status 137|[Oo]ut of memory|MemoryError'),
       'pids': re.compile(r'Resource temporarily unavailable|fork: retry|can.t start new thread|BlockingIOError')}
NAMES = {'memory': re.compile(r'memory|OOM|out-of-memory|killed', re.I),
         'pids': re.compile(r'fork|process(es)? limit|resource temporarily|pids|too many processes', re.I)}


def text(c):
    return c if isinstance(c, str) else json.dumps(c)


rows = []
for kind, camps in (('memory', ['memory_cliff']), ('pids', ['pids', 'pids_mid'])):
    for camp in camps:
        for run in sorted((ROOT / camp).glob(f'{camp}_claude_*_r*')):
            level = run.name.split('_claude_')[1].rsplit('_r', 1)[0]
            res = json.loads((run / 'result.json').read_text())
            calls, first_err, final = 0, None, None
            for _, e in events(run):
                if e.get('type') == 'result':
                    final = str(e.get('result') or '')
                for b in (e.get('message') or {}).get('content') or []:
                    if not isinstance(b, dict):
                        continue
                    if b.get('type') == 'tool_use':
                        calls += 1
                    elif b.get('type') == 'tool_result' and first_err is None and ERR[kind].search(text(b.get('content'))):
                        first_err = calls
            exit_code = (run / 'a1' / 'exit_code').read_text().strip() if (run / 'a1' / 'exit_code').exists() else ''
            rows.append(dict(kind=kind, campaign=camp, run=run.name, level=level, solved=res.get('ok'),
                             agent_exit=exit_code, error_seen=first_err is not None, ended=final is not None,
                             mentions=bool(final and NAMES[kind].search(final)),
                             after=calls - first_err if first_err is not None else '', tool_calls=calls,
                             final=(final or '')[:300].replace('\n', ' ')))
with open(HERE / 'errors.csv', 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)

g = defaultdict(list)
for r in rows:
    g[(r['kind'], r['level'])].append(r)
key = lambda k: (k[0], -int(re.sub(r'\D', '', k[1]) or 10 ** 6))
out = [f"{'kind':<8}{'level':<8}{'runs':>5}{'solved':>7}{'error seen':>11}{'agent died':>11}{'names cause':>12}"
       f"{'calls after':>12}  agent exit codes"]
for k in sorted(g, key=key):
    v = g[k]
    seen = [r for r in v if r['error_seen']]
    after = sorted(r['after'] for r in seen)
    out.append(f"{k[0]:<8}{k[1]:<8}{len(v):>5}{sum(r['solved'] for r in v):>7}{len(seen):>11}"
               f"{sum(not r['ended'] for r in v):>11}{sum(r['mentions'] for r in seen):>9}/{len(seen):<2}"
               f"{str(after) if after else '':>12}  {sorted({r['agent_exit'] for r in v})}")
(HERE / 'errors.txt').write_text('\n'.join(out) + '\n', encoding='utf-8')
print('\n'.join(out))
