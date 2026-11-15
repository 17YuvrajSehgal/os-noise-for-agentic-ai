# Collector (version 2)

Runs AI coding agents under container limits and records everything the
kernel and the agent can tell us about the run. Written from scratch for
the extended study. The workshop collector stays where it was
(`latency/1_svc_cpu_cap/agentic-os-noise/collection/`) as a record of how
the first 262 runs were made.

Why it was rewritten, and every design decision: `DESIGN.md`.

## Files

| File | Role |
|---|---|
| `vm_setup.sh` | One-time setup of a fresh VM: tracer, tools, quiet machine, pinned kernel, checks, machine snapshot |
| `collect.py` | One run, described by a JSON spec |
| `sampler.py` | Time series of the cgroup tree during a run (started by `collect.py`) |
| `campaign.py` | One experiment: a grid of specs, repetitions, random order, resumable |
| `campaigns/*.json` | The experiments |
| `tasks/*.sh` | What the agent is asked to do. Each builds a fresh repository with a `.prompt` and a `.check` |
| `test_collector.py` | Checks that need no VM: `python3 test_collector.py` |
| `docker/` | Image for `runtime: docker` runs (`bash docker/build.sh` once) |
| `swe/` | Real tasks from SWE-bench Verified: `setup_task.py` prepares them once, `check.py` is their success check |

Python 3 standard library only. The real tasks (`tasks/swe.sh`) also need
`uv` and a tools environment: `python3 -m venv ~/osn-tools && ~/osn-tools/bin/pip
install pandas pyarrow swebench==3.0.15`, then
`~/osn-tools/bin/python swe/setup_task.py <instance_id> ...` (download the
dataset to `~/osn-swe/verified.parquet` first; the command is in the script).

## Quick start on the VM

```bash
bash vm_setup.sh                                   # once
# sign in Claude Code and Codex by hand (the script prints how)
python3 campaign.py campaigns/smoke_fake.json      # collector test, no agent, no API cost
python3 campaign.py campaigns/smoke.json           # one real run per agent
python3 campaign.py campaigns/cpu.json             # a whole experiment
python3 campaign.py campaigns/cpu.json --list      # only print the planned runs
python3 collect.py spec.json --dry-run             # print every command of one run
```

Runs go to `~/osn-runs/<campaign>/<run>/`. A campaign can be stopped and
started again; finished runs are skipped.

## What one run holds

```
<run>/
├── spec.json            the run as asked for, defaults filled in
├── result.json          exit codes, task check, wall time, timing of each collector step
├── trace/               raw kernel trace (CTF). Never deleted
├── trace.txt.gz         the trace decoded to text
├── samples.jsonl        time series, 5 per second: CPU, throttling, memory, processes,
│                        I/O bytes, pressure, per agent and for the group
├── SHA256SUMS
├── meta/
│   ├── before/ after/   every counter, before and after the run:
│   │                    group/ a1/ ... (cgroup files), proc_* (machine), energy_uj.json
│   ├── clock_anchors.jsonl   agents start and end, each on three clocks
│   ├── snapshot_anchors.jsonl  when the before and after counters were read
│   ├── versions.json    kernel, tracer, agents, CPU, collector commit
│   ├── lttng_enabled.txt     what was traced
│   ├── lttng_stats.txt       discarded events and lost packets of this trace
│   ├── babeltrace_stderr.txt warnings from decoding
│   ├── launcher.sh      the exact script that started the agents
│   ├── root.pid         root of the agents' process tree
│   └── ground_truth.json     the keys the Phase 1 analysis scripts read
└── a1/ (a2/ ...)        one per agent
    ├── events.jsonl     the agent's JSON event stream, one line per event,
    │                    each with its arrival time on two clocks
    ├── agent.stderr  exit_code  root.pid
    ├── task_check.txt   output of the task's success check
    └── agent.patch      everything the agent changed
```

## The spec

Every key is optional except `run` and `task`.

| Key | Default | Meaning |
|---|---|---|
| `run` | | Run name, used as the folder name |
| `task` | | Script in `tasks/` |
| `task_arg` | `""` | Passed to the task (worker count, file size, ...) |
| `agent` | `claude` | `claude`, `codex`, or `fake` (runs `fake_cmd`, for testing) |
| `model` | agent default | Model name passed to the agent |
| `agents` | 1 | Agents running at the same time, each in its own cgroup and repository |
| `limits` | `{}` | `cpu_max`, `cpu_weight`, `cpuset`, `memory_high`, `memory_max`, `memory_swap_max`, `pids_max`, `io_max` (`rbps`, `wbps`, `riops`, `wiops`) |
| `limit_scope` | `each` | `each`: every agent gets the limits. `group`: all agents share them |
| `net` | none | `{delay_ms, jitter_ms, loss_pct, rate_kbit}`. Puts the agents in a network namespace and impairs both directions. `{}` = namespace with no impairment (the control). `delay_ms` is one way, so a round trip grows by twice that |
| `neighbour` | none | `{kind: cpu, vm or io, workers}`: a busy process outside the agents' group |
| `runtime` | `host` | `docker`: each agent runs in a container whose cgroup docker creates under the agent's own cgroup, so the same limits apply. Needs docker with the `cgroupfs` driver. `root.pid` is then the container's first process |
| `trace` | `full` | `full`: every kernel tracepoint and system call. `core`: the main subset. `none` |
| `cache` | `cold` | `cold`: drop the page cache before the run. `warm`: leave it |
| `sample_hz` | 5 | Sampler rate. 0 = off |
| `timeout_s` | 900 | Per agent |

## The experiments

| Campaign | Question | Runs |
|---|---|---|
| `smoke_fake`, `smoke` | Does the collector work? | 4, 2 |
| `overhead` | What does tracing itself cost? (none, core, full) | 30 |
| `cpu` | CPU quota, six steps from unlimited to 0.25 core | 120 |
| `threads` | More workers than cores | 40 |
| `subagents` | Does the agent over-subscribe on its own? | 40 |
| `memory_soft`, `memory_hard_file`, `memory_cliff` | Soft limit, hard limit on file memory, the OOM cliff in fine steps | 50, 40, 90 |
| `disk` | Disk read limit | 60 |
| `e2e_memory`, `e2e_disk` | The coding task under memory and disk limits | 90, 40 |
| `network` | Delay, loss, bandwidth | 80 |
| `pids` | Process-count limit | 70 |
| `density` | 1 to 32 agents on one machine | 36 |
| `two_limits` | Two limits at once | 40 |
| `neighbour` | A busy neighbour | 50 |
| `real` | Six SWE-bench Verified tasks in a container at four platform settings (RQ3) | 120 |
| `real_host` | The same tasks with no limit and no container (what the container costs) | 30 |
| `real_quarter` | The same tasks in a container at 0.25 CPU / 512 MiB (Fargate minimum) | 30 |

About 880 runs in all. Order within a campaign is random with a fixed seed.

## Before the first campaign

These cannot be tested without the VM. Check each on the smoke runs:

1. `meta/lttng_stats.txt` reports no discarded events with the `full`
   profile. If it does, raise the buffer size in `collect.py` (`SUBBUF`).
2. `a1/events.jsonl` has many lines for both agents. If it has one line,
   the agent's streaming flags changed in its version.
3. Size of `trace/` and `trace.txt.gz` for one run, times 880, fits the
   disk. Copy finished campaigns off the VM before deleting anything.
4. A `network` run with `net: {}` reaches the model (name lookup works
   inside the namespace).
5. A `disk` run shows the limit in `meta/before/a1/io.max`.
6. `vm_setup.sh` printed whether hardware counters and the energy counter
   are available. On a normal cloud VM both are usually "no".

## Getting the data off the VM

The Codex raw traces of the workshop study were lost with the VM. Do not
repeat that:

```bash
# on the VM, after each campaign
tar -C ~/osn-runs -cf - cpu | zstd -T0 -o cpu.tar.zst && sha256sum cpu.tar.zst
gcloud storage cp cpu.tar.zst gs://<bucket>/osn/
```

Delete a campaign from the VM only after the copy is verified.
