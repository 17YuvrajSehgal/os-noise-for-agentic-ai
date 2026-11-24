#!/usr/bin/env python3
"""How much of the Claude account's usage is left, from one tiny Haiku call.

  python3 usage.py              # prints the 5-hour and 7-day usage
  python3 usage.py --max 0.85   # exit 3 if either window is at or above 0.85

The agent reports its rate limits in the stream-json event `rate_limit_event`
(utilization 0..1 per window). Exit 2 if no answer (signed out, network).
"""
import argparse, json, subprocess, sys, time

ap = argparse.ArgumentParser()
ap.add_argument('--max', type=float, default=None)
args = ap.parse_args()
try:
    out = subprocess.run(['bash', '-lc', 'cd /tmp && claude -p "Reply with the single word OK" '
                          '--model claude-haiku-5-5 --output-format stream-json --verbose'],
                         capture_output=True, text=True, timeout=180).stdout
except subprocess.TimeoutExpired:
    out = ''
win = None
for line in out.splitlines():
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if ev.get('type') == 'rate_limit_event':
        win = ev['rate_limit_info'].get('unifiedWindows') or {}
if win is None:
    print('usage: no answer from the agent (signed out, limit reached or no network)')
    sys.exit(2)
parts, worst = [], 0.0
for name, w in win.items():
    u = float(w.get('utilization', 0))
    worst = max(worst, u)
    reset = time.strftime('%m-%d %H:%M UTC', time.gmtime(w.get('resetsAt', 0)))
    parts.append(f'{name}={u:.2f} (resets {reset})')
print('usage: ' + ' '.join(parts))
sys.exit(3 if args.max is not None and worst >= args.max else 0)
