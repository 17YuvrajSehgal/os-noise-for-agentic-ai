#!/usr/bin/env python3
"""Review 2/3: long sessions. sympy-13878 (SWE-bench Verified, rated '>4 hours'),
Docker, M0 set 2, 5 runs at no limit, 1 CPU / 512 MB and 0.25 CPU / 512 MB.

Per size: wall, model, local (medians), turns, tool calls, f, slowdowns with
95% bootstrap intervals, solved. Then the predictions of Section RQ2 for this
task from its runs with no limit: Eq. 1 with s = 1/q, and the replay.

  python rev/a13_long.py -> rev/a13.txt
"""
import json, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import REV, load, boot_ratio, wilson   # noqa: E402
from predict import slices, predict, split_times    # noqa: E402

out = []


def p(*a):
    out.append(' '.join(str(x) for x in a))
    print(*a, flush=True)


def tools_turns(run):
    turns = calls = 0
    for line in open(run / 'a1' / 'events.jsonl', encoding='utf-8'):
        try:
            e = json.loads(json.loads(line)['line'])
        except (ValueError, KeyError):
            continue
        if not isinstance(e, dict):
            continue
        if e.get('type') == 'assistant':
            turns += 1
            for b in (e.get('message') or {}).get('content') or []:
                calls += isinstance(b, dict) and b.get('type') == 'tool_use'
    return turns, calls


g = defaultdict(list)
for r in load(REV, 'r_long'):
    run = REV / 'r_long' / r['run']
    sl, wall = slices(run)
    turns, calls = tools_turns(run)
    g[r['limits']].append(dict(r, sl=sl, turns=turns, calls=calls))
order = sorted(g, key=lambda k: (k != '{}', -float(json.loads(k).get('cpu_max', '99 1').split()[0]) if k != '{}' else 0))
base = g['{}']
bw, bl = st.median(r['wall'] for r in base), st.median(r['local'] for r in base)
p('sympy-13878, Docker, M0 set 2')
p(f"{'size':<30}{'n':>3}{'solved':>8}{'wall s':>9}{'model s':>9}{'local s':>9}{'f':>6}{'turns':>7}{'tools':>7}"
  f"{'wall x [95%]':>20}{'local x [95%]':>20}")
for k in order:
    v = g[k]
    lim = json.loads(k)
    name = 'no limit' if not lim else f"{int(lim['cpu_max'].split()[0]) / 100000:g} CPU / {lim.get('memory_max', '')}"
    w, l, m = [r['wall'] for r in v], [r['local'] for r in v], [r['model_s'] for r in v]
    f = st.median(r['local'] / r['wall'] for r in v)
    sw, (lo, hi) = st.median(w) / bw, ((1, 1) if v is base else boot_ratio(w, [r['wall'] for r in base]))
    slo, (llo, lhi) = st.median(l) / bl, ((1, 1) if v is base else boot_ratio(l, [r['local'] for r in base]))
    ok = sum(r['ok'] for r in v)
    p(f'{name:<30}{len(v):>3}{ok:>5}/{len(v):<3}{st.median(w):>9.0f}{st.median(m):>9.0f}{st.median(l):>9.0f}{f:>6.2f}'
      f'{st.median(r["turns"] for r in v):>7.0f}{st.median(r["calls"] for r in v):>7.0f}'
      f'{sw:>8.2f} [{lo:.2f}-{hi:.2f}]{slo:>8.2f} [{llo:.2f}-{lhi:.2f}]')
    p(f'{"":<30}   walls: {" ".join(f"{x:.0f}" for x in sorted(w))}')

p('\npredictions from the runs with no limit (f = %.2f):' % st.median(r['local'] / r['wall'] for r in base))
for k in order:
    if k == '{}':
        continue
    q = int(json.loads(k)['cpu_max'].split()[0]) / 100000
    v = g[k]
    obs_w, obs_l = st.median(r['wall'] for r in v), st.median(r['local'] for r in v)
    f = st.median(r['local'] / r['wall'] for r in base)
    eq1 = 1 + f * (max(1, 1 / q) - 1)
    rep_w = st.median(predict(r['sl'], q, None) for r in base)
    rep_l = st.median(predict(r['sl'], q, None) - split_times(r['sl'])[0] for r in base)
    p(f'  {q:g} CPU: measured wall x{obs_w / bw:.2f}, local x{obs_l / bl:.2f} | Eq.1 wall x{eq1:.2f} (err {100 * (eq1 / (obs_w / bw) - 1):+.0f}%), '
      f'local x{max(1, 1 / q):.2f} (err {100 * (max(1, 1 / q) / (obs_l / bl) - 1):+.0f}%) | '
      f'replay wall x{rep_w / bw:.2f} (err {100 * (rep_w / obs_w - 1):+.0f}%), local x{rep_l / bl:.2f} (err {100 * (rep_l / obs_l - 1):+.0f}%)')
(HERE / 'a13.txt').write_text('\n'.join(out) + '\n')
