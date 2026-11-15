# RQ1. Where does an agent's time go when nothing limits it?

Analyzed 2026-11-13. Scripts: `split.py` (one row per single-agent run,
`runs.csv`, 790 runs) and `table.py` (`table.txt`). Runs with no limit, no
network change and no neighbour: 230.

```
cd phase2
OSNOISE_RUNS=<runs root> python rq1/split.py <campaigns>   # -> rq1/runs.csv
python rq1/table.py                                         # -> rq1/table.txt
```

## Method

- Model turns and tool calls come from the agent's own event log
  (`a1/events.jsonl`), which time-stamps every line the agent prints. A model
  turn runs from the event that triggers the request (session start or a
  tool result) to the last block of the answer. A tool call runs from the
  tool request to its result.
- This also counts tools that run inside the agent process (file read, edit,
  search). The trace sees those as the agent's own work, not as tool
  processes.
- CPU time and waiting times come from the kernel trace, for the agent's
  process tree.

## Check of the turn count

The turn count from the log equals the count from the network rule (the
Phase 1 rule on the trace) in 739 of 790 runs. The 51 others:

- Slow network (20 runs): the network rule counts too many turns, because a
  slow answer looks like several. The log is right.
- Sub-agents (20 runs): the network rule counts the sub-agents' turns too;
  the log count above is the main agent only. Not a disagreement.
- Memory, two-limit and real-task runs (11 runs): off by 1 to 3. Not yet
  checked one by one.

This corrects finding N6 in `phase2/CAMPAIGNS.md`. There the network rule
was compared with the agent's own "number of turns" field, which counts
differently. Against the event log, the rule is right except on slow
networks and with sub-agents.

## Results

Shares of wall time, medians over runs:

| Workload | Runs | Wall | Start-up | Model | Tools | Agent's own work |
|---|---|---|---|---|---|---|
| Small coding tasks, Opus | 50 | 18 to 21 s | 7 to 8% | 72 to 79% | 12 to 20% | 0.1% |
| Small coding tasks, Haiku | 30 | 15 to 17 s | 8 to 10% | 67 to 76% | 11 to 21% | 0.1% |
| Small coding tasks, Fable | 10 | 17 to 19 s | 8% | 75 to 80% | 10 to 15% | 0.1% |
| Real tasks, no container, Opus | 30 | 20 to 36 s | 8 to 13% | 49 to 75% | 16 to 39% | 0.1% |
| Real tasks, in Docker, Opus | 30 | 22 to 38 s | 10 to 17% | 42 to 66% | 20 to 38% | 0.1% |

Over all coding runs: Opus spends a median of 68% of the time waiting for
the model (range 18 to 84%), and 20% running tools.

What this means:

- **Waiting for the model is most of the time**, about two thirds to four
  fifths. The agent's own processing between events is near zero (0.1%).
- **Real tasks shift time from the model to the tools.** On small tasks
  tools take 10 to 20%; on the real projects 16 to 39% (xarray and Flask
  37 to 39%). Real test suites are heavier, so the operating system matters
  more there than the small tasks suggested.
- **Start-up is a fixed cost of 2 to 4 s**, which is 7 to 17% of these
  short runs.
- **With no limit, the system adds almost no waiting.** CPU waits in the
  agent's process tree are 0.1 to 0.3 s per run. The exceptions are the
  thread test (3.8 s, as designed) and Django (1.5 to 2.1 s).
- **Disk wait is 4 to 12 s on real tasks against 1 s on small ones.** This
  is the first read of the project and its Python environment after the page
  cache was dropped (runs start cold on purpose). These are seconds summed
  over threads, so they can overlap in time.

## Docker against no container (same six tasks, no limit, 5 runs each)

- **Docker adds 1.2 s to start-up, every time.** Per task: +1.15 to +1.22 s,
  from 2.6 s to 3.8 s median. This is the most stable number in the set.
- **Total time: +0.8 to +4.1 s on four tasks; -1.9 and -0.1 s on two.**
  Within the spread of 5 runs, the rest of the run is not clearly slower in
  a container.
- Starting a container also runs network setup programs on the host
  (iptables, networkctl, chronyc). To measure: their CPU time per start.

## Agent behaviour is the largest source of spread

- The slowest run with no limit (Requests, no container, 85 s against 20 to
  27 s for the others) is the agent's own choice: it ran the project's whole
  test suite once (63 s). The other runs tested only the changed function.
- Django tool CPU is 14.4 s in Docker against 7.1 s without (medians), but 3
  of 5 Docker runs chose to add a large extra test group, against 2 of 5
  without. With 5 runs, Docker's own effect on tool CPU cannot be told apart
  from this choice.
- For the paper: the time spent in tools depends more on which tests the
  agent decides to run than on the machine. Compare like with like (same
  commands) before claiming a container or limit effect on tool time.

## Open

- Measure the host-side cost of container start (the network setup
  programs).
- Check by hand the 11 runs where the log and the network rule differ by 1
  to 3 turns.
- Compare tool time per test command (same command in both settings), not
  per run.
