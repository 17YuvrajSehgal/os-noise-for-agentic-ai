# Step 1 results: the shape of a run (P3, P4, P5)

Date: 2026-11-10. Data: all 262 traces. Numbers below are for the 40 + 40
coding-task runs (bug-fix and implement, four CPU settings, 5 reps, both
agents) unless said otherwise.

How to rerun (about 30 seconds):

```bash
export OSNOISE_RUNS=C:/workplace/microservice-trace-dataset/agentic-runs
cd phase1
python parse_all.py > results/parsed_all.jsonl   # trace -> exchanges, processes, CPU bins
python step1.py                                  # -> results/step1_runs.csv, step1_turns.csv
```

Scripts: `exchanges.py` (parser), `parse_all.py`, `step1.py`. Exploration
helpers: `explore_sockets.py`, `explore_timeline.py`.

## Definitions used

- **Exchange**: on one HTTPS socket, the bytes the agent writes (request)
  and the bytes it then reads (response), until the next request.
- **Model turn**: an exchange of the agent process with a request of at
  least 2 KB whose response is still arriving 0.7 s after the request.
- **Tool process**: a process the agent starts that has exited before the
  last model response ends. Launchers and session-long helpers count as the
  agent.
- **Wall clock** is split into six parts that do not overlap: start-up
  (before the first model request), model only, model and tool together,
  tool only, agent only, shutdown (after the last model response).

Why the model-turn rule is safe: over all 262 runs, exchanges with a
request of 2 KB or more fall in two groups with nothing in between. For
Claude Code 510 last 0.47 s or less and 469 last 0.88 s or more. For Codex
136 last 0.2 s or less and 819 last 1.0 s or more. The short ones are
start-up configuration calls and telemetry uploads.

Not validated against ground truth. The old runs did not save the agent's
own turn count. The Codex logs list tool calls, but one turn can hold
several calls, so the counts do not map one to one. New runs must save the
agent's JSON report so this can be checked.

## P3. Turns

Unlimited runs, per agent and task:

| | Claude bug-fix | Claude implement | Codex bug-fix | Codex implement |
|---|---|---|---|---|
| Model turns per run | 3, 3, 5, 6, 6 | 3, 3, 3, 3, 3 | 10, 11, 11, 14, 15 | 6, 7, 9, 9, 10 |
| Wall time (s) | 16 to 27 | 17 to 20 | 31 to 68 | 23 to 41 |
| Wait for first byte, median / 90th pct (s) | 1.19 / 4.17 | 1.00 / 4.29 | 0.70 / 1.60 | 0.70 / 1.91 |
| Streaming time per turn, median (s) | 1.68 | 0.77 | 1.70 | 2.04 |
| Request size per turn, median (KB) | 4.0 | 3.8 | 65.7 | 63.3 |
| Correlation of wall time with turn count | 0.99 | (no spread) | 0.91 | 0.58 |

What this means:

- **Run-to-run variation is mostly the number of turns.** For Claude
  bug-fix, runs with 3 turns take 16 to 17 s and runs with 5 or 6 turns take
  23 to 27 s. This is model behaviour, not the machine.
- **The two agents work differently.** Claude Code finishes in 3 to 6
  turns. It puts several tool calls in one turn and runs them while the
  response is still streaming. Codex uses one turn per tool call, so it
  needs 6 to 15 turns.
- **Codex uploads far more.** Codex sends about 55 to 75 KB on every turn
  and opens a new connection each time: about 640 KB per run. Claude Code
  sends one 30 KB request and then about 4 KB per turn on one connection:
  about 38 KB per run. Not sure why Claude's later requests are so small
  (possibly compressed request bodies).

## P4. Start-up

Start anchor to first model request, all coding runs (n = 10 per cell):

| CPU setting | Claude start-up (s) | Claude CPU used (s) | Codex start-up (s) | Codex CPU used (s) |
|---|---|---|---|---|
| unlimited | 1.65 | 1.23 | 0.31 | 0.28 |
| 1 core | 1.91 | 1.23 | 0.41 | 0.27 |
| 0.5 core | 2.84 | 1.20 | 0.74 | 0.27 |
| 0.25 core | 5.12 | 1.21 | 1.60 | 0.27 |

- **Start-up is CPU work.** Claude Code burns 1.23 CPU-seconds before its
  first model request. That is more than half of all the CPU the agent
  process itself uses in a run (2.2 s).
- **The cap stretches it as expected.** The CPU used stays the same, and
  the start-up time grows to about CPU divided by the cap (1.23 / 0.25 =
  4.9 s, measured 5.1 s).
- For a short task this fixed cost matters: at 0.25 core, start-up alone is
  5 s of a 33 s run.

## P5. Where the wall clock goes

Unlimited coding runs, share of wall time, median and range over 10 runs:

| Part | Claude Code | Codex |
|---|---|---|
| Start-up | 8.9% (6.1 to 10.6) | 0.9% (0.7 to 1.6) |
| Model only | 74.9% (69.6 to 82.0) | 89.2% (84.3 to 92.9) |
| Model and tool together | 1.4% (0.0 to 5.1) | 0.3% (0.2 to 0.5) |
| Tool only | 13.4% (6.6 to 17.5) | 7.9% (3.9 to 11.9) |
| Agent only | 0.4% | 1.1% |
| Shutdown | 1.3% | 0.6% |

CPU per run: agent process 2.2 s (Claude) and 0.8 s (Codex); tool processes
about 3.0 s for both (the test suite).

### The 84% figure needs a correction

The workshop paper says the agent has a model request in flight 84% of the
time. That number counted every HTTPS exchange, including about 1.5 s of
start-up configuration calls and the telemetry uploads at the end. Counting
only model turns:

| | Old method (any HTTPS request) | Model turns only |
|---|---|---|
| Claude Code, 10 unlimited runs | 84% (80 to 91) | 75.7% (71.2 to 85.6) |
| Codex, 10 unlimited runs | not in the paper as a 10-run figure | 89.6% (84.7 to 93.1) |

So "about 84%" should become "about 76% for Claude Code and about 90% for
Codex". The claim that the agent is mostly waiting for the model still
holds.

### What a CPU cap does to each part

Implement task, median seconds:

| | unlimited | 1 core | 0.5 core | 0.25 core |
|---|---|---|---|---|
| Claude: start-up | 1.67 | 1.90 | 2.83 | 5.10 |
| Claude: model only | 13.33 | 12.97 | 13.52 | 12.40 |
| Claude: tool only | 2.99 | 3.07 | 6.26 | 12.72 |
| Claude: wall | 18.66 | 18.66 | 23.66 | 32.69 |
| Codex: start-up | 0.31 | 0.41 | 0.73 | 1.61 |
| Codex: model only | 26.57 | 25.60 | 24.83 | 24.09 |
| Codex: tool only | 2.77 | 2.81 | 5.54 | 21.37 |
| Codex: wall | 30.30 | 29.64 | 31.82 | 48.40 |

- **The cap does not slow the model part.** Model time is flat across caps
  for both agents.
- **All of the slowdown is in start-up and in tools.** For Claude at 0.25
  core, tool time grows from 3.0 to 12.7 s and start-up from 1.7 to 5.1 s.
  Together that is about 13 of the 14 extra seconds.
- This is a stronger statement than the workshop paper made. It says where
  the throttle time lands, not only how much there is.

The model share at 0.25 core (implement) is 41% for Claude and 62% for
Codex with the corrected method. The paper has 53% and 62%.

## What this decides for the new runs

- **Network experiment.** Codex re-uploads about 60 KB per turn on a new
  connection each time, and Claude sends about 4 KB on one connection. An
  upload bandwidth limit and a connection set-up delay should hurt Codex
  much more. Wait for first byte is about 1 s, so added delay below about
  100 ms should be hard to see. Both are predictions to test.
- **Reps.** Wall time depends on the turn count, which the model decides.
  Compare conditions on per-part times (start-up, tool time), which are
  stable, not only on wall time.
- **Collector.** Save the agent's JSON report (turns, API time) so the
  model-turn rule can be validated.

## Open questions

- Codex at 0.25 core (implement) shows 5.5 CPU-seconds of tool work against
  2.9 in every other cell. Not yet explained. Possibly a tool call that
  timed out and was run again.
- Codex starts about 100 tool processes for about 10 tool calls. To look at
  in P9.
- The split was computed for all 262 runs but only the coding runs are
  summarized here.
