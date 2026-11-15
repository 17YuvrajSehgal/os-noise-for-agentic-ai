# Plan to ICPE 2027 (deadline 2026-11-23 AoE)

Written 2026-11-14. Research Track, 10 pages + references, ACM two-column,
double-blind. Aim: submit on 2026-11-22, one day early.

## The story of the paper

An AI coding agent spends most of its time waiting for the model, so the
system it runs on looks unimportant. We show the opposite: the system's
cost is large but hidden by the model wait, and we give the numbers and a
simple model to predict it.

Contributions:

1. **Dataset:** 1,100 runs with full kernel traces, two agents, two
   machines, 20 experiments. Public.
2. **Hidden cost and a model of it:** wall slowdown = 1 + local share ×
   (local slowdown − 1). It explains why a 3.9x cost on the machine shows
   as 2.0x to the user. Checked on every limit.
3. **A map of every limit:** breaking point, shape (smooth, cliff, crash),
   and which part of the time grows.
4. **Real use:** the breaking point predicts which cloud settings hurt real
   GitHub fixes, and how many agents fit on one machine (with a capacity
   model).
5. **Behaviour and reliability:** the agent changes its work under a CPU
   limit; memory and process limits can kill or crash the agent itself.
6. **The workshop results, checked on two machines and two agents.**

## Weak spots and how we fix them

| Weak spot a reviewer will raise | Fix | Needs |
|---|---|---|
| "How much does the tracing slow the agent?" | Run `overhead` (none, core, full tracing) | VM, ~1 to 2 h |
| "A CPU cap slowing things is obvious" | The model in contribution 2, checked on all limits; lead with the hidden cost, not the slowdown | analysis only |
| RQ5 rests on 5 runs, one cell | 10 more Haiku runs per cell (t3, t9 at 0.25 core, printed and quiet); correct for many tests | VM, ~1 h |
| Real tasks are short (26 s median) | 4 longer SWE-bench tasks (more turns, bigger test suites) at no limit, 1 CPU, 0.25 CPU | VM, ~3 h, task setup |
| One machine shape | Repeat the key curves on 8 vCPU: CPU quota (t3), threads, density | second VM, ~4 h + setup |
| Density is only numbers | Capacity model: agents per machine = cores / CPU per agent; check it on 4 and 8 vCPU | analysis + the 8 vCPU runs |
| Codex only in old data | Optional: new Codex runs on the main cells | your model choice and sign-in, by 11-16 |
| The cause-finding method (RQ6) | Keep or cut | your supervisor's answer, by 11-17 |

## Day by day

**Fri 11-14**
- Commit `phase2/`, `phase1/`, `collector/` to git.
- Start the `overhead` campaign on the VM.
- Set up a venv with matplotlib. Write the figure script.

**Sat 11-15**
- Start the RQ5 extra runs, then the longer real tasks.
- Fit and check the hidden-cost model on all RQ2 limits.
- Set up the ACM template in `paper-icpe/`, anonymized.

**Sun 11-16**
- Create the 8 vCPU VM (new VM, the old one stays). Run CPU, threads,
  density there.
- Last day to decide on Codex.
- Figures done for RQ1 to RQ4.

**Mon 11-17 to Wed 11-19**
- Analyze the new runs as they arrive.
- Write: introduction, background, method, RQ1 to RQ5, workshop
  replication, threats to validity, related work.
- Decide RQ6.

**Thu 11-20**
- Full draft to the supervisor.
- Stop both VMs (never delete).

**Fri 11-21**
- Apply the supervisor's comments. Language pass.
- Anonymized artifact: code, scripts, a small data sample, how to get the
  full data.

**Sat 11-22**
- Check every number in the paper against the result files (a script).
- Page limit, references, figure readability in black and white.
- Submit.

**Sun 11-23** buffer.

## Figures (planned)

1. Where the time goes: model, tools, start-up, system (RQ1).
2. Wall against local slowdown for every limit, with the model line
   (contribution 2).
3. One small panel per limit: slowdown against level (RQ2).
4. Real tasks at cloud settings (RQ3).
5. Agents per machine: time and throughput, 4 and 8 vCPU (RQ4).

## Cut list if time runs out (cut in this order)

1. Codex new runs.
2. RQ6 (one sentence in future work).
3. The 8 vCPU repeat (move to threats to validity).
4. The longer real tasks.

Never cut: overhead runs, the hidden-cost model, figures, anonymization.
