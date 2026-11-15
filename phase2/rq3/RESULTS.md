# RQ3. Do real platform settings hurt real coding tasks?

Analyzed 2026-11-13. Six SWE-bench Verified tasks, Opus, in Docker, 5 runs per
task and setting (120 runs in `real`, 30 more at 0.25 CPU in
`real_quarter`), plus the same tasks without a container (30 runs,
`real_host`). Settings from official platform docs (sources in
`collector/campaigns/real.json` and `real_quarter.json`).

```
cd phase2
python rq3/table.py       # -> rq3/table.txt   (per task and setting)
python rq3/commands.py    # -> rq3/commands.txt (same test command across settings)
```

## Method

- Slowdown and local slowdown as in RQ2 (median ratio against the same task
  with no limit, 95% bootstrap interval). "All tasks" is the mean of the six
  per-task ratios.
- Throttled: time the container was held back by its CPU quota (kernel
  counter `cpu.stat`). Memory peak: the container's highest memory use,
  including file cache (`memory.peak`).
- Same-command check: the agent picks different tests in each run, so tool
  time per run mixes the setting with the agent's choice. `commands.py`
  keeps only the test-runner part of each shell command and compares the
  same test run across settings.

## Results

| Setting (platform) | Solved | Wall, all tasks | Local, all tasks | Same test command | Throttled |
|---|---|---|---|---|---|
| No limit | 30/30 | 1.00 | 1.00 | 1.00 | 0 s |
| 2 CPU / 8 GB (CI runners) | 30/30 | 1.01 [0.89-1.16] | 0.99 [0.87-1.18] | 0.98 | 0 s |
| 2 CPU / 512 MB (agent sandbox) | 30/30 | 1.02 [0.91-1.17] | 0.99 [0.89-1.18] | 0.98 | 0 s |
| 1 CPU / 512 MB (Cloud Run, Kubernetes example) | 30/30 | 1.03 [0.93-1.76] | 1.06 [0.95-2.89] | 1.04 (1.02 to 1.09) | 1.7 s (Django 5.4 s) |
| 0.25 CPU / 512 MB (Fargate minimum) | 30/30 | **1.76 [1.50-2.02]** | **2.53 [2.11-3.03]** | **3.26 (2.94 to 3.57)** | 37 s |

What this means:

- **Every run solved its task at every setting. No memory kills.** For tasks
  of this size, even the smallest tier finishes the work.
- **The usual settings (1 CPU and up) give no clear slowdown of the whole
  run.** Their intervals include 1.0. The wide upper ends at 1 CPU come from
  one Requests run that chose to run the whole test suite (see RQ1), not
  from the limit.
- **The smallest tier does hurt: 0.25 CPU makes a run 1.76 times longer**
  (26 s to 48 s median), and the time on the machine 2.5 times longer. Every
  task is slower; the per-task wall ratio is 1.35 (Requests) to 2.15
  (Flask). This is what RQ2 predicted: 0.25 core is below the 0.75-core
  breaking point.
- **Where the extra 22 s goes at 0.25 CPU:** tools +15 s (7 s to 22 s) and
  start-up +3.5 s (3.8 s to 7.3 s; Django 17 s). Model time does not change
  (15.2 against 15.4 s). The same test command takes 3.3 times longer. The
  container is held back by its quota for 37 s per run.
- **The cause-finding method names it.** CPU quota in 28 of 30 runs. The
  other 2 are named memory: they are the two runs that touched the 512 MB
  limit (Django r4 with 379 reclaim events, Sympy r4 with 74). The method
  reports one main cause per run, so the CPU quota is hidden in those two;
  this supports the "report every signal" fix in RQ6.
- **Tool CPU drops at 0.25 CPU** (6.4 to 4.7 s median; Django 14.4 to
  5.8 s). Not the agent's choice: it runs the same number of tests and
  never mentions slowness (RQ5, part 3). A system effect; cause not
  confirmed.
- **1 CPU costs a small, steady amount.** The same test command takes 2 to 9%
  longer at 1 CPU than with no limit; at 2 CPU there is no difference. The
  container is throttled for 1.7 s per run (median), 5.4 s on Django, whose
  test runner starts one worker per CPU.
- **Why so small at 1 CPU and up?** These settings sit above the breaking
  point from RQ2 (0.75 core). The test runs here are short and mostly use
  one core. Only the tier below that point (0.25) hurts. Modal's 0.125 core
  default is lower still and was not run.
- **RQ2 to RQ3 in one line:** the breaking point found on small tasks
  predicts which platform tiers hurt real tasks. Above it, no clear cost;
  below it, x1.8 wall, x2.5 local, and the model wait hides part of it
  (x2.5 on the machine shows as x1.8 to the user).
- **512 MB is right at the edge.** Peak memory is 345 to 453 MB on five
  tasks. Django reaches the 512 MB limit in 9 of 10 runs (585 MB with no
  limit) and the kernel reclaims memory (474 reclaim events at 2 CPU /
  512 MB). It still finishes, because what is pushed out is mostly file
  cache. Django's larger test group took 1.5 times longer at 2 CPU / 512 MB
  than with no limit, but that rests on one baseline run. A slightly bigger
  project would cross the limit.
- **Docker itself:** +1.2 s at start-up (RQ1), and the same test command
  takes the same time with or without the container (ratio 1.00).

## Limits of this analysis

- Six tasks, all small fixes (median 26 s, 4 model turns). Longer tasks
  with more test runs would show more of the CPU effect.
- 5 runs per cell. The same-command check rests on 2 to 3 commands per
  setting with 2 or more runs on each side.
- The 0.25 CPU cell was collected after the others (same VM, same day,
  same image and agent version). Model service speed can differ by time of
  day; model time did not change (15.2 against 15.4 s), so this did not
  matter here.
- The memory peak includes file cache, so it overstates what the programs
  need. I'm not sure how much of Django's 512 MB is cache; the trace could
  tell (reclaim of file pages against process pages), not yet checked.
- One machine shape (4 vCPU). On a busy shared host the picture could be
  worse (RQ2 neighbour: +86% local).

## Open

- Split Django's memory peak into file cache and process memory.
- Why tool CPU drops at 0.25 CPU (needs hardware counters).

## Longer tasks (real_long, analyzed 2026-11-15)

Four longer SWE-bench Verified tasks (django-15957, sympy-14248,
pytest-10356, xarray-6992), Opus, Docker, 5 runs per task and setting, 60
runs. `python rq3/table.py real_long` -> `rq3/table_real_long.txt`.

| Task | No limit | 1 CPU / 512 MB | 0.25 CPU / 512 MB | Memory kills |
|---|---|---|---|---|
| django | 5/5, 51 s | 5/5, x1.21 [0.91-1.85] | 5/5, x2.02 [1.63-2.65] | 0 |
| sympy | 5/5, 111 s | 5/5, x0.96 [0.49-1.60] | 5/5, x1.92 [0.99-2.20] | 0 |
| pytest | 1/5, 67 s | 2/5, x1.18 | 1/5, x2.46 | 0 |
| xarray | 0/5, 40 s | 0/5, x5.09 [0.76-7.96] | 0/5, x11.95 [1.77-15.90] | 63 (4 to 9 in every limited run) |

What this means:

- **Solve rate does not depend on the setting.** django and sympy are solved
  in every run at every setting. pytest is solved about 1 in 4 times with or
  without limits (agent difficulty).
- **xarray is never solved, even with no limit.** The environment works (902
  of 902 existing tests pass after every run); all 12 target tests fail
  because the agent's fix (11 different patches, same idea) does not match
  the behaviour the hidden tests expect. Not checked by running the
  reference fix (VM stopped).
- **xarray needs more memory than the sandbox tier.** Its test runs peak at
  about 810 MB with no limit. Under 512 MB every limited run has 4 to 9 OOM
  kills (63 in total), about 90 thousand reclaim events, and runs 5 to 12
  times longer. Tool time goes from 17-31 s to 106-580 s.
- **The kill is silent to the agent.** The test output just stops (for
  example at "34%"); the tool result has no error flag and no "Killed" line.
  In 6 of 10 limited runs the agent saw no error message at all; in none did
  its final answer mention memory. It reran tests and kept going.
- **The CPU result of the short tasks holds.** 0.25 CPU gives x1.9 to x2.5 on
  the three tasks that fit in memory (short tasks: x1.76); 1 CPU gives no
  clear slowdown.
- Model cost: $20.15 for the 60 runs.
