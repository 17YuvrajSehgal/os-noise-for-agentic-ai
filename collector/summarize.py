#!/usr/bin/env python3
"""Quick look at a campaign folder, without reading any trace.

  python3 summarize.py ~/osn-runs/overhead [--by trace] [--csv out.csv]

One row per run from result.json, the agent's own report (the last
"result" event of a1/events.jsonl), the cgroup counters and the tracer
statistics. Then medians per group (--by takes spec keys, dotted for nested
ones, comma separated; default: agent,trace).

This is for checking a campaign right after it ran. The real analysis reads
the traces.
"""
import argparse, csv, json, statistics, sys
from collections import defaultdict
from pathlib import Path


def kv(path):
    try:
        return {k: int(v) for k, v in (l.split()[:2] for l in path.read_text().splitlines()) if v.isdigit()}
    except OSError:
        return {}


def psi(path):
    try:
        return {l.split()[0]: int(l.rsplit('total=', 1)[1]) for l in path.read_text().splitlines()}
    except (OSError, IndexError, ValueError):
        return {}


def agent_report(run):
    """The agent's own summary of the run (Claude Code: the 'result' event)."""
    rep = {}
    try:
        for line in open(run / 'a1/events.jsonl'):
            try:
                ev = json.loads(json.loads(line)['line'])
            except (ValueError, KeyError):
                continue
            if isinstance(ev, dict) and ev.get('type') == 'result':
                rep = ev
    except OSError:
        pass
    return rep


def dig(d, dotted):
    for k in dotted.split('.'):
        d = d.get(k) if isinstance(d, dict) else None
    return json.dumps(d) if isinstance(d, (dict, list)) else d


def row(run):
    res = json.loads((run / 'result.json').read_text())
    rep = agent_report(run)
    after = run / 'meta/after'
    cpu, mem_ev = kv(after / 'a1/cpu.stat'), kv(after / 'a1/memory.events')
    size = lambda p: sum(f.stat().st_size for f in p.rglob('*') if f.is_file()) / 1e6 if p.exists() else 0.0
    disc = None
    stats = run / 'meta/lttng_stats.txt'
    if stats.exists():
        disc = sum(int(l.rsplit(':', 1)[1]) for l in stats.read_text().splitlines() if 'Discarded event' in l)
    peak = after / 'a1/memory.peak'
    api = rep.get('duration_api_ms')
    return dict(run=run.name, spec=res['spec'], ok=res['ok'], wall_s=res['wall_s'],
                turns=rep.get('num_turns'), api_s=api / 1000 if api is not None else None,
                agent_s=rep.get('duration_ms', 0) / 1000 if rep else None,
                model_pct=round(100 * api / 1000 / res['wall_s'], 1) if api else None,
                cpu_s=cpu.get('usage_usec', 0) / 1e6, user_s=cpu.get('user_usec', 0) / 1e6,
                sys_s=cpu.get('system_usec', 0) / 1e6, throttled_s=cpu.get('throttled_usec', 0) / 1e6,
                psi_cpu_s=psi(after / 'a1/cpu.pressure').get('some', 0) / 1e6,
                psi_io_s=psi(after / 'a1/io.pressure').get('some', 0) / 1e6,
                psi_mem_s=psi(after / 'a1/memory.pressure').get('some', 0) / 1e6,
                mem_peak_mb=int(peak.read_text()) / 2 ** 20 if peak.exists() else None,
                oom_kill=mem_ev.get('oom_kill'), cost_usd=rep.get('total_cost_usd'),
                raw_mb=size(run / 'trace'),
                txt_mb=(run / 'trace.txt.gz').stat().st_size / 1e6 if (run / 'trace.txt.gz').exists() else 0.0,
                discarded=disc)


COLS = ['wall_s', 'turns', 'api_s', 'model_pct', 'cpu_s', 'user_s', 'sys_s', 'throttled_s', 'psi_cpu_s',
        'psi_io_s', 'psi_mem_s', 'mem_peak_mb', 'raw_mb', 'txt_mb']

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('campaign_dir')
    ap.add_argument('--by', default='agent,trace')
    ap.add_argument('--csv')
    args = ap.parse_args()
    runs = sorted(p.parent for p in Path(args.campaign_dir).glob('*/result.json'))
    if not runs:
        sys.exit('no finished runs there')
    rows = [row(r) for r in runs]
    keys = args.by.split(',')
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(str(dig(r['spec'], k)) for k in keys)].append(r)
    med = lambda v: statistics.median(v) if v else float('nan')
    print(f"{' / '.join(keys):<34}{'n':>3}{'ok':>6}" + ''.join(f'{c:>12}' for c in COLS) + f"{'discarded':>11}")
    for g in sorted(groups):
        v = groups[g]
        cells = ''.join(f"{med([r[c] for r in v if r[c] is not None]):>12.2f}" for c in COLS)
        print(f"{' / '.join(g):<34}{len(v):>3}{sum(r['ok'] for r in v):>4}/{len(v):<1}" + cells
              + f"{sum(r['discarded'] or 0 for r in v):>11}")
    cost = sum(r['cost_usd'] or 0 for r in rows)
    print(f'{len(rows)} runs, {sum(r["raw_mb"] + r["txt_mb"] for r in rows) / 1000:.1f} GB of trace, '
          f'agent-reported cost ${cost:.2f}')
    if args.csv:
        with open(args.csv, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=[k for k in rows[0] if k != 'spec'] + ['spec'])
            w.writeheader()
            for r in rows:
                w.writerow({**r, 'spec': json.dumps(r['spec'])})
