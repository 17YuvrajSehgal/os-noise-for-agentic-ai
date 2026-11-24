#!/usr/bin/env python3
"""Write the campaign files of the revision (review 1, 2026-11-18).

  python3 campaigns/gen_revision.py          # writes campaigns/r_*.json, m1_*.json, m2_*.json
  python3 campaigns/gen_revision.py --check  # prints the run counts only

M0 = agentic-noise-2 (n2-standard-4) after the disk shrink: a fresh set, so every
comparison has its own unlimited runs on the new disk. M1 = osn-m1 (n2-standard-2),
M2 = osn-m2 (n2d-standard-8): the same core set on other machines.
The order of QUEUES is the order to run them: most important first, so that a
usage limit cuts off the least important campaigns.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = {'agent': 'claude', 'trace': 'full', 'cache': 'cold'}
OPUS, HAIKU, FABLE = 'claude-opus-5-5', 'claude-haiku-5-5', 'claude-fable-5-1'
CORE = lambda q: {'cpu_max': 'max' if q is None else f'{int(q * 100000)} 100000'}
MB = lambda n: {'rbps': n * 1024 * 1024}
SHORT = ['django__django-15930', 'sympy__sympy-24562', 'pydata__xarray-6461',
         'pytest-dev__pytest-10081', 'pallets__flask-5014', 'psf__requests-5414']
SWE = {'task': 'swe.sh', 'runtime': 'docker', 'timeout_s': 1200}
SIZES = {'none': {}, 'pod': {'cpu_max': '100000 100000', 'memory_max': '512M'},
         'fargate': {'cpu_max': '25000 100000', 'memory_max': '512M'}}


def camp(name, seed, reps, note, cells=None, grid=None, base=None):
    c = {'name': name, 'reps': reps, 'seed': seed, '_note': note, 'base': {**BASE, **(base or {})}}
    if cells:
        c['cells'] = cells
    else:
        c['grid'] = grid
    return c


def cell(task, task_arg='', limits=None, **kw):
    return {'task': task, 'task_arg': task_arg, 'limits': limits or {}, **kw}


def m0():
    return [
        camp('r_feedback', 101, 15, 'RQ5 controls, 0.25 core unless noted: a fixed fast time (time printed but '
             'not slow), a fixed slow time with no limit (slow number on a fast machine), an instruction that '
             'run time is not a goal (Haiku); printed vs silent with a second model (Fable).', cells=[
                 cell('t11_implement_variants.sh', 'const_fast', CORE(0.25), model=HAIKU),
                 cell('t11_implement_variants.sh', 'const_slow', CORE(None), model=HAIKU),
                 cell('t11_implement_variants.sh', 'instruct', CORE(0.25), model=HAIKU),
                 cell('t3_implement.sh', '', CORE(0.25), model=FABLE),
                 cell('t9_implement_quiet.sh', '', CORE(0.25), model=FABLE)]),
        camp('r_feedback_ref', 102, 10, 'RQ5 reference cells on the new disk: Haiku t3 (time printed) with no '
             'limit and at 0.25 core, t9 (silent) at 0.25 core.', cells=[
                 cell('t3_implement.sh', '', CORE(None), model=HAIKU),
                 cell('t3_implement.sh', '', CORE(0.25), model=HAIKU),
                 cell('t9_implement_quiet.sh', '', CORE(0.25), model=HAIKU)]),
        camp('r_cutout', 103, 10, 'RQ5: a test process killed by memory.max while its output is piped through '
             'tee, so the agent only sees output that stops (t12, 700 MB fixture). Opus and Haiku.', cells=[
                 cell('t12_silent_kill.sh', 700, {'memory_max': '768M'}, model=m) for m in (OPUS, HAIKU)] + [
                 cell('t12_silent_kill.sh', 700, {}, model=m) for m in (OPUS, HAIKU)]),
        camp('r_cpu', 104, 15, 'CPU quota on t3 (Opus), 15 runs per step on the new disk (review: more runs '
             'around the breaking point).', grid={'task': ['t3_implement.sh'],
                                                  'limits.cpu_max': ['max', '100000 100000', '75000 100000',
                                                                     '50000 100000', '25000 100000']}),
        camp('r_overhead', 105, 10, 'Tracing cost under limits: no trace against the full trace at 0.25 core '
             'and at memory.max 192M (t3, Opus).', cells=[
                 cell('t3_implement.sh', '', lim, trace=tr)
                 for lim in (CORE(0.25), {'memory_max': '192M'}) for tr in ('none', 'full')]),
        camp('r_pids', 106, 10, 'Process limit around the crash, 10 runs per step (t3, Opus). Baseline: r_cpu max.',
             grid={'task': ['t3_implement.sh'], 'limits.pids_max': [24, 20, 19, 18, 17, 16]}),
        camp('r_mem', 107, 10, 'Process memory around the kill (t7, 512 MB), 10 runs per step.',
             grid={'task': ['t7_memhog.sh'], 'task_arg': [512], 'limits.memory_max': ['768M', '704M', '640M']}),
        camp('r_interact', 108, 5, 'Limit interactions on t3 (Opus): each single limit and the pairs CPU + disk, '
             'memory + processes; and 4 agents at 1 core each (CPU quota + crowding). Baselines: r_cpu, r_pids, '
             'r_density.', cells=[
                 cell('t3_implement.sh', '', {'io_max': MB(20)}),
                 cell('t3_implement.sh', '', {'memory_max': '192M'}),
                 cell('t3_implement.sh', '', {**CORE(0.5), 'io_max': MB(20)}),
                 cell('t3_implement.sh', '', {'memory_max': '192M', 'pids_max': 20}),
                 cell('t3_implement.sh', '', CORE(1), agents=4)]),
        camp('r_real', 109, 10, 'Six short SWE-bench Verified tasks in Docker, no limit and Fargate minimum '
             '(0.25 CPU / 512 MiB), 10 runs per cell on the new disk.', base=SWE,
             grid={'task_arg': SHORT, 'limits': [SIZES['none'], SIZES['fargate']]}),
        camp('r_density', 110, 3, '1 to 32 agents on t3 on the new disk (3 more groups per level; the old 3 '
             'were on the 400 GB disk).', grid={'task': ['t3_implement.sh'], 'agents': [1, 2, 4, 8, 16, 32]}),
        camp('r_density_real', 111, 3, 'Density with a second, real task (Requests in Docker).', base=SWE,
             grid={'task_arg': ['psf__requests-5414'], 'agents': [1, 2, 4, 8, 16]}),
        camp('r_overhead_density', 112, 5, 'Tracing cost with 8 agents at once: no trace against the full trace.',
             grid={'task': ['t3_implement.sh'], 'agents': [8], 'trace': ['none', 'full']}),
    ]


def core_set(m, vcpu, seed0):
    """The same experiments on another machine; thread and density levels scale with the vCPUs."""
    cpu = ['max', '100000 100000', '75000 100000', '50000 100000', '25000 100000']
    if vcpu >= 8:
        cpu.insert(1, '200000 100000')
    density = [1, 2, 4, 8, 16] if vcpu <= 2 else [1, 2, 4, 8, 16, 32, 64]
    return [
        camp(f'{m}_cpu', seed0 + 1, 10, f'CPU quota on t3 (Opus), {m}.',
             grid={'task': ['t3_implement.sh'], 'limits.cpu_max': cpu}),
        camp(f'{m}_threads', seed0 + 2, 5, f'W CPU-bound workers on {vcpu} vCPUs: W = C/2, C, 2C, 4C.',
             grid={'task': ['t4_parallel.sh'], 'task_arg': [max(1, vcpu // 2), vcpu, 2 * vcpu, 4 * vcpu]}),
        camp(f'{m}_memory', seed0 + 3, 5, f'Soft limit on file memory (t6) and hard limit on process memory (t7), {m}.',
             cells=[cell('t6_memtouch.sh', 1024, {'memory_high': v}) for v in ('max', '1344M', '1152M', '768M')] +
                   [cell('t7_memhog.sh', 512, {'memory_max': v}) for v in ('768M', '704M', '640M')]),
        camp(f'{m}_disk', seed0 + 4, 5, f'Disk read limit on t8, {m}.',
             grid={'task': ['t8_ioread.sh'], 'task_arg': [1024],
                   'limits.io_max': [None, MB(150), MB(50), MB(20)]}),
        camp(f'{m}_pids', seed0 + 5, 5, f'Process limit on t3, {m}. Baseline: {m}_cpu max.',
             grid={'task': ['t3_implement.sh'], 'limits.pids_max': [24, 20, 18, 17, 16]}),
        camp(f'{m}_real', seed0 + 6, 5, f'Three short SWE-bench tasks in Docker at three platform sizes, {m}.',
             base=SWE, grid={'task_arg': ['django__django-15930', 'sympy__sympy-24562', 'psf__requests-5414'],
                             'limits': list(SIZES.values())}),
        camp(f'{m}_density', seed0 + 7, 3, f'1 to {density[-1]} agents on t3, {m} ({vcpu} vCPUs).',
             grid={'task': ['t3_implement.sh'], 'agents': density}),
    ]


def pids_follow_up():
    """Added 2026-11-18 after the first pass: the agent survived 16 processes on 2 vCPUs but crashed
    at 24 on 8 vCPUs, so the crash level moves with the vCPU count. Find the edge on each machine."""
    return {
        'M1': [camp('m1_pids_lo', 208, 5, 'Process limit below 16 on 2 vCPUs (t3, Opus): where does the agent crash?',
                    grid={'task': ['t3_implement.sh'], 'limits.pids_max': [14, 12, 10, 8]})],
        'M2': [camp('m2_pids_hi', 308, 5, 'Process limit above 24 on 8 vCPUs (t3, Opus): where does the agent stop crashing?',
                    grid={'task': ['t3_implement.sh'], 'limits.pids_max': [64, 48, 40, 32, 28]})],
    }


QUEUES = {'M0': m0(), 'M1': core_set('m1', 2, 200), 'M2': core_set('m2', 8, 300)}
for _q, _c in pids_follow_up().items():
    QUEUES[_q] += _c


def count(c):
    n = len(c['cells']) if c.get('cells') else 1
    if not c.get('cells'):
        for v in c['grid'].values():
            n *= len(v)
    runs = n * c['reps']
    agents = c['grid'].get('agents') if c.get('grid') else None
    return runs, (sum(agents) * c['reps'] if agents else sum(cl.get('agents', 1) for cl in c.get('cells', [])) * c['reps'] or runs)


if __name__ == '__main__':
    total = [0, 0]
    for q, camps in QUEUES.items():
        print(f'{q}: ' + ' '.join(c['name'] for c in camps))
        for c in camps:
            runs, agents = count(c)
            total[0] += runs; total[1] += agents
            print(f'  {c["name"]:20s} {runs:4d} runs  {agents:4d} agent runs')
            if '--check' not in sys.argv:
                (HERE / f'{c["name"]}.json').write_text(json.dumps(c, indent=1) + '\n')
    print(f'total {total[0]} runs, {total[1]} agent runs')
