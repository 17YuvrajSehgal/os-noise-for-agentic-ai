# Dataset

The study runs split in two:

- **Metadata** — ships in this repo, under `latency/*/runs*/<run>/`. Small,
  and enough to inspect every run's ground truth.
- **Kernel traces** — released on Zenodo (large). Needed only to re-derive
  the table numbers from scratch.

> **Zenodo DOI:** _pending release._ This section will carry the DOI and the
> direct download once the dataset is published.

## What one run contains

```
<run>/
├── agent.log            # the agent's transcript for this run
├── meta/                # ← ships in this repo
│   ├── ground_truth.json    # agent, exit codes, success, the limit set, kernel
│   ├── cpu.stat.before/after    # cgroup CPU counters (usage, nr_throttled, throttled_usec)
│   ├── memory.stat|events|peak.*  # cgroup memory counters (problem 3 runs)
│   ├── io.stat.before/after       # cgroup I/O counters (problem 4 runs)
│   ├── clock_anchors.jsonl        # realtime/monotonic/boottime anchors (wall time)
│   ├── root.pid                   # the agent's root PID (process-tree seed)
│   ├── lttng_enabled.txt          # the exact tracepoints recorded
│   ├── agent_diff.txt             # files the agent changed
│   └── task_check.txt             # the success check's output
└── trace/               # ← Zenodo only: raw CTF kernel trace (channel0_*, index/, metadata)
    trace.txt.gz         # ← Zenodo only: the decoded trace (babeltrace2 text, gzipped)
```

The counters in `meta/` are the paper's **ground truth** (throttle time, OOM
events, bytes moved). The analysis cross-checks the trace against them. So the
headline numbers can be verified from `meta/` alone; the trace is what lets
`analyze_run.py` attribute *where* the time went.

## Run families

Runs live beside their experiment, in `runs*` directories. Per-agent at
parity (Claude in `runs`/plain dirs, Codex in `runs_codex*`):

| experiment | directory | grid |
|---|---|---|
| P1 CPU cap | `latency/1_svc_cpu_cap/agentic-os-noise/runs`, `runs_codex` | 2 tasks × {max,1,0.5,0.25 core} × 5 |
| P2 threads | `latency/2_threads_vs_cores/runs`, `.../runs_codex_t4` | W ∈ {2,4,8,16} × 5 |
| P2 sub-agents | `latency/2_threads_vs_cores/runs_partB`, `.../runs_codex_t5` | N ∈ {4,8} × 3 |
| P3 memory | `latency/3_memory_cap/runs/runs_t6`, `.../runs_codex_t6` | `memory.high`/`memory.max` sweeps |
| P3 OOM cliff | `latency/3_memory_cap/runs/runs_t7`, `.../runs_codex_t7` | `memory.max` + anon sweep |
| P4 disk I/O | `latency/4_io_cap/runs`, `.../runs_codex_t8` | `io.max rbps` ∈ {∞,200,100,50 MB/s} × 5 |
| end-to-end | `.../runs_e2e_cl`, `.../runs_e2e_cx` | realistic task under memory + disk sweeps |

Each `runs*` directory has a `manifest.csv` listing its runs and conditions —
the exact per-cell counts are there.

## Placing the traces

The Zenodo archive mirrors the `latency/.../runs*/<run>/` layout. Unpack it at
the repo root so each `trace.txt.gz` lands next to its `meta/`:

```bash
# from the repo root, once the DOI is known:
curl -L -o traces.tar.gz "<zenodo-download-url>"
tar xzf traces.tar.gz          # fills in trace/ and trace.txt.gz under latency/*/runs*/
```

Then `analyze_run.py` and the `research-paper/` scripts work against the full
dataset (see [`REPRODUCE.md`](REPRODUCE.md)).

## License

Dataset: CC-BY-4.0. Code in this repo: MIT.
