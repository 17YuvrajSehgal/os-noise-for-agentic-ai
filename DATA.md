# Dataset

The study runs split in two:

- **Metadata** — ships in this repo, under `latency/*/runs*/<run>/`. Small,
  and enough to inspect every run's ground truth.
- **Kernel traces** — released on Zenodo (large). Needed only to re-derive
  the table numbers from scratch.

> **Zenodo DOI:** [10.5281/zenodo.23523441](https://doi.org/10.5281/zenodo.23523441)
> — 2.6 GB compressed (6.5 GB unpacked), CC-BY-4.0. Uploaded as 25 × 100 MB
> parts; see [Placing the traces](#placing-the-traces) for the one-liner that
> fetches and reassembles them.

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

## Provenance

`provenance/` (in this repo, and in the Zenodo archive) records the
environment the data came from:

- `vm_env.txt` — the VM snapshot: CPU model, cores/SMT, memory, swap state,
  disk and its native speed, OS and kernel versions, LTTng/Babeltrace
  versions, agent versions, cgroup controllers.
- `campaign*.log` — what ran, in what order, with timings.
- `manifest_*.csv` — the per-campaign run manifests.
- `collection_as_run/` — the collection scripts exactly as executed on the VM.

## Run families

Runs live beside their experiment, in `runs*` directories. Per-agent at
parity (Claude in `runs`/plain dirs, Codex in `runs_codex*`):

Claude runs sit beside their experiment; **every Codex run and both
end-to-end families live under `latency/1_svc_cpu_cap/agentic-os-noise/`**
(abbreviated `AON/` below), because that is where the shared collector and
analyzer live.

| experiment | Claude runs | Codex runs | grid |
|---|---|---|---|
| P1 CPU cap | `AON/runs` | `AON/runs_codex` | 2 tasks × {max,1,0.5,0.25 core} × 5 |
| P2 threads | `latency/2_threads_vs_cores/runs` | `AON/runs_codex_t4` | W ∈ {2,4,8,16} × 5 |
| P2 sub-agents | `latency/2_threads_vs_cores/runs_partB` | `AON/runs_codex_t5` | N ∈ {4,8} × 3 |
| P3 memory | `latency/3_memory_cap/runs/runs_t6` | `AON/runs_codex_t6` | `memory.high`/`memory.max` sweeps |
| P3 OOM cliff | `latency/3_memory_cap/runs/runs_t7` | `AON/runs_codex_t7` | `memory.max` + anon sweep |
| P4 disk I/O | `latency/4_io_cap/runs` | `AON/runs_codex_t8` | `io.max rbps` ∈ {∞,200,100,50 MB/s} × 5 |
| end-to-end | `AON/runs_e2e_cl` | `AON/runs_e2e_cx` | realistic task under memory + disk sweeps |

`AON/` = `latency/1_svc_cpu_cap/agentic-os-noise/`. The end-to-end families
carry `meta/` and `agent.log` only (no traces) — their result is completion
time and task success, which the counters already give.

Each `runs*` directory has a `manifest.csv` listing its runs and conditions —
the exact per-cell counts are there.

## Placing the traces

The Zenodo archive mirrors the `latency/.../runs*/<run>/` layout. Unpack it at
the repo root so each `trace.txt.gz` lands next to its `meta/`:

The archive is uploaded as 25 × 100 MB parts (`traces.tar.gz.part00` …
`part24`), because Zenodo's gateway drops long single-file transfers.
Download them all, concatenate, and unpack at the repo root:

```bash
# from the repo root — fetch every part, then join and extract
for i in $(seq -w 0 24); do
  curl -L -O "https://zenodo.org/records/23523441/files/traces.tar.gz.part$i?download=1"
done
cat traces.tar.gz.part* > traces.tar.gz
sha256sum -c <<< "4ccfbd7ce5e49ad5b6eaadf290fe780bf90e6ce6b381ee5f3f951860a3bd2f8c  traces.tar.gz"
tar xzf traces.tar.gz          # fills in trace/ and trace.txt.gz under latency/*/runs*/
```

The parts are a plain `split` of one gzip file, so `cat` in name order is all
that is needed. The archive also carries `provenance/`; a copy of that
directory already ships in this repo, so unpacking overwrites it with the
same content.

Then `analyze_run.py` and the `research-paper/` scripts work against the full
dataset (see [`REPRODUCE.md`](REPRODUCE.md)).

## License

Dataset: CC-BY-4.0. Code in this repo: MIT.
