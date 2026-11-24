# Review 2 (fable5.2-review1.md): status, 2026-11-19

Rule: fix with the data we have. Items that need new runs are listed at the end.

| # | Review point | What was done | Evidence |
|---|---|---|---|
| 1 | Eq. 1 is Amdahl's law | Cited (amdahl1967); presented as an application; contribution reworded | main.tex Intro, RQ2 |
| 2 | "Hidden" too strong | Reframed as "diluted": large costs visible but understated, moderate costs below the noise. Title still says "Hidden" (decide with supervisor) | abstract, Intro, RQ2, Conclusion |
| 3 | Replay barely beats the guess | Paired tests: closer in 50 of 80, sign test p=0.017, mean gain 6.2 points p<0.001. Without t3: 7.0% vs 10.0% (n=66, p=0.003). Held-out mix: 44 real, 23 t3, 11 t2, 11 t8 | rev/a1_single.py, a1_single.txt |
| 3b | Depends on the baseline run | CORRECTION: the 6.9% uses the median of all 5-15 unlimited runs, not one run. One run: wall time typical error 9.7% (spread 34%); slowdown typical 7.1%, worst run 10.6%. All "one run" claims reworded | a1_single.txt |
| 4 | Kernel traces underused | New subsection "What the kernel trace shows" + fig_states: on-CPU flat under quota (6.3 -> 6.7 s), quota wait 0.1 -> 26.4 s; busy-core wait 45.9 s with 16 workers; disk wait under io/memory limits. Quota-vs-busy rule validated against cpu.stat throttled time (ratio 1.10, n=275) | rq1/runs.csv, fig_states |
| 5 | RQ2 is known cgroup behaviour | t4-t8 stated as calibration; agent-specific results named | RQ2 opening |
| 6 | Narrow workload | Threats rewritten (one closed agent, two versions, short runs, ten Python issues) | Threats, External |
| 7 | Density weak for a headline | Moved last in findings, marked exploratory; trace evidence added (neighbour: CPU time 6.2 -> 10.4 s for the same work) | Intro, RQ4 |
| 8 | RQ5 on one synthetic task | Stated in Threats; tee choice justified (pipelines hide exit status); API cost added (Haiku +44%, 8,600 vs 4,100 output tokens; Fable +20%) | rev/feedback_cost.py |
| s1 | "We do not know why" baseline shift | Trace: same bytes and reads, but disk wait 3.5-11.8 s (set 1) vs 1.2-3.1 s (set 2); start-up 3.9-12.4 vs 2.0-4.0 s. Agent version also differs. Split between the two causes not known | RQ3 |
| s1b | (found) wrong agent version in paper | Set 1 + 68 runs of set 2: 2.1.322; 470 runs of set 2, M1, M2: 2.1.327 | Study Design |
| s2 | "No clear cost at 1 CPU" | Reworded: no cost we can detect; interval reaches 1.38 | RQ3 |
| s3 | Long-task interval too wide | Said so in RQ3; not in abstract | RQ3 |
| s4 | 2-vCPU abort dip | Caption states it (3 of 5 at limit 10) and that we cannot explain it | fig_limits caption |
| s5 | "8 + 2 per vCPU" from three points | Called a summary, not a law | Section 7 |
| s6 | Common view has no citation | Cited yuan2026; gap sentence added | Intro |
| s8 | No token cost for RQ5 | Added (see 8) | RQ5 |

## Needs new runs or a decision
- Second agent (OpenHands or SWE-agent) or Codex on a core set.
- Long sessions (10+ minutes).
- Haiku with a printed time on real tasks.
- Density with staggered arrivals or mixed tasks, more than 3 runs per level.
- Title: "Hidden" vs "Diluted".
- Data link (anonymous artifact).

## Added 2026-11-19 (evening)
- Means next to medians: `machines.py` now also computes every slowdown and breaking point with means (37 of 42 breaking points the same; local slowdown differs by 1.1% median, 4.5% p90). `robust.py`: replay error mean 11.6%, p90 28% (table now has both); real tasks at 0.25 CPU 1.67 with means vs 1.74; at 1 CPU 1.11 vs 1.02 (one 123 s Requests run).
- OOM fixes: collector option `tool_guard` (oom_adj | cgroup), campaign `r_oomfix` (40 runs). Smoke test passed for both. Queued on M0 behind the usage gate (7-day usage 0.89, resets 2026-11-20 03:00 UTC).
- OOM fixes DONE 2026-11-20 00:40 UTC: r_oomfix, 40 runs on M0 set 2, all verified (verify_campaign: 0 problems), downloaded to osn-export-rev/m0/d, checksums and manifest match, unpacked to runs-rev/r_oomfix. M0 stopped. Agent killed 0/20 with oom_adj and 0/20 with child cgroup vs 9/20 with no fix (Fisher one-sided p=0.0006 each). All 40 solved; report names kill 39/40. oom_adj runs slower (27-29 s vs 20-24 s); cgroup not (19-21 s). Totals now 2,154 runs / 2,114 traced / set 2 = 578. rev/oomfix.py -> oomfix.txt.
