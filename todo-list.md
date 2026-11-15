# To-do list

## Where we are (2026-11-10)

- **Phase 1 is finished.** All 27 analysis points (P0 to P26) on the
  existing 262 traces are done. No new runs were made.
- **Every finding is in `phase1/results/FINDINGS.md`** (F1 to F73), with
  detail in `STEP0.md` to `STEP4.md` next to it.
- **Nothing is committed.** Changed: `analyze_run.py` (bug fix),
  `make_data.py`, `compare_agents.py`, `llm_wait.py`. New: `phase1/`,
  `collector/`, this file, and the two related papers (PDF). `zenodo-traces/` (2.4 GB) must stay out of git.
- **Phase 2 collector is written** (`collector/`), tested without the VM.
- **Next:** create the VM, run the smoke and overhead campaigns, then the
  experiments (Phase 3).
- **To confirm:** was the ICPE abstract registered on 2026-11-09?

## Corrections the paper needs

Found in Phase 1. The full table is at the end of `FINDINGS.md`.

- [ ] **Model share.** "About 84%" becomes about 76% (Claude Code) and 90%
  (Codex). At 0.25 core, implement: 53% becomes 41% for Claude. (F15)
- [ ] **Numbers changed by the analyzer fix.** Local compute 4.7 to 5.3
  CPU-s. Table 1 on-CPU column. Table 2 at 4 workers (wait 0.05 to 0.00)
  and both stall columns (8, 17, 2544, 5232 and 0, 0, 0, 133). (F4)
- [ ] **Trace against `cpu.stat`.** "About 2%, loosening to about 18%"
  becomes under 1% on CPU-cap runs. (F3)
- [ ] **Claude Code runtime.** Node becomes Bun. (F11)
- [ ] **Kernel and LTTng versions.** Two kernels were used (1011 for 42
  runs, 1014 for 280). LTTng was 2.15.1, not 2.15.3. Remove "the limit is
  the only thing that varies" or qualify it. (F10)
- [ ] **Harness does not over-subscribe.** True for Claude Code in 6 runs.
  Codex did in 1 of 6: the model launched all 8 workers with one shell
  line. (F70)
- [ ] **Agent footprint.** Use 331 MiB peak (Claude Code) and 63 MiB
  (Codex). Drop "about 250 MB" and "about 190 MiB", which have no counter
  behind them. (F48, F49)
- [ ] **Say what was lost.** One of the ten unlimited Claude runs lost
  events (`t3_implement_nocap_r5`). Decide: drop it or keep it and say so.
  Codex raw traces no longer exist, so lost events cannot be checked for
  Codex. (F6, F7, F8)
- [ ] **New results to add.** Wall-clock split (F16), turns explain
  variation (F17), start-up cost (F20, F54), a cap slows start-up and
  tools but not the model (F53), disk limit slows start-up (F60), limits
  never show as error returns (F52), naming the limit from the trace
  (F66, F67, F69).

## Corrections the repository needs

- [ ] **`DATA.md` and `README.md` overstate the archive.** Raw traces on
  Zenodo cover the Claude runs only. (F12)
- [ ] **Stale analysis README.**
  `latency/1_svc_cpu_cap/agentic-os-noise/analysis/README.md` still says
  model wait is not separated and throttle is under-counted.
- [ ] **`latency/2_threads_vs_cores/RESULTS.md` stall counts** are from an
  older analyzer. Replace with the corrected ones.
- [ ] **Replace `llm_wait.py`** by the model-turn rule (`phase1/step1.py`).
- [ ] **Claude end-to-end manifest is incomplete.**
  `runs_e2e_cl/manifest.csv` lists 21 of 30 runs. (F13)
- [ ] **Add `zenodo-traces/` to `.gitignore`.**
- [ ] **Decide where `phase1/` lives in the released artifact**, and remove
  machine-specific paths from its documents first.
- [ ] **Check the per-problem aggregators** (`aggregate_t4.py`,
  `aggregate_mem.py`, `aggregate_io.py`) for the same pattern bug.

## Open questions from Phase 1

- [ ] Why Claude Code's later requests are only about 4 KB. (F28)
- [ ] Block bytes in the trace are 1.9 times `io.stat`. (F14)
- [ ] The remaining 4% CPU gap on Codex memory runs. (F3)
- [ ] Codex tool CPU at 0.25 core: 5.5 s against 2.9 s. (F65)
- [ ] Codex file-read runs peak at 1,299 MiB when Codex alone needs 63.
- [ ] Rerun the slow-call screen on the agent's process tree only, keeping
  every finding. (F72)
- [ ] Summarize the wall-clock split for the non-coding runs.

---

# Extension plan (ICPE 2027, Research Track, EERCS paper)

Written 2026-11-09. Target: 10 pages + references, ACM two-column format,
double-anonymous. Abstract due 2026-11-09, paper due 2026-11-16 (AoE).

## What the extended paper should answer

The workshop version showed four mechanisms on fixed workloads. The extended
version should answer five questions:

- **RQ1. Anatomy.** With no limit, where does an agent's time go at the
  kernel level (model wait, tool processes, system calls, network, idle)?
- **RQ2. Mechanisms.** How does each container limit change that picture?
  (The four existing problems, plus network and process-count limits.)
- **RQ3. Realistic use.** Which limits hurt real coding tasks at the limits
  that real platforms set?
- **RQ4. Density.** How many agents can share one machine before they slow
  each other down?
- **RQ5. Diagnosis.** Given only a kernel trace of a slow agent run, can a
  fixed procedure name the limit that caused it? And how much of that can
  cheap counters do without a trace?

## What the existing traces already contain

Checked on one trace (`t3_implement_cap25_r1`). The current profile is
already wide, so a lot of new analysis needs no new runs:

- Present: every system call (entry and exit), scheduler events,
  `power_cpu_idle`, hard and soft interrupts, block layer, writeback,
  network device and socket-buffer events.
- Missing: page faults, timers, TCP-level events, CPU frequency events
  (a cloud VM does not expose them), and any energy reading.

## Phase 0. Clean up (before any new claim)

- [ ] Fix the items under "Corrections" at the top of this file.
- [x] Make the paper scripts read traces from the dataset folder
  (`OSNOISE_RUNS`).
- [ ] Move the paper to the ACM template and remove names, repo link and
  DOI. Prepare an anonymized copy of the artifact.

## Analysis method to reuse (do not re-invent)

We already have a tested set of trace-analysis scripts and a fixed way of
using them, from our earlier root-cause work on kernel traces. The paper
describes the method in its own words and cites the public sources it is
built on (wait analysis of Giraldeau and Dagenais, off-CPU analysis, the
LTTng analyses). It does not name or cite the earlier internal material.

Tested on `t3_implement_cap25_r1`: the scripts run on our decoded traces
with no change (unzip first).

### The procedure, in order

1. **Health gate.** Lost events, time gaps, and which event types the trace
   holds. A missing event type cannot be used as evidence.
2. **Slice to active windows.** The agent is idle most of the run, so
   whole-run averages hide everything. Measure inside the windows where the
   agent or its tools are working.
3. **Time budget per process and thread.** Four states: running, ready but
   waiting for a CPU, sleeping (S), disk-type sleep (D). Count single waits
   of 1, 10 and 50 ms or more, and the longest.
4. **Compare with the run's own baseline.** The unlimited run of the same
   task and agent. Judge the jump, not the absolute value.
5. **First split by state.** Waiting for CPU points to a CPU cause. D sleep
   points to memory reclaim or disk. S sleep points to network, a lock, or
   the model.
6. **One decisive check per mechanism** (table below).
7. **Rule out look-alikes.** If one check does not fit, the result is
   "unconfirmed".
8. **Report.** Window, victim, cause, at least two independent pieces of
   evidence, each marked Measured or Inferred. Write "no X found", never
   "no fault".

### Decisive check per mechanism

| Mechanism | Decisive check | Script | Look-alike it must rule out |
|---|---|---|---|
| CPU cap | On-CPU time per 100 ms period sits at a ceiling below the period, and the CPUs are idle while the victim waits | `cpu_ceiling.py`, `cpu_hogs.py`, `rhythm.py` | Competition: same ceiling but CPUs busy |
| Too many threads / shared machine | Victim waits while other threads hold the CPUs; waits are short and many | `cpu_hogs.py`, `runq_wait.py`, `thread_top.py` | CPU cap: CPUs idle |
| Memory limit (soft) | Memory-cgroup reclaim events in one group, far above baseline, plus re-reads from disk | `mem_pressure.py` | Cold cache: reads with zero reclaim |
| Memory limit (hard) | A process exits within about 1 ms of its own reclaim | `mem_pressure.py` | Normal exit: 8 ms or more after reclaim |
| Disk limit | D sleep rises, block requests slow, no reclaim | `sched_budget.py` + block events (new script needed) | Memory limit: reclaim present |
| Slow network or slow model | Gap between a request write and the next answer read on the same socket grows against baseline | `sock_lag.py`, `net_loss.py` | Loss shows as retransmissions; pure delay does not |
| Process or descriptor limit | Error returns on `clone`/`fork` (EAGAIN) or on `open`/`socket` (EMFILE) from one process | `fd_pressure.py`, `connect_census.py` | Restart loop with no error returns |
| Lock wait | Long `futex` waits ended by a wake from another thread | `futex_wait.py`, `wait_chain.py` | Timed sleeps and runtime parking |
| Slow system call | One call that burns CPU or sits in D for 10 ms or more and freezes sibling threads | `syscall_stall.py` | Calls that only sleep inside |
| Interrupt load on one core | Network receive work concentrated on one CPU | `irq_balance.py` | Small share of total load |

### Known limits of the scripts on our data

- They read plain text, so each trace must be unzipped first (or the
  scripts get a small change to read gzip).
- The index and slicing scripts need the raw trace folder and `babeltrace2`.
  The raw `trace/` folders are in the dataset, but `babeltrace2` is not on
  this laptop. For text traces we slice by timestamp ourselves.
- Thresholds were set on other systems (steady services, bare-metal boxes).
  We must set them again from our own unlimited runs.
- An older copy of the time-budget script counted a preempted thread
  wrongly on our kernel (state 256). Check each script handles it before
  trusting it.
- The network loss check needs packet headers in the trace. Checked: our
  traces hold full IP and TCP headers.
- The memory kill rule (exit within 1 ms of reclaim) comes from 8 runs on
  one machine.

### Overlap to decide with the supervisor

The diagnosis procedure is also the core of the other paper in progress.
If this paper presents it as a contribution, the two papers overlap. Safer
split: here the procedure is the measuring instrument and the contribution
is what it shows about agents. Confirm before writing RQ5 up.

## Phase 1. New analysis on existing traces (no new runs)

Data: the 262 traces in `C:\workplace\microservice-trace-dataset\agentic-runs`.
Output: one JSON per run, plus one summary table per point. Every point is
done for both agents (Claude Code and Codex) and reports the median and the
spread across reps, not only the median.

Each point lists the question, the trace events it uses, and what it decides
for the new runs.

### Step 0. Trust the data first

Done 2026-11-09. Full write-up: `phase1/results/STEP0.md`.

- [x] **P0. Reproduce the old numbers.** Done. With the released analyzer,
  every number in the four problem tables, the cross-agent table and the
  84% figure comes out the same as in the workshop paper.
- [x] **P1. Trace health.** Done for the 132 Claude runs: 131 clean, 1 with
  lost events (`t3_implement_nocap_r5`). Every trace covers its full run.
  Not possible for the 130 Codex runs: their raw `trace/` folders are empty
  on this laptop.
- [x] **P2. Close the 18% gap.** Done. Cause: a pattern in `analyze_run.py`
  did not match scheduler switches from real-time threads (negative
  priority). Fixed. Trace on-CPU now agrees with `cpu.stat` to a median of
  0.5%, worst case 4.5%, over all 262 runs.

Follow-ups from Step 0:

- [ ] **Update the numbers that the fix changes.** Table 1 on-CPU column
  (for example bug-fix unlimited 4.4 to 5.0 s), the "4.7 CPU-seconds"
  figure (now 5.3), Table 2 at W=4 (wait 0.05 to 0.00, on-CPU 0.91 to 0.94)
  and the stall columns (1 ms: 8, 17, 2544, 5232; 10 ms: 0, 0, 0, 133), and
  the sentence on trace vs `cpu.stat` agreement.
- [ ] **Decide on `t3_implement_nocap_r5`.** It lost events on 2 of 4 CPUs
  and is one of the ten runs behind the 84% figure. Drop it, or keep it
  and say so.
- [ ] **Codex raw traces are not on Zenodo.** The archive in
  `zenodo-traces/` (checksum verified, not unpacked) has raw traces for
  the 132 Claude runs only. Check if the VM still has the Codex ones. A
  text-only check shows no scheduler switch is missing in any of the 262
  runs, but losses of other event types on Codex cannot be ruled out.
- [ ] **`DATA.md` and `README.md` overstate the archive.** They say the
  raw trace of every run is on Zenodo. For Codex only the decoded text is.
- [ ] **Keep `zenodo-traces/` out of git.** It is 2.4 GB and not covered by
  `.gitignore`.
- [ ] **Check the other scripts for the same pattern.** `llm_wait.py` and
  the per-problem aggregators parse the trace text too.

### Step 1. The shape of a run

Done 2026-11-10. Full write-up: `phase1/results/STEP1.md`.

- [x] **P3. Turns.** Done. Run-to-run variation is mostly the number of
  turns (correlation with wall time 0.99 for Claude bug-fix). Claude Code
  uses 3 to 6 turns and batches tool calls; Codex uses 6 to 15 turns, one
  tool call each, and re-uploads about 60 KB per turn.
- [x] **P4. Start-up cost.** Done. Claude Code burns 1.23 CPU-seconds
  before its first model request (1.65 s wall). At 0.25 core this becomes
  5.1 s. Codex: 0.28 CPU-seconds, 0.31 s, 1.6 s at 0.25 core.
- [x] **P5. The non-model time.** Done. Claude: start-up 9%, model 76%,
  tools 13%. Codex: start-up 1%, model 90%, tools 8%. A CPU cap leaves the
  model time flat; the slowdown is all in start-up and tools.

Follow-ups from Step 1:

- [ ] **Correct the 84% figure.** It counted every HTTPS exchange,
  including start-up configuration calls and telemetry. Model turns only:
  about 76% for Claude Code, about 90% for Codex. The model share at 0.25
  core changes too (Claude 53% to 41%). `llm_wait.py` should be replaced by
  the model-turn rule.
- [ ] **Validate the model-turn rule** on new runs that save the agent's
  own turn count and API time.
- [ ] **Explain Codex tool CPU at 0.25 core** (5.5 s against 2.9 s in the
  other cells, implement task).
- [ ] **Summarize the split for the non-coding runs** (threads, memory,
  disk). Computed, not yet looked at.

### Step 2. The model wait (the 84%)

Done 2026-11-10. Full write-up: `phase1/results/STEP2.md`.

- [x] **P6. Request anatomy.** Done. A turn is about 1 s of waiting for the
  first byte plus 1 to 2 s of streaming. Both are the same at every CPU
  setting. Responses arrive at 2 KB/s (Claude) and 11 KB/s (Codex).
- [x] **P7. Connections.** Done. Claude Code reuses one model connection
  for the whole run. Codex opens a new one per turn (26 ms each, about 2.5
  round trips). Round-trip time to both model endpoints is 10.8 ms.
- [x] **P8. Other network traffic.** Done. 85% of the bytes Claude Code
  sends and 95% of those it receives are not model traffic (start-up
  configuration, uploads at exit). Codex uploads about 530 KB at exit.

Follow-ups from Step 2:

- [ ] **Find out why Claude's later requests are only about 4 KB.**
- [ ] **Design the network grid from these numbers**: delay 0, 50, 100,
  200 ms; loss 0, 1, 5%; bandwidth unlimited, 1 Mbit/s, 256 kbit/s.
  Predictions to test are in `STEP2.md`.

### Step 3. Local work

Done 2026-11-10. Full write-up: `phase1/results/STEP3.md`.

- [x] **P9. Tool-process anatomy.** Done. 62 (Claude) and 100 (Codex)
  processes per run, median life 1.4 ms, mostly shell helpers. Both agents
  start tools with a cheap spawn (no memory copy).
- [x] **P10. System-call profile.** Done. Kernel work is about 0.1 to 0.2 s
  per run. The agent process mostly does thread management (`futex`).
- [x] **P11. CPU demand over time.** Done. Mean 0.26 cores (Claude) and
  0.10 (Codex), bursts of 1 to 2 cores. Explains why 1 core is enough and
  0.5 is not.
- [x] **P12. Machine idle time.** Done. 93% and 97% idle.
- [x] **P13. Disk and file activity.** Done. Coding runs are not
  disk-bound (0.01 to 0.13 s of disk-type sleep). Disk-type sleep cleanly
  marks the disk and memory runs (7 to 30 s).
- [x] **P14. Memory footprint.** Done. Peak 331 MiB (Claude) against
  62 MiB (Codex) on the same task.
- [x] **P15. Interrupt cost.** Done. 0.05% of machine time. Not a factor.
- [x] **P16. Lock waits.** Done. No lock problem in any of the 262 runs.
- [x] **P17. Slow system calls and process creation.** Done. Under a CPU
  cap, tool start-up freezes for up to one throttle period (17 runs).
  Under the tightest disk limit, loading a program freezes (2 runs).
- [x] **P18. Who wakes the agent.** Done on one run per agent. Agrees with
  the model-wait picture but is not an independent measurement.
- [x] **P19. Error returns.** Done. Resource limits never appear as error
  returns in any of the 262 runs. They appear as waiting or as a kill.
- [x] **P20. Retransmissions.** Done early, with Step 2. The traces hold
  full TCP headers. Zero retransmissions in about 35,000 data segments
  over all 262 runs, so the network was clean in every existing run.


Follow-ups from Step 3:

- [ ] **Fix the footprint numbers in the paper.** "About 340 MiB peak" is
  backed by the counter. "About 250 MB" and "about 190 MiB" are not.
- [ ] **Explain block bytes in the trace being 1.9 times `io.stat`.**
- [ ] **Rerun the slow-call screen restricted to the agent's process
  tree**, keeping every finding, not only the first per run.
- [ ] **Save memory counters for every run** in the collector (the Claude
  Problem 1 runs have none).

### Step 4. The limits, looked at again

Done 2026-11-10. Full write-up: `phase1/results/STEP4.md`.

- [x] **P21. Throttle timeline.** Done. The CPU-cap wait lands on start-up
  and on tool runs, almost never on the model wait. At 1 core only
  start-up waits. Trace wait now agrees with `cpu.stat` throttled time.
- [x] **P22. Per-part slowdown under each limit.** Done. Every limit slows
  the tool phase and leaves the model wait alone. New: a disk limit also
  slows the agent's own start-up when caches are cold (2.7 to 4.0 s).
- [x] **P23. What is stable and what is not.** Done. Kernel signals repeat
  to 0 to 1%. Turns, model time and wall time vary by about half.
- [x] **P24. Run the full procedure on every run.** Done. Four trace
  signals name the limit correctly in 259 of 262 runs (98.9%). In-sample:
  the thresholds were set on these runs.
- [x] **P25. Trace against counters.** Done. Counters alone: 222 of 262
  (84.7%). Perfect for CPU quota and memory, blind to disk limits and CPU
  competition.

Follow-ups from Step 4:

- [ ] **Validate the procedure on new runs** with the thresholds frozen.
- [ ] **Correct the claim that the harness does not over-subscribe.** In 1
  of 6 Codex sub-agent runs the model launched all 8 workers at once with
  a shell line. Repeat with more runs, both agents.
- [ ] **Add the disk-limit effect on agent start-up** to the paper.
- [ ] **Make kill detection stricter.** The 1 ms rule found all 3 kills
  but raised 2 false alarms.
- [ ] **Tell soft and hard memory limits apart** in the procedure.
- [ ] **Save `cpu.pressure`, `io.pressure`, `memory.pressure`** in the
  collector to test a counter-only version fairly.

### Step 5. Decide

- [x] **P26. Summary.** Done. `phase1/results/FINDINGS.md` lists every
  finding (F1 to F73), the paper corrections, what the data predicts for
  each new experiment, and what the collector must add.

## Phase 2. Collector (rebuilt from scratch)

Rewritten 2026-11-10 in `collector/`. See `collector/README.md` (how to use)
and `collector/DESIGN.md` (why, and what two related papers add). Runs are
collected from scratch on a new VM; the old runs stay as the workshop
record.

Written and tested as far as possible without the VM (unit tests, dry
runs, and the agent launch, time-stamping, checks and sampler under WSL):

- [x] **One spec per run, one grid per experiment** (`collect.py`,
  `campaign.py`, 17 campaign files, about 880 runs planned).
- [x] **Full kernel trace**: every tracepoint and every system call, with
  larger buffers. `core` and `none` profiles for comparison.
- [x] **Raw trace kept for every run**, plus the tracer's own statistics
  on discarded events. (F7, F8)
- [x] **Agent's own event stream**, one JSON event per line, time-stamped
  on arrival. Gives turns, tool calls and tokens. (F15, F73)
- [x] **All counters for every run**, before and after: every cgroup
  controller, pressure files, machine-wide `/proc` files. (F13, F69)
- [x] **Time series at 5 Hz** (`sampler.py`): CPU, throttling, memory,
  processes, I/O, pressure, per agent and for the group.
- [x] **Same cache state for every run** (cold by default). (F22)
- [x] **Versions and collector commit saved per run.** (F10)
- [x] **Network limit**: namespace with delay, loss and rate in both
  directions, and a control cell with the namespace alone.
- [x] **Process-count limit, several agents at once, busy neighbour, any
  combination of limits.**
- [x] **Quiet, pinned machine** in `vm_setup.sh`: updates and timers off,
  kernel held, checks for cgroup v2, pressure files, hardware and energy
  counters. (F10, F72)
- [x] **Tracing overhead experiment** defined (`campaigns/overhead.json`).
- [x] **Energy and hardware counters** are recorded when the machine has
  them, and their absence is recorded when it does not.

To do on the VM (cannot be tested here):

- [x] **Create the VM.** Done 2026-11-10: `agentic-noise-2`, project
  `project-ba99825a-df02-4405-af4` (account gcp200106), zone `us-east1-d`,
  `n2-standard-4`, Ubuntu 24.04.5, kernel `7.0.0-1017-gcp` (held), 400 GB
  disk (the project's SSD quota is 400 GB), 256 MB/s sequential read.
  `vm_setup.sh` ran. Claude Code 2.1.322 and Codex 0.167.0 are installed.
  SSH: `gcloud compute ssh yuvraj@agentic-noise-2 --project=project-ba99825a-df02-4405-af4 --zone=us-east1-d`
- [x] **Claude Code signed in on the VM** (2026-11-10). Codex is installed
  but not signed in; for now only Claude Code runs are collected
  (`campaign.py <file> --agent claude`).
- [x] **`smoke_fake` campaign** passed on the VM: cgroups and limits
  (throttling shows in `cpu.stat` and in the pressure file), full and core
  trace with 0 discarded events, sampler, two agents at once, network
  namespace (name lookup works; 100 ms delay adds 200 ms per round trip; 5%
  loss produced a 1 s connect), combined limits.
- [x] **Found on the VM and fixed**: asking the tracer for hardware
  counters on a VM without a PMU crashes the kernel (now off unless set by
  hand); this kernel rejects the `mnt_ns` trace context (contexts are now
  added one by one); the first setup script disabled no timers at all.
- [ ] **The VM costs money while it runs.** Stop it when idle:
  `gcloud compute instances stop agentic-noise-2 --project=project-ba99825a-df02-4405-af4 --zone=us-east1-d`
- [x] **Real smoke run (Claude Code)** passed: task solved, 0 discarded
  events with the full profile, 19 agent events with turns, tokens, API
  time and cost, about 46 MB of trace per run (so 880 runs fit the disk).
- [x] **Agent streaming flags confirmed** for Claude Code 2.1.322. Codex
  still to confirm.
- [x] **`overhead` campaign (Claude Code, 15 runs)**: the full profile is
  usable. Median wall time 20.8 s with no trace, 19.6 s core, 20.5 s full:
  no difference beyond run-to-run noise. Kernel CPU time rises from 0.36 to
  0.51 s per run. No events discarded. Per-run numbers in
  `phase2/overhead_claude.csv`. Small sample (n=5 per profile).
- [x] **Independent check of the model share**: the agent's own report
  gives 74 to 76% of wall time in the API, against 76% from the trace in
  Phase 1 (F15).
- [x] **Model pinned**: `claude-opus-5-5` in
  `collector/campaigns/models.json`. `cpu_model2.json` repeats the CPU
  experiment with `claude-haiku-5-5` as the second-model check.
- [x] **`cpu` campaign (Claude Code, 60 runs)** done and checked. 0
  measurement problems. Trace CPU agrees with `cpu.stat` to 0.74%. Model
  turns from the trace equal the agent's own count in 51 of 60 runs, and
  model time is within 2%. The frozen diagnosis thresholds name 58 of 60
  new runs correctly. Write-up: `phase2/CPU-CAMPAIGN.md`.
- [x] **Unattended queue started 2026-11-10 08:37 UTC** (Claude Code only,
  443 runs): network, threads, subagents, disk, memory_soft,
  memory_hard_file, memory_cliff, e2e_disk, neighbour, two_limits,
  cpu_model2, e2e_memory, pids, density. Log on the VM: `~/osn-queue.log`.
  It stops itself if the agent stops answering or the disk fills.
- [x] **Queue ended 2026-11-10 15:18 UTC**: all 14 campaigns complete, 503
  Claude Code runs in total, one kernel. The 19 flagged runs are real
  outcomes (10 memory kills, 9 aborts at the process limit).
- [x] **Copied off the VM** as one `.tar.zst` per campaign (24 GB) to
  `C:\workplace\microservice-trace-dataset\agentic-runs-phase2\osn-export\`,
  checksums verified. VM stopped (not deleted).
- [x] **All 14 campaigns analyzed** with the Phase 1 passes. Write-up:
  `phase2/CAMPAIGNS.md` (findings N1 to N8), per campaign `phase2/<c>/`.
- [ ] **Diagnosis procedure, four changes** (N3): report every signal above
  its threshold with its time (two limits: 20 of 20 then name both); run
  per agent in multi-agent runs (density: correct per agent, wrong on the
  group); add the fork-EAGAIN check for the process limit; add a network
  check.
- [x] **N1 checked (N9 in `phase2/CAMPAIGNS.md`)**: `feedback` campaign, 120
  runs, 2026-11-11. With the run time printed, Haiku keeps working after
  the tests pass (turns 5 / 7 / 11 at no limit / 50% / 25%); with the line
  removed it does not (7 / 8 / 7). Opus does no extra work. On a second
  task Haiku talks about speed (5 of 5 at 25%) but rarely acts.
- [x] **RQ3 real tasks, collected 2026-11-12/13**, 150 of 150 solved, copied with checksums verified, VM stopped. Broken trace decode in `real_django__django-15930_cpu_max200000-memory_max512M_r3` (last 15 of 47 s missing): rerun 2026-11-13 01:38 UTC, clean, replaced in `real.tar.zst`; the broken one is in `real_excluded.tar.zst`. Queue started 2026-11-12 21:43 UTC (`real`, 120
  runs + `real_host`, 30 runs). Six SWE-bench Verified tasks (Django, SymPy,
  xarray, pytest, Flask, Requests), Opus only, in Docker at four platform
  settings from official docs: no limit; 2 CPU / 8 GB (CI runners); 2 CPU /
  512 MiB (agent sandbox); 1 CPU / 512 MiB (Cloud Run, Kubernetes example).
  `real_host` = no limit, no container. Smoke runs: solved in about 22 s,
  peak memory 472 MB of 512 at the pod setting. Container start runs
  iptables, networkctl and chronyc on the host: measure this cost.
- [x] **RQ3 extra cell `real_quarter`, collected 2026-11-13** 05:14 to 05:58
  UTC: the same six tasks at 0.25 CPU / 512 MiB (Fargate minimum), 30 of 30
  solved, no measurement problem, `real_quarter.tar.zst` (`SHA256SUMS-5`),
  verified, VM stopped. Result in `phase2/rq3/RESULTS.md`.
- [ ] **N9 is still thin**: one model reacts, 5 reps, small tasks. Needs
  more reps for Haiku, a task with a larger printed time, and Codex.
- [ ] **N4, a neighbour makes the agent's own CPU time grow** (6.2 to 10.4 s)
  with little waiting. Needs a machine with hardware counters.
- [ ] **Model-turn rule** (N6): over-counts on slow networks, under-counts
  with Haiku, not valid for sub-agents and multi-agent runs. Use the
  agent's event stream for turn counts; write the per-agent reader.
- [x] **Process limit, levels 17 to 23** (`pids_mid`, 35 runs, N10): failed
  forks in all 20 runs at 17 to 20, none in all 15 runs at 21 to 23. 3 of
  20 aborted, 17 solved the task anyway.
- [x] **Second queue copied off the VM** 2026-11-11 (`feedback.tar.zst`,
  `pids_mid.tar.zst`, `SHA256SUMS-2`), checksums verified, VM stopped.
  Claude Code total: 658 runs.
- [ ] **CPU accounting gap is 2 to 4%** in the disk and memory campaigns
  (under 1% elsewhere). Find where the difference is.
- [ ] **Known limit of the full trace**: this tracer has no page-fault,
  TCP-level, memory-allocation or function-probe events on this kernel.
  Covered by counters. Decide if a second tracer is worth adding.
- [ ] **Decide the Codex model**, sign Codex in, run its smoke and overhead
  runs, then the same queue with `--agent codex`.

Still to build:

- [ ] **Agents inside containers, and real repository tasks.** The largest
  gap against the closest related paper, which reports that OS-side work is
  55 to 60% of task time on real tasks with container start-up counted.
  Add a `runtime: container` option and tasks from a public benchmark.
- [ ] **Readers for the new layout**: multi-agent runs, `samples.jsonl`,
  `events.jsonl`. The Phase 1 scripts already run on single-agent runs.
- [ ] **Validate the model-turn rule** against the agent's event stream.
- [ ] **Sandbox on or off** as an experiment: the workshop runs switched
  the agents' own sandboxes off. With 60 to 100 short processes per run,
  per-process protection may have a visible cost. (F37)

## Phase 3. New experiments

Updated 2026-11-10. Each uses 5 reps, random order, both agents. The
"predicts" lines come from the existing traces and are there to be tested.

Each experiment is a file in `collector/campaigns/`: B = `cpu`,
`memory_cliff`, `e2e_memory`, `e2e_disk`; C = `network`; D = `pids`;
E = `density`; G = `two_limits`; H = `neighbour`; I = `subagents`. The four
workshop problems are repeated as `cpu`, `threads`, `memory_soft`,
`memory_hard_file`, `memory_cliff`, `disk`. A (platform limits), F (real
repository tasks) and J (second machine) have no campaign file yet.

- [ ] **A. Real platform limits (RQ3).** Collect the default CPU, memory,
  disk and process limits of common platforms (CI runners, Kubernetes
  defaults, agent sandboxes). Mark them on our curves.
- [ ] **B. Fill the weak cells (RQ2).** Bring every n=3 cell to n=5. Find
  the Codex OOM cliff below 640 MB. Add CPU steps between 0.5 and 1 core,
  where bursts start to be clipped (F56), and memory steps between 640 and
  768 MB.
- [ ] **C. Network limit, Problem 5 (RQ2).** Grid: delay 0, 50, 100,
  200 ms; loss 0, 1, 5%; rate unlimited, 1 Mbit/s, 256 kbit/s.
  Predicts: delay costs Codex about 2.5 round trips on every turn and
  Claude Code only at start-up (F29). Bandwidth bites only near 1 Mbit/s
  and hits start-up, exit uploads and Codex requests first (F27, F31).
  Loss is untested and may matter most.
- [ ] **D. Process-count limit, Problem 6 (RQ2).** `pids.max` from loose
  down to below the peak concurrency of 14 to 16 (F43).
  Predicts: the first limit that produces error returns (F52). Record how
  the agent reacts.
- [ ] **E. Agent density (RQ4).** 1, 2, 4, 8, 16, 32 agents at once on
  4 vCPUs. Per-agent completion time and success.
  Predicts: by average CPU, about 15 Claude or 38 Codex agents fit (F42).
  Bursts and memory (331 MiB per Claude agent, F48) will bind earlier.
- [ ] **F. Heavier real tasks (RQ3).** 5 to 10 tasks from real
  repositories with a build and a test suite, under CPU, memory and disk
  limits. The current tasks are not disk-bound and use 3 CPU-s of tools
  (F23, F46).
- [ ] **G. Two limits at once (RQ2, RQ5).** CPU cap with memory cap, and
  CPU cap with disk cap. Needed for the diagnosis procedure, which so far
  saw one limit per run (F73).
- [ ] **H. Busy neighbour (RQ2, RQ5).** A second busy container, no limit
  on the agent. The competition signal should name it (F66).
- [ ] **I. Sub-agent runs repeated (RQ2).** 10 or more runs per agent, to
  measure how often the model chooses plain shell parallelism (F70).
- [ ] **J. Second machine shape (generality).** A small part of the grid
  with swap on and with a larger machine type.

## Phase 4. Diagnosis procedure (RQ5)

- [x] Trace procedure and counter-only view on the existing runs: 259 and
  222 of 262. (F66, F69)
- [ ] **Freeze the four thresholds, then test on the new runs**, including
  network, process count, two limits at once and a busy neighbour.
- [ ] **Add checks for the new mechanisms**: network (gap between request
  and answer per socket, retransmissions), process limit (error returns
  on spawn).
- [ ] **Make kill detection strict** (F71) and tell soft from hard memory
  limits.
- [ ] **Counter-only version** with the pressure files, for engineers with
  no trace. Report how often each version names the right limit.
- [ ] **Confirm with the supervisor** how much of the procedure this paper
  may present, given the overlap with the other paper in progress.

## Energy and power: what is possible

- A cloud VM does not expose energy counters (RAPL) or CPU frequency, so we
  cannot measure joules on the current VM. Not sure yet if GCP bare-metal
  machine types expose RAPL. This must be checked before planning on it.
- Option 1 (cheap): report CPU-seconds and idle time per task as a proxy,
  and say clearly that it is not an energy measurement.
- Option 2 (real): one bare-metal machine with RAPL, repeat Problem 1 and
  the density experiment, report joules per completed task.
- Recommendation: keep energy out of the ICPE version unless a bare-metal
  machine is available this week. It fits better as a follow-up paper.

## What fits by 2026-11-16, and what does not

- **Done:** Phase 1 (2026-11-10).
- **Must have:** Phase 0, Phase 2 (VM, raw traces, agent report, counters,
  overhead), experiments A and B.
- **Should have:** C (network) and E (density). These are the two new
  results that most change the paper.
- **If time allows:** D (process limit), Phase 4 tool in a simple form.
- **Not this week:** F (real repositories), G, H, I, energy. If these are
  needed for the paper to be strong enough, a later venue is the safer
  choice than a rushed submission.

## Order of work from here

1. Confirm the abstract was registered, and decide: submit on 2026-11-16
   with what fits, or aim at a later venue with the full plan.
2. Create the VM, run `vm_setup.sh`, then the `smoke_fake`, `smoke` and
   `overhead` campaigns.
3. Fix whatever the smoke runs show, then start the `cpu`, `network` and
   `density` campaigns.
4. Analyze the new runs with the `phase1/` scripts. Test the frozen
   diagnosis procedure on them.
5. Apply the paper corrections, move to the ACM template, anonymize.
