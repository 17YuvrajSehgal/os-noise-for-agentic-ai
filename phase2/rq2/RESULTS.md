# RQ2. How does each limit change where the time goes?

Analyzed 2026-11-13. Script: `curves.py` (reads `rq1/runs.csv`, writes
`curves.txt` with every level and `curves.csv`). Opus unless a model is
named. 5 runs per level.

```
cd phase2 && python rq2/curves.py
```

## Method

- Baseline: the same task and model with no limit (or the loosest level when
  the experiment has no unlimited cell).
- Slowdown = median time / median baseline time, with a 95% bootstrap
  interval.
- Two measures:
  - **wall time**: what a user waits.
  - **local time** = wall time minus time waiting for the model. This is
    the time spent on the machine, where the limits act.
- Why local time: the model's answer time varies by a few seconds from run
  to run, whatever the limit. With 5 runs, this noise hides any change in
  wall time below about 20%. Local time shows changes of about 10%.
- Breaking point: the loosest level whose interval lies above 1.10.

## Results per limit

| Limit | No effect down to | Breaking point (local) | At the tightest level | Which part grows |
|---|---|---|---|---|
| CPU quota | 1 core | 0.75 core (+35%) | 0.25 core: local x3.9, wall x2.0 | tools, start-up, CPU-quota waiting |
| File memory (soft or hard limit) | 1280 MB | 1152 MB soft / 1024 MB hard: a cliff, x3.4 at once | same as the cliff | tools: every read goes to disk again |
| Memory, tool needs 512 MB | 768 MB | 640 MB: the tool is killed (5 of 5) | 512 MB: killed | model (the agent reacts to the failure) |
| Memory, whole agent | 192 MB (+11%) | 128 MB: x15 local, then killed | 96 and 64 MB: dies at start-up | start-up, reclaim, disk |
| Disk read speed | none: smooth from the first step | 150 MB/s (+43%) | 20 MB/s: local x9.2, wall x4.6 | tools (reading the file) |
| Disk, coding task | none: the first step already costs | 50 MB/s (+26%) | 5 MB/s: start-up +21 s | start-up (the agent itself is read from disk) |
| Network | all levels, in local time | none | 256 kbit/s: wall +29% | model time only |
| Process count | 18 | 17 (+55%, failed process starts) | 16 and 12: abort in 3 s | tools |
| More threads than cores | 2 workers | 8 workers (+60%; 4 workers +24%, interval [1.10-1.31] not above 1.10) | 16 workers: x2.4 local | tools, CPU waiting |
| Busy neighbour (no limit on the agent) | an I/O neighbour (+8%) | CPU neighbour: +86% local | memory neighbour: +62% local | tools, start-up |

What this means:

- **The model wait hides most of the system's cost.** At a quarter of a CPU
  core, the agent's work on the machine takes 3.9 times longer, but the user
  sees only 2.0 times. With a busy CPU neighbour, local time is +86% while
  wall time moves 2 to 9%, inside the noise. Measuring only wall time, as
  most agent benchmarks do, misses these effects.
- **Three shapes of damage:**
  - Smooth: CPU quota, disk speed and threads. The cost grows step by step,
    roughly with how much the resource is cut.
  - Cliff: memory. Nothing happens, then at one step the time doubles (the
    file no longer fits in memory) or the process is killed. A soft memory
    limit gives the same cliff as a hard one for file memory.
  - Abort: process count. No cost down to 17, then the agent dies in 3 s.
- **The network is the only limit that does not touch local time.** It
  shows up only in model time (+2 to +6 s). Local time stays flat, which
  confirms the split puts the cost in the right part.
- **Where the cost lands depends on the limit:**
  - In the tools: CPU, file memory, disk, threads, neighbour.
  - In start-up: disk on the coding task (+21 s at 5 MB/s), because the
    agent program itself is read from disk at start.
  - In model time: network, and the agent's own reaction to a failure.
- **Smaller models react to a CPU limit by working more.** At 0.25 core,
  Haiku's model time on the implement task grows by 16 s (10 turns against
  4) and Fable's by 10 to 15 s, against 5 s for Opus. That is RQ5.

## The hidden-cost model

Script: `rq2/hidden.py` (writes `hidden.txt`, `hidden.csv`). Analyzed
2026-11-14.

    wall slowdown = 1 + f × (local slowdown − 1),   f = local / wall with no limit

- f, the share of the time spent on the machine, is 0.20 to 0.45 here. So
  only a fifth to a half of any cost on the machine reaches the user.
- Tested on all 68 limited cells (Opus, Haiku, Fable; every limit).
  - **Cells where the model time stayed the same (moved under 2 s): 44 of
    45 within 10%, median error 3.3%.**
  - All 68 cells: 52 within 10%, median error 4.9%.
- 16 cells miss by more than 10%. In 15 of them the model time moved by
  2 s or more, and the miss has the same sign: model slower, prediction
  too low; model faster, prediction too high (`hidden.txt`).
  - Network (1% and 5% loss, 256 kbit/s): model +2.6 to +5.8 s,
    prediction 12 to 21% too low.
  - Smaller models at tight caps (Fable t2 0.25, Fable t3 0.5 and 0.25,
    Haiku t3 0.25): the agent does more turns (RQ5), model +3.6 to
    +16.3 s, prediction 13 to 33% too low.
  - Busy CPU neighbour and three Opus CPU cells (t2 0.75 and 0.375, t3
    1 core): model 2.5 to 3.6 s faster, prediction 10 to 18% too high.
    Model service noise; I'm not sure of a cause.
  - Also model slower: Haiku t2 1 core, memory_cliff 704M, pids 24.
  - The one miss with stable model time: memory_cliff 896M (15%).
- So the error of the model is itself a measurement: it tells how much of
  the slowdown came from the model side instead of the machine.

## Limits of this analysis

- 5 runs per level. Intervals are wide where the agent's behaviour varies
  (Haiku at 0.25 core: x3.7 to x25 local).
- One machine shape (4 vCPU, no swap). Memory cliffs depend on how much the
  task reads; the levels are specific to these tasks.
- Small tasks, except the coding task (`t3_implement`). RQ3 repeats the
  question on real tasks.
- Waiting times in the trace are summed over threads, so they can be larger
  than the wall time they explain.

## Open

- Figures: one panel per limit, slowdown (wall and local) against level
  with intervals. Needs matplotlib in a project venv.
- Pool both tasks of the CPU experiments for tighter intervals.
