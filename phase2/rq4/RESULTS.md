# RQ4. How many agents can share one machine?

Analyzed 2026-11-13. Campaign `density`: 1, 2, 4, 8, 16 and 32 Claude Code
agents (Opus) started at once on one 4-vCPU, 15 GB VM, each on its own copy
of the same small coding task (`t3_implement`), no limits, 3 runs per level,
189 agents in total.

```
cd phase2
python rq4/agents.py      # -> rq4/agents.csv (one row per agent), rq4/table.txt
```

## Method

- Per agent, from its own event log: wall = run start to its final result;
  start-up, model time and tool time as in RQ1. Local = wall minus model.
- Waits per agent process tree from the trace (`density/diag_agents.jsonl`).
  Waiting for CPU = ready to run while all CPUs were busy; summed over
  threads, so it can be larger than the wall time.
- Throughput = agents finished per minute = N / time until the last agent
  of the run finished.
- Memory peak is for the whole group (`meta/memory.peak`); cost is each
  agent's own reported cost.

## Results (medians per agent)

| Agents | Solved | Wall | x wall | x local | Start-up | Model | Tools | CPU used | CPU wait | Agents/min | Memory (group) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3/3 | 21 s | 1.00 | 1.00 | 1.4 s | 16.4 s | 4 s | 5.9 s | 0 s | 2.8 | 0.3 GB |
| 2 | 6/6 | 22 s | 1.02 | 1.02 | 1.6 s | 16.5 s | 4 s | 6.1 s | 0.2 s | 4.9 | 0.5 GB |
| 4 | 12/12 | 25 s | 1.14 | 1.41 | 2.0 s | 16.4 s | 6 s | 8.3 s | 1.7 s | 8.9 | 0.8 GB |
| 8 | 24/24 | 34 s | 1.57 | 3.22 | 3.6 s | 16.2 s | 14 s | 11.0 s | 12 s | 13.1 | 1.4 GB |
| 16 | 48/48 | 56 s | 2.63 | 7.04 | 7.3 s | 17.0 s | 31 s | 11.6 s | 43 s | 16.3 | 2.5 GB |
| 32 | 96/96 | 105 s | 4.92 | 15.9 | 14.8 s | 20.3 s | 71 s | 12.2 s | 122 s | 16.5 | 4.8 GB |

What this means:

- **All 189 agents solved the task.** Crowding makes agents slow, not wrong.
- **Up to 2 agents (half an agent per vCPU): free.** No change.
- **4 agents (one per vCPU): the first cost.** Local time +41%, wall +14%.
  The user barely notices; the machine already does.
- **8 agents (two per vCPU): clearly slower.** Wall x1.57, local x3.2.
- **The machine is full at about 16 agents (four per vCPU).** Throughput
  grows from 2.8 to 16.3 agents per minute, then stops: 32 agents finish
  at the same rate as 16 (16.5 per minute), each just waits twice as long.
  Past this point, more agents only add waiting.
- **CPU is the limit, not memory.** Each extra agent adds about 150 MB
  (0.3 GB for one, 4.8 GB for 32). On this 15 GB machine memory would last
  to roughly 90 agents; CPU runs out at 16.
- **Where the time goes:** tools (4 s to 71 s) and start-up (1.4 s to
  15 s). Model time is flat up to 16 agents and +24% at 32. Waiting for
  the model still hides some of the cost: at 4 agents the machine's part
  is +41%, the user sees +14%.
- **Each agent uses more CPU when crowded:** 5.9 s alone, 12.2 s at 32
  agents, for the same work. This is finding N4 again (a CPU neighbour
  makes the agent's own CPU time grow). Likely cause: the 4 vCPUs are 2
  cores with 2 hardware threads each, plus shared caches. I'm not sure;
  this VM has no hardware counters to check.
- **Fair sharing:** the slowest agent in a run is close to the median
  (32 agents: median 105 s, 90th percentile 112 s, max 123 s). No agent is
  starved.
- **Cost per agent is flat** ($0.144 to $0.152). Crowding costs time, not
  money.
- **Rule of thumb for operators (this task, this machine):** one agent per
  vCPU keeps the user-visible slowdown near 15%; above four per vCPU,
  throughput no longer grows.

## Limits of this analysis

- One small task (median 5 model turns, 4 s of tools alone). Agents with
  heavier tests (RQ3: 7 to 22 s of tools) will fill the machine sooner.
- All agents start at the same moment, so their start-ups and test runs
  collide more than in a real service where arrivals are spread out.
  This is a worst case for start-up.
- 3 runs per level, one machine shape, no intervals: the agents inside a
  run are not independent, so the run is the unit and 3 is too few for a
  bootstrap.
- The +24% model time at 32 agents: possibly the agent reads the answer
  stream later when it is waiting for CPU, which the log counts as model
  time. I'm not sure; not checked.

## Open

- Check whether model time at 32 agents is local delay in reading the
  stream (compare the trace's network receive times with the log times).
- Optional extra data: spread-out arrivals (one new agent every few
  seconds) to see the steady-state capacity instead of the burst.
