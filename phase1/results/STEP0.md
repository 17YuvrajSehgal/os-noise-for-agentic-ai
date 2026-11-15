# Step 0 results: can we trust the data?

Date: 2026-11-09. Data: 262 traces in the dataset folder (132 Claude Code,
130 Codex). Scripts: `phase1/p1_trace_health.py`, `phase1/analyze_all.py`,
`phase1/p2_gap_debug.py`.

How to rerun:

```bash
export OSNOISE_RUNS=C:/workplace/microservice-trace-dataset/agentic-runs
cd research-paper && python make_data.py && python compare_agents.py
cd ../phase1 && python analyze_all.py > results/analyze_all.jsonl   # about 1 minute
```

## P0. The old numbers reproduce

With the analyzer as released, every number matches the workshop paper:

- Table 1 (CPU cap): all wall, on-CPU and throttle medians.
- Table 2 (threads): phase, wait, and stall counts (9, 21, 2550, 5234 and
  1, 3, 2, 138).
- Table 3 (memory.high), the OOM cliff counts, Table 4 (disk).
- The cross-agent numbers in the Discussion.
- The 84% model share: per-run 80.0 to 91.5%, median 84.3%, over the ten
  unlimited runs. Local compute median 4.66 CPU-seconds.

So the paper was computed from this data with this code.

## P1. Trace health

| | Claude (132 runs) | Codex (130 runs) |
|---|---|---|
| Lost events | 131 none, 1 with losses | cannot check |
| Missing packets | none | cannot check |
| Index matches data files | all | cannot check |
| Trace covers the full run | all | all |

- **One run lost events**: `t3_implement_nocap_r5` (CPUs 1 and 3, plus a
  19 ms gap). This is the known outlier run with 3.2 million events. It is
  one of the ten runs behind the 84% figure and one of five in the
  implement/unlimited cell.
- **Time gaps**: 36 Claude runs have small gaps between packets. 33 are
  under 1 ms (30 of them under 0.1 ms) and harmless. Three are 1 ms or more: `t6B_max_768_r1`
  (28 ms), `t3_implement_nocap_r5` (19 ms), `t4_w16_r4` (1 ms).
- **Coverage**: in every run the first trace event is before the start
  anchor (by 0.03 to 6.3 s) and the last is after the end anchor (by 0.014
  to 0.08 s).
- **Codex**: the raw `trace/` folders are empty on this laptop, so the
  lost-event check could not run. The decoded text does not record lost
  events. Needs the raw traces from Zenodo or the VM.

Per-run table: `results/p1_trace_health.csv`.

### Update: Zenodo archive and a text-only check

- The Zenodo archive (checksum verified) holds raw traces for the 132
  Claude runs only. For the 130 Codex runs it holds the decoded text and
  nothing else. So the Codex raw traces exist only on the VM, if at all.
- Text-only check (`p1b_switch_chain.py`): on each CPU, the thread one
  switch brings in must be the thread the next switch takes out. Result:
  0 breaks in 7.7 million switches over all 262 runs. So no scheduler
  switch is missing in any run, Codex included, and the time accounting
  rests on complete data.
- Limit of this check: it also finds 0 breaks in `t3_implement_nocap_r5`,
  the run with known lost events. So it does not detect losses of other
  event types (system calls, network, block). For Codex those remain
  unverified.

## P2. The gap between trace CPU time and cpu.stat

**What we saw.** Trace on-CPU time was always below `cpu.stat`. Over all
262 runs the median gap was 2.3%, but 39 runs were off by more than 5% and
the worst by 35%. On the ten unlimited Claude runs the median was 7.2% and
the worst 17.6%. That worst case is the "about 18%" in the workshop paper.

**Cause.** A bug in `analyze_run.py`, not short-lived threads. The pattern
for `sched_switch` expected a non-negative `prev_prio`. Real-time kernel
threads (`migration/N`, `multipathd`) have a negative priority, so their
switches did not match. When such a thread handed the CPU to an agent
thread, the analyzer never marked the agent thread as running. Its time on
the CPU was then counted as waiting. Only 39 to 99 lines per run were
affected, but each could hide a long stretch of CPU time.

**Fix.** One character in the pattern (`-?\d+`).

**Result.**

| | before | after |
|---|---|---|
| Gap, median over 262 runs | 2.3% | 0.5% |
| Gap, worst run | 35.0% | 4.5% |
| Runs off by more than 5% | 39 | 0 |
| Unlimited Claude runs, median / worst | 7.2% / 17.6% | 0.3% / 0.6% |
| Throttled Claude runs, median / worst | 1.5% / 3.4% | 0.4% / 0.8% |

The remaining 4% cases are all Codex memory runs, off by about 0.13 s each.
Not yet explained. A likely cause is kernel reclaim work charged to the
group, but this is a guess.

Old results are kept in `results/analyze_all.before_prio_fix.jsonl`.

## What the fix changes in the paper

Wall time, throttle time, phase time, refaults, OOM counts, disk numbers and
the 84% share do not change. These do:

| Where | Old | New |
|---|---|---|
| Table 1 on-CPU, bug-fix (unlimited, 1, 0.5, 0.25 core) | 4.4, 3.7, 3.7, 3.9 | 5.0, 3.9, 3.7, 4.0 |
| Table 1 on-CPU, implement | 5.2, 5.0, 5.2, 5.3 | 5.3, 5.1, 5.2 (unchanged), 5.4 |
| Local compute per unlimited run | 4.7 CPU-s | 5.3 CPU-s |
| Table 2, W=4: on-CPU per worker / wait | 0.91 / 0.05 | 0.94 / 0.00 |
| Table 2, stalls of 1 ms or more | 9, 21, 2550, 5234 | 8, 17, 2544, 5232 |
| Table 2, stalls of 10 ms or more | 1, 3, 2, 138 | 0, 0, 0, 133 |
| Trace vs cpu.stat agreement | "about 2%, loosening to about 18%" | under 1% on all CPU-cap runs |

Two results get cleaner. At W=4 the measured wait is now 0.00, which equals
the predicted value. And stalls of 10 ms or more are now zero until the
machine is four times over-subscribed.

## Still open

- Decide what to do with `t3_implement_nocap_r5` (lost events).
- Get the Codex raw traces and check them for lost events.
- Check `llm_wait.py` and the per-problem aggregators for the same kind of
  pattern problem.
- Explain the remaining 4% gap on Codex memory runs.
