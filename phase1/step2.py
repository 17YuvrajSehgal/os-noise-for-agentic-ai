#!/usr/bin/env python3
"""Step 2 (P6, P7, P8): the model wait and the rest of the network traffic.

Reads results/parsed_all.jsonl. Writes results/step2_turns.csv (one row per
model turn) and results/step2_runs.csv (one row per run), and prints the
summary tables for the coding-task runs.

Uses the model-turn rule from step1.py.
"""
import csv, json, statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from step1 import REQ_MIN, DUR_MIN, rel

HERE = Path(__file__).resolve().parent
CAP = {'max': 'unlimited', '100000 100000': '1 core', '50000 100000': '0.5 core',
       '25000 100000': '0.25 core'}
# what each destination is. Resolved on 2026-11-10; the runs are from October.
DEST = {'160.79.104.10': 'api.anthropic.com', '104.18.2.115': 'openrouter.ai',
        '104.18.3.115': 'openrouter.ai', '104.18.32.47': 'chatgpt.com (likely)',
        '172.64.155.209': 'chatgpt.com (likely)', '34.149.66.165': 'unknown (Google Cloud)'}


def dest(ip):
    if ip.startswith('140.82.'):
        return 'github.com'
    return DEST.get(ip, ip)


def union(iv):
    tot, end = 0.0, None
    for a, b in sorted(iv):
        if end is None or a > end:
            tot += b - a
            end = b
        elif b > end:
            tot += b - end
            end = b
    return tot


def analyze(r):
    gt = r['ground_truth']
    t_start, t_end = rel(r['anchors'][0], r['t0']), rel(r['anchors'][-1], r['t0'])
    xs = [x for x in r['exchanges'] if x['dport'] == 443]
    n_by_pid = Counter(x['pid'] for x in xs)
    agent = n_by_pid.most_common(1)[0][0]
    is_turn = lambda x: (x['pid'] == agent and x['out_bytes'] >= REQ_MIN
                         and x['t_last_in'] - x['t_req'] >= DUR_MIN)
    turns = [x for x in xs if is_turn(x)]
    other = [x for x in xs if not is_turn(x)]
    base = dict(family=r['family'], run=r['run'], agent=gt.get('agent', 'claude'), task=gt['task'],
                cpu=CAP.get(gt['cpu_max'], gt['cpu_max']), mem_limit=gt.get('mem_limit', ''),
                io_limit=gt.get('io_limit', ''))
    trows, seen = [], set()
    for k, x in enumerate(turns):
        new = x['conn'] not in seen       # first turn on this connection: it paid the set-up
        seen.add(x['conn'])
        stream = x['t_last_in'] - x['t_first_in']
        trows.append(dict(base, turn=k + 1, new_conn=int(new),
                          setup_s=round(x['t_req'] - x['t_conn'], 4) if new else '',
                          upload_s=round(x['t_req_end'] - x['t_req'], 4),
                          ttfb_s=round(x['t_first_in'] - x['t_req_end'], 3),
                          stream_s=round(stream, 3), max_gap_s=round(x['max_gap'], 3),
                          out_bytes=x['out_bytes'], in_bytes=x['in_bytes'], n_reads=x['n_reads'],
                          rate_bps=round(x['in_bytes'] / stream) if stream > 0.2 else ''))
    con = [c for c in r['connects'] if c['dport'] == 443]
    wall = t_end - t_start
    row = dict(base, wall_s=round(wall, 2), n_turns=len(turns),
               https_connects=len(con), https_used=sum(1 for c in con if c['in_bytes']),
               model_conns=len(seen),
               model_out_kb=round(sum(x['out_bytes'] for x in turns) / 1024, 1),
               model_in_kb=round(sum(x['in_bytes'] for x in turns) / 1024, 1),
               other_n=len(other),
               other_out_kb=round(sum(x['out_bytes'] for x in other) / 1024, 1),
               other_in_kb=round(sum(x['in_bytes'] for x in other) / 1024, 1),
               other_busy_s=round(union([(x['t_req'], x['t_last_in']) for x in other]), 2),
               other_busy_outside_model_s=None,
               dns_n=sum(1 for x in r['exchanges'] if x['dport'] == 53 and x['comm'] != 'sudo'))
    # time with a non-model request in flight and no model request in flight
    model_iv = [(x['t_req'], x['t_last_in']) for x in turns]
    both = union(model_iv + [(x['t_req'], x['t_last_in']) for x in other])
    row['other_busy_outside_model_s'] = round(both - union(model_iv), 2)
    per_dest = defaultdict(lambda: [0, 0, 0])
    for x in other:
        d = per_dest[dest(x['ip'])]
        d[0] += 1; d[1] += x['out_bytes']; d[2] += x['in_bytes']
    row['other_by_dest'] = json.dumps({k: v for k, v in per_dest.items()})
    return row, trows


def med(v, nd=2):
    v = [x for x in v if x != '']
    return round(st.median(v), nd) if v else ''


def p90(v, nd=2):
    v = sorted(x for x in v if x != '')
    return round(v[int(0.9 * (len(v) - 1))], nd) if v else ''


if __name__ == '__main__':
    rows, turns = [], []
    for line in open(HERE / 'results/parsed_all.jsonl'):
        row, t = analyze(json.loads(line))
        rows.append(row); turns += t
    for name, data in (('step2_runs.csv', rows), ('step2_turns.csv', turns)):
        with open(HERE / 'results' / name, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader(); w.writerows(data)

    coding = lambda x: (x['task'] in ('t2_medium.sh', 't3_implement.sh')
                        and x['run'] not in ('t2_nocap_r1', 't2_cap100_r1'))
    print('=== P6: model turns on coding runs, by CPU setting (median / 90th pct) ===')
    print(f"{'agent':<7}{'cpu':<10}{'turns':>6}{'ttfb s':>14}{'stream s':>14}{'longest pause s':>17}"
          f"{'upload ms':>11}{'req KB':>8}{'resp KB':>8}{'resp B/s':>9}")
    for agent in ('claude', 'codex'):
        for cap in CAP.values():
            g = [t for t in turns if t['agent'] == agent and t['cpu'] == cap and coding(t)]
            print(f"{agent:<7}{cap:<10}{len(g):>6}"
                  f"{str(med([t['ttfb_s'] for t in g])) + ' / ' + str(p90([t['ttfb_s'] for t in g])):>14}"
                  f"{str(med([t['stream_s'] for t in g])) + ' / ' + str(p90([t['stream_s'] for t in g])):>14}"
                  f"{str(med([t['max_gap_s'] for t in g])) + ' / ' + str(p90([t['max_gap_s'] for t in g])):>17}"
                  f"{med([1000 * t['upload_s'] for t in g], 1):>11}"
                  f"{med([t['out_bytes'] / 1024 for t in g], 1):>8}{med([t['in_bytes'] / 1024 for t in g], 1):>8}"
                  f"{med([t['rate_bps'] for t in g], 0):>9}")
    print('\n=== P7: connections, unlimited coding runs (median per run) ===')
    for agent in ('claude', 'codex'):
        g = [x for x in rows if x['agent'] == agent and x['cpu'] == 'unlimited' and coding(x)]
        tg = [t for t in turns if t['agent'] == agent and t['cpu'] == 'unlimited' and coding(t)]
        su = [1000 * t['setup_s'] for t in tg if t['setup_s'] != '']
        print(f"{agent:<7} HTTPS connects {med([x['https_connects'] for x in g])}, with data "
              f"{med([x['https_used'] for x in g])}, used for model turns {med([x['model_conns'] for x in g])}; "
              f"turns {med([x['n_turns'] for x in g])}; DNS lookups seen {med([x['dns_n'] for x in g])}; "
              f"set-up before a model request on a new connection: median {med(su, 1)} ms, "
              f"90th pct {p90(su, 1)} ms (n={len(su)})")
    print('\n=== P8: model traffic vs other HTTPS traffic, unlimited coding runs (median per run) ===')
    for agent in ('claude', 'codex'):
        g = [x for x in rows if x['agent'] == agent and x['cpu'] == 'unlimited' and coding(x)]
        print(f"{agent:<7} model: {med([x['model_out_kb'] for x in g], 1)} KB out, "
              f"{med([x['model_in_kb'] for x in g], 1)} KB in | other: {med([x['other_n'] for x in g])} exchanges, "
              f"{med([x['other_out_kb'] for x in g], 1)} KB out, {med([x['other_in_kb'] for x in g], 1)} KB in, "
              f"in flight {med([x['other_busy_s'] for x in g])} s "
              f"({med([x['other_busy_outside_model_s'] for x in g])} s outside model turns)")
        tot = defaultdict(lambda: [0, 0, 0])
        for x in g:
            for k, v in json.loads(x['other_by_dest']).items():
                for i in range(3):
                    tot[k][i] += v[i]
        for k, v in sorted(tot.items(), key=lambda kv: -kv[1][1]):
            print(f"         {k:<24} {v[0] / len(g):5.1f} exchanges/run {v[1] / 1024 / len(g):7.1f} KB out "
                  f"{v[2] / 1024 / len(g):7.1f} KB in")
