#!/usr/bin/env python3
"""One measured run of one or more AI coding agents under container limits.

  python3 collect.py spec.json [--out RUNS_DIR] [--dry-run]

Runs ON the collection VM, as the user the agents are signed in for. That
user needs password-less sudo. Standard library only.

A run is described by a spec (JSON, see SPEC_DEFAULTS and README.md). The
collector:
  1. builds one fresh task repository per agent
  2. creates a cgroup tree and sets the limits from the spec
  3. optionally puts the agents in a network namespace with delay/loss/rate
  4. snapshots every counter (cgroup, /proc, pressure, energy if present)
  5. starts a full kernel trace (LTTng) and a time-series sampler
  6. starts the agents inside their cgroups, time-stamping every line of
     their JSON event stream
  7. stops everything, snapshots the counters again, checks the task result
  8. decodes the trace and writes checksums

Output layout (one folder per run):
  spec.json                 the spec as run (with defaults filled in)
  result.json               what happened: exit codes, checks, durations
  trace/                    raw LTTng trace (CTF). Never deleted.
  trace.txt.gz              the same trace decoded to text
  samples.jsonl             cgroup / pressure / CPU time series
  meta/                     counters before and after, versions, anchors,
                            tracer statistics (lost events), launcher script
  a1/ a2/ ...               per agent: events.jsonl (time-stamped agent
                            output), stderr, exit code, check output, patch
  SHA256SUMS
"""
import argparse, hashlib, json, os, shlex, shutil, subprocess, sys, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CG_ROOT = Path('/sys/fs/cgroup/osn')        # our subtree; recreated every run
CONTROLLERS = '+cpu +cpuset +memory +io +pids'
NETNS = 'osn'
DOCKER_IMAGE = 'osn-agent:1'                # built by docker/build.sh
# Host paths the container sees at the same path: the agent binary, its sign-in and
# settings, and the Python builds the task environments link to.
DOCKER_MOUNTS = [('.local/share/claude', 'ro'), ('.local/bin', 'ro'), ('.local/share/uv', 'ro'),
                 ('.claude', 'rw'), ('.claude.json', 'rw')]

SPEC_DEFAULTS = {
    'run': None,                 # run name (folder name). Required.
    'agent': 'claude',           # claude | codex | fake
    'model': None,               # passed to the agent if set; else the agent's default
    'task': None,                # script in tasks/. Required.
    'task_arg': '',              # exported to the task script as TASK_ARG
    'agents': 1,                 # how many agents run at the same time
    'limits': {},                # cpu_max, cpu_weight, cpuset, memory_high, memory_max,
                                 # memory_swap_max, pids_max, io_max: {rbps, wbps, riops, wiops}
    'limit_scope': 'each',       # each: every agent gets the limits; group: all agents share them
    'net': None,                 # {delay_ms, jitter_ms, loss_pct, rate_kbit}; {} = namespace, no impairment
    'neighbour': None,           # {kind: cpu|vm|io, workers: N}: a busy process outside the agents' group
    'runtime': 'host',           # host: agent runs as a plain process; docker: inside a container
                                 # (image DOCKER_IMAGE) placed under the same cgroup, same limits
    'trace': 'full',             # full | core | none
    'cache': 'cold',             # cold: drop page cache before the run; warm: leave it
    'sample_hz': 5,              # time-series sampler rate
    'timeout_s': 900,            # per agent
    'fake_cmd': 'sleep 1',       # command run when agent == fake (collector tests)
    'tool_guard': None,          # keep the OOM killer away from the agent (host runtime, one agent):
                                 #   oom_adj: every tool shell raises its own oom_score_adj to 1000
                                 #   cgroup:  tool shells move to a child cgroup with tool_memory_max
    'tool_memory_max': None,     # memory.max of the tools' cgroup when tool_guard == cgroup
}

# ---- trace profiles -------------------------------------------------------
# full: every kernel tracepoint and every system call. This is the dataset
#       profile: nothing has to be guessed in advance.
# core: the scheduling / syscall / block / net / memory subset used in the
#       workshop study plus page faults, timers, signals, TCP. For measuring
#       what the full profile costs.
CORE_EVENTS = ['sched_*', 'block_*', 'net_*', 'netif_*', 'napi_*', 'skb_*', 'sock_*', 'tcp_*',
               'udp_*', 'irq_*', 'softirq_*', 'power_*', 'mm_vmscan_*', 'writeback_*',
               'mm_compaction_*', 'mm_migrate_*', 'x86_exceptions_page_fault_*', 'timer_*',
               'hrtimer_*', 'signal_*', 'cgroup_*', 'oom_*', 'task_*', 'lttng_statedump_*']
# Attached to every event. The first three are required and must come first (the
# analysis scripts read them in this order). The rest are added one by one and a
# kernel that lacks one is tolerated (7.0.0-1017-gcp rejects mnt_ns, for example).
CONTEXTS = ['pid', 'tid', 'procname']
EXTRA_CONTEXTS = ['ppid', 'prio', 'cgroup_ns', 'pid_ns', 'net_ns', 'mnt_ns']
# Hardware counters can ride along with every event, but ONLY on a machine with
# a PMU. Asking for them on a VM without one crashes the kernel (LTTng 2.15.3 on
# 7.0.0-1017-gcp), so they are off unless OSN_PERF=1 is set by hand.
PERF_CONTEXTS = (['perf:cpu:cpu-cycles', 'perf:cpu:instructions', 'perf:cpu:cache-misses']
                 if os.environ.get('OSN_PERF') == '1' else [])
SUBBUF = {'full': ('16M', '8'), 'core': ('8M', '8')}     # per-CPU buffer: size x count

CG_FILES = ['cpu.stat', 'cpu.pressure', 'cpu.max', 'cpu.weight', 'cpuset.cpus.effective',
            'memory.current', 'memory.peak', 'memory.stat', 'memory.events', 'memory.high',
            'memory.max', 'memory.pressure', 'memory.swap.current', 'memory.swap.max',
            'io.stat', 'io.pressure', 'io.max', 'pids.current', 'pids.peak', 'pids.max',
            'pids.events', 'cgroup.events', 'cgroup.stat', 'cgroup.procs']
PROC_FILES = ['/proc/stat', '/proc/meminfo', '/proc/vmstat', '/proc/net/dev', '/proc/diskstats',
              '/proc/interrupts', '/proc/softirqs', '/proc/schedstat', '/proc/loadavg',
              '/proc/pressure/cpu', '/proc/pressure/memory', '/proc/pressure/io',
              '/proc/net/snmp', '/proc/net/netstat']
RAPL = Path('/sys/class/powercap')


class Collector:
    def __init__(self, spec, out_root, dry):
        self.spec = spec
        self.dry = dry
        self.out = Path(out_root) / spec['run']
        self.meta = self.out / 'meta'
        self.n = spec['agents']
        self.grp = CG_ROOT / 'run'                  # the measured group
        self.work = Path.home() / 'osn-work' / spec['run']
        self.log = []                               # (seconds since start, step) for result.json
        self.t0 = time.monotonic()

    # ---- small helpers ----------------------------------------------------
    def sh(self, cmd, sudo=False, check=True, **kw):
        """Run a command (list). In a dry run, print it instead."""
        cmd = (['sudo', '-n'] if sudo else []) + [str(c) for c in cmd]
        if self.dry:
            print('  $', ' '.join(shlex.quote(c) for c in cmd))
            return subprocess.CompletedProcess(cmd, 0, '', '')
        r = subprocess.run(cmd, text=True, capture_output=True, **kw)
        if check and r.returncode:
            raise RuntimeError(f'FAILED ({r.returncode}): ' + ' '.join(cmd) + '\n' + r.stdout + r.stderr)
        return r

    def write_root(self, path, text):
        """Write a root-owned file (cgroup knobs, /proc/sys)."""
        if self.dry:
            print(f'  # {text!r} > {path}')
            return
        subprocess.run(['sudo', '-n', 'tee', str(path)], input=text, text=True,
                       check=True, stdout=subprocess.DEVNULL)

    def step(self, name):
        self.log.append((round(time.monotonic() - self.t0, 3), name))
        print(f'[{self.spec["run"]}] {name}', flush=True)

    def leaf(self, i):
        return self.grp / f'a{i}'

    # ---- 1. task repositories --------------------------------------------
    def make_tasks(self):
        self.step('tasks')
        if not self.dry:
            shutil.rmtree(self.work, ignore_errors=True)
            self.work.mkdir(parents=True)
        for i in range(1, self.n + 1):
            self.sh(['bash', HERE / 'tasks' / self.spec['task'], self.work / f'a{i}'],
                    env=dict(os.environ, TASK_ARG=str(self.spec['task_arg'])))
        return 'DRY RUN PROMPT' if self.dry else (self.work / 'a1/.prompt').read_text()

    # ---- 2. cgroups and limits -------------------------------------------
    def make_cgroups(self):
        self.step('cgroups')
        self.remove_cgroups()
        self.write_root('/sys/fs/cgroup/cgroup.subtree_control', CONTROLLERS)
        for d in (CG_ROOT, self.grp, CG_ROOT / 'col', CG_ROOT / 'nb'):
            self.sh(['mkdir', '-p', d], sudo=True)
        self.write_root(CG_ROOT / 'cgroup.subtree_control', CONTROLLERS)
        self.write_root(self.grp / 'cgroup.subtree_control', CONTROLLERS)
        for i in range(1, self.n + 1):
            self.sh(['mkdir', '-p', self.leaf(i)], sudo=True)
            if self.spec['runtime'] == 'docker':      # the container's cgroup is a child of the leaf
                self.write_root(self.leaf(i) / 'cgroup.subtree_control', CONTROLLERS)
        targets = [self.grp] if self.spec['limit_scope'] == 'group' else \
                  [self.leaf(i) for i in range(1, self.n + 1)]
        lim = self.spec['limits']
        for cg in targets:
            for key, fname in (('cpu_max', 'cpu.max'), ('cpu_weight', 'cpu.weight'),
                               ('cpuset', 'cpuset.cpus'), ('memory_high', 'memory.high'),
                               ('memory_max', 'memory.max'), ('memory_swap_max', 'memory.swap.max'),
                               ('pids_max', 'pids.max')):
                if lim.get(key) not in (None, ''):
                    self.write_root(cg / fname, str(lim[key]))
            if lim.get('io_max'):
                dev = 'MAJ:MIN' if self.dry else self.block_device()
                self.write_root(cg / 'io.max', dev + ' ' + ' '.join(
                    f'{k}={v}' for k, v in lim['io_max'].items()))
        if self.spec['tool_guard'] == 'cgroup':
            # agent and tools in two children of the leaf (a cgroup with children holds no
            # processes itself); the leaf keeps the limits, the tools get their own memory.max
            leaf = self.leaf(1)
            self.write_root(leaf / 'cgroup.subtree_control', CONTROLLERS)
            for d in (leaf / 'agent', leaf / 'tools'):
                self.sh(['mkdir', '-p', d], sudo=True)
            self.write_root(leaf / 'tools' / 'memory.max', str(self.spec['tool_memory_max']))
            # a tool shell moves itself: it needs to write cgroup.procs here and in the parent
            self.sh(['chown', f'{os.getuid()}:{os.getgid()}', leaf / 'cgroup.procs',
                     leaf / 'agent' / 'cgroup.procs', leaf / 'tools' / 'cgroup.procs'], sudo=True)

    def tool_guard(self):
        """Lines for the file that every non-interactive bash sources (BASH_ENV), that is,
        every shell the agent starts for a tool. The agent itself is not bash."""
        log = shlex.quote(str(self.meta / 'tool_guard.log'))
        act = ('echo 1000 > /proc/$$/oom_score_adj' if self.spec['tool_guard'] == 'oom_adj' else
               f'echo $$ > {self.leaf(1)}/tools/cgroup.procs')
        return f'{act} 2>/dev/null && echo $$ >> {log}\n'

    def remove_cgroups(self):
        # leaves first; a cgroup can only be removed when empty
        self.sh(['bash', '-c', f'[ -d {CG_ROOT} ] && find {CG_ROOT} -depth -type d -exec rmdir {{}} \\; ; true'],
                sudo=True, check=False)

    def block_device(self):
        """MAJ:MIN of the disk that holds the work directory."""
        src = subprocess.run(['df', '--output=source', str(Path.home())], text=True,
                             capture_output=True).stdout.split()[-1]
        disk = subprocess.run(['lsblk', '-no', 'PKNAME', src], text=True,
                              capture_output=True).stdout.split()
        dev = f'/dev/{disk[0]}' if disk else src
        return subprocess.run(['lsblk', '-dno', 'MAJ:MIN', dev], text=True,
                              capture_output=True).stdout.split()[0]

    # ---- 3. network namespace with impairment ----------------------------
    def make_netns(self):
        net = self.spec['net']
        if net is None:
            return
        self.step('netns')
        self.remove_netns()
        s = lambda *c: self.sh(c, sudo=True)
        s('ip', 'netns', 'add', NETNS)
        s('ip', 'link', 'add', 'osn0', 'type', 'veth', 'peer', 'name', 'osn1')
        s('ip', 'link', 'set', 'osn1', 'netns', NETNS)
        s('ip', 'addr', 'add', '10.200.0.1/24', 'dev', 'osn0')
        s('ip', 'link', 'set', 'osn0', 'up')
        s('ip', 'netns', 'exec', NETNS, 'ip', 'addr', 'add', '10.200.0.2/24', 'dev', 'osn1')
        s('ip', 'netns', 'exec', NETNS, 'ip', 'link', 'set', 'osn1', 'up')
        s('ip', 'netns', 'exec', NETNS, 'ip', 'link', 'set', 'lo', 'up')
        s('ip', 'netns', 'exec', NETNS, 'ip', 'route', 'add', 'default', 'via', '10.200.0.1')
        s('sysctl', '-qw', 'net.ipv4.ip_forward=1')
        s('iptables', '-t', 'nat', '-A', 'POSTROUTING', '-s', '10.200.0.0/24', '-j', 'MASQUERADE')
        # the host resolver listens on host loopback, which the namespace cannot reach
        s('mkdir', '-p', f'/etc/netns/{NETNS}')
        self.write_root(f'/etc/netns/{NETNS}/resolv.conf', 'nameserver 169.254.169.254\nnameserver 8.8.8.8\n')
        # the same impairment in both directions: agent->world on osn1, world->agent on osn0
        netem = []
        if net.get('delay_ms'):
            netem += ['delay', f"{net['delay_ms']}ms"] + ([f"{net['jitter_ms']}ms"] if net.get('jitter_ms') else [])
        if net.get('loss_pct'):
            netem += ['loss', f"{net['loss_pct']}%"]
        if net.get('rate_kbit'):
            netem += ['rate', f"{net['rate_kbit']}kbit"]
        if netem:
            s('tc', 'qdisc', 'add', 'dev', 'osn0', 'root', 'netem', *netem)
            s('ip', 'netns', 'exec', NETNS, 'tc', 'qdisc', 'add', 'dev', 'osn1', 'root', 'netem', *netem)

    def remove_netns(self):
        self.sh(['iptables', '-t', 'nat', '-D', 'POSTROUTING', '-s', '10.200.0.0/24', '-j', 'MASQUERADE'],
                sudo=True, check=False)
        self.sh(['ip', 'link', 'del', 'osn0'], sudo=True, check=False)
        self.sh(['ip', 'netns', 'del', NETNS], sudo=True, check=False)

    # ---- 4. snapshots -----------------------------------------------------
    def snapshot(self, tag):
        """Copy every counter we can read into meta/<tag>/."""
        self.step(f'snapshot {tag}')
        if self.dry:
            return
        d = self.meta / tag
        d.mkdir(parents=True, exist_ok=True)
        groups = {'group': self.grp, **{f'a{i}': self.leaf(i) for i in range(1, self.n + 1)},
                  'neighbour': CG_ROOT / 'nb', 'collector': CG_ROOT / 'col'}
        for name, cg in groups.items():
            (d / name).mkdir(exist_ok=True)
            for f in CG_FILES:
                try:
                    (d / name / f).write_text((cg / f).read_text())
                except OSError:
                    pass                                   # controller file not present
        for f in PROC_FILES:
            try:
                (d / f.strip('/').replace('/', '_')).write_text(Path(f).read_text())
            except OSError:
                pass
        energy = {}
        for z in RAPL.glob('intel-rapl*') if RAPL.exists() else []:
            try:      # energy counters are root-readable on recent kernels
                energy[z.name] = int(subprocess.run(['sudo', '-n', 'cat', str(z / 'energy_uj')],
                                                    text=True, capture_output=True).stdout)
            except ValueError:
                pass
        (d / 'energy_uj.json').write_text(json.dumps(energy))
        # The same counters again under the flat names the Phase 1 analysis reads. With one
        # agent they come from the agent's own cgroup: throttling and memory events are
        # counted where the limit is set, and the parent group does not repeat them.
        src = d / ('a1' if self.n == 1 else 'group')
        for f in ('cpu.stat', 'memory.stat', 'memory.events', 'io.stat'):
            if (src / f).exists():
                shutil.copy(src / f, self.meta / f'{f}.{tag}')
        if tag == 'after' and (src / 'memory.peak').exists():
            shutil.copy(src / 'memory.peak', self.meta / 'memory.peak')
        self.anchor(tag, 'snapshot_anchors.jsonl')

    def anchor(self, label, fname='clock_anchors.jsonl'):
        """The same instant on three clocks, to line up trace, samples and agent events.
        clock_anchors.jsonl holds exactly two rows: agents start, agents end."""
        row = dict(label=label, realtime=time.clock_gettime(time.CLOCK_REALTIME),
                   monotonic=time.clock_gettime(time.CLOCK_MONOTONIC),
                   boottime=time.clock_gettime(time.CLOCK_BOOTTIME))
        with open(self.meta / fname, 'a') as f:
            f.write(json.dumps(row) + '\n')

    def versions(self):
        self.step('versions')
        if self.dry:
            return
        def out(*c):
            try:
                return subprocess.run(c, text=True, capture_output=True, timeout=30).stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                return ''
        v = dict(kernel=out('uname', '-r'), uname=out('uname', '-a'), nproc=os.cpu_count(),
                 host=out('hostname'), lttng=out('lttng', '--version'),
                 babeltrace2=out('babeltrace2', '--version').splitlines()[:1],
                 claude=out(self.agent_bin('claude'), '--version'),
                 codex=out(self.agent_bin('codex'), '--version'), python=sys.version.split()[0],
                 os_release=Path('/etc/os-release').read_text(), cmdline=Path('/proc/cmdline').read_text(),
                 swaps=Path('/proc/swaps').read_text(), lscpu=out('lscpu'),
                 docker=out('sudo', '-n', 'docker', 'version', '--format', '{{.Server.Version}}'),
                 docker_image=out('sudo', '-n', 'docker', 'image', 'inspect', '-f', '{{.Id}}', DOCKER_IMAGE),
                 collector_git=out('git', '-C', str(HERE), 'rev-parse', 'HEAD'),
                 collector_dirty=bool(out('git', '-C', str(HERE), 'status', '--porcelain', '.')),
                 # works without git too: one hash over the collector's own code and tasks
                 collector_sha256=hashlib.sha256(b''.join(
                     p.read_bytes() for p in sorted(HERE.glob('*.py')) + sorted((HERE / 'tasks').glob('*.sh'))
                 )).hexdigest(),
                 rapl=sorted(z.name for z in RAPL.glob('intel-rapl*')) if RAPL.exists() else [])
        (self.meta / 'versions.json').write_text(json.dumps(v, indent=1))

    # ---- 5. tracing -------------------------------------------------------
    def trace_start(self):
        prof = self.spec['trace']
        if prof == 'none':
            return
        self.step(f'trace start ({prof})')
        s = lambda *c, **k: self.sh(c, sudo=True, **k)
        ses = self.spec['run']
        s('lttng', 'destroy', ses, check=False)
        s('lttng', 'create', ses, f'--output={self.out / "trace"}')
        size, count = SUBBUF[prof]
        s('lttng', 'enable-channel', '-k', 'ch', f'--subbuf-size={size}', f'--num-subbuf={count}')
        s('lttng', 'enable-event', '-k', '-c', 'ch', '--syscall', '--all')
        if prof == 'full':
            s('lttng', 'enable-event', '-k', '-c', 'ch', '--tracepoint', '--all')
        else:
            for pat in CORE_EVENTS:
                s('lttng', 'enable-event', '-k', '-c', 'ch', '--tracepoint', pat, check=False)
        s('lttng', 'add-context', '-k', '-c', 'ch', *sum((['-t', c] for c in CONTEXTS), []))
        for c in EXTRA_CONTEXTS + PERF_CONTEXTS:
            s('lttng', 'add-context', '-k', '-c', 'ch', '-t', c, check=False)
        r = s('lttng', 'list', ses)
        if not self.dry:
            (self.meta / 'lttng_enabled.txt').write_text(r.stdout)
        s('lttng', 'start')

    def trace_stop(self):
        if self.spec['trace'] == 'none':
            return
        self.step('trace stop')
        ses = self.spec['run']
        self.sh(['lttng', 'stop'], sudo=True)
        r = self.sh(['lttng', 'list', ses, '-k', '-c', 'ch'], sudo=True, check=False)
        if not self.dry:      # holds the channel statistics: discarded events, lost packets
            (self.meta / 'lttng_stats.txt').write_text(r.stdout + r.stderr)
        self.sh(['lttng', 'destroy', ses], sudo=True)

    def trace_decode(self):
        if self.spec['trace'] == 'none':
            return
        self.step('trace decode')
        self.sh(['chown', '-R', f'{os.getuid()}:{os.getgid()}', self.out], sudo=True)
        if self.dry:
            return
        with open(self.out / 'trace.txt.gz', 'wb') as gz, open(self.meta / 'babeltrace_stderr.txt', 'wb') as err:
            bt = subprocess.Popen(['babeltrace2', '--clock-gmt', str(self.out / 'trace')],
                                  stdout=subprocess.PIPE, stderr=err)
            subprocess.run(['gzip', '-c'], stdin=bt.stdout, stdout=gz, check=True)
            bt.wait()

    # ---- 6. agents --------------------------------------------------------
    def agent_bin(self, agent):
        if agent == 'claude':
            return os.environ.get('CLAUDE_BIN', str(Path.home() / '.local/bin/claude'))
        return shutil.which('codex') or 'codex'

    def agent_cmd(self, prompt):
        a, model = self.spec['agent'], self.spec['model']
        if a == 'claude':     # stream-json gives one JSON event per line: turns, tool calls, usage
            cmd = [self.agent_bin('claude'), '-p', prompt, '--output-format', 'stream-json',
                   '--verbose', '--dangerously-skip-permissions']
            return cmd + (['--model', model] if model else [])
        if a == 'codex':
            cmd = [self.agent_bin('codex'), 'exec', '--json', '--skip-git-repo-check',
                   '--dangerously-bypass-approvals-and-sandbox']
            return cmd + (['-m', model] if model else []) + [prompt]
        if a == 'fake':
            return ['bash', '-c', self.spec['fake_cmd']]
        raise ValueError(f'unknown agent {a}')

    def launcher(self, prompt):
        """A bash script that starts every agent inside its own cgroup.
        The script's own pid is the root of the process tree for the analysis."""
        cmd = ' '.join(shlex.quote(c) for c in ['timeout', str(self.spec['timeout_s'])] + self.agent_cmd(prompt))
        if self.spec['net'] is not None:
            # enter the namespace as root, then drop back to this user. `ip netns exec` (not
            # nsenter) because it also swaps in the namespace's resolv.conf.
            cmd = (f'sudo -n -E ip netns exec {NETNS} setpriv --reuid={os.getuid()} '
                   f'--regid={os.getgid()} --init-groups -- ' + cmd)
        lines = ['#!/bin/bash', f'echo $$ > {shlex.quote(str(self.meta / "root.pid"))}',
                 '[ -f "$HOME/.codex-env" ] && { set -a; . "$HOME/.codex-env"; set +a; }']
        if self.spec['runtime'] == 'docker':
            return self.docker_launcher(lines, cmd)
        if self.spec['tool_guard']:
            guard = self.meta / 'tool_guard.sh'
            if not self.dry:
                guard.write_text(self.tool_guard())
            lines += [f'export BASH_ENV={shlex.quote(str(guard))}']
        for i in range(1, self.n + 1):
            a, w, cg = self.out / f'a{i}', self.work / f'a{i}', self.leaf(i)
            if self.spec['tool_guard'] == 'cgroup':
                cg = cg / 'agent'
            lines += ['(',
                      '  pid=$BASHPID',      # $BASHPID, not $$: this subshell is what enters the cgroup
                      f'  echo $pid | sudo -n tee {cg}/cgroup.procs >/dev/null',
                      f'  echo $pid > {shlex.quote(str(a / "root.pid"))}',
                      f'  cd {shlex.quote(str(w))} && exec {cmd}',
                      f') > {shlex.quote(str(a / "out.fifo"))} 2> {shlex.quote(str(a / "agent.stderr"))} &',
                      f'pids[{i}]=$!']
        for i in range(1, self.n + 1):
            lines += [f'wait ${{pids[{i}]}}; echo $? > {shlex.quote(str(self.out / f"a{i}" / "exit_code"))}']
        return '\n'.join(lines) + '\n'

    def docker_launcher(self, lines, cmd):
        """Every agent in its own container, whose cgroup docker creates under the
        agent's leaf, so the leaf's limits apply as in a host run. The docker client
        stays outside the measured group. The process tree root for the analysis is
        the container's first process (its init), found with docker inspect; with
        one agent it also replaces the launcher pid in meta/root.pid."""
        q = shlex.quote
        home = Path.home()
        for i in range(1, self.n + 1):
            a, w, name = self.out / f'a{i}', self.work / f'a{i}', f'osn-a{i}'
            vols = sum((['-v', f'{home / p}:{home / p}:{m}'] for p, m in DOCKER_MOUNTS), [])
            run = ['sudo', '-n', 'docker', 'run', '--rm', '--init', '--name', name,
                   f'--cgroup-parent=/{self.leaf(i).relative_to("/sys/fs/cgroup")}',
                   '--user', f'{os.getuid()}:{os.getgid()}', '-e', f'HOME={home}',
                   '-v', f'{w}:{w}:rw', *vols, '-w', str(w), DOCKER_IMAGE]
            roots = [a / 'root.pid'] + ([self.meta / 'root.pid'] if self.n == 1 else [])
            lines += [f'sudo -n docker rm -f {name} >/dev/null 2>&1',
                      f'( exec {" ".join(q(str(c)) for c in run)} {cmd} ) '
                      f'> {q(str(a / "out.fifo"))} 2> {q(str(a / "agent.stderr"))} &',
                      f'pids[{i}]=$!',
                      # poll until the container's init exists; give up when the client has ended
                      f'( while kill -0 ${{pids[{i}]}} 2>/dev/null; do',
                      f'    p=$(sudo -n docker inspect -f "{{{{.State.Pid}}}}" {name} 2>/dev/null)',
                      f'    [ -n "$p" ] && [ "$p" -gt 0 ] && {{ for f in {" ".join(q(str(r)) for r in roots)}; '
                      f'do echo $p > $f; done; break; }}',
                      '    sleep 0.05; done ) &']
        for i in range(1, self.n + 1):
            lines += [f'wait ${{pids[{i}]}}; echo $? > {shlex.quote(str(self.out / f"a{i}" / "exit_code"))}']
        return '\n'.join(lines) + '\n'

    def stamp(self, fifo, dest):
        """Copy an agent's output line by line, adding the arrival time."""
        with open(fifo, 'rb') as src, open(dest, 'w') as out:
            for raw in src:
                out.write(json.dumps(dict(realtime=time.clock_gettime(time.CLOCK_REALTIME),
                                          monotonic=time.clock_gettime(time.CLOCK_MONOTONIC),
                                          line=raw.decode('utf-8', 'replace').rstrip('\n'))) + '\n')
                out.flush()

    def run_agents(self, prompt):
        self.step('agents start')
        script = self.launcher(prompt)
        if self.dry:
            print('  --- launcher.sh ---\n' + script + '  -------------------')
            return
        (self.meta / 'launcher.sh').write_text(script)
        readers = []
        for i in range(1, self.n + 1):
            a = self.out / f'a{i}'
            a.mkdir(exist_ok=True)
            os.mkfifo(a / 'out.fifo')
            th = threading.Thread(target=self.stamp, args=(a / 'out.fifo', a / 'events.jsonl'))
            th.start()
            readers.append(th)
        self.anchor('start')
        subprocess.run(['bash', str(self.meta / 'launcher.sh')])
        self.anchor('end')
        for th in readers:
            th.join()
        for i in range(1, self.n + 1):
            (self.out / f'a{i}' / 'out.fifo').unlink()
        self.step('agents done')

    # ---- helpers that run next to the agents ------------------------------
    def start_side(self, name, cmd, cg):
        """Start a helper process (sampler, neighbour) inside its own cgroup."""
        line = ' '.join(shlex.quote(str(c)) for c in cmd)
        if self.dry:
            print('  $ (in', cg, ')', line)
            return None
        # join the cgroup first, then exec, so every child starts inside it
        wrapped = f'echo $$ | sudo -n tee {cg}/cgroup.procs >/dev/null; exec {line}'
        return subprocess.Popen(['bash', '-c', wrapped], stdout=subprocess.DEVNULL,
                                stderr=open(self.meta / f'{name}.stderr', 'w'))

    def neighbour_cmd(self):
        nb = self.spec['neighbour']
        kind, w = nb.get('kind', 'cpu'), str(nb.get('workers', os.cpu_count()))
        return ['stress-ng', {'cpu': '--cpu', 'vm': '--vm', 'io': '--hdd'}[kind], w, '--timeout', '0']

    # ---- 7. result --------------------------------------------------------
    def check_tasks(self):
        self.step('check')
        res = []
        for i in range(1, self.n + 1):
            a, w = self.out / f'a{i}', self.work / f'a{i}'
            if self.dry:
                continue
            chk = subprocess.run(['bash', '.check'], cwd=w, text=True, capture_output=True)
            (a / 'task_check.txt').write_text(chk.stdout + chk.stderr)
            git = lambda *c: subprocess.run(['git', *c], cwd=w, text=True, capture_output=True).stdout
            (a / 'agent.patch').write_text(git('diff', 'HEAD'))
            (a / 'agent_untracked.txt').write_text(git('status', '--porcelain'))
            tampered = bool(git('diff', '--name-only', 'HEAD', '--', 'test_*.py').strip())
            code = (a / 'exit_code').read_text().strip() if (a / 'exit_code').exists() else ''
            res.append(dict(agent=f'a{i}', agent_exit=int(code) if code.lstrip('-').isdigit() else None,
                            task_check_exit=chk.returncode, test_file_tampered=tampered))
        return res

    def finish(self, agents, t_start, t_end):
        s = self.spec
        lim = s['limits']
        mem = (f"high:{lim['memory_high']}" if lim.get('memory_high') else
               f"max:{lim['memory_max']}" if lim.get('memory_max') else '')
        io = ' '.join(f'{k}:{v}' for k, v in (lim.get('io_max') or {}).items())
        first = agents[0] if agents else {}
        result = dict(run=s['run'], spec=s, agents=agents, wall_s=round(t_end - t_start, 3),
                      steps=self.log, ok=all(a['task_check_exit'] == 0 for a in agents))
        (self.out / 'result.json').write_text(json.dumps(result, indent=1))
        # the keys the Phase 1 analysis scripts read, for the first agent
        legacy = dict(run=s['run'], task=s['task'], cpu_max=lim.get('cpu_max', 'max'),
                      task_arg=str(s['task_arg']), mem_limit=mem, io_limit=io, agent=s['agent'],
                      agent_exit=first.get('agent_exit'), task_check_exit=first.get('task_check_exit'),
                      test_file_tampered=first.get('test_file_tampered'))
        (self.meta / 'ground_truth.json').write_text(json.dumps(legacy, indent=1))

    def checksums(self):
        self.step('checksums')
        if self.dry:
            return
        with open(self.out / 'SHA256SUMS', 'w') as f:
            for p in sorted(self.out.rglob('*')):
                if p.is_file() and p.name != 'SHA256SUMS':
                    h = hashlib.sha256()
                    with open(p, 'rb') as src:
                        for block in iter(lambda: src.read(1 << 20), b''):
                            h.update(block)
                    f.write(f'{h.hexdigest()}  {p.relative_to(self.out).as_posix()}\n')

    # ---- the run ----------------------------------------------------------
    def run(self):
        s = self.spec
        if not self.dry:
            if self.out.exists():
                sys.exit(f'{self.out} exists. Remove it or pick another run name.')
            self.meta.mkdir(parents=True)
            (self.out / 'spec.json').write_text(json.dumps(s, indent=1))
        sampler = neighbour = None
        agents, t_start, t_end = [], 0.0, 0.0
        try:
            prompt = self.make_tasks()
            self.versions()
            self.make_cgroups()
            self.make_netns()
            if s['cache'] == 'cold':
                self.step('drop caches')
                self.sh(['sync'])
                self.write_root('/proc/sys/vm/drop_caches', '3')
            self.snapshot('before')
            self.trace_start()
            if s['sample_hz']:
                sampler = self.start_side('sampler', [sys.executable, HERE / 'sampler.py', self.grp,
                                                      self.out / 'samples.jsonl', s['sample_hz']],
                                          CG_ROOT / 'col')
            if s['neighbour']:
                neighbour = self.start_side('neighbour', self.neighbour_cmd(), CG_ROOT / 'nb')
                time.sleep(0 if self.dry else 2)          # let it reach steady state
            t_start = time.monotonic()
            self.run_agents(prompt)
            t_end = time.monotonic()
        finally:
            for p in (neighbour, sampler):
                if p:
                    p.terminate()
                    try:
                        p.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        p.kill()
            self.trace_stop()
            if not self.dry and self.meta.exists():
                self.snapshot('after')
            self.remove_netns() if s['net'] is not None else None
        agents = self.check_tasks()
        if not self.dry:
            self.finish(agents, t_start, t_end)
        self.trace_decode()
        self.checksums()
        self.step('done')
        if not self.dry:
            print(f'[{s["run"]}] ok={all(a["task_check_exit"] == 0 for a in agents)} '
                  f'wall={t_end - t_start:.1f}s -> {self.out}')


def fill_spec(raw):
    """Defaults + validation. Raises ValueError with a readable message."""
    unknown = set(raw) - set(SPEC_DEFAULTS)
    if unknown:
        raise ValueError(f'unknown spec keys: {sorted(unknown)}')
    spec = {**SPEC_DEFAULTS, **raw}
    for key in ('run', 'task'):
        if not spec[key]:
            raise ValueError(f'spec needs "{key}"')
    if not (HERE / 'tasks' / spec['task']).exists():
        raise ValueError(f'no such task: tasks/{spec["task"]}')
    if spec['agent'] not in ('claude', 'codex', 'fake'):
        raise ValueError(f'agent must be claude, codex or fake, not {spec["agent"]!r}')
    if spec['trace'] not in ('full', 'core', 'none'):
        raise ValueError(f'trace must be full, core or none, not {spec["trace"]!r}')
    if spec['cache'] not in ('cold', 'warm'):
        raise ValueError('cache must be cold or warm')
    if spec['limit_scope'] not in ('each', 'group'):
        raise ValueError('limit_scope must be each or group')
    if not isinstance(spec['agents'], int) or spec['agents'] < 1:
        raise ValueError('agents must be a positive integer')
    known = {'cpu_max', 'cpu_weight', 'cpuset', 'memory_high', 'memory_max', 'memory_swap_max',
             'pids_max', 'io_max'}
    bad = set(spec['limits']) - known
    if bad:
        raise ValueError(f'unknown limits: {sorted(bad)}')
    if spec['limits'].get('io_max') and set(spec['limits']['io_max']) - {'rbps', 'wbps', 'riops', 'wiops'}:
        raise ValueError('io_max keys must be rbps, wbps, riops, wiops')
    if spec['net'] is not None and set(spec['net']) - {'delay_ms', 'jitter_ms', 'loss_pct', 'rate_kbit'}:
        raise ValueError('net keys must be delay_ms, jitter_ms, loss_pct, rate_kbit')
    if spec['runtime'] not in ('host', 'docker'):
        raise ValueError('runtime must be host or docker')
    if spec['runtime'] == 'docker' and spec['net'] is not None:
        raise ValueError('runtime docker uses docker networking; net impairment is host only')
    if spec['tool_guard'] not in (None, 'oom_adj', 'cgroup'):
        raise ValueError('tool_guard must be oom_adj or cgroup')
    if spec['tool_guard'] and (spec['runtime'] != 'host' or spec['agents'] != 1):
        raise ValueError('tool_guard needs the host runtime and one agent')
    if spec['tool_guard'] == 'cgroup' and not spec['tool_memory_max']:
        raise ValueError('tool_guard cgroup needs tool_memory_max')
    if any(c in spec['run'] for c in '/ \t'):
        raise ValueError('run name must not contain spaces or slashes')
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('spec', help='run spec (JSON file)')
    ap.add_argument('--out', default=str(Path.home() / 'osn-runs'), help='where run folders go')
    ap.add_argument('--dry-run', action='store_true', help='print the commands, change nothing')
    args = ap.parse_args()
    try:
        spec = fill_spec(json.loads(Path(args.spec).read_text()))
    except ValueError as e:
        sys.exit(f'bad spec: {e}')
    Collector(spec, args.out, args.dry_run).run()
