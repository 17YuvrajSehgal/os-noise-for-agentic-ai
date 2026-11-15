# The workshop paper, redone on old and new data

The workshop paper (`research-paper/paper.tex`, OXAI 2026) was withdrawn and
is only on arXiv, so its experiments and results go into the extended paper.
Every table is recomputed here on three sets: the old Claude Code runs, the
old Codex runs (Phase 1 traces) and the new Claude Code runs (Phase 2, new
VM, new collector). Same analyzer (`analyze_run.py`) on all three.

```
cd phase2 && python workshop/replicate.py      # -> workshop/tables.txt
```

Analyzed 2026-11-13. Corrections already found in Phase 1 are in
`phase1/results/FINDINGS.md` ("What must change in the paper"); they are
included below.

## Claim by claim

| # | Workshop claim | Old data, recomputed | New data | Verdict |
|---|---|---|---|---|
| 1 | The agent is ~84% LLM-bound when not limited | 72 to 81% Claude, 88 to 91% Codex (turn rule) | Opus 70 to 77%; Haiku 69 to 75%; Fable 75 to 79%; the agent's log agrees with the turn rule within 1 to 4 points | **Correct the number.** 84% counted all HTTPS traffic. Say ~75% for Claude Code, ~90% for Codex |
| 2 | Model share falls under a CPU cap (to ~53% at 0.25 core) | implement: 72 to 41% Claude, 88 to 62% Codex | Opus implement 70 to 34%, finer steps (0.75, 0.375) fall smoothly | **Confirmed, number corrected** (41%, not 53%) |
| 3 | A CPU cap does not reduce the work: on-CPU time is flat, throttle time grows (61% of the implement run at 0.25 core) | flat (5.3 to 5.4 s); throttle 61% | Opus flat (6.3 to 6.7 s), throttle 58%. **Not flat for smaller models:** Haiku 5.8 to 16.8 s, Fable 5.5 to 9.9 s at 0.25 core | **Confirmed for Opus and Codex. Refine:** a smaller model does more work under a tight cap (RQ5: the printed time) |
| 4 | Threads: wait share follows (W−C)/W | 0.49 vs 0.50, 0.73 vs 0.75 | 0.48 vs 0.50, 0.73 vs 0.75; Codex the same | **Confirmed** on three sets |
| 5 | Stalls ≥1 ms jump from tens to thousands once W>C; ≥10 ms stalls reach 138 at 4x | 17 → 2544 → 5232; ≥10 ms 133 | 31 → 2534 → 5316; ≥10 ms **421** (275 to 791) | **Confirmed for ≥1 ms.** The ≥10 ms tail is 3 times larger on the new VM. Report it as a range that depends on the machine |
| 6 | Sub-agents do not fight for cores | runnable/worker 0.00, ~18 stalls | 0.00, 18 to 20 stalls (20 runs, was 6) | **Confirmed**, now with 20 runs. Phase 1: Codex over-subscribed in 1 of 6 |
| 7 | Soft memory limit below the file working set: ~1.05 M refaults, x4.7 slower read, 8 to 9k `high` events, tiny reclaim stall, never killed | x4.7 (6.5 → 30.4 s), 1.05 M refaults, 8505 events | x4.5 (4.7 → 21.3 s), 1.05 M refaults, 8469 events, reclaim 0.2 s, 0 kills; the edge is between 1344 and 1152 MB (was 1536 to 1152) | **Confirmed**, edge narrowed |
| 8 | Hard limit on the file workload: no kill, same refault cost | no kill down to 768 MB; refaulting already at 1280 MB | no kill down to 768 MB; **no refaults at 1280 MB**, cliff between 1280 and 1024 MB | **Confirmed.** The edge moved (see machine note) |
| 9 | Anonymous 512 MB: no kill at 768 MB, all killed at 640 MB | Claude: 768 ok, 640 3/3 killed; Codex survives 640 | 704 ok, 640 to 512 all killed (25/25); edge between 704 and 640 MB | **Confirmed, edge narrowed** |
| 10 | "The OOM killer takes the worker, not the agent; the agent survives and reports" | 3/3 the worker | **2 of 25 the agent itself was killed** (576 and 512 MB); the other 23 report correctly | **Correct this claim.** Usually the worker, but not always; when the agent is the victim, there is no report (RQ5) |
| 11 | Disk cap: the read phase scales with the cap; same bytes moved; device rate tracks the cap; 200 MB/s has no effect | 200: none; 100: x1.7; 50: x3.4 | 200: x1.20; 150: x1.6; 100: x2.4; 50: x4.9; 20: x12.2. Same 1.2 GB in every cell; device rate 239 / 179 / 119 / 59 / 24 MB/s | **Confirmed.** The 200 MB/s cap now bites because the new disk is faster (287 MB/s against 205) |
| 12 | Realistic task: only the CPU cap and a below-footprint memory cap bite; disk 20 to 50 MB/s has no effect | 0.25 core 33 s; 128 MiB 149 s 1/3; 96 MiB 656 s 0/3 | 0.25 core 41 s; 192 MiB fine; 128 MiB 178 s 0/5; 96 MiB 295 s 0/5; 64 MiB 78 s 0/5; **disk 20 MB/s 26 s (+30%), 5 MB/s 44 s** | **Mostly confirmed. Refine:** a slow disk does bite, at start-up (the agent program is read from disk, RQ2) |
| 13 | Trace on-CPU agrees with `cpu.stat`: ~2%, loosening to ~18% unthrottled | 0.4% throttled, 0.9% not (after the Phase 1 fix) | 0.7% throttled, 1.2% not (365 runs, max 6%) | **Correct the number:** under 1.5% median on all sets. The 18% came from the analyzer bug fixed in Phase 1 |
| 14 | Every effect reproduces on Codex | yes (old runs) | no new Codex runs | **Keep from old data.** Say the cross-agent check is on the first data set |

## Machine note

The new VM is the same type (`n2-standard-4`, 4 vCPU, 15 GB, no swap) but
its disk reads at 287 MB/s against 205 MB/s, and its kernel is
7.0.0-1017 against 7.0.0-1011. This explains the shorter read phases
(4.7 s against 6.5 s; 4.2 s against 6.0 s) and why the 200 MB/s cap now
has an effect. It likely comes from a larger disk (the throughput of this
disk type grows with its size). I'm not sure the old disk was smaller;
its size was not recorded. The memory edge moving from above 1280 MB to
between 1280 and 1024 MB on the file workload may come from a smaller
agent footprint in the newer agent version (2.1.322 against 2.1.296); not
checked.

For the paper: every mechanism and law holds on both machines; where an
edge moved, the move has a known cause (disk speed, footprint). This is a
stronger statement than the workshop could make with one machine.

## What the extended paper adds on top

- Real tasks in containers at platform settings (RQ3), density (RQ4),
  behaviour (RQ5), network, process count, neighbour and two-limit
  experiments (RQ2), the time split from the agent's own log (RQ1).

## Open

- Codex: only old data. New Codex runs would let claims 1 to 14 be checked
  on both agents again (needs the model choice and sign-in).
- Check the agent's memory footprint across versions (claim 8 edge).
- The ≥10 ms stall tail (claim 5): compare the scheduler settings of the
  two kernels.
