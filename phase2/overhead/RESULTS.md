# What does the tracing itself cost?

Analyzed 2026-11-15. Campaigns `overhead` (coding task t3, 10 runs per
profile) and `overhead_real` (Django real task in Docker, 5 per profile).
Profiles: no trace, `core` (main subset) and `full` (every tracepoint and
system call, used in every other campaign). Same VM, same collector, Opus.

```
cd phase2 && OSNOISE_RUNS=... python overhead/analyze.py   # -> overhead/overhead.txt
```

## Results

Full trace against no trace (ratio of medians, 95% bootstrap interval,
exact one-sided rank-sum p that the traced runs are slower):

| Measure | Coding task (10 vs 10) | Django real task (5 vs 5) |
|---|---|---|
| Wall | x0.99 [0.93-1.03], p=0.80 | x1.00 [0.88-1.18], p=0.50 |
| Local (wall - model) | x1.07 [0.98-1.11], +0.48 s, p=0.08 | x0.98 [0.82-1.27], p=0.60 |
| Tool time | x1.08 [0.97-1.18], +0.33 s, p=0.03 | x0.99 [0.73-1.50], p=0.66 |
| CPU time of the agent's group | x1.07 [0.99-1.22], +0.42 s, p=0.01 | x0.99 [0.66-1.56], p=0.35 |
| Start-up | x0.95, -0.12 s | x0.99 |
| Solved | 10/10 in every profile | 5/5 in every profile |
| Discarded trace events | 0 | 0 |

The `core` profile costs about the same as `full` (CPU +0.45 s, local
+0.47 s on the coding task).

What this means:

- **The user sees no cost from the tracing.** Wall time does not change on
  either task.
- **The full trace adds about 7% CPU time to the agent (+0.4 s per run)
  on the coding task.** This is the cost of writing every system call and
  scheduler event. It shows in tool time (+0.3 s) and local time
  (+0.5 s, interval includes no change). On the Django task, the run-to-run
  spread (x0.66 to x1.56) is larger than any tracing cost, so none is seen.
- **No events were lost** in any of the 30 traced runs.
- **For the paper:** every slowdown we report is a ratio between two cells
  that are both traced, so a constant 7% CPU cost mostly cancels. The
  smallest effects we claim (+24% local with 4 workers, +35% at 0.75 core)
  are 3 to 5 times larger than this cost.
- Start-up is 0.1 s faster with tracing. Probably the tracer start reads
  files that the agent's start then finds in memory (the cache is dropped
  before the tracer starts). I'm not sure; not checked.

## Limits

- The tracing cost depends on how many system calls a run makes. A task
  that makes many more than ours would pay more.
- The tracer's own consumer process runs outside the agent's group; its CPU
  time is not in these numbers. On 4 vCPUs with the agent using under one
  core, it does not compete for CPU, but under a tight CPU quota it does
  not count against the agent's quota either.
- 15 older overhead runs from 2026-11-10 (earlier collector) are kept on
  the VM in `overhead_nov10`, not used here.
