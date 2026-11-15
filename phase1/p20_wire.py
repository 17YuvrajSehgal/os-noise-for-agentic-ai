#!/usr/bin/env python3
"""P20 / P7: what the packets on the wire say (TCP port 443 only).

Per run, from net_dev_queue (packets sent) and net_if_receive_skb (packets
received), which carry the IP and TCP headers:
- round-trip time per destination: SYN sent -> SYN-ACK received
- retransmissions: a data segment sent twice with the same sequence number
- bytes on the wire in each direction

  OSNOISE_RUNS=<runs root> python p20_wire.py > results/p20_wire.csv
"""
import csv, gzip, json, os, re, statistics, sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(os.environ['OSNOISE_RUNS'])
TS = re.compile(r'^\[(\d\d):(\d\d):(\d\d)\.(\d{9})\]')
HDR = re.compile(r'ihl = (\d+), .*?tot_len = (\d+), .*?'
                 r'saddr = \[ \[0\] = (\d+), \[1\] = (\d+), \[2\] = (\d+), \[3\] = (\d+) \], '
                 r'daddr = \[ \[0\] = (\d+), \[1\] = (\d+), \[2\] = (\d+), \[3\] = (\d+) \], .*?'
                 r'source_port = (\d+), dest_port = (\d+), seq = (\d+), ack_seq = \d+, '
                 r'data_offset = (\d+), reserved = \d+, flags = (0x[0-9A-Fa-f]+)')


def check(run):
    syn, rtt = {}, {}            # (ip, local port) -> t ; ip -> [rtt]
    seen, retx, data_segs = set(), 0, 0
    tx = rx = 0
    with gzip.open(run / 'trace.txt.gz', 'rt', errors='replace') as f:
        for line in f:
            out = ' net_dev_queue: ' in line
            if not out and ' net_if_receive_skb: ' not in line:
                continue
            if '"tcp"' not in line or 'name = "lo"' in line:
                continue
            h = HDR.search(line)
            if not h:
                continue
            g = h.groups()
            ihl, tot = int(g[0]), int(g[1])
            src, dst = '.'.join(g[2:6]), '.'.join(g[6:10])
            sport, dport, seq, doff, flags = int(g[10]), int(g[11]), int(g[12]), int(g[13]), int(g[14], 16)
            m = TS.match(line)
            t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1e9
            if out and dport == 443:
                tx += tot
                if flags & 0x3F == 0x02:                       # SYN
                    syn.setdefault((dst, sport), t)
                elif tot - 4 * ihl - 4 * doff > 0:             # data segment
                    data_segs += 1
                    key = (dst, sport, seq)
                    if key in seen:
                        retx += 1
                    seen.add(key)
            elif not out and sport == 443:
                rx += tot
                if flags & 0x3F == 0x12 and (src, dport) in syn:   # SYN-ACK
                    rtt.setdefault(src, []).append(t - syn.pop((src, dport)))
    gt = json.loads((run / 'meta/ground_truth.json').read_text())
    allr = [x for v in rtt.values() for x in v]
    return dict(family=run.parent.relative_to(ROOT).as_posix(), run=run.name,
                agent=gt.get('agent', 'claude'), tcp_handshakes=len(allr),
                rtt_ms_med=round(1000 * statistics.median(allr), 2) if allr else '',
                rtt_ms_max=round(1000 * max(allr), 2) if allr else '',
                rtt_by_dest=json.dumps({k: round(1000 * statistics.median(v), 2) for k, v in rtt.items()}),
                data_segments_sent=data_segs, retransmitted=retx,
                wire_kb_out=round(tx / 1024, 1), wire_kb_in=round(rx / 1024, 1))


if __name__ == '__main__':
    runs = sorted(p.parent for p in ROOT.glob('**/trace.txt.gz'))
    with Pool(12) as pool:
        rows = pool.map(check, runs)
    w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]), lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
