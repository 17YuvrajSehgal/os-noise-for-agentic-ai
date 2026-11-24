# Research questions (extended paper)

Written 2026-11-13. Data: 808 Claude Code runs (Phase 2), list in
`../todo-list.md` and archives in
`microservice-trace-dataset/agentic-runs-phase2/osn-export/`. We work on the
questions in this order, one at a time; each gets its own results file.

## RQ1. Anatomy: where does an agent's time go when nothing limits it?

- Split each run into: start-up, waiting for the model, running tools, the
  agent's own work, and time lost to the system (waiting for CPU, disk,
  memory).
- Model turns are counted from the agent's own event log, not guessed from
  network traffic (the network rule miscounts on slow networks, with Haiku,
  and with sub-agents).
- Data: the unlimited runs of every experiment, plus the 30 `real_host` and 30
  roomy `real` runs (real tasks).
- Output: `phase2/rq1/`.
- Status: first pass done 2026-11-13, see `rq1/RESULTS.md`. Model wait is
  about two thirds of the time (Opus median 68%), tools 20%; real tasks
  spend more in tools (16 to 39%); Docker adds 1.2 s to start-up.

## RQ2. Mechanisms: how does each limit change that picture?

- Limits: CPU quota, memory (soft, hard, file memory), disk speed, network,
  process count, more threads than cores, a busy neighbour, two limits at
  once.
- For each: slowdown against limit size, the point where it gets bad, and
  which part of the time split grows.
- Data: `cpu`, `cpu_model2`, `memory_*`, `e2e_*`, `disk`, `network`, `pids`,
  `pids_mid`, `threads`, `neighbour`, `two_limits`, `subagents`.
- Output: `phase2/rq2/`.
- Status: first pass done 2026-11-13, see `rq2/RESULTS.md`. Measured on
  local time (wall minus model wait), because model noise hides effects
  under 20% in wall time. Three shapes: smooth (CPU, disk, threads), cliff
  (memory), abort (process count). Figures to do.

## RQ3. Realistic use: do real platform settings hurt real coding tasks?

- Six SWE-bench Verified tasks in Docker at four settings from official
  platform docs: no limit; 2 CPU / 8 GB (CI runners); 2 CPU / 512 MiB (agent
  sandbox); 1 CPU / 512 MiB (Cloud Run, Kubernetes example).
- Also: what the container itself costs (`real` no limit against
  `real_host`), and how close runs come to the memory limit.
- Data: `real` (120), `real_host` (30), `real_quarter` (30).
- Output: `phase2/rq3/`.
- Status: first pass done 2026-11-13, see `rq3/RESULTS.md`. 120/120 solved,
  no memory kills, no clear slowdown at any setting. 1 CPU makes the same
  test command 2 to 9% slower; Django hits the 512 MB limit in 9/10 runs
  but survives. Extra cell `real_quarter` (0.25 CPU / 512 MB, 30 runs):
  30/30 solved but x1.76 wall, x2.53 local, same test command x3.3. The
  RQ2 breaking point holds on real tasks.

## RQ4. Density: how many agents can share one machine?

- Time per agent, success, and the cause of the slowdown for 1 to 32 agents
  on 4 vCPUs.
- Data: `density` (18 runs, 189 agents).
- Output: `phase2/rq4/`.
- Status: first pass done 2026-11-13, see `rq4/RESULTS.md`. 189/189
  solved. Free up to 2 agents; 4 (one per vCPU) local +41%, wall +14%;
  throughput stops at about 16 agents (16.5 per minute); CPU is the limit,
  memory about 150 MB per agent; cost per agent flat.

## RQ5. Behaviour: does the agent change what it does because of the system?

- The printed-time effect: when the test prints its own run time and the CPU
  is limited, Haiku keeps working after the tests pass; Opus does not.
- Also: how the agent reacts to errors from the system (failed process
  starts at the process limit, memory kills).
- Data: `feedback` (120), `cpu`, `cpu_model2`, `pids`, `pids_mid`,
  `e2e_memory`.
- Output: `phase2/rq5/`.
- Status: first pass done 2026-11-13, see `rq5/RESULTS.md`. Printed time:
  Haiku 11 vs 7 turns (p=0.012), wall 70 vs 31 s; Opus no extra work.
  Memory kill: agent names it in 23/23 and stops; 2/25 the agent itself
  is killed. Process limit: the agent rarely sees an error; it crashes
  itself (exit 134) in 12 of 25 runs at 19 and below. Real tasks at 0.25
  CPU: same tests, no mention of slowness. Tests not corrected for
  multiple comparisons; 10 more Haiku runs per cell would fix that.

## The workshop paper's results

The workshop paper (OXAI 2026) was withdrawn and is only on arXiv, so all
its experiments and results go into this paper, on the old and new data.
Done 2026-11-13, see `workshop/RESULTS.md`: 14 claims, 9 confirmed
(several with narrower edges), 5 corrected or refined (84% → ~75%; on-CPU
not flat for small models; the agent itself is OOM-killed in 2 of 25;
disk bites at start-up; trace vs `cpu.stat` under 1.5%).

## RQ6. Diagnosis: can a fixed method name the cause of a slow run? Can cheap counters do it?

- Thresholds frozen from Phase 1, tested on all new runs, with the four fixes
  found in Phase 2 (report every signal, judge each agent separately, check
  failed process starts, state that the network is not covered).
- Same test with the simple counters only, to show what each data source
  costs and gives.
- Data: all runs; the applied limit is the ground truth.
- Output: `phase2/rq6/`.
- Status: verdicts exist per experiment (`phase2/<c>/report.txt`).
- Open: the method is also central to another paper in progress. Confirm
  with the supervisor how this paper presents it before writing it up; the
  safe framing is "our measuring tool, and how often it is right".
