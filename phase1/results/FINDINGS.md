# Phase 1 findings: everything the existing traces told us

Date: 2026-11-10. Data: 262 kernel traces (132 Claude Code, 130 Codex) from
the workshop study. No new runs were made. Detail and rerun commands are in
`STEP0.md` to `STEP4.md` in this folder.

"Coding runs" = the bug-fix and implement tasks. Unless said otherwise,
numbers are medians over the 10 unlimited coding runs of each agent.

Every finding has a number (F1 to F73) so it can be referred to later.

---

## A. Is the data sound?

- **F1. The workshop numbers reproduce exactly.** With the released code,
  every number in the four problem tables, the cross-agent comparison and
  the 84% figure comes out the same.
- **F2. The analyzer had a bug, now fixed.** Its pattern for scheduler
  switches did not match threads with a negative priority (real-time kernel
  threads). When such a thread handed a CPU to an agent thread, the agent's
  CPU time was counted as waiting.
- **F3. After the fix, trace CPU time agrees with `cpu.stat`.** Median gap
  0.5% (was 2.3%), worst run 4.5% (was 35%), runs off by more than 5%: 0
  (was 39). The remaining 4% cases are Codex memory runs and are not
  explained.
- **F4. The fix changes some paper numbers.** Local compute per run 4.7 to
  5.3 CPU-s. Table 1 on-CPU column shifts slightly. Table 2 at 4 workers:
  wait 0.05 to 0.00 (now equals the prediction), on-CPU 0.91 to 0.94.
  Stalls of 1 ms or more: 8, 17, 2544, 5232. Stalls of 10 ms or more: 0, 0,
  0, 133. Wall time, throttle time, phase times, refaults, OOM counts and
  disk numbers do not change.
- **F5. Claude traces are healthy.** 131 of 132 have no lost events. Every
  trace covers its whole run. 36 runs have small gaps between packets; only
  3 are 1 ms or more.
- **F6. One run lost events**: `t3_implement_nocap_r5` (2 of 4 CPUs). It is
  one of the ten runs behind the model-share figure.
- **F7. The Codex raw traces no longer exist.** They are not on Zenodo, not
  on this PC, and the VM and its disk are deleted. The decoded text exists
  for all 130 Codex runs and all analysis uses it.
- **F8. Scheduler data is complete for every run.** A consistency check
  finds 0 breaks in 7.7 million scheduler switches over all 262 runs.
  Whether Codex runs lost events of other types cannot be verified.
- **F9. The network was clean in every run.** Zero retransmissions in about
  35,000 data segments. Round-trip time to both model endpoints: 10.8 ms.
- **F10. The runs did not all use one kernel.** 42 Claude runs used kernel
  `7.0.0-1011-gcp`, the other 280 used `7.0.0-1014-gcp`. The paper names
  one kernel. LTTng was 2.15.1; the paper says 2.15.3.
- **F11. Claude Code runs on the Bun runtime, not Node.** Its threads are
  named `Bun Pool`, `JSCWarmUp`, `JITWorker`. The paper calls it a Node
  process.
- **F12. The Zenodo archive is correct but smaller than described.** The
  checksum matches. It holds raw traces for the Claude runs only. `DATA.md`
  and `README.md` say every run's raw trace is there.
- **F13. Gaps in the saved metadata.** The Claude runs of Problems 1 and 2
  have no memory or I/O counters. The Claude end-to-end manifest lists 21
  of 30 runs. Some runs lack the agent version.
- **F14. Block bytes from the trace are about 1.9 times `io.stat`** (2,313
  MB against 1,228 MB for the 1 GB read). Not explained. Use `io.stat` for
  bytes.

## B. The shape of a run

- **F15. The model share is 76% for Claude Code and 90% for Codex**, not
  84%. Ranges: 71 to 86% and 85 to 93%. The old method counted every HTTPS
  exchange, including start-up configuration calls and telemetry uploads.
- **F16. Where the wall clock goes** (share of the run):

| Part | Claude Code | Codex |
|---|---|---|
| Start-up | 8.9% | 0.9% |
| Model only | 74.9% | 89.2% |
| Model and tool together | 1.4% | 0.3% |
| Tool only | 13.4% | 7.9% |
| Agent only | 0.4% | 1.1% |
| Shutdown | 1.3% | 0.6% |

- **F17. Run-to-run variation is mostly the number of model turns.** Claude
  bug-fix: 3-turn runs take 16 to 17 s, 5 or 6-turn runs take 23 to 27 s
  (correlation with wall time 0.99).
- **F18. The two agents work differently.** Claude Code needs 3 to 6 turns
  per task, Codex 6 to 15.
- **F19. Claude Code puts several tool calls in one turn and runs them
  while the response is still streaming.** Codex uses one turn per tool
  call.
- **F20. Start-up is CPU work.** Claude Code: 1.23 CPU-s and 1.65 s before
  the first model request. Codex: 0.28 CPU-s and 0.31 s.
- **F21. Start-up is more than half of the agent process's own CPU** for
  Claude Code (1.23 of 2.2 CPU-s).
- **F22. Cold caches add about 1 s to start-up** (Claude 2.6 s, Codex 1.6 s
  in the runs that drop caches first).
- **F23. CPU per run**: agent process 2.2 s (Claude) and 0.8 s (Codex).
  Tool processes about 3.0 s for both, which is the test suite.

## C. The model turn and the network

- **F24. A turn is about 1 s of waiting plus 1 to 2 s of streaming.** Wait
  for first byte: 1.13 s (Claude), 0.70 s (Codex). 90th percentile: 4.17 s
  and 1.75 s.
- **F25. Responses are small and slow**: about 3 KB at 1.8 KB/s (Claude),
  about 18 KB at 11 KB/s (Codex). The model is far slower than the network.
- **F26. No limit touches the model turn.** Wait for first byte and
  streaming time are the same at every CPU setting, and under every memory,
  disk and thread condition.
- **F27. Codex uploads far more.** About 64 KB per turn and 640 KB per run,
  against about 4 KB per turn and 38 KB per run for Claude Code.
- **F28. Claude Code's later requests are only about 4 KB** after a first
  request of 30 KB. Not explained (compressed request bodies is a guess).
- **F29. Connections.** Claude Code opens one model connection at start-up
  and reuses it. Codex opens a new one for every turn, at 26 ms each (about
  2.5 round trips).
- **F30. Claude Code makes 23 HTTPS connection attempts per run; 14 carry
  data.** The rest are IPv6 attempts and address probes. The VM has no IPv6
  route, so each IPv6 attempt fails at once.
- **F31. Most of Claude Code's bytes are not model traffic.** 85% of bytes
  sent and 95% of bytes received are start-up configuration and uploads at
  exit: about 34 exchanges with `api.anthropic.com`, and 131 KB sent to an
  unknown Google Cloud address near the end.
- **F32. Codex uploads about 530 KB at the end of each run** to an address
  that matches `chatgpt.com`, and fetches from `github.com` at start-up.
- **F33. Non-model traffic takes 1.6 s per Claude run and 0.3 s per Codex
  run** outside the model turns. This is what inflated the 84%.
- **F34. DNS is cheap**: about 7 lookups per Claude run, under 4 ms each.
- **F35. Upload time is not visible in system calls.** The kernel accepts
  the request into its buffer at once.
- **F36. Codex streams pause for 0.42 s in almost every turn.** Looks like
  a fixed feature of that service. Not explained.

## D. Local work

- **F37. An agent run is a storm of very short processes.** 62 (Claude) and
  100 (Codex) per run, median life 1.4 ms, 48 and 88 of them under 10 ms.
- **F38. Most processes are shell helpers.** Claude: `bash` 18, `git` 7,
  `cat` 6, `python3` 6. Codex: `lsb_release` 27, `bash` 18, `git` 16,
  `tr` 12. Codex runs each command in a login shell, whose scripts start
  most of them.
- **F39. Both agents start tools the cheap way.** Claude Code uses `vfork`
  (0.28 ms), Codex uses `clone` with spawn flags (0.30 ms). Neither copies
  the agent's memory.
- **F40. Kernel work is negligible.** System calls that do work add up to
  0.1 to 0.2 s per run. 27,000 (Claude) and 54,000 (Codex) calls by the
  agent process, about 21,000 to 25,000 by tools.
- **F41. The agent process mostly manages its own threads.** `futex` is
  the top call for both (12,300 and 22,400 per run).
- **F42. CPU demand is low on average and comes in bursts.** Mean 0.26
  cores (Claude) and 0.10 (Codex). Busiest 100 ms window: 1.8 and 2.1
  cores. Windows with any CPU use: 34% and 14%. Windows above one core: 16%
  and 2%.
- **F43. At most 14 to 16 threads want a CPU at once.**
- **F44. The machine is idle 93% (Claude) and 97% (Codex) of the run.**
- **F45. Interrupts cost 0.05% of machine time.** Not a noise source here.
- **F46. A coding task is not disk-bound.** Thousands of files are opened
  but disk-type sleep is 0.01 to 0.13 s.
- **F47. Disk-type sleep separates the disk and memory runs from the
  rest**: 6.8 s for a cold 1 GB read, 11.2 s at 100 MB/s, 22.7 s at 50
  MB/s, 29.8 s under a memory limit below the working set.
- **F48. Claude Code needs about five times the memory of Codex.** Peak of
  the group on the implement task: 331 MiB against 63 MiB.
- **F49. The paper's footprint figures are only partly backed.** "About 340
  MiB peak" matches the counter. "About 250 MB" and "about 190 MiB" have no
  counter behind them.
- **F50. No lock problem in any of the 262 runs.** Long `futex` waits are
  parked worker threads.
- **F51. Claude Code's main thread polls on a 200 ms timer.** It is asleep
  93% of the run, and 74% of its sleep ends by the timer. Its network
  thread is woken by incoming data 55% of the time. Checked on one run.
- **F52. Resource limits never appear as error returns.** In all 262 runs,
  including the out-of-memory ones, no system call returns out-of-memory,
  out-of-descriptors, out-of-space or cannot-create-process. A limit shows
  as waiting or as a kill. About 3,500 to 4,600 calls fail per run, all for
  ordinary reasons.

## E. What each limit does

- **F53. A CPU cap slows start-up and tools, not the model.** Implement
  task, Claude, unlimited to 0.25 core: start-up 1.7 to 5.1 s, tool time
  3.0 to 12.7 s, model time 13.3 to 12.4 s. That is about 13 of the 14
  extra seconds. Codex: start-up 0.3 to 1.6 s, tool time 2.8 to 21.4 s,
  model time 26.6 to 24.1 s.
- **F54. Start-up under a cap is CPU divided by the cap.** 1.23 / 0.25 =
  4.9 s predicted, 5.1 s measured.
- **F55. At 1 core only start-up waits** (0.3 to 0.4 s). This is why a
  1-core cap looks free.
- **F56. CPU demand explains the cap thresholds.** A 1-core cap only clips
  the bursts. 0.5 and 0.25 core are at or below what the busy windows need.
- **F57. For Claude Code the agent process waits more than its tools under
  a cap** (10.1 s against 8.4 s at 0.25 core). For Codex it is the tools
  (9.6 s against 3.8 s).
- **F58. Total wait from the trace now agrees with `cpu.stat` throttled
  time** to within about 5 to 25%.
- **F59. A CPU cap freezes tool start-up.** In 17 capped runs a spawn call
  froze for 57 to 93 ms, close to one throttle period. Mean spawn time goes
  from 0.28 ms to 4.9 ms at 0.25 core.
- **F60. A disk limit slows the agent's own start-up when caches are
  cold.** At 50 MB/s: 2.7 to 4.0 s (Claude), 1.6 to 3.9 s (Codex). Not in
  the workshop paper.
- **F61. A disk limit can freeze an ordinary tool.** At 50 MB/s, loading a
  program froze for 61 ms in 2 runs.
- **F62. A memory limit does not touch the agent's start-up** (2.6 s at
  every setting).
- **F63. More threads than cores slows only the tool phase.**
- **F64. Kernel signals repeat almost perfectly; model choices do not.**
  Spread across repetitions: reclaim count 0%, disk sleep 1%, start-up 5%,
  agent CPU 11%, throttled time 16%, tool time 18%, wall time 44%, turns
  56%.
- **F65. Not explained**: Codex at 0.25 core on the implement task uses 5.5
  CPU-s of tool work against 2.9 in every other cell.

## F. Naming the limit

- **F66. Four trace signals name the limit in 259 of 262 runs (98.9%).**
  In order: memory reclaim by the tree (50 or more), disk-type sleep with
  no request in flight (1 s or more), ready while a CPU is idle (0.3 s or
  more), ready while all CPUs are busy (1 s or more).

| What was done | Runs | From the trace | From counters alone |
|---|---|---|---|
| CPU quota | 61 | 59 | 61 |
| CPU competition | 20 | 20 | 0 |
| Memory limit below the footprint | 50 | 50 | 50 |
| Disk limit below disk speed | 20 | 20 | 0 |
| No limit, or too loose to bite | 111 | 110 | 111 |
| All | 262 | 259 (98.9%) | 222 (84.7%) |

- **F67. A throttled disk has its own signature.** The process sleeps on
  the disk while no request is in flight, because the request is held back
  before it reaches the device. Non-limited runs: 0.19 s at most. Limited
  runs: 8.9 s at least.
- **F68. Three of the four signals have a very wide gap.** The CPU-quota
  signal is clear from 0.5 core down and marginal at 1 core. The two missed
  runs are Codex at 1 core (0.25 and 0.26 s against a 0.3 s bar).
- **F69. Counters alone name 222 of 262 (84.7%).** Perfect for CPU quota
  and memory. Blind to a disk limit and to CPU competition.
- **F70. The agent can over-subscribe the CPUs by its own choice.** In 1 of
  6 Codex sub-agent runs the model did not start sub-agents. It wrote one
  shell line that launched all 8 workers at once. Each then waited 0.94 s,
  the same as the 8-worker stress run. Claude Code did not do this in its 6
  runs. The paper says the harness does not over-subscribe.
- **F71. Kill detection is not reliable yet.** "A process exits within 1 ms
  of its own reclaim" found all 3 real out-of-memory kills and raised 2
  false alarms in 194 runs.
- **F72. A diagnosis must look only at the agent's process tree.** The
  slow-call screen, run on the whole machine, mostly reported the
  collector's own `sync` and one background system process.
- **F73. This result is in-sample.** The thresholds were set after looking
  at these runs. Each run had one limit and a known workload.

---

## What must change in the paper

| Where | Now | Should be |
|---|---|---|
| Model share | about 84% | about 76% (Claude Code) and 90% (Codex) |
| Model share at 0.25 core, implement | 53% and 62% | 41% and 62% |
| Local compute per run | 4.7 CPU-s | 5.3 CPU-s |
| Table 1 on-CPU column | old values | values after the fix (F4) |
| Table 2, 4 workers, and stall columns | old values | values after the fix (F4) |
| Trace against `cpu.stat` | about 2%, loosening to 18% | under 1% on CPU-cap runs |
| Claude Code runtime | Node | Bun |
| Kernel and LTTng versions | one kernel, 2.15.3 | two kernels, 2.15.1 |
| Harness does not over-subscribe | stated for all | true for Claude Code in 6 runs; Codex did in 1 of 6 |
| Agent footprint | 340 MiB, 250 MB, 190 MiB | 331 MiB peak (Claude), 63 MiB (Codex) |
| Raw traces on Zenodo | all runs | Claude runs only |

New statements the paper can now make: F16, F17, F19, F20, F26, F31, F42,
F52, F53, F55, F59, F60, F66, F67, F69.

## What the data says about the new experiments

| Experiment | Supported? | What the data predicts |
|---|---|---|
| Network delay | Yes | Codex pays about 2.5 round trips on every turn, Claude Code only at start-up. With 100 ms added: about 0.25 s per Codex turn |
| Network loss | Yes, untested ground | One lost packet costs 200 ms or more against a 1 s wait for first byte |
| Network bandwidth | Weak | A run moves 0.5 to 1.5 MB. A limit must be near 1 Mbit/s or below to bite, and hits start-up, exit uploads and Codex requests first |
| Agent density | Yes | By average CPU, 4 vCPUs carry about 15 Claude or 38 Codex agents. Bursts (16% of Claude windows above one core) and memory (331 MiB each) will bind earlier |
| Process-count limit | Yes | Must be set near the peak concurrency (14 to 16) to bite. It should be the first limit that produces error returns |
| Two limits at once | Yes | Needed to test the diagnosis procedure, which so far saw one limit per run |
| Real repository tasks | Yes | Coding tasks here are not disk-bound and use 3 CPU-s of tools. Heavier tasks should bring disk and memory limits into play |
| Busy neighbour | Yes | The competition signal already separates it from a quota |
| Sub-agent runs repeated | Yes | To measure how often the model chooses shell parallelism (1 of 6 for Codex) |
| Finer CPU steps | Yes | The interesting range is between 0.5 and 1 core, where bursts start to be clipped |
| More repetitions on wall time | Only where needed | Kernel signals and per-part times are stable at 5 reps. Wall time is not |

## What the collector must add

- Keep the raw trace of every run, for both agents.
- Save the agent's own JSON report (turns, tokens, API time) to validate
  the model-turn rule.
- Save memory and I/O counters for every run, and the pressure files
  (`cpu.pressure`, `io.pressure`, `memory.pressure`).
- Record kernel, LTTng, agent and model version in every run.
- Drop caches, or not, the same way for every family, so start-up is
  comparable.
- Use one kernel for the whole campaign.
- Measure the cost of tracing itself (no tracing against the profile).

## Still open

- Why Claude Code's later requests are only about 4 KB (F28).
- What the uploads at exit are (F31, F32). The trace shows size and time,
  not content.
- Block bytes at 1.9 times `io.stat` (F14).
- The remaining 4% CPU gap on Codex memory runs (F3).
- Codex tool CPU at 0.25 core (F65).
- Why Codex file-read runs peak at 1,299 MiB when Codex alone needs 63.
- The model-turn rule is not validated against the agent's own count.
- F51 was checked on one run per agent.
