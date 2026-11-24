# Step 4 results: the limits, looked at again (P21 to P25)

Date: 2026-11-10. Data: all 262 traces.

How to rerun (about 1 minute):

```bash
export OSNOISE_RUNS=C:/workplace/microservice-trace-dataset/agentic-runs
cd phase1
python diag_pass.py > results/diag_all.jsonl   # trace signals, agent process tree only
python step4.py                                # tables + results/step4_diagnosis.csv
```

## P21. Where the CPU-cap wait lands

Coding runs, median seconds a thread was ready to run but not running:

| | Start-up | Model only | Model and tool | Tool only | Agent only | Waited by agent | Waited by tools | Total | `cpu.stat` throttled |
|---|---|---|---|---|---|---|---|---|---|
| Claude, 1 core | 0.32 | 0.02 | 0.00 | 0.04 | 0.01 | 0.37 | 0.04 | 0.45 | 0.42 |
| Claude, 0.5 core | 2.13 | 0.07 | 0.25 | 3.39 | 0.23 | 3.15 | 3.17 | 6.14 | 5.93 |
| Claude, 0.25 core | 6.32 | 0.61 | 1.46 | 8.31 | 1.20 | 10.11 | 8.44 | 18.32 | 17.16 |
| Codex, 1 core | 0.38 | 0.01 | 0.00 | 0.00 | 0.00 | 0.21 | 0.16 | 0.44 | 0.18 |
| Codex, 0.5 core | 1.35 | 0.01 | 0.00 | 2.65 | 0.09 | 0.95 | 3.15 | 4.15 | 3.55 |
| Codex, 0.25 core | 3.76 | 0.02 | 0.04 | 8.67 | 0.37 | 3.77 | 9.62 | 14.15 | 11.43 |

- **The wait lands on start-up and on tool runs, almost never on the model
  wait.** While only the model is working, the agent waits 0.6 s at most
  even at 0.25 core.
- **At 1 core the only part that waits is start-up.** This is why a 1-core
  cap looks free in the wall-clock numbers.
- **For Claude Code the agent process itself waits more than its tools**
  (10.1 s against 8.4 s at 0.25 core), because its start-up is heavy. For
  Codex it is the tools (9.6 s against 3.8 s).
- **The trace now agrees with the counter.** Total ready-wait from the
  trace is within about 5 to 25% of `cpu.stat` throttled time. The old note
  that the trace under-counts throttle no longer holds.

## P22. Which part of a run each limit slows

Median seconds. "Tool only" is where the workload runs.

| Condition | Agent | Start-up | Tool only | Wait for first byte |
|---|---|---|---|---|
| Disk, no limit | Claude / Codex | 2.70 / 1.61 | 6.07 / 6.03 | 1.04 / 0.78 |
| Disk, 100 MB/s | Claude / Codex | 2.93 / 2.08 | 10.19 / 10.26 | 1.06 / 0.88 |
| Disk, 50 MB/s | Claude / Codex | 4.02 / 3.85 | 20.49 / 20.50 | 1.10 / 0.54 |
| Memory, no limit | Claude / Codex | 2.61 / 1.61 | 6.61 / 5.22 | 0.99 / 0.89 |
| Memory, soft 768 MB | Claude / Codex | 2.62 / 1.57 | 30.48 / 27.20 | 1.05 / 0.74 |
| Memory, hard 768 MB | Claude / Codex | 2.65 / 1.60 | 30.48 / 26.70 | 1.16 / 0.77 |
| 4 workers on 4 CPUs | Claude / Codex | 1.63 / 0.31 | 1.08 / 1.01 | 0.72 / 0.76 |
| 16 workers on 4 CPUs | Claude / Codex | 1.67 / 0.30 | 3.99 / 2.07 | 0.61 / 0.71 |

- **Every limit slows the tool phase and leaves the model wait alone.** The
  wait for the first byte does not move under any limit.
- **A disk limit also slows the agent's own start-up.** With cold caches,
  start-up goes from 2.7 to 4.0 s for Claude Code and from 1.6 to 3.9 s for
  Codex at 50 MB/s, because the agent's program is read from the limited
  disk. The workshop paper did not report this.
- **A memory limit does not touch start-up** (2.6 s at every setting). The
  paper's statement that the agent itself is untouched holds for memory.
- Cold caches alone add about 1 s to Claude Code's start-up (2.6 to 2.7 s
  here against 1.65 s in the coding runs, where caches were warm).

## P23. What is stable and what is not

Spread of a cell = (max - min) / median over its repetitions.

| Metric | Median spread | Worst cell |
|---|---|---|
| Reclaim episodes (memory runs) | 0% | 1% |
| Disk-type sleep (disk and memory runs) | 1% | 2% |
| Worker phase time (synthetic runs) | 0% | 163% |
| Start-up time | 5% | 270% |
| Agent CPU | 11% | 78% |
| Tool CPU (coding runs) | 13% | 84% |
| Throttled time (capped runs) | 16% | 47% |
| Tool-only time (coding runs) | 18% | 115% |
| Wall time (coding runs) | 44% | 108% |
| Number of model turns (coding runs) | 56% | 133% |
| Model time (coding runs) | 56% | 156% |

- **Kernel-side signals are almost perfectly repeatable** (0 to 1%).
- **Anything that depends on the model's choices is noisy**: turns, model
  time and so wall time vary by about half within a cell.
- **For the new runs**: compare conditions on per-part times and on kernel
  signals. Five repetitions are enough for those. Wall time on coding tasks
  needs more repetitions, or a comparison per turn.
- The large "worst cell" values come from single outlier runs, which is
  why medians are used.

## P24. Naming the limit from the trace alone

The procedure reads four signals from the trace, for the agent's process
tree only, and never sees which limit was set. The first check that fires
decides.

| Order | Check | Signal | Fires at |
|---|---|---|---|
| 1 | Memory limit | Memory-cgroup reclaim episodes started by the tree | 50 or more |
| 2 | Disk limit | Disk-type sleep while no block request is in flight | 1 s or more |
| 3 | CPU quota | Ready to run while a CPU is idle | 0.3 s or more |
| 4 | CPU competition | Ready to run while all CPUs are busy | 1 s or more |
| 5 | Nothing found | none of the above | |

Why each signal means what it says:

- **Reclaim by the tree** only happens when the group presses on a memory
  limit.
- **Sleeping on the disk with nothing in flight** means the request is
  being held back before it reaches the device. A slow or busy disk shows
  the opposite: sleep with requests in flight.
- **Ready while a CPU is idle** means CPU time was available and withheld.
  That is a quota.
- **Ready while all CPUs are busy** means too many threads for the cores.

Result over all 262 runs (rows: what was really done; columns: what the
procedure said):

| What was done | Runs | CPU quota | CPU competition | Memory limit | Disk limit | Nothing found | Correct |
|---|---|---|---|---|---|---|---|
| CPU quota | 61 | 59 | 0 | 0 | 0 | 2 | 97% |
| CPU competition (8 or 16 workers) | 20 | 0 | 20 | 0 | 0 | 0 | 100% |
| Memory limit below the footprint | 50 | 0 | 0 | 50 | 0 | 0 | 100% |
| Disk limit below disk speed | 20 | 0 | 0 | 0 | 20 | 0 | 100% |
| No limit, or a limit too loose to bite | 111 | 0 | 1 | 0 | 0 | 110 | 99% |
| **All** | **262** | | | | | | **98.9%** |

The three runs that differ:

- **Two Codex runs at 1 core were called "nothing found".** Their idle-CPU
  wait was 0.25 and 0.26 s, just under the 0.3 s bar. A 1-core cap barely
  affects these runs, so the miss is a mild quota with almost no effect.
- **One unlimited Codex sub-agent run was called "CPU competition".** This
  is not a mistake of the procedure. In that run (`t5_n8_r1`) all 8 workers
  really did run at the same time: each waited 0.94 s, the same as the
  8-worker stress run. The agent log shows why. Codex did not start
  sub-agents. The model wrote one shell line that launched all 8 workers
  in the background. So the agent over-subscribed the CPUs by its own
  choice in 1 of the 6 Codex sub-agent runs. The workshop paper says the
  harness does not do this, based on Claude Code only.

How wide the margins are:

| Signal | Highest value where it should not fire | Lowest value where it should fire |
|---|---|---|
| Reclaim episodes | 0 | 86 |
| Disk sleep with nothing in flight | 0.19 s | 8.9 s |
| Ready while all CPUs busy | 0.13 s (apart from the run above) | 7.3 s |
| Ready while a CPU is idle | 0.25 s | 0.25 s at 1 core, 3.9 s at 0.5 core |

Three of the four signals have a very wide gap. The CPU-quota signal is
clear from 0.5 core down and marginal at 1 core.

**Kill detection.** The rule "a process exits within 1 ms of its own
reclaim" found all 3 real out-of-memory kills (checked against the
`oom_kill` counter), and raised 2 false alarms in 194 runs. Both false
alarms are the file reader finishing normally while reclaim was running.
The rule needs a second condition before it can be trusted.

### Limits of this result

- **The thresholds were set after looking at these same runs.** This is an
  in-sample result. It must be repeated on new runs before it is a claim.
- **Each run had one limit and a known workload.** Runs with two limits at
  once, and real repository tasks, are untested.
- **"Memory limit" covers soft and hard limits together.** The procedure
  does not yet tell them apart.
- Memory "below the footprint" uses the footprint figures from the workshop
  paper (1,380 MB for the file workload, 762 MB for the allocation one).

## P25. What the counters alone would have said

Using only the cgroup counters saved with each run (`cpu.stat` throttle
count, `memory.events`):

| What was done | Runs | Named correctly by counters | By the trace |
|---|---|---|---|
| CPU quota | 61 | 61 (100%) | 59 (97%) |
| CPU competition | 20 | 0 (0%) | 20 (100%) |
| Memory limit | 50 | 50 (100%) | 50 (100%) |
| Disk limit | 20 | 0 (0%) | 20 (100%) |
| No limit, or too loose to bite | 111 | 111 (100%) | 110 (99%) |
| **All** | **262** | **222 (84.7%)** | **259 (98.9%)** |

- **Counters are perfect for CPU quota and memory**, and cheaper. The
  throttle counter even catches the mild 1-core quota that the trace misses.
- **Counters are blind to a disk limit and to CPU competition.** `io.stat`
  counts bytes, not waiting, and `cpu.stat` has no entry for waiting behind
  other threads.
- **The trace adds two mechanisms and the "where".** It names the disk
  limit and competition, and it says which part of the run paid (P21, P22).
- Untested: the kernel's pressure files (`cpu.pressure`, `io.pressure`)
  might close this gap for counters. The old runs did not save them. The
  new collector should.

## What this decides for the new runs

- **Validate the procedure out of sample**: new runs, thresholds frozen.
- **Add the missing cases**: two limits at once, network limit,
  process-count limit, a busy neighbour, real repository tasks.
- **Save pressure files and memory counters for every run**, to test a
  counter-only version fairly.
- **Repeat the sub-agent runs** with more repetitions, for both agents, to
  see how often the model chooses plain shell parallelism.
