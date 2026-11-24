# RQ5. Does the agent change what it does because of the system?

Analyzed 2026-11-13. Three parts: the printed-time effect (`feedback`, 120
runs), reactions to system errors (`memory_cliff` 45, `pids` 35,
`pids_mid` 35), and test choice on slow real tasks (`real` no limit
against `real_quarter`, 60 runs).

```
cd phase2
OSNOISE_RUNS=<runs root> python feedback_cells.py   # cells + rq5/feedback_tests.txt
OSNOISE_RUNS=<runs root> python rq5/errors.py       # -> rq5/errors.csv, rq5/errors.txt
```

## 1. The printed time makes a small model work more

Tasks: t3 prints its own run time (`stress X.Xs`); t9 is the same task with
that line removed. Medians of 5 runs; p = exact one-sided rank-sum test
(all 252 splits of the 10 runs).

| Haiku, comparison | Tool calls after the tests pass | Turns | Output tokens | Wall |
|---|---|---|---|---|
| 25% CPU: time printed vs not printed | 8 vs 0 (p=0.056) | 11 vs 7 (p=0.012) | 3883 vs 2139 (p=0.028) | 70 vs 31 s (p=0.028) |
| 50% CPU: time printed vs not printed | 2 vs 0 (p=0.14) | 7 vs 8 (p=0.77) | 2833 vs 2745 | 40 vs 22 s (p=0.16) |
| Time printed: 25% CPU vs no limit | 8 vs 0 (p=0.028) | 11 vs 5 (p=0.028) | 3883 vs 1974 (p=0.028) | 70 vs 14 s (p=0.008) |
| Not printed: 25% CPU vs no limit | 0 vs 0 | 7 vs 7 (p=0.33) | 2139 vs 2308 | 31 vs 16 s (p=0.004) |

What this means:

- **Haiku reacts to a number, not to the limit.** With a quarter of a CPU
  and the run time printed, it keeps "optimizing" after the tests already
  pass (8 extra tool calls, 11 turns against 7). Remove the printed time,
  same task and same limit: it stops when the tests pass.
- **This extra work more than doubles the run** (70 s against 31 s at the
  same limit). So a slow machine costs Haiku twice: once directly, and
  again through the work the slowness provokes.
- **The effect needs a large printed number.** At 50% CPU it is not
  significant. On the second task (t10, the printed time is smaller) Haiku
  mentions speed in 5 of 5 runs at 25% but does not act (0 calls after the
  pass, turns 9 vs 7, p=0.15).
- **Opus does not do this.** 0 extra calls in every cell; 4 turns at 0.25 and 0.5 core, 5 with no
  limit. It
  writes slightly more at 25% with the time printed (1412 vs 1244 tokens,
  p=0.028, it mentions the time in 3 of 5 runs) but does no extra work.
- RQ2's "smaller models work more under a CPU limit" (Haiku 10 turns vs 4
  in `cpu_model2`) is this same effect: that task is t3, which prints its
  time.

## 2. Reactions to system errors

| Limit | Level | Runs | Solved | Agent saw the error | Agent itself died | Named the cause | Tool calls after the error |
|---|---|---|---|---|---|---|---|
| Memory (tool needs 512 MB) | 704M and up | 20 | 20 | 0 | 0 | | |
| | 640M to 512M | 25 | 0 | 23 | 2 | 23 of 23 | 0 to 2 |
| Process count | 20 and up | 50 | 50 | 0 | 0 | | |
| | 17 to 19 | 15 | 13 | 3 | 3 | 2 of 2 that finished | 2 |
| | 16 and 12 | 10 | 1 | 0 | 9 | | |

What this means:

- **Memory kill: the agent explains it correctly and stops.** In all 23
  runs where the tool was killed, the final message says the command was
  killed (exit 137) and why the result file is missing. It does not retry
  in a loop or try to work around it (0 to 2 calls after). It cannot solve
  the task, which needs the memory, and it says so.
- **Sometimes the kernel kills the agent instead of the tool** (2 of 25: at
  576M and 512M). The memory kill picks a process in the container, and
  the agent's own process is a candidate. The run then ends with no
  message at all. A user sees a dead agent, not an explanation.
- **Process limit: the agent mostly never sees an error.** Between 17 and
  20 processes, process starts fail 1 to 6 times per run (trace, N10), but
  the shell retries and succeeds. Only 3 of 15 runs at 17 to 19 show the
  message `fork: retry: Resource temporarily unavailable`; the 2 that
  finished mention it in their final message ("the machine was briefly
  short on processes or memory") and say it did not affect the result,
  which is correct.
- **When the process limit bites, the agent itself crashes** (exit 134,
  "dumped core"): 3 of 15 runs at 17 to 19, 9 of 10 at 16 and 12. The
  agent program needs threads of its own; when it cannot start one, it
  aborts. Again no message for the user.
- **Pattern:** when the error reaches the agent as text, it reports it
  well. The worst outcomes are when the system hits the agent's own
  process: then there is no reaction at all, only a dead run.

## 3. Does the agent run lighter tests when the machine is slow?

Real tasks, no limit against 0.25 CPU (5 runs each):

- **No.** Same number of test runs per task (medians 1 to 3, unchanged),
  and in 0 of 60 runs does the agent mention slowness, limits or time-outs.
  On real tasks with no printed time, the slowdown does not change what
  Opus does.
- **But tool CPU drops on every task** (to 0.77 of the no-limit median;
  Django 14.4 to 5.8 s, p=0.028 or lower on 5 of 6 tasks). Since the
  commands are the same, this is a system effect, not a choice. It is
  the other side of N4 (crowded CPUs make the same work cost more CPU):
  with no limit, test processes spread over 4 vCPUs that share 2 cores
  and caches; under the quota they run mostly one at a time. I'm not
  sure this is the cause; this VM has no hardware counters to check.

## Limits of this analysis

- Part 1: 5 runs per cell, Haiku only reacts, two small tasks. 10 tests
  were run without a correction for multiple tests; the main results
  (turns p=0.012, output and wall p=0.028) would not survive a strict
  Bonferroni correction (0.005). Report as a clear pattern with an
  explained cause (the removed line), not as a proven general law.
- Part 2: the error counts come from the agent's own log; a tool that
  hides an error (the shell retrying fork) is invisible to the agent and
  to this check, visible only in the trace.
- Part 3: Opus only.

## Open

- More runs for part 1 (Haiku, t3/t9 at 25%, 10 more each) would make the
  main test hold after correction. About 40 minutes on the VM.
- Which process the memory kill picks, and why: the trace has the kill
  event with the victim.

## More runs for the feedback test (feedback_extra, analyzed 2026-11-15)

10 more Haiku runs each of t3 (test prints its time) and t9 (silent) at 0.25
CPU, so these two cells have 15 runs. `python feedback_cells.py` (needs
OSNOISE_RUNS). Test: one-sided rank-sum, exact when there are at most 1e5
splits, else 200000 random splits (seed 7); Holm correction over the 20
tests of one model.

| Haiku at 0.25 CPU | printed (t3) | silent (t9) | p (Holm) |
|---|---|---|---|
| runs that talk about speed | 15/15 | 1/15 | |
| tool calls after the first pass | 5 | 0 | 0.005 |
| turns | 11 | 8 | 0.040 |
| output tokens | 4238 | 2503 | 0.002 |
| wall | 73 s | 35 s | <0.001 |

- **The earlier result now holds after correction for many tests.** When the
  slow time is printed, Haiku keeps working on speed after the task is
  already done; when it is not printed, it stops.
- With no limit, the printed time does not trigger this (t3: 0 extra tool
  calls, 1 of 5 runs talk about speed). So it is the slow number, not the
  print itself.
- Opus: no effect in any test (all Holm p >= 0.08).
- New from real_long (RQ3): OOM kills inside a test run are silent to the
  agent; output stops without an error. See rq3/RESULTS.md.
