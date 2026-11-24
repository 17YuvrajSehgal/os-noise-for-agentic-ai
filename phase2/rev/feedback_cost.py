#!/usr/bin/env python3
"""Review 2: API cost and output tokens of the printed-run-time cells (set 2), from each
run's event log.   python rev/feedback_cost.py -> rev/feedback_cost.txt"""
import json, re, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import REV   # noqa: E402

USE = re.compile(r'\\*"(outputTokens|costUSD)\\*":([\d.]+)')
g = defaultdict(list)
for camp in ('r_feedback', 'r_feedback_ref'):
    for sp in (REV / camp).glob('*/spec.json'):
        s = json.loads(sp.read_text())
        ev = sp.parent / 'a1' / 'events.jsonl'
        if not ev.exists():
            continue
        tot = defaultdict(float)
        for line in ev.open(errors='ignore'):
            if 'model_usage_since_last_result' in line:
                for k, v in USE.findall(line):
                    tot[k] += float(v)
        lim = (s.get('limits') or {}).get('cpu_max') or 'max'
        task = s['task'].split('_')[0] + (' ' + str(s['task_arg']) if s.get('task_arg') else '')
        g[((s.get('model') or '').replace('claude-', ''), task, '0.25 core' if lim.startswith('25000') else 'no limit')].append(tot)
lines = [f"{'model':<12}{'task':<18}{'limit':<11}{'n':>3}{'cost $ (median)':>17}{'output tokens':>15}"]
for k, v in sorted(g.items()):
    lines.append(f'{k[0]:<12}{k[1]:<18}{k[2]:<11}{len(v):>3}{st.median(t["costUSD"] for t in v):>17.4f}'
                 f'{st.median(t["outputTokens"] for t in v):>15.0f}')
(HERE / 'feedback_cost.txt').write_text('\n'.join(lines) + '\n')
print('\n'.join(lines))
