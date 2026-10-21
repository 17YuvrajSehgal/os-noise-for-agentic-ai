# Research paper — OS Noise for Agentic AI

`paper.tex` — the paper. Self-contained, builds with plain pdfLaTeX (only
standard packages: geometry, booktabs, amsmath, amssymb, amstext, graphicx,
hyperref, caption, titlesec).

## Build

```bash
pdflatex paper.tex && pdflatex paper.tex   # twice, for refs
```

Or `latexmk -pdf paper.tex`. Build on a machine with TeX Live / MiKTeX, or
on Overleaf by uploading `paper.tex` and the `figures/` folder.

## Figures

- The paper embeds one figure, `figures/fig_method.pdf` (the
  trace-to-accounting method). A `.png` copy is provided for quick preview.
- The other `fig_*` files (llmshare, cpu, threads, memory, io, consistency)
  were dropped from the current draft to save space but are kept here as
  supplementary views; the tables carry those numbers. `make_figures.py`,
  `make_fig_llm.py`, and `make_fig_consistency.py` regenerate them
  (matplotlib, Okabe–Ito colorblind-safe palette).

## Numbers (reproduce the tables)

Every table number is recomputed straight from the run data, so the paper
matches the data exactly. Run these from this directory (they import the
analyzer from `../latency/1_svc_cpu_cap/agentic-os-noise/analysis`):

| script | produces |
|---|---|
| `make_data.py` | all four problem tables (median + min–max over reps) |
| `compare_agents.py` | the Claude-vs-Codex consistency table |
| `llm_wait.py` | the ~84% LLM-bound share (per-socket request timing) |

These need the **decoded traces** (`trace.txt.gz` per run), which are not in
this repo — see `../DATA.md` to fetch them from Zenodo. The per-run
`meta/` (cgroup ground truth) ships in the repo, so the throttle/memory/IO
counters can be inspected without the traces.

The prose write-ups of each result are `E2E-RESULT.md`,
`CONSISTENCY-RESULT.md`, and `LLM-SHARE-RESULT.md`.
