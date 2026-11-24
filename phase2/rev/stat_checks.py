#!/usr/bin/env python3
"""Checks asked for by the method papers (review notes, items 2-4). No new runs.

  2. Coverage: with 5 runs per side, how often does the 95% bootstrap interval
     of a local slowdown hold the value from all runs, and how often does the
     breaking-point verdict (interval above 1.10) agree with the one from all
     runs? Uses the 15-run CPU cells of set 2 and the 10-run real-task cells.
  3. A/A test: split the unlimited runs of one campaign into two random halves
     and count how often the rule calls one half slower (interval above 1.10).
  4. Drift: Spearman correlation of unlimited local and wall time with the start
     time of the run, per campaign.

  python rev/stat_checks.py   -> rev/stat_checks.txt
"""
import json, random, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import FIRST, REV, load, boot_ratio   # noqa: E402

KNEE, NOLIM, SUB, BOOT = 1.10, '{}', 400, 1000
rng = random.Random(11)
out = []


def p(*a):
    out.append(' '.join(str(x) for x in a))
    print(*a)


def cells(root, camp):
    g = defaultdict(list)
    for r in load(root, camp):
        if r['local'] is not None:
            g[(r['task'], r['task_arg'], r['model'], r['limits'])].append(r)
    return g


def start(root, camp, run):
    with open(Path(root) / camp / run / 'samples.jsonl') as f:
        return json.loads(f.readline())['realtime']


def spearman(x, y):
    rank = lambda v: {i: r for r, i in enumerate(sorted(range(len(v)), key=v.__getitem__))}
    rx, ry = rank(x), rank(y)
    n = len(x)
    return 1 - 6 * sum((rx[i] - ry[i]) ** 2 for i in range(n)) / (n * (n * n - 1))


def perm_p(x, y, n=2000):
    """Two-sided permutation p-value of the Spearman correlation."""
    r0 = abs(spearman(x, y))
    y = list(y)
    hits = 0
    for _ in range(n):
        rng.shuffle(y)
        hits += abs(spearman(x, y)) >= r0
    return (hits + 1) / (n + 1)


# --- 2. coverage and verdict stability with 5 runs ------------------------------------
p('== 2. Five runs per side, subsampled from cells with 10-15 runs (local slowdown)')
p(f'{"cell":<52}{"n":>4}{"all-run ratio":>14}{"verdict":>9}{"covered":>9}{"same verdict":>13}')
tot_cov = tot_same = tot = 0
for camp in ('r_cpu', 'r_real'):
    g = cells(REV, camp)
    for key, runs in sorted(g.items()):
        if key[3] == NOLIM:
            continue
        base = g.get(key[:3] + (NOLIM,))
        if not base or len(runs) < 10 or len(base) < 10:
            continue
        a, b = [r['local'] for r in runs], [r['local'] for r in base]
        ref = st.median(a) / st.median(b)
        v_all = boot_ratio(a, b)[0] > KNEE
        cov = same = 0
        for i in range(SUB):
            sa, sb = rng.sample(a, 5), rng.sample(b, 5)
            lo, hi = boot_ratio(sa, sb, n=BOOT, seed=i)
            cov += lo <= ref <= hi
            same += (lo > KNEE) == v_all
        tot_cov, tot_same, tot = tot_cov + cov, tot_same + same, tot + SUB
        name = f'{camp} {key[1] or key[0]} {key[3]}'[:51]
        p(f'{name:<52}{len(a):>4}{ref:>14.2f}{"break" if v_all else "-":>9}{cov / SUB:>9.2f}{same / SUB:>13.2f}')
p(f'overall: interval holds the all-run value in {tot_cov / tot:.2f} of subsamples; verdict agrees in {tot_same / tot:.2f}')

# --- 3. A/A test ------------------------------------------------------------------------
p('\n== 3. A/A test: unlimited runs split into random halves (local and wall)')
p(f'{"campaign / cell":<52}{"n":>4}{"local fires":>12}{"wall fires":>11}')
aa_l = aa_w = aa_n = 0
for root, camps in ((FIRST, ('cpu', 'real')), (REV, ('r_cpu', 'r_real', 'r_pids', 'm1_cpu', 'm2_cpu',
                                                      'm1_real', 'm2_real', 'r_overhead'))):
    for camp in camps:
        for key, runs in sorted(cells(root, camp).items()):
            if key[3] != NOLIM or len(runs) < 6:
                continue
            fl = fw = 0
            for i in range(SUB):
                rs = runs[:]
                rng.shuffle(rs)
                h = len(rs) // 2
                x, y = rs[:h], rs[h:2 * h]
                fl += boot_ratio([r['local'] for r in x], [r['local'] for r in y], n=BOOT, seed=i)[0] > KNEE
                fw += boot_ratio([r['wall'] for r in x], [r['wall'] for r in y], n=BOOT, seed=i)[0] > KNEE
            aa_l, aa_w, aa_n = aa_l + fl, aa_w + fw, aa_n + SUB
            name = f'{camp} {key[1] or key[0]} {key[2]}'[:51]
            p(f'{name:<52}{len(runs):>4}{fl / SUB:>12.3f}{fw / SUB:>11.3f}')
p(f'overall false "slower" rate: local {aa_l / aa_n:.3f}, wall {aa_w / aa_n:.3f} '
  f'(one direction; the rule would also fire for the other half at about the same rate)')

# --- 4. drift with run order -------------------------------------------------------------
p('\n== 4. Drift: unlimited runs, Spearman correlation with start time (permutation p)')
p(f'{"campaign / cell":<52}{"n":>4}{"local rho":>10}{"p":>7}{"wall rho":>10}{"p":>7}{"span h":>8}')
ps = []
for root, camps in ((FIRST, ('cpu', 'real', 'pids')), (REV, ('r_cpu', 'r_real', 'r_pids', 'm1_cpu', 'm2_cpu',
                                                              'm1_real', 'm2_real'))):
    for camp in camps:
        for key, runs in sorted(cells(root, camp).items()):
            if key[3] != NOLIM or len(runs) < 6:
                continue
            t = [start(root, camp, r['run']) for r in runs]
            lr, lp = spearman(t, [r['local'] for r in runs]), perm_p(t, [r['local'] for r in runs])
            wr, wp = spearman(t, [r['wall'] for r in runs]), perm_p(t, [r['wall'] for r in runs])
            ps += [lp, wp]
            name = f'{camp} {key[1] or key[0]} {key[2]}'[:51]
            p(f'{name:<52}{len(runs):>4}{lr:>10.2f}{lp:>7.3f}{wr:>10.2f}{wp:>7.3f}{(max(t) - min(t)) / 3600:>8.1f}')
ps.sort()
m = len(ps)
holm = [min(1, max(ps[j] * (m - j) for j in range(i + 1))) for i in range(m)]
p(f'{m} tests; smallest p {ps[0]:.3f}; after Holm, {sum(h < 0.05 for h in holm)} below 0.05')

(HERE / 'stat_checks.txt').write_text('\n'.join(out) + '\n')
