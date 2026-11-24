# Review 3 (review-3.md): status, 2026-11-20

| Point | Done | Evidence |
|---|---|---|
| 1 Strawman headline | Abstract and intro reframed: no "widely assumed", no "platforms act on this view"; three new results named | main.tex |
| 2 Replay error diluted by f | Local-time error added: replay 7.1% median (p90 40%) | rev/a1_local.py, a1_local.txt |
| 3 Weak baselines, non-independence, one-sided p | Whole-run max-rule baseline added (11.8% local; replay closer in 29/35 groups, p<0.001). Group-level two-sided tests. vs s=1/q: CPU <1 core simple estimate as good (7.6 vs 11.6%), q>=1 replay better (21/28, p=0.01), disk replay 4.7% vs 59% (14/14). Overall wall vs 1/q not significant per group (19/35, p=0.74). Claims rewritten everywhere | a1_local.txt |
| 4 Generality, model IDs | Model IDs added (claude-opus-5-5, claude-haiku-5-5, claude-fable-5-1). Second agent: not done | |
| 5 pids rule | Thread names from trace: Bun Pool = vCPUs, HeapHelper = vCPUs-1, +~8 fixed. Sampled kept-alive 12-13/16-17/24-26 vs pids.peak 15/21/33; edge follows kept-alive. "exactly" -> "almost always" with counts (3/55 set 1, 1/50 set 2 above edge; M1 limit 10: 3/5). Docker/K8s no default limit noted | rev/pids_threads.py |
| 6 OOM fix overlap, RSS | Kernel OOM report from trace: largest task killed first (test ~615 MB); agent (~150 MB) killed only after test, as largest left. Known fixes and AgentCgroup credited. xarray 810 MB under 512 MB as real case | rev/oom_victims.py |
| 7 Density / SMT / throughput / vendor | Throughput defined as batch; staggered + more groups running on M0 (r_density_stagger, r_density_more). SMT and vendor stated in Threats; threads-per-core test NOT done | |
| Minor: page cache | Sentence added | |
| Errors: neighbour vs Amdahl | Explained: model 2-3 s faster in those runs | rq2/curves.csv |
| Errors: 0.5-core values | Sets named; pairs compared with sum AND product | |
| Errors: f range | 0.20-0.30 small, 0.17-0.61 real; "10 to 30%" | |
| Errors: "starts to grow below 0.75" | Fixed | |
| Errors: Fig 2 means vs text | Text now uses the same means | |
| Errors: 1,736 / 365 subsets | Hidden work rerun on all 1,836 traced single-agent runs; trace vs cpu.stat on all 1,912 (0.8% median, p90 2.0%) | |
| Errors: 2,154 counts groups | Stated in abstract and intro | |
| Errors: Aegis wording | "reduce failures of state awareness" (3 places) | |
| Refs: yuan2026 title | KEPT "Characterization": PDF and IISWC program use it; arXiv metadata says "Characteristics" | |
| Refs: agentcgroup 20-35% | KEPT: v3 says exactly "20-35% of active time"; cite v3 | |
| Refs: gao2026 | DOI added | |
| Refs: shetty wording | "at or just above" | |
| Refs: lindenbauer | pilot study noted; workshop name "Deep Learning for Code in the Agentic Era" | |
| Refs: access dates | 2026-11-19 | |
| Refs: missing | Added Sizeless (Middleware 2021, 248-259; reviewer's venue right), Mind the Gap (SoCC 2021, 243-257), Duet Benchmarking (ICPE 2020, 100-107) | Crossref |

## Open (need a decision or new runs)
- BibTeX + ACM-Reference-Format instead of hand-written list with "et al."
- threads-per-core=1 density test (SMT); cpu.max.burst / cpu.weight test; n2-standard-8 to separate vendor from size
- Second open agent
- Shorten RQ5 and RQ2 calibration (cutting)

## Added 2026-11-20 (new runs, all on M0 set 2)
- r_density_more (2 more groups per level): M0 set 2 now 5 groups per level; 14.5/min at 16, 15.4 at 32. a11_density.py updated; fig_density regenerated.
- r_density_stagger (agents start at random within 60 s, 5 groups per level, 300 agents, all solved): below the machine's rate agents run as if alone (local 4.6-6.4 s); at 32/min arrivals 14.5 alive avg, local 42 s (= simultaneous 16), CPU/agent 11.6 s (1.9x), throughput 16.9/min (+10% vs together). Limit and CPU doubling do not depend on simultaneous start. a12_stagger.py -> a12.txt.
- r_long (sympy-13878, >4 h rating, 5 runs x 3 sizes, all solved): f=0.73; 1 CPU/512 MB x2.26 wall (x2.45 local) caused by the memory limit (working set 510-660 MB, hundreds of memory.max hits, CPU 234->568 s, turns 29->43) not the quota (replay/Eq.1 predict 1.0); 0.25 CPU x2.92 (x3.37 local), Eq.1 +9%, replay +14%; agent tool time-out (2 min) fires 1-5x per run under limits, agent runs smaller tests, CPU work falls to 199 s. a13_long.py -> a13.txt.
- Paper: abstract (sessions up to 24 min), intro bullet, Study Design (fifth long task), dataset table (set 2 = 623; totals 2,199 / 2,159 / 2,067), RQ2 (miss at 1 CPU on the long task), RQ3 (long-session paragraph, answer), RQ4 (5 groups; random-arrival paragraph; 1,067 agents), RQ5 (tool time-outs), Statistics (density now tested), Threats (second and third points rewritten).
