#!/usr/bin/env python3
"""Step 3 (P9-P15, P17, P19): local work of the agent and its tools.

Joins results/parsed_all.jsonl (who is agent, who is tool, CPU bins),
results/local_all.jsonl (system calls, spawns, errors, sleep, idle,
interrupts, block I/O) and results/analyze_all.jsonl (peak concurrency).
Writes results/step3_runs.csv and prints the summary tables.

Memory peaks (P14) come from meta/memory.peak, read from OSNOISE_RUNS and
from this repo's latency/ folder (the end-to-end runs live only there).
"""
import csv, json, os, statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from step1 import roles

HERE = Path(__file__).resolve().parent
CAP = {'max': 'unlimited', '100000 100000': '1 core', '50000 100000': '0.5 core',
       '25000 100000': '0.25 core'}
WIN = 10            # CPU bins (10 ms) per 100 ms window
NCPU = 4
ERRNO = {-1: 'EPERM', -2: 'ENOENT', -4: 'EINTR', -9: 'EBADF', -10: 'ECHILD', -11: 'EAGAIN',
         -12: 'ENOMEM', -13: 'EACCES', -17: 'EEXIST', -19: 'ENODEV', -20: 'ENOTDIR', -21: 'EISDIR',
         -22: 'EINVAL', -24: 'EMFILE', -25: 'ENOTTY', -28: 'ENOSPC', -29: 'ESPIPE', -32: 'EPIPE',
         -38: 'ENOSYS', -61: 'ENODATA', -95: 'EOPNOTSUPP', -101: 'ENETUNREACH', -104: 'ECONNRESET',
         -107: 'ENOTCONN', -110: 'ETIMEDOUT', -111: 'ECONNREFUSED', -115: 'EINPROGRESS'}
RESOURCE = {'EMFILE', 'ENOMEM', 'ENOSPC', 'ETIMEDOUT', 'ECONNRESET', 'ECONNREFUSED'}
WAITS = {'futex', 'epoll_wait', 'epoll_pwait', 'epoll_pwait2', 'poll', 'ppoll', 'select', 'pselect6',
         'read', 'wait4', 'waitid', 'nanosleep', 'clock_nanosleep', 'recvfrom', 'recvmsg', 'accept',
         'accept4', 'rt_sigsuspend', 'pause', 'io_uring_enter', 'readv', 'rt_sigtimedwait'}


def med(v, nd=2):
    v = [x for x in v if x is not None and x != '']
    return round(st.median(v), nd) if v else ''


def load(name):
    return {(r['family'], r['run']): r for r in map(json.loads, open(HERE / 'results' / name))}


def analyze(r, loc, an):
    gt = r['ground_truth']
    ro = roles(r)
    agent, tools, procs = ro['agent'], ro['tools'], ro['procs']
    wall = ro['t_end'] - ro['t_start']
    row = dict(family=r['family'], run=r['run'], agent=gt.get('agent', 'claude'), task=gt['task'],
               cpu=CAP.get(gt['cpu_max'], gt['cpu_max']), mem_limit=gt.get('mem_limit', ''),
               io_limit=gt.get('io_limit', ''), wall_s=round(wall, 2))
    # P9 tool processes
    life = [procs[p][1] - procs[p][0] for p in tools]
    names = Counter(procs[p][2] for p in tools)
    row.update(n_tools=len(tools), tool_life_med_ms=med([1000 * x for x in life], 1),
               tool_life_max_s=round(max(life), 2) if life else '',
               tools_under_10ms=sum(1 for x in life if x < 0.01),
               tool_names=json.dumps(names.most_common(12)))
    # P11 CPU demand in 100 ms windows (cores in use by the whole subtree)
    win = defaultdict(float)
    tot = [0.0, 0.0]
    for p, bins in r['cpu'].items():
        col = 1 if int(p) in tools else 0
        for i, on, _ in bins:
            ts = i * 0.01
            if ro['t_start'] <= ts <= ro['t_end']:
                win[int(i // WIN)] += on
                tot[col] += on
    nwin = max(1, int(wall / 0.1))
    cores = sorted(v / 0.1 for v in win.values())
    busy = [c for c in cores if c >= 0.05]
    row.update(agent_cpu_s=round(tot[0], 2), tool_cpu_s=round(tot[1], 2),
               mean_cores=round(sum(tot) / wall, 3),
               busy_windows_pct=round(100 * len(busy) / nwin, 1),
               cores_p90_busy=round(busy[int(0.9 * (len(busy) - 1))], 2) if busy else 0,
               cores_max=round(cores[-1], 2) if cores else 0,
               windows_over_1core_pct=round(100 * sum(1 for c in cores if c > 1.0) / nwin, 1),
               peak_threads=an['max_concurrent_active'])
    # P12 idle, P15 interrupts
    span = loc['span_s']
    row.update(machine_idle_pct=round(100 * sum(loc['idle'].values()) / (NCPU * span), 1),
               irq_hard_ms=round(1000 * loc['irq']['hard_s'], 1),
               irq_soft_ms=round(1000 * loc['irq']['soft_s'], 1),
               irq_on_agent_ms=round(1000 * (loc['irq']['hard_on_agent_s'] + loc['irq']['soft_on_agent_s']), 1),
               irq_pct_machine=round(100 * (loc['irq']['hard_s'] + loc['irq']['soft_s']) / (NCPU * span), 3))
    # P10 system calls, P13 disk, P17 spawns, P19 errors
    sc = {int(p): v for p, v in loc['syscalls'].items()}
    for who, pids in (('agent', [p for p in sc if p not in tools and p != r['root']]),
                      ('tool', [p for p in sc if p in tools])):
        t = defaultdict(lambda: [0, 0.0])
        for p in pids:
            for k, v in sc[p].items():
                t[k][0] += v[0]; t[k][1] += v[1]
        row[f'{who}_syscalls'] = sum(v[0] for v in t.values())
        row[f'{who}_sys_work_s'] = round(sum(v[1] for k, v in t.items() if k not in WAITS), 3)
        row[f'{who}_top_count'] = json.dumps(sorted(((k, v[0]) for k, v in t.items()), key=lambda kv: -kv[1])[:12])
        row[f'{who}_top_work'] = json.dumps(sorted(((k, round(v[1], 3)) for k, v in t.items() if k not in WAITS),
                                                   key=lambda kv: -kv[1])[:8])
        row[f'{who}_openat'] = t['openat'][0] + t['open'][0]
        row[f'{who}_fsync'] = t['fsync'][0] + t['fdatasync'][0]
    row['dsleep_s'] = round(sum(loc['dsleep'].values()), 3)
    row['blk_read_mb'] = round(loc['block']['read_bytes'] / 1e6, 2)
    row['blk_write_mb'] = round(loc['block']['write_bytes'] / 1e6, 2)
    sp = loc['spawns'].get(str(agent), {})
    row['agent_spawns'] = json.dumps({k: [v[0], round(1000 * v[1] / v[0], 3), round(1000 * v[2], 3)]
                                      for k, v in sp.items()})        # count, mean ms, max ms
    errs, res = Counter(), Counter()
    for p, e in loc['errors'].items():
        for k, n in e.items():
            name, ret = k.rsplit(':', 1)
            en = ERRNO.get(int(ret), ret)
            errs[f'{name}:{en}'] += n
            if name == 'futex':            # a timed wait that timed out is normal
                continue
            if en in RESOURCE or (en == 'EAGAIN' and name in ('clone', 'clone3', 'fork', 'vfork')):
                res[f'{name}:{en}'] += n
    row['errors_total'] = sum(errs.values())
    row['errors_top'] = json.dumps(errs.most_common(8))
    row['errors_resource'] = json.dumps(dict(res))
    return row


def peaks():
    """meta/memory.peak for every run that has it -> rows(agent, task, limit, MiB)."""
    roots = [Path(os.environ['OSNOISE_RUNS']), HERE.parent / 'latency']
    seen, out = set(), []
    for root in roots:
        for f in root.glob('**/meta/memory.peak'):
            run = f.parent.parent
            key = (run.parent.name, run.name)       # run names repeat across families
            if key in seen:
                continue
            seen.add(key)
            txt = f.read_text().strip()
            if not txt.isdigit():
                continue
            gt = json.loads((run / 'meta/ground_truth.json').read_text())
            out.append(dict(run=run.name, agent=gt.get('agent', 'claude'), task=gt['task'],
                            mem_limit=gt.get('mem_limit', ''), ok=gt['task_check_exit'] == 0,
                            peak_mib=int(txt) / 2 ** 20))
    return out


if __name__ == '__main__':
    P, L, A = load('parsed_all.jsonl'), load('local_all.jsonl'), load('analyze_all.jsonl')
    rows = [analyze(P[k], L[k], A[k]) for k in P]
    with open(HERE / 'results/step3_runs.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)

    coding = lambda x: (x['task'] in ('t2_medium.sh', 't3_implement.sh')
                        and x['run'] not in ('t2_nocap_r1', 't2_cap100_r1'))
    U = {a: [x for x in rows if x['agent'] == a and x['cpu'] == 'unlimited' and coding(x)]
         for a in ('claude', 'codex')}

    def line(label, key, nd=2):
        print(f"  {label:<44}" + ''.join(f"{str(med([x[key] for x in U[a]], nd)):>12}" for a in U))

    def merged(key, a, top=10):
        c = Counter()
        for x in U[a]:
            for k, v in json.loads(x[key]):
                c[k] += v
        return [(k, round(v / len(U[a]), 3 if isinstance(v, float) else 1)) for k, v in c.most_common(top)]

    print(f"unlimited coding runs, median per run{'':<9}{'claude':>12}{'codex':>12}")
    print('P9 tool processes')
    line('tool processes started', 'n_tools')
    line('median lifetime (ms)', 'tool_life_med_ms', 1)
    line('longest lifetime (s)', 'tool_life_max_s')
    line('processes living under 10 ms', 'tools_under_10ms')
    for a in U:
        print(f'    {a} programs per run: {merged("tool_names", a, 14)}')
        sp = Counter(); tm = defaultdict(list)
        for x in U[a]:
            for k, v in json.loads(x['agent_spawns']).items():
                sp[k] += v[0]; tm[k].append(v[1])
        print(f'    {a} agent spawn calls per run: ' + ', '.join(
            f'{k} x{sp[k] / len(U[a]):.1f} (mean {st.median(tm[k]):.2f} ms)' for k in sp))
    print('P10 system calls')
    line('agent: calls per run', 'agent_syscalls', 0)
    line('agent: time in non-waiting calls (s)', 'agent_sys_work_s', 3)
    line('tools: calls per run', 'tool_syscalls', 0)
    line('tools: time in non-waiting calls (s)', 'tool_sys_work_s', 3)
    for a in U:
        print(f'    {a} agent top by count: {merged("agent_top_count", a)}')
        print(f'    {a} agent top by time (non-waiting, s): {merged("agent_top_work", a, 6)}')
        print(f'    {a} tools top by count: {merged("tool_top_count", a)}')
    print('P11 CPU demand')
    line('agent CPU (s)', 'agent_cpu_s'); line('tool CPU (s)', 'tool_cpu_s')
    line('mean cores in use over the run', 'mean_cores', 3)
    line('100 ms windows with any CPU use (%)', 'busy_windows_pct', 1)
    line('cores in use, 90th pct of busy windows', 'cores_p90_busy')
    line('cores in use, busiest window', 'cores_max')
    line('windows using more than 1 core (%)', 'windows_over_1core_pct', 1)
    line('most threads wanting a CPU at once', 'peak_threads', 0)
    print('P12 / P15 machine')
    line('machine idle (%)', 'machine_idle_pct', 1)
    line('hard interrupt time (ms)', 'irq_hard_ms', 1)
    line('soft interrupt time (ms)', 'irq_soft_ms', 1)
    line('interrupt time while agent on CPU (ms)', 'irq_on_agent_ms', 1)
    line('interrupt time, % of machine', 'irq_pct_machine', 3)
    print('P13 disk and files')
    line('agent: files opened', 'agent_openat', 0); line('tools: files opened', 'tool_openat', 0)
    line('agent: fsync calls', 'agent_fsync', 0)
    line('disk-type sleep, whole subtree (s)', 'dsleep_s', 3)
    line('block reads, whole machine (MB)', 'blk_read_mb'); line('block writes, whole machine (MB)', 'blk_write_mb')
    print('P19 failed system calls')
    line('failed calls per run', 'errors_total', 0)
    for a in U:
        print(f'    {a} top: {merged("errors_top", a, 8)}')
    res = Counter()
    for x in rows:
        for k, n in json.loads(x['errors_resource']).items():
            res[(x['agent'], x['family'].split('/')[-1], x['mem_limit'] or x['io_limit'] or x['cpu'], k)] += n
    print('  resource-type errors over ALL 262 runs (agent, family, limit, call:error -> count):')
    for k, n in sorted(res.items()):
        print('   ', k, n)
    print('P14 peak memory of the cgroup (MiB), runs with no memory limit or a loose one')
    pk = defaultdict(list)
    for x in peaks():
        if x['mem_limit'] in ('', 'high:max', 'max:2G') and x['ok']:
            pk[(x['agent'], x['task'])].append(x['peak_mib'])
    for k in sorted(pk):
        v = pk[k]
        print(f'    {k[0]:<7}{k[1]:<18} n={len(v):<3} median {st.median(v):7.1f}  min {min(v):7.1f}  max {max(v):7.1f}')
