# OS Noise for Agentic AI

A kernel-trace study of how container resource limits slow down and break AI
coding agents.

Yuvraj Sehgal, Naser Ezzati-Jivan — Department of Computer Science, Brock
University.

This repository is the **code and metadata artifact** for the paper. The full
raw traces are released separately on Zenodo (see [`DATA.md`](DATA.md)).

---

## What this is

When a coding agent feels slow, people blame the language model. But agents
run inside containers, and containers come with resource limits — a
fractional CPU, a memory ceiling, an I/O budget. This study measures how much
of an agent's wall-clock time those limits silently take, using **kernel
tracing (LTTng)** on two production agents, **Claude Code** and **Codex CLI**.

The method needs no change to the agent: put it in a cgroup, set one limit,
record a kernel trace, and use the cgroup's own counters as ground truth.

## The experiments

Four mechanism studies plus one reality check. Each isolates a mechanism with
a workload built to stress it; the end-to-end test then asks which a
lightweight coding task actually trips.

| # | folder | what it limits | headline result |
|---|---|---|---|
| 1 | `latency/1_svc_cpu_cap/agentic-os-noise` | CPU bandwidth (`cpu.max`) | +75% wall at 0.25 core; on-CPU demand flat, the cap turns it into throttle wait |
| 2 | `latency/2_threads_vs_cores` | cores (over-subscription, no cgroup) | parallel phase +295% at 4×, matching the `(W−C)/W` queueing law |
| 3 | `latency/3_memory_cap` | memory (`memory.high` / `memory.max`) | 4.7× slower on refaults; a sharp OOM cliff on unreclaimable memory |
| 4 | `latency/4_io_cap` | disk read bandwidth (`io.max`) | 3.4× slower read phase at 50 MB/s |
| E2E | `latency/1_svc_cpu_cap/.../runs_e2e_*` | all of the above, realistic task | a lightweight coding task trips **only** the CPU cap, and memory only below the agent's own footprint |

Baseline finding: on a well-provisioned machine the agent is **≈84%
LLM-bound**. Every effect reproduces across both agents and agrees with the
cgroup counters.

## Repository layout

```
.
├── README.md            ← you are here
├── REPRODUCE.md         ← step-by-step: set up a VM, collect, analyze
├── DATA.md              ← what a run contains + how to get the traces (Zenodo)
├── CITATION.cff         ← how to cite
├── LICENSE              ← MIT (code); data is CC-BY-4.0 on Zenodo
├── research-paper/      ← the paper (paper.tex), figures, and the scripts
│   │                      that turn runs into every table/figure number
│   ├── paper.tex
│   ├── make_data.py  compare_agents.py  llm_wait.py  make_fig_*.py
│   └── *-RESULT.md    ← prose write-up of each result
├── provenance/          ← VM environment snapshot, campaign logs, manifests,
│                          and the collection scripts exactly as executed
└── latency/
    ├── 1_svc_cpu_cap/agentic-os-noise/
    │   ├── PLAN.md  RESULTS.md
    │   ├── collection/   ← how one run is produced (see its README)
    │   │   ├── collect_agent_run.sh   ← ★ the collector
    │   │   ├── tasks/                 ← what the agent is told to do
    │   │   └── run_campaign_*.sh      ← one loop per experiment
    │   ├── analysis/     ← analyze_run.py (★ one run → time budget), aggregate.py
    │   └── runs*/        ← per-run meta/ + agent.log (traces on Zenodo)
    ├── 2_threads_vs_cores/   { PLAN, RESULTS, analysis/aggregate_t4.py, runs* }
    ├── 3_memory_cap/         { PLAN, RESULTS, analysis/aggregate_mem.py, runs* }
    └── 4_io_cap/             { PLAN, RESULTS, analysis/aggregate_io.py, runs* }
```

The two files worth reading closely are
`latency/1_svc_cpu_cap/agentic-os-noise/collection/collect_agent_run.sh` (how
a run is produced) and `.../analysis/analyze_run.py` (how a run becomes
numbers). Each has a README next to it.

## What ships here vs. on Zenodo

| | here (this repo, ~12 MB) | Zenodo (2.6 GB download, 6.5 GB unpacked) |
|---|---|---|
| all code (collect + analyze + paper) | ✓ | — |
| the paper and figures | ✓ | — |
| per-run **metadata**: cgroup counters (`cpu.stat`, `memory.*`, `io.stat`), `ground_truth.json`, clock anchors, agent log | ✓ | — |
| per-run **kernel traces** (raw CTF + decoded `trace.txt.gz`) | — | ✓ |
| **provenance**: VM environment snapshot, campaign logs, manifests | ✓ | ✓ |

So you can inspect every run's ground truth offline. Re-deriving the paper's
table numbers (which parse the traces) needs the Zenodo data — see
[`DATA.md`](DATA.md).

## Quickstart

Inspect one run's ground truth (ships in the repo, no download needed):

```bash
cd latency/1_svc_cpu_cap/agentic-os-noise/runs/t3_implement_cap25_r1
cat meta/ground_truth.json          # agent, limits, exit, kernel
# throttle this run took, from the cgroup counter:
python - <<'PY'
b=dict(l.split() for l in open('meta/cpu.stat.before'))
a=dict(l.split() for l in open('meta/cpu.stat.after'))
print('throttled_s =', (int(a['throttled_usec'])-int(b['throttled_usec']))/1e6)
PY
```

To run the full pipeline (analyze traces → tables), fetch the traces from
Zenodo and follow [`REPRODUCE.md`](REPRODUCE.md).

## Requirements

- **Collection** (Linux, root): LTTng 2.15, Babeltrace2, cgroup v2, Python 3,
  and the agent CLIs (Claude Code and/or Codex). See `REPRODUCE.md`.
- **Analysis** (any OS): Python 3.10+ (standard library only; matplotlib only
  for the optional figures).

## Citing

See [`CITATION.cff`](CITATION.cff). The dataset has its own DOI:

```bibtex
@dataset{sehgal_osnoise_traces_2026,
  author    = {Sehgal, Yuvraj and Ezzati-Jivan, Naser},
  title     = {{OS Noise for Agentic AI: kernel traces of AI coding
               agents under container resource limits}},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.23523441},
  url       = {https://doi.org/10.5281/zenodo.23523441}
}
```

## License

Code: MIT ([`LICENSE`](LICENSE)). The dataset on Zenodo is released under
CC-BY-4.0.
