# Revision analyses (review 1), results

Data: the first pass on M0 (963 runs, `runs/`) and the revision runs
(1,019 runs on M0, M1, M2, `runs-rev/`). Scripts are in this folder; each
writes the `.txt` named below. M0 = n2-standard-4 (4 vCPU, Intel),
M1 = n2-standard-2 (2 vCPU, Intel), M2 = n2d-standard-8 (8 vCPU, AMD).
"First pass" and "revision" on M0 are the same VM type with a different
disk (287 against 187 MB/s), so each keeps its own unlimited runs.

## A1-A3. A real prediction of the wall time (`predict.py`, `a1_eval.py` -> `a1.txt`)

Eq. 1 is a decomposition, not a prediction: with the measured local
slowdown it only checks itself. The paper now adds a prediction that uses
the unlimited run and the limit setting only.

- **Method (replay).** Cut the unlimited run into the sampler's 0.2 s
  slices. A slice inside a model answer keeps its length. A local slice that
  used `d` CPU-seconds and read `b` bytes takes `max(dt, d/q, b/r)` under a
  quota of `q` cores and a read rate `r`. Predicted wall = sum of slices.
  Nothing is fitted.
- **Held out.** The method was written looking only at the first-pass t3
  CPU cells (5 cells). All other 89 cells (CPU quota and read-rate limits;
  small and real tasks; Opus, Haiku, Fable; M0 first pass, M0 revision, M1,
  M2) are held out.

| Method (held-out, 89 cells) | Median error [95%] | Within 10% |
|---|---|---|
| **Replay (prediction)** | **6.9% [5.2-8.2]** | **61** |
| Eq. 1 with naive `s = 1/q` (prediction) | 9.4% [6.7-11.9] | 47 |
| Wall unchanged | 17.2% [11.4-27.2] | 30 |
| Wall = 1/q, no dilution | 21.9% [15.5-54.8] | 29 |
| Eq. 1 with measured `s` (consistency check only) | 4.3% [3.1-5.8] | 71 |

- Per machine: M0 first pass 7.5%, M0 revision 4.9%, M1 7.6%, M2 5.7%.
  Real tasks 7.0%, disk-only limits 7.5% (the simple baselines miss disk by
  about 40%).
- Cell by cell, replay is closer than naive Eq. 1 in 50 cells, farther in 30.
- **Where it misses (28 cells over 10%).** 19 are cells where the model time
  moved by 2 s or more, that is, the agent did something else (Haiku
  chasing the printed time, the long xarray task); in 17 the miss has the
  sign of that change. The other 9: three pytest cells that ran slightly
  faster than unlimited (noise), very low read rates (5 and 20 MB/s, small
  reads cost more than their bytes), and Django at 512 MB (reclaim time the
  replay cannot see).
- With stable model time and every run solved (57 cells): replay 5.1%
  median error, 48 of 57 within 10%.

What this means for the paper: Eq. 1 explains, the replay predicts. A
platform can take one unlimited trace of a task and predict its wall time
under a quota or a read rate within about 7%, as long as the agent does not
change its plan.

## A4. Model/tool overlap (`a4_overlap.py` -> `a4_first.txt`, `a4_rev.txt`)

From the kernel trace: every process the run started, except the agent,
the collector's wrappers, Docker's init and anything alive for 90% of the
run. Its lifetime inside an open model answer is machine work that the
paper counts as model time. Trace and event clocks agree to about 20 ms.

- 842 first-pass runs: median 0.2% of local time, p90 18.7%.
- Small tasks: 0.0 to 0.3% median in every campaign.
- Real tasks in Docker: median 0.4 to 1.6 s per run. It is the agent's own
  `git` call at session start (up to 10 s in the Django repository), which
  runs while the first model answer streams.
- Sub-agent runs: 53%, by design (helpers work while the main agent waits).
- **Sensitivity.** Moving this time to local changes `f` for Docker tasks
  (0.45 -> 0.53) but not the result: Eq. 1 median error 3.6% either way, 30
  of 36 cells within 10% either way.
- The same work runs beside the model, not after it, so it delays the run
  only when a limit stretches it past the model's answer.
- Revision runs (894, M0, M1, M2): median 0.3%, p90 1.9%. Real tasks again
  the highest (median 0.3 to 5.7%, the session-start git). Eq. 1 median
  error 3.5% as in the paper, 3.6% with hidden time as local; 35 of 39 cells
  within 10% either way.

## A5. Statistics (`machines.py` -> `machines.txt`, also `a7.txt`, `a11.txt`)

Every cell now has: n, wall and local slowdown with a 95% bootstrap
interval, Cliff's delta of wall against the baseline, solve rate and
abnormal-exit rate with 95% Wilson intervals. Key cells have 10 to 15 runs
(CPU quota and process limit on M0: 15 and 10).

Confirmatory (designed before the data it tests): every revision campaign
on M0, M1, M2 (the replication of the breaking points, the printed-time
controls, the process-limit edge follow-ups `m1_pids_lo`, `m2_pids_hi`).
Exploratory (found in the data): all first-pass findings, the agent being
killed in t12 (below), the 4 agents per vCPU saturation (A11).

To do: dot plots of single runs for the key cells (figure).

## A6. 5%, 10% and 20% thresholds (`a6_thresholds.py` -> `a6.txt`, `a6_machines.txt`)

- First pass: 19 of 32 breaking points the same at all three thresholds, 12
  move one level, 1 more (the memory kill, where local time stops growing
  because runs are killed).
- All machines: 24 of 42 the same, 15 one level, 3 more.
- Local-time breaking points do not move on any machine: CPU 0.75 core,
  soft memory 1152 MB, the process-limit edges. The ones that move are
  wall-time points, where model time dilutes the effect. So the paper states
  breaking points on local time.

## Results across machines (`machines.py` -> `machines.txt`): new Section 7

| Limit | M1 (2 vCPU) | M0 (4 vCPU) | M2 (8 vCPU) | Kind |
|---|---|---|---|---|
| CPU quota, local break | 0.75 core | 0.75 core | 0.75 core | same everywhere |
| CPU quota at 0.25, local | x4.8 | x3.9 to 4.0 | x4.0 | same mechanism |
| Threads, local break | 2 per vCPU | 2 per vCPU | 2 per vCPU | scales with vCPUs |
| Soft memory, break | 1152 MB | 1152 MB | 1152 MB | set by the task's file (1 GB) |
| Hard memory, kill | 640 MB | 640 MB | 640 MB | set by the tool (512 MB) |
| Disk read, local break | 150 MB/s | 150 MB/s | 50-150 MB/s | set by the disk (all 187 MB/s) |
| Process limit, crash edge | 12 to 14 | 16 to 17 | 24 to 28 | scales with vCPUs |

- **Process limit: the edge is the agent's own peak task count.** With no
  limit, the agent's cgroup peaks at 12-13 tasks (processes and threads)
  on 2 vCPU, 16-17 on 4, 24-26 on 8: about 8 + 2 per vCPU (the runtime's
  thread pools grow with the CPU count). The agent crashes (exit 134) when
  the limit is below that peak, on every machine. Rule for the paper: set
  `pids.max` above the agent's peak task count on the target machine; one
  unlimited run measures it.
- At 10 processes on M1, 3 of 5 agents crashed but 4 of 5 had already
  solved the task (crash after the work was done); at 17 on M0 (revision),
  1 of 10 the same.
- Hard memory: the solve rate drops to 0 at 640 MB on every machine; the
  agent itself survives (abnormal exits 0 to 2 of 5-10, from the agent
  being picked by the kernel).

## A7 + A9. Real tasks, per task (`a7_tasks.py` -> `a7.txt`)

Three outcomes kept apart:
- **Speed.** At 0.25 CPU / 512 MB every short task is slower on every
  machine: wall x1.35 to x2.38, local x1.6 to x6.5. At 1 CPU the wall change
  is within noise for most tasks (Django-15930 on M2: x1.37).
- **Success.** No task that is solvable without limits loses success under
  any size on any machine (every cell 5/5 or 10/10). xarray-6992 (never
  solved, also unlimited) and pytest-10356 (1 of 5 unlimited) are marked and
  left out of every success claim.
- **Behaviour.** Turns and tool calls hardly change on the short tasks
  (median 4 turns at every size). On the long, failing xarray-6992 they grow
  from 4 to 10-11 turns under 512 MB (it hits the memory limit 4 to 9 times
  per run).

## A8. Two limits at once (`a8_pairs.py` -> `a8.txt`)

The plan said 4 pairs exist; 3 pairs have both single limits measured on
the same task, 3 only one of them.

| Pair (t3) | Local: pair vs singles | Verdict |
|---|---|---|
| CPU 0.5 + disk 20 MB/s | 2.53 vs 1.92 and 1.84 (sum 2.76) | less than additive |
| CPU 0.5 + memory 256 MB | 2.04 vs 1.82 and 1.04 | slightly more than multiplying |
| memory 192 MB + 20 processes | 1.22 vs 1.23 and 0.90 | the stronger limit alone |

- CPU and disk slow different moments of the run (CPU-heavy slices, read
  slices), so their costs overlap instead of adding. The replay predicts
  this: it takes the larger of `d/q` and `b/r` per slice.
- Wall time: for every pair the interval holds both the sum and the
  product; model time hides the difference.
- t6 soft memory 768 MB + disk 50 MB/s: x7.5 wall against x2.2 for memory
  alone (pages that memory drops are read again through the slow disk).

## A10. Mechanisms and numbers

| Finding | General mechanism | Number depends on |
|---|---|---|
| CPU quota: local slows from 0.75 core | quota below the agent's CPU bursts | task (bursts of the test run) |
| Wall hides local slowdown | model wait dilutes it (Eq. 1) | task (`f`) |
| Soft memory cliff | file pages reclaimed and reread | task (file size) |
| Hard memory kill | tool + agent above `memory.max` | tool and agent memory |
| Process crash | limit below the runtime's peak tasks | vCPU count (8 + 2/vCPU) |
| Density saturates | CPU contention, CPU per agent doubles | vCPU count (4 agents/vCPU) and task |
| Printed time changes the plan | agent reads a moving slow number | model (Haiku strong, Fable weaker, Opus none) |

Recommendations become: "for the tested setup" plus how to calibrate:
measure the agent's peak task count and its unlimited trace on the target
machine, then set `pids.max` above the peak and use the replay to choose
the CPU quota.

## A11. Many agents on one machine (`a11_density.py` -> `a11.txt`)

| Machine | Throughput stops at | Peak agents/min | From one agent | Over-estimate |
|---|---|---|---|---|
| M1 (2 vCPU) | 8 agents | 7.7 | 19 | x2.5 |
| M0 first pass (4) | 16 | 16.5 | 41 | x2.5 |
| M0 revision (4) | 16 | 15.4 | 38 | x2.5 |
| M2 (8 vCPU) | 32 | 33.9 | 79 | x2.3 |

- Saturation at about 4 agents per vCPU on every machine.
- CPU seconds per agent double under crowding (about 6 -> 12-13), so a
  capacity estimate from one agent is 2.3-2.5 times too high everywhere.
- Memory about 150 MB per agent at high N on every machine.
- p95 agent wall is 1.0-1.1 times the median from 16 agents up (up to 1.3 at 8).
- All 945 agents solved (189 + 189 + 93 + 381 + 93).
- Second task (Requests in Docker, M0): lighter (4.5 CPU-s), still growing
  at 16 agents (19.5 agents/min), so the saturation point depends on the task.

## Tracing cost under limits (`overhead.py` -> `overhead.txt`), review issue 4

| Setting | Wall full/none [95%] | Cgroup CPU full/none |
|---|---|---|
| no limit | 0.99 [0.93-1.03] | 1.07 |
| 0.25 core | 1.00 [0.94-1.07] | 1.02 |
| memory 192 MB | 1.01 [0.88-1.11] | 1.04 |
| 8 agents | 1.08 [0.93-1.25] | 1.08 |

No setting shows a wall change; a tight quota does not make tracing
costlier. The tracer's consumer daemon runs outside the agent's cgroup, so
its CPU is not in these numbers (it competes only for the machine, which
matters at 8 agents; the interval there reaches +25%).

## Behaviour (`behaviour.py` -> `behaviour.txt`), review priority 4

Printed run time, Haiku at 0.25 core unless noted (tool calls after the
tests first passed, median; one-sided rank-sum, Holm):

| Comparison | After first pass | Wall | p (Holm) |
|---|---|---|---|
| New disk: printed vs silent | 4 vs 0 | 79 vs 30 s | 0.019 |
| Printed slow vs fixed fast number | 4 vs 0 | 79 vs 33 s | 0.002 |
| Printed vs same + "run time is not a goal" | 4 vs 0 | 79 vs 31 s | < 0.001 |
| Fixed slow number, no limit, vs printed, no limit | 0 vs 0 | 17 vs 18 s | 1.0 |
| Fable: printed vs silent | 1 vs 0 | 64 vs 37 s | < 0.001 |

- Replicates on the new disk, and with a second model (Fable, weaker:
  1 extra tool call, but 13 of 15 runs talk about speed).
- A fixed fast number removes it; one sentence in the prompt removes it.
- A fixed slow number on a fast machine does not cause it. So the trigger
  is not the number alone. I'm not sure why; one reading is that the agent
  chases a number that moves when it edits the code, and a fixed number
  gives it nothing to chase.

Silent test kill (t12, `memory.max` 768 MB, output piped through `tee`):

| | Agent itself killed | Report names the kill | Ran tests without tee |
|---|---|---|---|
| Haiku, limit | 6 / 10 | 4 / 4 | 9 / 10 |
| Opus, limit | 3 / 10 | 7 / 7 | 7 / 10 |
| no limit (both) | 0 / 20 | (warnings only) | 0 / 20 |

- The limit covers the agent and its tests. When the test grabs 700 MB,
  the kernel kills the agent in 9 of 20 runs: the session ends with no
  report, although the code is already correct.
- When the agent survives, it finds the kill (it reruns the test without
  `tee` to see exit 137) and says so; none claimed success.
