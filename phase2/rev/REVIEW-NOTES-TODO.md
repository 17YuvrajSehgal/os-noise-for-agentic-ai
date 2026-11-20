# Fixes found while reading related papers (2026-11-19)

Rule: fix with the data we have, no new runs.

| # | Issue | Source | Check / fix | Status |
|---|---|---|---|---|
| 1 | Real-task table averages ratios (mean of per-task median ratios) | Hoefler 2015, Rule 4 | Recompute with geometric mean; see if numbers or claims change | done: geometric mean; short 1.76->1.74, long 2.13->2.12, no claim changes (rq3/table.py, long.py) |
| 2 | 5 runs (3 for density) may be too few for a 95% bootstrap interval | Hoefler 2015, Maricq 2018 | Subsample 5 of the 15-run set-2 CPU cells; measure how often the 5-run interval covers the 15-run median and how often the breaking-point verdict changes | done: 5-run interval covers all-run value in 99%; verdict agrees 90%; misses only near threshold, never false (stat_checks.txt). Text in Statistics and Threats |
| 3 | No A/A test of the breaking-point rule | Laaber 2019 | Split no-limit runs into random halves; count how often "interval above 1.10" fires | done: false "slower" rate 0.1% local and wall (stat_checks.txt). Text in Statistics |
| 4 | No check for drift with run order | Uta 2020, Maricq 2018 | Correlate no-limit local time with run order and time of day per campaign | done: local time no trend in any cell; wall rho up to 0.85, none after Holm over 18 tests. Text in Threats |
| 5 | SWE-bench Verified has no own reference | SWE-bench note | Add bibitem | done: bibitem swebenchverified, cited twice |
| 6 | Choi et al. (MASCOTS 2026) must be cited | Choi note | Add bibitem and one sentence in Intro | done: bibitem choi2026, one sentence in Intro |
| 7 | Tracing cost 7% vs 23-42% in DepGraph | DepGraph note | Check where the trace is written and where the daemon runs; one sentence | done: trace written to same disk by system-service daemon outside agent cgroup; sentence in Checks, cites ezzati2020 |
| 8 | Replay treats quota as smooth; kernel enforces per period | Turner 2010 | One sentence in Threats | done: sentence in Threats (internal), cites turner2010 |
| 9 | Sandboxes (gVisor) may shift memory/disk results; shared kernel locks may add to density cost | Anjali 2020, 2025 | One sentence each in Threats | done: sentences in Threats (external), cite agache2020, anjali2020, anjali2025 |
