# Collector design

Written 2026-11-10. Why the collector was rebuilt and what each choice is
for. The finding numbers (F..) refer to `phase1/results/FINDINGS.md`.

## Goals

1. **A dataset others can reuse.** Record everything once, so later
   questions (ours or anyone's) do not need new runs.
2. **Results that hold up in review.** Every number must be checkable
   against an independent source, and the cost of measuring must be known.
3. **No silent loss.** The workshop study lost its Codex raw traces, ran on
   two kernels without noticing, and could not check lost events for half
   its runs (F7, F8, F10).

## Decisions

### Trace everything (`trace: full`)

Every kernel tracepoint and every system call, with process, thread,
parent, priority and namespace attached to each event.

- **Why**: Phase 1 showed the workshop profile was wide enough for our own
  questions, but it missed page faults, timers, signals, TCP state and
  memory allocation. A reusable dataset should not depend on what we
  thought to ask.
- **Cost, and how we bound it**: a full trace is larger and slows the
  machine more. The `overhead` campaign measures this directly (no trace,
  core subset, full), so the paper can state the cost instead of assuming
  it is small. Buffers are 16 MB x 8 per CPU to avoid dropped events, and
  the tracer's own statistics are saved for every run.
- **If the full profile disturbs the agent too much**: the `core` profile
  is one spec key away. The decision is made from the `overhead` numbers,
  not in advance.

### Three independent views of every run

| View | File | Good for |
|---|---|---|
| Kernel trace | `trace/`, `trace.txt.gz` | Mechanism: who waited, for what, for how long |
| Counters, before and after | `meta/before`, `meta/after` | Ground truth totals from the kernel's own accounting |
| Time series, 5 Hz | `samples.jsonl` | Peaks and bursts without reading a trace |
| Agent event stream | `a*/events.jsonl` | What the agent says it did: turns, tool calls, tokens |

Phase 1 had only the first two, and the counters were missing for some
families (F13). The agent's own stream closes the biggest gap: the
model-turn rule of Phase 1 could not be validated (F73). Each stream line
is time-stamped on arrival, so tool calls can be matched to processes in
the trace.

### Pressure files and all controllers, always

`cpu.pressure`, `memory.pressure`, `io.pressure`, `pids.*`, `memory.*`,
`io.*` are saved for every run of every family. Phase 1 found that the
counters saved back then could not see a disk limit or CPU competition
(F69). Pressure files are the candidate fix, and now we can test it.

### One spec per run, one grid per experiment

A run is a JSON spec; an experiment is a grid of specs. The workshop
collector took positional arguments and had one hand-written loop per
experiment, which is how the end-to-end manifest lost nine runs (F13).
Now the spec is saved with the run, and the campaign file is the record of
the experiment.

### Limits the workshop study could not set

- **Network** (`net`): the agents run in a network namespace joined to the
  machine by a virtual cable. Delay, loss and rate are applied to both ends
  of the cable, so both directions are impaired and nothing else on the
  machine is. The control cell uses the namespace with no impairment, so
  the namespace itself is not mistaken for an effect.
- **Process count** (`pids_max`).
- **Several agents at once** (`agents`): each agent has its own cgroup and
  repository, one trace covers all. Limits apply per agent or to the group.
- **A busy neighbour** (`neighbour`): `stress-ng` in a sibling cgroup.
- **Any combination**: `limits` takes several keys at once.

### Same cache state for every run

The page cache is dropped before every run (`cache: cold`). In the workshop
study only the memory and disk families did this, which made start-up 1 s
longer there and not comparable with the coding runs (F22).

### A quiet, pinned machine

`vm_setup.sh` turns off automatic updates and timers and holds the kernel
package. Phase 1 found a background package helper stalled for 0.8 s
inside one run (F72), and the kernel changed between campaigns (F10).

### Energy and hardware counters: recorded if the machine has them

The collector reads the energy counter and attaches hardware counters to
trace events when they exist, and records plainly when they do not. On an
ordinary cloud VM neither is exposed. Energy results need a bare-metal
machine; the collector needs no change for that.

### Kept from the workshop collector

- A fresh cgroup per run, so counters start at zero.
- The agent enters the cgroup before it starts; the collector stays out.
- Byte-identical task repositories, fixed prompts, a success check, and a
  check that the test file was not edited.
- Random run order, medians, resumable campaigns.

## What two related papers add

### AgentCgroup (arXiv 2602.09345)

Characterizes Claude Code on 144 real repository tasks (SWE-rebench) in
containers, sampling CPU and memory once per second, then proposes an
eBPF resource controller.

What it finds: OS-side work (container start-up plus tools) is 55 to 60% of
task time; memory, not CPU, limits how many agents fit; memory peaks are
15 times the average and come from tool calls; the same task varies 1.8
times between runs.

What we take:

- **Real repository tasks in real containers.** Their model share (40 to
  45%) is far below ours (76 to 90%) because their tasks run real test
  suites and start multi-gigabyte containers. Our small tasks are the
  weak point a reviewer will press. Next step for the collector: a
  `runtime: container` option and tasks from a public benchmark.
- **Container start-up as part of the cost.** They count it; we never
  measured it.
- **Time series next to the trace.** Their peak-to-average and burst
  figures come from simple sampling. Our sampler now gives the same view
  at 5 Hz, so results can be compared directly.
- **Density tested, not extrapolated.** They argue memory is the limit
  from single-agent peaks. Our `density` campaign runs the agents together.
- **Group tool calls by what they do** (test run, package install, file
  search, git). The agent event stream makes this possible.

Where our study is different, and should say so:

- They sample once per second and impose no limits during measurement.
  We trace every scheduling decision and set each limit on purpose, so we
  can say which mechanism costs how much.
- One agent there, two here.
- Their controller is evaluated by replaying traces. We do not build a
  controller; we measure and diagnose.

Weak points in their method to avoid: 1 s sampling cannot see sub-second
bursts (our 100 ms windows show 16% of windows above one core, F42); run
variance rests on one task run three times; the two model groups differ in
size (33 and 111 tasks).

### AgentKernel (arXiv 2609.29647)

A security design: every agent input, memory item and tool call passes
through a mandatory layer, with tool calls bound to kernel enforcement
(eBPF allow-lists installed before each tool's process tree starts). It has
no measurements and names the cost of per-tool enforcement as an open
question.

What we take:

- **The cost of per-tool mediation is a measurable question, and our data
  bears on it.** An agent starts 60 to 100 processes per run with a median
  life of 1.4 ms (F37). Anything installed "before each tool call" is paid
  that many times, on processes that barely live. A possible later
  experiment: the same tasks with and without the agents' own sandbox
  modes, which the workshop runs switched off.
- **Match what the agent says to what the kernel saw.** Their plan-to-trace
  check needs exactly the pairing our event stream and trace now allow.

Not relevant to this study: identity, input filtering and memory labelling.

## Not done yet

- **Agents inside containers** and **real repository tasks**. The biggest
  remaining gap (see AgentCgroup above).
- **Per-tool-call cgroups.** Would give memory peaks per tool call
  directly. The trace already attributes CPU and waiting per process.
- **Automatic copy to a bucket** after each campaign. Today it is a manual
  step in the README.
- **Analysis scripts for the new layout.** `meta/ground_truth.json`,
  `meta/root.pid`, `meta/clock_anchors.jsonl` and `trace.txt.gz` keep the
  names the Phase 1 scripts read, so those run on single-agent runs as they
  are. Multi-agent runs and the new files need new readers.
