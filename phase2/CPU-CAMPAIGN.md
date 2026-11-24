# First new campaign: CPU quota, Claude Code (2026-11-10)

60 runs on the new VM (`agentic-noise-2`, kernel `7.0.0-1017-gcp`), Claude
Code 2.1.322 with `claude-opus-5-5`, full kernel trace, cold cache. Two
tasks x six CPU settings x 5 repetitions, in random order. Cost reported
by the agent: $8.56. Trace size: 2.8 GB.

Files: `cpu/osn-summary-cpu.csv` (per run, from counters and the agent's
report), `cpu/step1_runs.csv`, `cpu/step1_turns.csv`, `cpu/diag_all.jsonl`,
`cpu/analyze_all.jsonl` (from the trace), `cpu/cpu_check.txt`.

## Is the measurement complete?

`verify_campaign.py`: 60 runs, 0 with a measurement problem, one kernel.
Every run has its raw trace, 0 discarded events, a complete decoded trace,
the agent's event stream, all counters and the time series. All 60 tasks
were solved.

## Do the new traces give sound numbers?

Each trace-based number was checked against an independent source.

| Check | Result |
|---|---|
| Trace on-CPU time against `cpu.stat` | median gap 0.74%, worst 1.1% |
| Trace ready-wait with idle CPUs against throttled time | ratio 1.08 (range 1.03 to 1.17) |
| Model turns: trace against the agent's own count | equal in 51 of 60 runs, one fewer in 8, one more in 1 |
| Model time: trace against the agent's own API time | ratio 0.98 (range 0.92 to 0.99) |

The last two are new. Phase 1 could not validate the model-turn rule
(F73); the agent's event stream now does.

## Result

Median seconds, n = 5 per cell:

| Task | CPU | Wall | Start-up | Model | Tool only | Throttled |
|---|---|---|---|---|---|---|
| bug-fix | unlimited | 18.4 | 1.53 | 14.8 | 1.74 | 0.0 |
| bug-fix | 1 core | 19.5 | 1.74 | 14.7 | 2.10 | 0.33 |
| bug-fix | 0.75 core | 16.7 | 1.95 | 11.2 | 2.64 | 1.86 |
| bug-fix | 0.5 core | 20.5 | 2.87 | 12.7 | 3.88 | 4.84 |
| bug-fix | 0.375 core | 22.2 | 3.98 | 11.8 | 5.23 | 8.05 |
| bug-fix | 0.25 core | 27.0 | 5.48 | 12.2 | 7.90 | 14.85 |
| implement | unlimited | 20.6 | 1.50 | 14.6 | 4.12 | 0.0 |
| implement | 1 core | 18.1 | 1.67 | 12.0 | 3.82 | 0.24 |
| implement | 0.75 core | 21.2 | 1.98 | 12.7 | 5.52 | 2.31 |
| implement | 0.5 core | 25.0 | 2.75 | 14.1 | 7.94 | 6.59 |
| implement | 0.375 core | 31.6 | 4.10 | 15.4 | 10.92 | 11.68 |
| implement | 0.25 core | 41.4 | 5.30 | 18.6 | 16.52 | 24.99 |

- **The Phase 1 picture repeats on new data.** Start-up and tool time grow
  step by step as the quota tightens; throttle time grows from 0 to 25 s.
- **The two new steps fill the gap.** At 0.75 core throttling is already
  visible (about 2 s) but the run is barely slower. The cost becomes clear
  at 0.5 core.
- **Start-up scales as predicted**: 1.5 s unlimited, 5.3 to 5.5 s at 0.25
  core.
- **One thing differs from Phase 1**: on the implement task, model time
  rises at the tightest quotas (14.6 to 18.6 s). On the bug-fix task it
  does not. Not yet explained. The number of turns varies between runs,
  so this needs the per-turn view before any claim.

## Diagnosis on data it has never seen

The four thresholds were frozen in Phase 1 on the old runs. On these 60 new
runs:

| What was done | Runs | Named correctly |
|---|---|---|
| No limit | 10 | 10 |
| 1 core | 10 | 8 (2 called "nothing found") |
| 0.75, 0.5, 0.375, 0.25 core | 40 | 40 |

58 of 60. The two misses are the mild 1-core quota, as in Phase 1. This is
the first out-of-sample test of the procedure, on one mechanism only.

## What the full trace does and does not contain

The `full` profile enables every tracepoint the tracer offers on this
kernel: 298 event types. In a real run the events are, by group: system
calls, timers, RCU, scheduler, interrupts, power (idle), block, SCSI,
writeback, workqueues, network device, socket buffers, signals, modules,
journal.

Not available from this tracer on this kernel, so not in the trace:

- **Page faults** (the tracer's module for them does not exist for this
  kernel).
- **TCP-level events and memory-allocation events** (no probe module).
- **Kernel function probes** (module missing).

These are covered at counter level instead: page faults and reclaim in
`memory.stat` and `/proc/vmstat`, TCP retransmissions in
`/proc/net/netstat` and in the packet headers of the network events.

## Problems found and fixed on the way

- The tracer crashes the kernel when asked for hardware counters on a VM
  without them. Now off unless set by hand.
- This kernel rejects one trace context (`mnt_ns`). Contexts are now added
  one by one.
- The first setup script disabled no background timers.
- Throttle counters live in the agent's own cgroup, not in its parent. The
  flat counter copies now come from the right place.
