# Step 3 results: local work (P9 to P19)

Date: 2026-11-10. Data: all 262 traces. "Coding runs" means the bug-fix and
implement tasks. Unless said otherwise, numbers are medians per run over
the 10 unlimited coding runs of each agent.

How to rerun:

```bash
export OSNOISE_RUNS=C:/workplace/microservice-trace-dataset/agentic-runs
cd phase1
python local_pass.py > results/local_all.jsonl   # about 2 minutes
python step3.py                                  # -> results/step3_runs.csv + tables
export SCREEN_TOOLS=<folder with futex_wait.py and syscall_stall.py>
python screens.py results/screens.csv            # about 15 minutes, resumable
```

## P9. Tool processes

| | Claude Code | Codex |
|---|---|---|
| Tool processes started per run | 62 | 100 |
| Median lifetime | 1.4 ms | 1.4 ms |
| Processes that live under 10 ms | 48 | 88 |
| Longest-lived tool | 2.2 s | 1.8 s |

- **An agent run is a storm of very short processes.** Most are shell
  helpers, not the tools the model asked for. Claude Code: `bash` 18, `git`
  7, `cat` 6, `python3` 6 per run. Codex: `lsb_release` 27, `bash` 18,
  `git` 16, `tr` 12. Codex runs each command in a login shell, and the
  login scripts start most of these.
- **Both agents start tools the cheap way.** Claude Code uses `vfork`
  (16 per run, 0.28 ms each). Codex uses `clone` with the spawn flags
  (32 per run, 0.30 ms each). Neither copies the agent's memory, so
  starting a tool stays cheap even for a 330 MiB agent process.
- The agent's 5 CPU-seconds go to very few processes: the test runs.

## P10. System calls

| | Claude Code | Codex |
|---|---|---|
| Agent process: calls per run | 26,600 | 53,800 |
| Agent process: time in calls that do work | 0.07 s | 0.14 s |
| Tool processes: calls per run | 21,100 | 25,200 |
| Tool processes: time in calls that do work | 0.05 s | 0.06 s |

- **Kernel work is negligible.** All calls that do work (everything except
  waiting calls such as `futex`, `epoll`, `read`) add up to about 0.1 to
  0.2 s per run.
- **The agent process mostly manages its own threads.** `futex` is the top
  call for both (12,300 and 22,400 per run). After that Claude Code does
  memory housekeeping (`madvise` 3,800) and file checks (`statx` 2,000,
  `openat` 1,400). Codex does `read` 4,100 and `mmap`/`munmap` 6,200.
- **Tools look like any short Unix program**: `stat`, `open`, `close`,
  `read`, `mmap`. This is process start-up cost, repeated 60 to 100 times.

## P11. CPU demand over time

| | Claude Code | Codex |
|---|---|---|
| Agent process CPU | 2.2 s | 0.8 s |
| Tool CPU | 3.0 s | 2.9 s |
| Mean cores in use over the run | 0.26 | 0.10 |
| 100 ms windows with any CPU use | 34% | 14% |
| Cores in use, busiest window | 1.8 | 2.1 |
| Windows that use more than one core | 16% | 2% |
| Most threads wanting a CPU at once | 14 | 16 |

- **Low average, sharp bursts.** The agent needs a quarter of a core on
  average (Claude) or a tenth (Codex), but in its busy moments it wants
  one to two cores.
- **This explains the CPU-cap result.** A 1-core cap is above the average
  and only clips the bursts, so it costs almost nothing. A 0.5 or 0.25
  core cap is at or below what the busy windows need, so every burst is
  stretched.
- **Prediction for agent density.** By average demand, 4 vCPUs could carry
  about 15 Claude Code agents or about 38 Codex agents. Because Claude Code
  uses more than one core in 16% of its windows, bursts will collide long
  before that. The density experiment should find the real number.

## P12 and P15. The machine

| | Claude Code | Codex |
|---|---|---|
| Machine idle | 93% | 97% |
| Hard interrupt time | 2.6 ms | 3.5 ms |
| Soft interrupt time | 45 ms | 56 ms |
| Interrupt time, share of machine | 0.06% | 0.05% |

The 4-vCPU machine is idle almost the whole run. Interrupt cost is
negligible and is not a noise source for this workload.

## P13. Disk and files

| | Claude Code | Codex |
|---|---|---|
| Files opened by the agent process | 1,293 | 1,005 |
| Files opened by tools | 2,214 | 2,920 |
| `fsync` calls by the agent | 1 | 8 |
| Disk-type sleep, whole process tree | 0.01 s | 0.04 s |

- **A coding task is not disk-bound at all.** Thousands of files are
  opened, but they are served from memory.
- **Disk-type sleep is a clean signal for the disk and memory limits.**
  Over all families:

| Condition | Disk-type sleep (s) |
|---|---|
| Coding runs, any CPU setting | 0.01 to 0.13 |
| Cold 1 GB read, no limit | 6.8 |
| Disk limit 100 MB/s | 11.2 |
| Disk limit 50 MB/s | 22.7 |
| Soft or hard memory limit below the working set | 29.8 |

- Not explained: block bytes counted from the trace are about 1.9 times
  the `io.stat` value (2,313 MB against 1,228 MB for the 1 GB read). Use
  `io.stat` for bytes until this is understood.

## P14. Memory footprint

Peak memory of the group, runs with no memory limit:

| Agent, task | Runs | Peak (MiB), median | Range |
|---|---|---|---|
| Claude Code, implement | 9 | 331 | 326 to 341 |
| Codex, bug-fix | 20 | 62 | 60 to 215 |
| Codex, implement | 29 | 63 | 60 to 299 |
| Claude Code, 1 GB file read | 28 | about 1,315 | |
| Codex, 1 GB file read | 28 | about 1,299 | |

- **Claude Code needs about five times the memory of Codex** on the same
  task. This is why its out-of-memory cliff sits higher.
- The peak includes page cache, so it is an upper bound on what the agent
  needs, not the minimum.
- The paper's "about 340 MiB peak" matches this counter. The "about 250 MB"
  and "about 190 MiB" figures elsewhere in the paper and notes are not
  backed by a counter in the data.
- Gap: the Claude coding runs of Problem 1 did not save memory counters.
  The Claude number comes from the end-to-end runs.

## P16. Lock waits

The lock-wait screen ran on all 262 runs: **no lock problem in any run.**
The long `futex` waits are worker threads parked until there is work, not
threads queuing on a lock.

## P17. Slow system calls

The screen looks for one call that burns CPU or sits in disk-type sleep
for 10 ms or more. In the agent's own process tree it finds:

| Finding | Runs | Where |
|---|---|---|
| Tool start (`vfork` / `clone`) frozen for 57 to 93 ms | 17 | only under a CPU cap: 13 at 0.25 core, 2 at 0.5 core, 2 at 1 core |
| Tool start (`execve`) frozen for 61 ms | 2 | only under the 50 MB/s disk limit |
| Freeing 512 MB (`munmap`) takes 21 ms | 3 | the memory workload itself |
| `fsync` of 11 ms | 1 | Codex session database |
| No slow call | all other coding and thread runs | |

- **A CPU cap freezes tool start-up.** The agent process waits inside the
  spawn call until the child has started, and the child cannot run because
  the group is throttled. The wait is close to one throttle period (100
  ms). The mean spawn time goes from 0.28 ms to 4.9 ms at 0.25 core.
- **A disk limit can freeze an ordinary tool**, not only the synthetic
  reader: loading a program from disk is throttled like any other read.
- The screen also reports the collector's own `sync` and cache-drop calls
  in most memory and disk runs, and one background system process
  (828 ms in `close`) in one unlimited run. These are outside the agent's
  process tree. A diagnosis procedure must restrict itself to the tree.
- Limit: only the first finding of each run was kept. In the memory and
  disk runs that first finding is usually the collector's `sync`, so a
  slow call inside the agent's tree could be hidden behind it there.

## P18. Who wakes the agent

- **Claude Code main thread**: asleep 93% of the run, and never for more
  than 200 ms. 74% of its sleep ends by a timer, 22% by its own network
  thread. So the main thread polls on a 200 ms timer and is not a direct
  witness of the model wait.
- **Claude Code network thread**: asleep 85% of the run. 55% of that sleep
  is ended by incoming network data.
- **Codex**: the main thread does nothing; the work is in worker threads.
- So this view agrees with the model-wait picture but is not an
  independent measurement of it. Checked on one run per agent only.

## P19. Failed system calls

- About 3,500 (Claude) and 4,600 (Codex) calls fail per run. Almost all
  are normal: a file that does not exist (`ENOENT`), a terminal check on a
  non-terminal (`ENOTTY`), a non-blocking read with no data (`EAGAIN`).
- **Resource limits never appear as error returns.** Over all 262 runs,
  including the out-of-memory runs, there is not one out-of-memory, out of
  file descriptors, out of disk space, or cannot-create-process error from
  a system call. A limit shows up as waiting, or as a kill signal.
- Both agents try IPv6 first and fail (`ENETUNREACH`, 6 to 12 times per
  run) because the VM has no IPv6 route. Harmless here.

## What this decides for the new runs

- **Density experiment**: predicted limit is burst collisions, not average
  CPU. Memory will also bound Claude Code (331 MiB each).
- **Process-count limit**: an agent starts 60 to 100 processes per run but
  only a handful at once (peak 14 to 16 threads wanting a CPU). A
  `pids.max` limit must be set near that concurrency to bite, and it would
  be the first limit that produces error returns.
- **Diagnosis**: three cheap signals already separate the mechanisms on
  the existing runs. Waiting for CPU with idle cores means a CPU cap.
  Disk-type sleep means disk or memory. Memory reclaim events then
  separate memory from disk. Frozen tool start-up is a second signature of
  a CPU cap.
- **Collector**: save memory counters for every run, including coding
  runs.

## Open questions

- Why block bytes in the trace are 1.9 times `io.stat`.
- Why the Codex file-read runs peak at 1,299 MiB when Codex alone needs 62.
- P18 was checked on one run per agent.
