# The other 14 campaigns: Claude Code (analyzed 2026-11-10)

443 runs on `agentic-noise-2` (kernel `7.0.0-1017-gcp`, 4 vCPUs), Claude Code
2.1.322, full kernel trace, cold cache. Model `claude-opus-5-5` except in
`cpu_model2`. The `cpu` campaign is in `CPU-CAMPAIGN.md`.

How it was produced:

```bash
# unpack without the raw trace folders (18 GB instead of 92 GB)
zstd -dc osn-export/<c>.tar.zst | tar -x --exclude='*/trace'
# three trace passes + the wall-clock split, per campaign
OSNOISE_RUNS=<runs root> python phase2/run_passes.py <campaign> ...
python collector/summarize.py <runs root>/<c> --by <key> --csv phase2/<c>/counters.csv
python phase2/report.py <c> <key>          # -> phase2/<c>/report.txt
OSNOISE_RUNS=<runs root> python phase2/density_agents.py > phase2/density/diag_agents.jsonl
```

Per campaign folder: `analyze_all.jsonl`, `parsed_all.jsonl`, `diag_all.jsonl`,
`step1_runs.csv`, `step1_turns.csv`, `counters.csv`, `report.txt`.

All times below are medians in seconds. "Verdict" is the Phase 1 procedure
with its thresholds unchanged (memory: 50 reclaim episodes; disk: 1 s of
disk sleep with no request in flight; CPU quota: 0.3 s ready while a CPU is
idle; CPU competition: 1 s ready while all CPUs are busy).

## Are the trace numbers sound?

| Campaign | Runs | Trace CPU vs `cpu.stat` (median, worst) | Model time, trace / agent |
|---|---|---|---|
| network | 40 | 0.73%, 1.0% | 1.00 (0.99 to 1.20) |
| threads | 20 | 0.32%, 1.1% | 0.99 |
| subagents | 20 | 0.95%, 1.3% | 0.47 (see N6) |
| disk | 30 | 2.17%, 3.2% | 0.99 |
| memory_soft | 25 | 2.31%, 4.5% | 0.99 |
| memory_hard_file | 20 | 3.20%, 4.2% | 0.99 |
| memory_cliff | 45 | 1.32%, 1.9% | 0.99 |
| e2e_disk | 20 | 0.76%, 1.0% | 0.99 |
| neighbour | 25 | 0.20%, 0.8% | 0.99 |
| two_limits | 20 | 2.79%, 4.0% | 0.97 (one cell 5.6 to 7.4, see N6) |
| cpu_model2 | 80 | 0.86%, 1.4% | 0.99 (one run 0.24, not explained) |
| pids | 35 | 0.66%, 0.9% | 0.99 |
| density | 18 | 0.14%, 0.7% | group level, not valid (see N6) |
| e2e_memory | 45 | 0.77%, 6.2% | 0.99 |

- CPU accounting holds everywhere. The gap is larger (2 to 4%) in the
  campaigns with heavy disk reads and reclaim. Not investigated.
- All 19 runs the verify step flagged are real outcomes: 10 kernel memory
  kills (exit 137, `oom_kill 1`) and 9 aborts at the process limit (exit 134).

## Findings

### N1. A tight CPU quota makes the agent do more model work (answers the open question from `cpu`)

Implement task, median per run:

| Model | CPU | Wall | Model time | Turns (agent) | Agent CPU | Cost |
|---|---|---|---|---|---|---|
| Opus | unlimited | 20.6 | 14.6 | 5 | 6.4 | $0.149 |
| Opus | 0.25 core | 41.4 | 18.6 | 5 | 6.8 | $0.152 |
| Fable | unlimited | 19.2 | 14.5 | 3 | 5.6 | $0.350 |
| Fable | 0.5 core | 47.8 | 29.5 | 4 | 9.7 | $0.400 |
| Fable | 0.25 core | 62.5 | 24.3 | 4 | 10.0 | $0.396 |
| Haiku | unlimited | 17.8 | 12.5 | 5 | 5.8 | $0.005 |
| Haiku | 0.25 core | 88.3 | 27.1 | 14 | 16.8 | $0.009 |

- Time to first byte does not change with the quota. The model is not slower.
- What changes: more turns and more bytes from the model per run.
- The agent's own event stream shows why. The task's test prints how long
  its stress loop took. Under the quota it prints "stress 15.7s" instead of
  "2.6s". The agent reads that and starts to optimize code that already
  passes: it benchmarks variants, rewrites, and tests again.
- On the bug-fix task (no timing printed) there is no such effect in any
  model.
- Meaning: a resource limit can change what the agent decides to do, not
  only how fast it runs. The slowdown is then larger than the throttling
  alone, and the cost goes up (Fable +13%, Haiku +80%).
- Limit: seen on one task, read by hand in 3 runs. It needs a count over
  all runs (does the agent do work after the first ALL PASS?) and a second
  task before it is a claim.

### N2. Diagnosis on new mechanisms and new models

| Campaign | What was done | Runs | Named correctly |
|---|---|---|---|
| disk | read limit, 5 levels + none | 30 | 30 |
| e2e_disk | read limit on a coding task | 20 | 20 |
| memory_soft | `memory.high`, 4 levels + none | 25 | 25 |
| memory_hard_file | `memory.max` on file cache | 20 | 20 |
| memory_cliff | `memory.max` on anonymous memory | 45 | 45 |
| e2e_memory | `memory.max` on a coding task | 45 | 45 |
| threads | 2 to 16 workers on 4 CPUs | 20 | 20 |
| cpu_model2 | CPU quota, Haiku and Fable | 80 | 77 |
| neighbour | CPU, I/O and memory neighbours | 25 | 16 of 20 with a real effect (see N4) |

- "Correct" for a limit that never binds (for example `memory.max` above
  the peak) means "nothing found".
- The three misses in `cpu_model2` are the 1-core quota again.
- The verdict says a limit is acting, not that it costs time: at
  `memory.max` 1280M and at 768M in `memory_cliff` it reports memory (65 and
  89 reclaim episodes) and the run is not slower.

### N3. Where the diagnosis fails, and the fix for each

- **Two limits at once** (`two_limits`, 20 runs): the procedure returns the
  first signal only, always memory or disk. In CPU quota + `memory.max`
  256M it says memory, but the cost is the quota (7.4 s throttled against
  0.03 s of reclaim). If every signal above its threshold is reported, all
  20 runs get both limits named. The procedure should return a list with
  the time behind each signal.
- **Many agents** (`density`): on the whole group it says CPU quota at 4
  and 8 agents and disk at 16 and 32. Both are wrong. The thresholds are in
  seconds and the group sums over all agents. Run per agent, it names CPU
  competition for all 180 agents at 4 or more agents, and nothing at 1 and 2.
- **Process limit** (`pids`): no signal of the four reacts. But this limit
  does appear as an error return: fork calls return EAGAIN 3 to 11 times in
  every run at 12 and 16, and 0 times in every run at 24 and above. This is
  the one limit that reaches the agent as an error (in Phase 1 none did).
  A fifth check is one line.
- **Network** (`network`): no signal reacts. The procedure has no network
  check. Start-up grows with delay (1.5 s to 3.3 s at 200 ms) and model
  time grows at 256 kbit/s (14.4 to 21.8 s). A check needs the TCP
  handshake time or retransmissions; this trace has no TCP events, only
  counters.

### N4. A neighbour costs CPU time that no waiting signal shows

| Neighbour | Wall | Agent on-CPU | Ready, CPUs busy | Tool time |
|---|---|---|---|---|
| none | 22.7 | 6.2 | 0.02 | 4.1 |
| CPU, 4 workers | 24.9 | 10.4 | 3.0 | 8.1 |
| CPU, 8 workers | 23.1 | 10.0 | 2.8 | 7.8 |
| memory, 2 workers | 24.6 | 10.5 | 0.66 | 7.5 |
| I/O, 2 workers | 21.3 | 6.3 | 0.04 | 4.5 |

- With a CPU or memory neighbour the agent needs 4 s more CPU time for the
  same work. It waits only 0.7 to 3 s. Most of the cost is slower execution
  while on the CPU, which a scheduler trace cannot see.
- The same appears in `density`: CPU time per agent goes from 6.0 s (1
  agent) to 12.2 s (32 agents).
- Likely cause: the 4 vCPUs are 2 cores with 2 hardware threads each, plus
  shared caches. I'm not sure; this VM has no hardware counters to confirm.
- The memory neighbour is missed by the diagnosis in 4 of 5 runs for this
  reason. This is the case for a machine with hardware counters.

### N5. Memory: the slow death is worse than the kill

`e2e_memory` (coding task, agent peak about 300 MB):

| `memory.max` | Solved | Wall | Reclaim episodes | Outcome |
|---|---|---|---|---|
| none to 384M | 15 of 15 | 18 to 21 | 0 | no effect |
| 320M | 5 of 5 | 19.5 | 0 (1 run above 50) | no effect |
| 256M | 5 of 5 | 20.6 | 359 | no cost |
| 192M | 5 of 5 | 22.8 | 1,234 | +2 s |
| 128M | 0 of 5 | 178 | 190,609 | killed after 82 to 273 s |
| 96M | 0 of 5 | 295 | 420,547 | killed after 111 to 403 s |
| 64M | 0 of 5 | 78 | 128,969 | killed after 63 to 81 s |

- The agent works at 64% of its peak with a 2 s cost. Below that it does
  not fail fast: it reclaims for minutes (83 s of kernel CPU at 96M) and is
  then killed. The worst limit is not the tightest one.
- These runs are 58 GB of the 92 GB of traces.
- `memory_cliff`: with 512 MB of anonymous memory in a tool, the tool is
  killed at 640M and below and survives at 704M and above. The agent
  itself survives and reports the kill in every run.
- `memory_soft` and `memory_hard_file`: a step, not a slope. As soon as the
  1 GB file does not fit, the run takes about 33 s instead of 15 s, the
  same at 1152M and 768M.

### N6. Limits of the model-turn rule (new)

- **Slow network**: the trace counts 1 or 2 turns more than the agent in
  all 20 runs with 100 ms or 200 ms delay or a rate limit. A slow non-model
  exchange passes the rule (2 KB request, 0.7 s response).
- **Haiku**: the trace counts 1 to 6 turns fewer than the agent in most
  runs. Model time still agrees (0.99).
- **Sub-agents**: the agent reports 2 turns and sums the API time of all
  sub-agents; the trace sees 15 to 25 turns on one process and measures
  wall time. The two are not comparable (ratio 0.47).
- **`memory.high` + disk limit**: trace model time is 6 to 7 times the
  agent's. The agent process itself is stalled on disk, so responses are
  read late.
- **Density**: one agent process is picked for the whole run. A per-agent
  version is needed.

### N7. Two limits can multiply

`memory.high` 768M alone: 33.8 s. Disk limit 50 MB/s alone (read task):
33.7 s. Both on the file-reading task: 116.9 s. The memory limit turns
cached reads into disk reads, and the disk limit then throttles them
(96 s of disk sleep with no request in flight).

### N8. Smaller results

- **Disk limit and start-up**: with a cold cache, start-up goes from 1.5 s
  to 5.8 s at 20 MB/s and to 23 s at 5 MB/s. Model time does not move.
- **Network**: all 40 tasks solved. Worst case +6 s (256 kbit/s).
- **Threads**: 8 workers on 4 CPUs wait 7.6 s, 16 workers wait 45.9 s.
- **Sub-agents**: 4 or 8 sub-agents caused no CPU competition (ready-wait
  0.04 s) in any of the 20 runs.
- **Process limit**: the agent needs 18 to 21 tasks. At 24 and above there
  is no effect; at 16 and below it aborts in 2.5 to 3.5 s (one run at 16
  survived 11 failed forks and solved the task). There is no middle zone
  in this campaign; levels 17 to 23 are missing.
- **Density**: 189 agents, 0 failed tasks. Time per agent: 20 s (1 agent),
  23 s (4), 32 s (8), 52 s (16), 97 s (32). Model time per agent is flat
  up to 16 agents and +20% at 32. Cost per agent is flat.

## What this changes

- The diagnosis procedure needs four changes: report all signals, run per
  agent, add the fork-error check, add a network check.
- The model-turn rule needs the agent's event stream as the reference for
  turn counts; the trace rule is good for time, not for counts.
- N1 and N4 are the two results that are new compared with Phase 1 and with
  the two related papers. Both need more data before they are claims.

## Two follow-up campaigns (collected 2026-11-11, 155 runs)

Collected to close two open points above. Both complete, 0 measurement
problems, one kernel. Trace CPU agrees with `cpu.stat` (median gap 0.65%
and 0.59%). Archives: `feedback.tar.zst`, `pids_mid.tar.zst` in the same
export folder. Per-campaign files in `phase2/feedback/` and
`phase2/pids_mid/`; the table below is `phase2/feedback/cells.txt`
(`feedback_cells.py`).

### N9. The extra work under a CPU quota is caused by the printed run time (confirms and narrows N1)

`feedback`: 2 models x 4 tasks x 3 CPU levels x 5 reps = 120 runs, all
solved. Tasks: the implement task whose test prints `stress X.Xs` (t3),
the same task with that line removed (t9), and a second task (expression
evaluator, t10) with and without a printed `bench X.Xs`.

Haiku, medians of 5 runs (CPU level: no limit / 50% / 25% of one CPU):

| task | turns | tool calls after the first pass | runs that talk about speed |
|---|---|---|---|
| t3, time printed | 5 / 7 / 11 | 0 / 2 / 8 | 1 / 4 / 5 |
| t9, same task, no time printed | 7 / 8 / 7 | 0 / 0 / 0 | 0 / 1 / 0 |
| t10, time printed | 7 / 6 / 9 | 0 / 0 / 0 | 0 / 2 / 5 |
| t10, no time printed | 8 / 6 / 7 | 0 / 0 / 0 | 0 / 0 / 1 |

- With the time printed, Haiku keeps working after the tests pass (8 tool
  calls at 25%); with the line removed it stops. Same task, same limit,
  so the printed number is the cause, not the quota by itself.
- CPU used by the group grows from 4.8 s to 11.8 to 13.7 s on t3 with the
  time printed, and stays at 5.2 to 5.6 s without it. Output tokens grow
  from 1974 to 3883.
- On the second task the effect is weaker: Haiku mentions speed in 5 of 5
  runs at 25%, turns go 7 to 9, but it rarely acts after the pass. The
  printed time there is smaller (the loop takes 2.3 s unlimited).
- Opus mentions the time in 3 of 5 runs on t3 under a limit but does no
  extra work on any task (4 to 5 turns everywhere).
- Diagnosis: CPU quota named in 80 of 80 limited runs, nothing in 40 of 40
  unlimited runs.
- Limits: 5 reps per cell, Haiku has a wide spread without a limit (5 to
  13 turns on t3), two small tasks, one agent. The trace turn rule
  under-counts here (61 of 120 equal); turn counts above are the agent's own.

### N10. Process limit: the edge is between 20 and 21

`pids_mid`: limits 17 to 23, 5 reps each, 35 runs.

- Failed process creations (fork, vfork, clone, clone3 returning EAGAIN):
  17: 3 to 6 per run; 18: 2 to 3; 19: 1 to 2; 20: 1 to 2; 21, 22, 23: 0 in
  all 15 runs. So the fork-error check separates limited from unlimited in
  35 of 35 runs here (and in all 35 of the first `pids` campaign).
- This is the middle zone the first campaign missed: at 17 to 20 the agent
  hits the limit but mostly survives. 3 of 20 runs aborted (exit code 134,
  one each at 17, 18, 19); 2 of those left the task unsolved. The other 17
  solved the task with 1 to 6 failed forks and no visible slowdown.
- The four time signals stay silent in all 35 runs, as before.
