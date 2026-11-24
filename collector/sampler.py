#!/usr/bin/env python3
"""Time series of a cgroup tree while a run is in progress.

  python3 sampler.py <cgroup dir> <out.jsonl> <hz>

Every 1/hz seconds, one JSON line with the time on two clocks and, for the
group and each child cgroup: CPU use and throttling, memory (current, anon,
file), process count, I/O bytes, and the pressure totals. Also the
machine-wide CPU line, pressure and, if the machine has it, the energy
counter. Reads files only; needs no root except for the energy counter,
which is skipped if it cannot be read.

The trace says what happened and why. This file gives the same run as a
cheap time series that needs no trace to read: peaks, bursts, averages.
"""
import json, signal, sys, time
from pathlib import Path

MEM_KEYS = ('anon', 'file', 'file_mapped', 'shmem', 'slab', 'sock', 'kernel')


def kv(path):
    """'key value' lines -> dict of ints."""
    out = {}
    try:
        for line in path.read_text().splitlines():
            k, _, v = line.partition(' ')
            if v.strip().lstrip('-').isdigit():
                out[k] = int(v)
    except OSError:
        pass
    return out


def one_int(path):
    try:
        return int(path.read_text())
    except (OSError, ValueError):
        return None


def pressure(path):
    """'some avg10=.. total=N' / 'full ...' -> {'some': N, 'full': N} (microseconds stalled)."""
    out = {}
    try:
        for line in path.read_text().splitlines():
            kind, *fields = line.split()
            out[kind] = int(dict(f.split('=') for f in fields)['total'])
    except (OSError, KeyError, ValueError):
        pass
    return out


def io_totals(path):
    tot = {}
    try:
        for line in path.read_text().splitlines():
            for field in line.split()[1:]:
                k, _, v = field.partition('=')
                if v.isdigit():
                    tot[k] = tot.get(k, 0) + int(v)
    except OSError:
        pass
    return tot


def read_cgroup(cg):
    cpu, mem = kv(cg / 'cpu.stat'), kv(cg / 'memory.stat')
    return dict(cpu_usage_usec=cpu.get('usage_usec'), cpu_user_usec=cpu.get('user_usec'),
                cpu_system_usec=cpu.get('system_usec'), nr_throttled=cpu.get('nr_throttled'),
                throttled_usec=cpu.get('throttled_usec'),
                mem_current=one_int(cg / 'memory.current'), mem_swap=one_int(cg / 'memory.swap.current'),
                **{f'mem_{k}': mem.get(k) for k in MEM_KEYS},
                pids=one_int(cg / 'pids.current'), io=io_totals(cg / 'io.stat'),
                psi_cpu=pressure(cg / 'cpu.pressure'), psi_mem=pressure(cg / 'memory.pressure'),
                psi_io=pressure(cg / 'io.pressure'))


def main(cg, out, hz):
    cg = Path(cg)
    period = 1.0 / float(hz)
    rapl = sorted(Path('/sys/class/powercap').glob('intel-rapl:*')) if Path('/sys/class/powercap').exists() else []
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    nxt = time.monotonic()
    with open(out, 'w') as f:
        while not stop:
            row = dict(realtime=time.clock_gettime(time.CLOCK_REALTIME), monotonic=time.monotonic(),
                       group=read_cgroup(cg),
                       agents={c.name: read_cgroup(c) for c in sorted(cg.iterdir()) if c.is_dir()},
                       cpu=Path('/proc/stat').read_text().split('\n', 1)[0].split()[1:],
                       loadavg=Path('/proc/loadavg').read_text().split()[:3],
                       psi={k: pressure(Path(f'/proc/pressure/{k}')) for k in ('cpu', 'memory', 'io')})
            if rapl:
                row['energy_uj'] = {z.name: one_int(z / 'energy_uj') for z in rapl}
            f.write(json.dumps(row) + '\n')
            f.flush()
            nxt += period
            time.sleep(max(0.0, nxt - time.monotonic()))


if __name__ == '__main__':
    main(*sys.argv[1:4])
