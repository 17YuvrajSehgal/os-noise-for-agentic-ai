# What data we have

Counted from the run folders on 2026-11-14.

- **Old (workshop, Phase 1):** 262 runs with full kernel traces, first VM
  (now deleted). 132 Claude Code (2.1.296), 130 Codex (0.162.1).
  Analyzed in `phase1/results/analyze_all.jsonl`.
- **New (Phase 2):** 963 runs, all Claude Code (2.1.322), second VM. Same
  type (`n2-standard-4`, 4 CPUs, 15 GB) but a faster disk (287 MB/s
  against 205). Archives in
  `microservice-trace-dataset/agentic-runs-phase2/osn-export/`.
- **Total: 1,225 runs** (1,210 with a kernel trace; the 15 "no trace" overhead runs have none by design). 5 repeats per condition unless noted.

## The small test tasks

- **t2, t3:** small coding jobs. t3 adds a feature and runs its tests.
- **t4:** a program that starts many workers at once.
- **t5:** the agent splits the job across helper agents (sub-agents).
- **t6:** reads a 1 GB file, so it fills memory with file data.
- **t7:** a tool that grabs 512 MB of memory for itself.
- **t8:** reads 1 GB from disk.
- **t9, t10:** coding jobs where the test prints its own run time or stays
  quiet (the RQ5 behaviour test).
- **Real tasks:** 6 real bug fixes from SWE-bench Verified (Django, Flask,
  Requests, xarray, pytest, Sympy).

## Old data (262 runs)

| Experiment | Task | Conditions | Claude runs | Codex runs |
|---|---|---|---|---|
| CPU cap | t2, t3 | no cap, 1, 0.5, 0.25 core | 42 | 40 |
| More workers than cores | t4 | 2, 4, 8, 16 workers | 20 | 20 |
| Sub-agents | t5 | 4 or 8 helpers (3 runs each) | 6 | 6 |
| Soft memory limit | t6 | no limit, 1536, 1152, 768 MB | 20 | 20 |
| Hard memory limit, file data | t6 | 2 GB, 1280, 1024, 768 MB (3 runs each) | 12 | 12 |
| Hard memory limit, tool's own memory | t7 | 1024, 896, 768, 640 MB (3 runs each) | 12 | 12 |
| Disk speed cap | t8 | no cap, 200, 100, 50 MB/s | 20 | 20 |

The workshop's end-to-end coding-task runs under memory and disk limits
have no traces, so they are not in the 262. How many there were is not
known.

## New data (963 runs, Claude only)

| Experiment | Campaign | Task | Conditions | Runs |
|---|---|---|---|---|
| CPU cap, Opus | `cpu` | t2, t3 | no cap, 1, 0.75, 0.5, 0.375, 0.25 core | 60 |
| CPU cap, Haiku and Fable | `cpu_model2` | t2, t3 | no cap, 1, 0.5, 0.25 core | 80 |
| More workers than cores | `threads` | t4 | 2, 4, 8, 16 workers | 20 |
| Sub-agents | `subagents` | t5 | 4 or 8 helpers (10 runs each) | 20 |
| Soft memory limit | `memory_soft` | t6 | no limit, 1536, 1344, 1152, 768 MB | 25 |
| Hard memory limit, file data | `memory_hard_file` | t6 | 2 GB, 1280, 1024, 768 MB | 20 |
| Hard memory limit, tool's own memory | `memory_cliff` | t7 | 9 steps from 1024 down to 512 MB | 45 |
| Disk speed cap | `disk` | t8 | no cap, 200, 150, 100, 50, 20 MB/s | 30 |
| Coding task under a memory cap | `e2e_memory` | t3 | no cap, then 9 steps from 512 down to 64 MB | 45 |
| Coding task under a disk cap | `e2e_disk` | t3 | no cap, 50, 20, 5 MB/s | 20 |
| Slow network | `network` | t3 | normal, delay 50/100/200 ms, loss 1%/5%, bandwidth 1 Mbit/256 kbit | 40 |
| Process-count limit | `pids` | t3 | no limit, 64, 48, 32, 24, 16, 12 processes | 35 |
| Process-count limit, fine steps | `pids_mid` | t3 | 17 to 23 processes | 35 |
| Busy neighbour | `neighbour` | t3 | none, CPU hog (4 or 8), memory hog, disk hog | 25 |
| Two limits at once | `two_limits` | t3, t6, t8 | CPU+memory, CPU+soft memory, disk+soft memory, CPU+disk | 20 |
| Many agents on one machine | `density` | t3 | 1, 2, 4, 8, 16, 32 agents (3 runs each, 189 agents) | 18 |
| Printed run time (behaviour) | `feedback` | t3, t9, t10 | Opus and Haiku × no cap, 0.5, 0.25 core × printed or quiet | 120 |
| Real tasks in a container | `real` | 6 real fixes | no limit; 2 CPU/8 GB; 2 CPU/512 MB; 1 CPU/512 MB | 120 |
| Real tasks, no container | `real_host` | 6 real fixes | no limit | 30 |
| Real tasks, smallest cloud size | `real_quarter` | 6 real fixes | 0.25 CPU / 512 MB | 30 |
| Tracing cost | `overhead` | t3 | no trace, core, full (10 runs each) | 30 |
| Tracing cost, real task | `overhead_real` | Django fix | no trace, core, full | 15 |
| Printed run time, more runs | `feedback_extra` | t3, t9 | Haiku × 0.25 core (brings these cells to 15 runs) | 20 |
| Longer real tasks | `real_long` | django-15957, sympy-14248, pytest-10356, xarray-6992 | no limit, 1 CPU / 512 MB, 0.25 CPU / 512 MB | 60 |

Runs without a model in the table use Opus.

## What this means

- The 7 workshop experiments exist in both datasets, so old and new can be
  compared directly (`workshop/RESULTS.md`).
- 11 experiments exist only in the new data: network, process limit,
  neighbour, two limits, many agents, behaviour, real tasks, smaller
  models, and the coding task under memory and disk caps.
- Codex exists only in the old data.
- The old Claude runs do not record which model they used.
