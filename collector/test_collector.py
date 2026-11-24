#!/usr/bin/env python3
"""Checks that need no VM, no root and no agent:  python3 test_collector.py

Covers the spec validation, the campaign planner, the sampler's parsers and
a dry run of the collector for the main kinds of run. The parts that touch
the kernel (cgroups, tracing, network namespace) can only be tested on the
VM with campaigns/smoke_fake.json.
"""
import io, json, tempfile
from contextlib import redirect_stdout
from pathlib import Path

import sampler
from campaign import plan
from collect import Collector, fill_spec

HERE = Path(__file__).resolve().parent


def raises(fn, text):
    try:
        fn()
    except ValueError as e:
        assert text in str(e), e
        return
    raise AssertionError(f'expected an error containing {text!r}')


def test_spec():
    s = fill_spec({'run': 'x', 'task': 't3_implement.sh'})
    assert s['agent'] == 'claude' and s['trace'] == 'full' and s['agents'] == 1
    raises(lambda: fill_spec({'task': 't3_implement.sh'}), 'needs "run"')
    raises(lambda: fill_spec({'run': 'x', 'task': 'nope.sh'}), 'no such task')
    raises(lambda: fill_spec({'run': 'x', 'task': 't3_implement.sh', 'colour': 1}), 'unknown spec keys')
    raises(lambda: fill_spec({'run': 'x', 'task': 't3_implement.sh', 'limits': {'cpu': 1}}), 'unknown limits')
    raises(lambda: fill_spec({'run': 'x', 'task': 't3_implement.sh', 'net': {'lag': 1}}), 'net keys')
    raises(lambda: fill_spec({'run': 'a b', 'task': 't3_implement.sh'}), 'run name')
    raises(lambda: fill_spec({'run': 'x', 'task': 't3_implement.sh', 'agents': 0}), 'positive')


def test_plan():
    camp = {'name': 'c', 'reps': 3, 'seed': 7, 'base': {'task': 't3_implement.sh'},
            'grid': {'agent': ['claude', 'codex'], 'limits.cpu_max': ['max', '50000 100000'],
                     'limits.io_max': [None, {'rbps': 5}]}}
    a, b = plan(camp), plan(camp)
    assert len(a) == 2 * 2 * 2 * 3
    assert [s['run'] for s in a] == [s['run'] for s in b], 'same seed, same order'
    assert len({s['run'] for s in a}) == len(a), 'run names are unique'
    assert [s['run'] for s in a] != sorted(s['run'] for s in a), 'order is shuffled'
    one = next(s for s in a if s['run'] == 'c_codex_50000_rbps5_r2')
    assert one['limits'] == {'cpu_max': '50000 100000', 'io_max': {'rbps': 5}}
    assert plan(dict(camp, seed=8)) != a, 'another seed, another order'
    assert all(s['model'] == 'claude-opus-5-5' for s in a if s['agent'] == 'claude'), 'model is pinned'
    for f in sorted((HERE / 'campaigns').glob('*.json')):      # every shipped campaign must plan
        if f.name != 'models.json':
            assert plan(json.loads(f.read_text())), f.name


def test_sampler_parsers():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / 'cpu.stat').write_text('usage_usec 12\nnr_throttled 3\nthrottled_usec 99\n')
        (d / 'cpu.pressure').write_text('some avg10=0.00 avg60=0.00 avg300=0.00 total=41\n'
                                        'full avg10=0.00 avg60=0.00 avg300=0.00 total=7\n')
        (d / 'io.stat').write_text('8:0 rbytes=10 wbytes=1 rios=2 wios=1 dbytes=0 dios=0\n'
                                   '8:16 rbytes=5 wbytes=0 rios=1 wios=0 dbytes=0 dios=0\n')
        (d / 'memory.current').write_text('4096\n')
        row = sampler.read_cgroup(d)
        assert row['cpu_usage_usec'] == 12 and row['throttled_usec'] == 99
        assert row['psi_cpu'] == {'some': 41, 'full': 7}
        assert row['io']['rbytes'] == 15 and row['mem_current'] == 4096
        assert row['pids'] is None and row['psi_io'] == {}, 'missing files give empty values'


def dry(raw):
    buf = io.StringIO()
    with redirect_stdout(buf):
        Collector(fill_spec(raw), '/tmp/osn-test', dry=True).run()
    return buf.getvalue()


def test_dry_runs():
    base = {'run': 'd', 'task': 't3_implement.sh'}
    out = dry(base)
    assert '--tracepoint --all' in out and '--syscall --all' in out, 'full profile traces everything'
    assert 'drop_caches' in out and 'stream-json' in out
    assert out.index('lttng start') < out.index('launcher.sh') < out.index('lttng stop')

    out = dry(dict(base, trace='none', cache='warm', agent='codex'))
    assert 'lttng' not in out and 'drop_caches' not in out and 'exec --json' in out

    out = dry(dict(base, agents=3, limits={'cpu_max': '50000 100000', 'memory_max': '256M', 'pids_max': 32,
                                           'io_max': {'rbps': 1000}}))
    for i in (1, 2, 3):                       # each agent gets its own cgroup and its own limits
        assert f"'50000 100000' > /sys/fs/cgroup/osn/run/a{i}/cpu.max" in out
        assert f'/sys/fs/cgroup/osn/run/a{i}/cgroup.procs' in out
    assert "rbps=1000' > /sys/fs/cgroup/osn/run/a2/io.max" in out

    out = dry(dict(base, agents=2, limit_scope='group', limits={'memory_max': '1G'}))
    assert "'1G' > /sys/fs/cgroup/osn/run/memory.max" in out and 'run/a1/memory.max' not in out

    out = dry(dict(base, net={'delay_ms': 100, 'loss_pct': 1}))
    assert 'netem delay 100ms loss 1%' in out and 'ip netns exec osn setpriv' in out
    assert out.count('netem') == 2, 'impairment on both directions'
    assert 'netem' not in dry(dict(base, net={})), 'empty net = namespace only, the control cell'
    assert 'ip netns del' in dry(dict(base, net={})), 'namespace is removed afterwards'

    out = dry(dict(base, neighbour={'kind': 'cpu', 'workers': 4}))
    assert 'stress-ng --cpu 4' in out and '/sys/fs/cgroup/osn/nb' in out


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
