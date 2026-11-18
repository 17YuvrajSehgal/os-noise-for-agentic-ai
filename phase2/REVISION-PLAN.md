# Revision plan after review 1 (2026-11-18)

Source: `review-1.md`. Submission: ICPE 2027 Research Track, EERCS.
Paper due 2026-11-23 AoE. Abstract registration: see "Before anything".

## Before anything

1. **Check HotCRP today.** The review says abstract registration closed
   2026-11-17. `todo-list.md` still asks whether it was done. If the
   abstract is not registered, ask the PC chairs at once whether a late
   registration is possible. Everything below depends on this.
2. **Approve the new VMs** (M1, M2 below). They break the earlier rule
   "one VM for all collections" on purpose: the main results stay on M0,
   and M1/M2 are a separate cross-machine set.
3. **Prior arXiv version.** We remove every mention of it from the paper
   (decided by the author). Notes:
   - An arXiv withdrawal keeps the old versions readable. A reviewer can
     still find it.
   - It was never in peer-reviewed proceedings, so there is no
     double-publication problem.
   - Do not reuse its sentences word for word.
   - If the HotCRP form asks about prior versions or related preprints,
     declare it there (that field goes to the chairs, not the reviewers).
     I'm not sure what ICPE's form asks; check it when submitting.

## Machines

| Name | Type | vCPU | Memory | CPU | Role |
|---|---|---|---|---|---|
| M0 | n2-standard-4 (`agentic-noise-2`) | 4 | 16 GB | Intel Cascade Lake | main data (existing) |
| M1 | n2-standard-2 | 2 | 8 GB | Intel Cascade Lake | fewer CPUs, less memory, same CPU |
| M2 | n2d-standard-8 | 8 | 32 GB | AMD EPYC | more CPUs, more memory, other vendor |

- M1 and M2 are clones of M0's disk, so kernel, agent (2.1.322), LTTng
  2.15.1, Docker images and tools are identical. Same zone.
- Disk: the project has 400 GB of SSD quota, so it is split 134 (M0) /
  133 (M1) / 133 (M2) GB pd-balanced (decided 2026-11-18). Read speed of
  pd-balanced grows with size, so M0's new runs read slower than its old
  400 GB disk (287 MB/s). Measure every disk with `fio` before the first
  run and record it; do not pool disk- or start-up-sensitive results from
  before and after the change without checking they agree.
- Measured 2026-11-18 (dd, 4 GiB, direct I/O): all three disks read at
  186 to 187 MB/s, against 287 MB/s for M0's old 400 GB disk. So M1/M2/M0
  are equal on disk, and M0's new runs are a fresh set: rerun the
  unlimited baseline in every new M0 campaign instead of topping up old
  cells.
- Machines checked: M0 4 vCPU Intel Xeon 2.8 GHz (2 cores x 2 threads),
  15 GB; M1 2 vCPU same CPU (1 core x 2 threads), 7 GB; M2 8 vCPU AMD
  EPYC 7B13 (4 cores x 2 threads), 31 GB. All kernel 7.0.0-1017-gcp, LTTng
  2.15.1, Claude Code 2.1.322, no swap.
- Before the shrink, every file on M0 (262,099 files, plus overhead_nov10
  and home files) was matched against the archives on the PC; snapshot
  `m0-before-shrink` holds the old system disk.
- Record kernel and image of each VM in `provenance/`.
- The old VM (262 runs) stays in the paper as "a first VM of the same
  type" (VM0). So the paper covers 4 machines: two of one type, two others.
- DRAC clusters are not usable: no root, so no cgroup limits or kernel
  tracing.
- Stop every VM after use; never delete M0.

## Analysis only (no new runs)

These answer most of the review and need no VM.

| # | Review point | Work |
|---|---|---|
| A1 | Model is an accounting identity | Present Eq. 1 as a decomposition. Add a real prediction: estimate `s` *before* running the limited task, from the unlimited run only (CPU seconds, parallelism, I/O bytes) and the limit (quota, rate). Predict wall slowdown, compare with measured. |
| A2 | Baselines | Compare A1 against: wall = local slowdown (no dilution); wall unchanged; `s` = 1/quota. Report median error, 95% CI, share within 10%. |
| A3 | Held-out test | Fit on small tasks, predict real tasks (short, long) and M1/M2 with no refit. |
| A4 | Local time is a lower bound | From the trace, take the life of every tool process (fork, exec, exit under the agent). Count how much tool CPU/run time falls inside open model turns. Recompute `f`, `s` and the model error with that time moved to local. Report per limit. |
| A5 | Statistics | Effect sizes (Cliff's delta), Wilson intervals for solve, kill and crash rates, dot plots of single runs, confirmatory vs exploratory labels. |
| A6 | 10% threshold | Recompute every breaking point at 5% and 20%. |
| A7 | Per-task results | Table with every real task, size, solve rate, wall and local slowdown. |
| A8 | Interactions | The paper names only memory + disk. We already have 4 pairs (CPU+memory, CPU+soft memory, memory+disk, CPU+disk). Report all 4 and whether each is additive or multiplying. |
| A9 | Three outcomes | Split results into speed, task success, and agent behaviour. Keep xarray out of every success claim. |
| A10 | Thresholds vs mechanisms | Each finding labelled: general mechanism / machine-specific number / workload-specific number. Recommendations rewritten as "for the tested setup" plus a calibration rule. |
| A11 | Density | Add p95 and CPU per agent per level (data exists). |
| A12 | Remove arXiv | Rewrite Section 7 as "Results across machines": VM0 vs M0 (same type) and M0 vs M1 vs M2. Drop the 14-claim table. Remove the citation and the Related Work bullet. |

## New collections

Run counts are agent runs; "groups" are density runs (many agents at
once). Time per run is my estimate from earlier campaigns (about 2 min
for a small task, about 6 min for a real task, including setup). I'm not
sure about the real-task time on M1.

### M1 and M2: portable core set (same set on both)

| Campaign | Task | Steps | Reps | Runs |
|---|---|---|---|---|
| cpu | t3, Opus | none, 1, 0.75, 0.5, 0.25 core (M2 also 2 cores) | 10 | 50 (M2: 60) |
| threads | t4 | W = C/2, C, 2C, 4C | 5 | 20 |
| memory | t6 soft: none, 1344, 1152, 768 MB; t7 hard: 768, 704, 640 MB | | 5 | 35 |
| disk | t8 | none, 150, 50, 20 MB/s | 5 | 20 |
| pids | t3 | 24, 20, 18, 17, 16 | 5 | 25 |
| real | Django, Requests, Sympy short | none, 1 CPU/512 MB, 0.25 CPU/512 MB | 5 | 45 |
| density | t3 | M1: 1-16 agents; M2: 1-64 agents | 3 | 15 / 21 groups |

M1: 195 runs + 15 groups. M2: 205 runs + 21 groups. About 10 h each,
both in parallel.

### M0: more evidence for the main claims

| Campaign | What | Runs |
|---|---|---|
| reps_cpu | t3 Opus at none, 1, 0.75, 0.5 core, +10 each (15 per step) | 40 |
| reps_mem | t7 at 704 and 640 MB, +10 each | 20 |
| reps_pids | t3 at 20, 19, 18, 17, 16, +10 each | 50 |
| reps_real | 6 short tasks at none and 0.25 CPU, +5 each (10 per cell) | 60 |
| reps_density | t3, 1-32 agents, 2 more groups per level (5 per level) | 12 groups |
| density_task2 | a lighter real task (Requests), 1-16 agents, 3 each | 15 groups |
| overhead_limited | t3 at 0.25 core and at 192 MB, trace none vs full, 10 each | 40 |
| overhead_density | 8 agents, trace none vs full, 5 each | 10 groups |
| interact | t3: CPU 0.5 + disk 20 MB/s; memory 512 MB + pids 20; 4 agents at 1 core each | 10 + 5 groups |
| fb_constant | t3 that prints a fixed fast time, Haiku, 0.25 core and none | 20 |
| fb_instruct | t3 with "run time is not a goal" in the prompt, Haiku, 0.25 core | 15 |
| fb_model2 | t3/t9 with Fable at 0.25 core | 30 |
| fb_task2 | new timing task t11 (prints / silent), Haiku, 0.25 core | 20 |
| cut_output | new task t12: a test worker is killed by a memory limit mid-output; Opus and Haiku, limit and none | 40 |

M0: 345 runs + 42 groups. About 16 to 18 h, one campaign at a time.

### Stretch: non-Python real tasks

6 short tasks from SWE-bench Multilingual or Multi-SWE-bench (2 Java,
2 JavaScript/TypeScript, 2 Go or Rust), at none, 1 CPU/512 MB and 0.25
CPU/512 MB, 5 reps: 90 runs, about 9 h on M0. Only if the 6 Docker images
build and validate within one day. Otherwise it goes in Threats.

### Totals

| | Runs | Groups |
|---|---|---|
| M0 | 345 | 42 |
| M1 | 195 | 15 |
| M2 | 205 | 21 |
| Total | 745 | 78 |
| Stretch (M0) | +90 | |

Cost: I'm not sure. Rough guess: API about $0.15 per small Opus run and
$0.5 to $1 per real run, so about $200 to $400 plus the density agents;
VMs a few dollars per day each.

## What we will not do, and how the paper says so

- Codex on the new machines: no (needs sign-in and model choice). Codex
  stays on VM0 only.
- Every limit on every machine: no. M1/M2 get the core set only.
- More than 3 small-task families: no.

## Schedule

| Day | Work |
|---|---|
| 11-18 | HotCRP check. Approve VMs. Write t3-constant, t3-instruct, t11, t12 and campaign files; test each once on M0. Create M1, M2 and check the collector. Start M0 behaviour campaigns overnight. |
| 11-19 | M1, M2 core sets. M0 reps and overhead. In parallel: A1 to A12. |
| 11-20 | Finish runs. Stop VMs. Download, checksum, analyse new data. |
| 11-21 | Rewrite: model section, results across machines, behaviour, threats, recommendations. Related Work without the arXiv version. |
| 11-22 | Number check, anonymous artifact, final build, submit. |
| 11-23 | Buffer. |
