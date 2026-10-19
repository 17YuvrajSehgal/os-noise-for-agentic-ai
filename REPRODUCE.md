# Reproducing the study

Two independent things you can reproduce:

- **A: Re-analyze our runs** — download the traces from Zenodo and regenerate
  every table/figure number. No cloud, no agent keys. Start here.
- **B: Collect your own runs** — stand up a VM, point an agent at it, and
  record fresh traces. Needs a Linux VM and an agent CLI.

---

## A. Re-analyze our runs

### 1. Get the traces

The per-run `meta/` ships in this repo; the kernel traces do not. Fetch them
from Zenodo and unpack so each `trace.txt.gz` lands next to its `meta/` — see
[`DATA.md`](DATA.md) for the exact layout and the one-liner.

### 2. Analyze one run

```bash
cd latency/1_svc_cpu_cap/agentic-os-noise
python analysis/analyze_run.py runs/t3_implement_cap25_r1
```

This prints a JSON time budget for that run: on-CPU seconds, runnable-wait,
blocked-on-syscall buckets, the `cpu.stat` cross-check, and (where relevant)
the memory/IO metrics. How it works — process-tree rebuild from `root.pid`,
then a per-thread state machine over `sched_switch`/`sched_wakeup` — is in
`analysis/README.md`.

### 3. Regenerate the paper's numbers

From `research-paper/` (needs the traces from step 1):

```bash
cd research-paper
python make_data.py        # all four problem tables (median + min–max/reps)
python compare_agents.py   # the Claude-vs-Codex consistency table
python llm_wait.py         # the ~84% LLM-bound share
```

Optional figures (needs matplotlib):

```bash
python make_figures.py  make_fig_llm.py  make_fig_consistency.py
```

Build the paper itself on a machine with LaTeX: see `research-paper/README.md`.

---

## B. Collect your own runs

Full detail (every design decision, every gotcha) is in
`latency/1_svc_cpu_cap/agentic-os-noise/collection/README.md`. The short path:

### 1. A Linux VM

Ubuntu 24.04, 4 vCPUs, cgroup v2, no swap (so memory pressure OOMs rather
than swaps). Our setup is one Google Cloud `n2-standard-4` (see
`research-paper/paper.tex`, Table 1). Then:

```bash
bash collection/vm_setup_agentic.sh     # installs LTTng 2.15 + smoke-tests tracing
```

Sign the agent in for the user that runs the scripts: Claude Code needs
`~/.claude*`; Codex needs `~/.codex/config.toml` + `~/.codex-env` (an
OpenRouter key — keep it out of git).

### 2. One run

```bash
AGENT=claude RUNS_DIR=~/runs \
  bash collection/collect_agent_run.sh <run_name> <cpu.max> <task.sh> \
       [task_arg] [mem_limit] [io_limit]
```

- `cpu.max`: `max`, or `"<quota> <period>"` e.g. `"25000 100000"` (0.25 core).
- `mem_limit`: `high:<N>` or `max:<N>`; `io_limit`: `rbps:<N>` bytes/s.
- `AGENT=codex` runs `codex exec` instead of Claude Code.

Example: `bash collection/collect_agent_run.sh t3_cap25_r1 "25000 100000" t3_implement.sh`

Each run produces `runs/<name>/{trace/, trace.txt.gz, agent.log, meta/}` plus
a `manifest.csv` row.

### 3. A whole experiment

Each campaign is a thin, shuffled, resumable loop over one grid:

| campaign | experiment |
|---|---|
| `collection/run_campaign.sh`      | Problem 1 — CPU cap |
| `collection/run_campaign_t4.sh`   | Problem 2 — threads vs cores |
| `collection/run_campaign_t5.sh`   | Problem 2 — sub-agents |
| `collection/run_campaign_t6.sh`   | Problem 3 — memory |
| `collection/run_campaign_t8.sh`   | Problem 4 — disk I/O |
| `collection/run_campaign_e2e.sh`  | the realistic end-to-end task |

Then analyze as in part A.

---

## Gotchas (do not rediscover)

The hard-won ones are documented where they bite — the collector's
`collection/README.md` "Known gotchas" section (cgroup-v2 delegation, dropping
page cache before memory runs, the `mm_vmscan_*` tracepoint name, enabling the
`io` controller, the `prctl` worker-comm tags). One that affects analysis on
newer kernels: a preempted-runnable thread is reported as `prev_state=256`
(not 0); `analyze_run.py` counts it as runnable-wait. See `analysis/README.md`.
