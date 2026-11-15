"""Paper figures (vector PDF, one column = 3.3 in wide).

    ../.venv/Scripts/python figures/make_figures.py     # from phase2/ -> figures/*.pdf

Reads the result tables written by the RQ scripts; computes nothing new.
Colors: validated categorical slots 1-4 (scripts/validate_palette.js, light,
all checks pass; slots 3 and 4 are under 3:1 contrast, so every series also
has its own marker and a legend, which also keeps the figures readable in
black and white).
"""
import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

P2 = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
C = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100']
INK, MUTED, GRID = '#1f1f1e', '#6b6a64', '#e4e3df'

plt.rcParams.update({
    'font.size': 7.5, 'axes.titlesize': 7.5, 'axes.labelsize': 7.5,
    'xtick.labelsize': 6.5, 'ytick.labelsize': 6.5, 'legend.fontsize': 6.5,
    'axes.edgecolor': MUTED, 'axes.labelcolor': INK, 'xtick.color': MUTED, 'ytick.color': MUTED,
    'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.5,
    'axes.spines.top': False, 'axes.spines.right': False,
    'lines.linewidth': 1.2, 'lines.markersize': 4, 'pdf.fonttype': 42,
    'legend.frameon': False,
})


def rows(path):
    return list(csv.DictReader(open(P2 / path)))


def fig_hidden():
    """Measured against predicted wall slowdown, one point per limited cell."""
    groups = {
        'model time stable (<2 s)': ([], C[0], 'o'),
        'network limit': ([], C[1], 's'),
        'smaller model reacts (RQ5)': ([], C[2], '^'),
        'other, model time moved': ([], C[3], 'D'),
    }
    for r in rows('rq2/hidden.csv'):
        pt = (float(r['wall_pred']), float(r['wall_obs']))
        if abs(float(r['d_model_s'])) < 2:
            g = 'model time stable (<2 s)'
        elif r['experiment'] == 'network':
            g = 'network limit'
        elif r['model'] != 'opus-5-5':
            g = 'smaller model reacts (RQ5)'
        else:
            g = 'other, model time moved'
        groups[g][0].append(pt)
    fig, ax = plt.subplots(figsize=(3.3, 2.6))
    lim = (0.8, 5.2)
    ax.plot(lim, lim, color=MUTED, lw=0.8, zorder=1)
    ax.fill_between(lim, [v * 0.9 for v in lim], [v * 1.1 for v in lim], color=GRID, lw=0, zorder=0)
    for name, (pts, col, mk) in groups.items():
        if pts:
            ax.scatter(*zip(*pts), s=16, color=col, marker=mk, edgecolor='white', linewidth=0.6,
                       label=f'{name} ({len(pts)})', zorder=3)
    ax.set(xscale='log', yscale='log', xlim=lim, ylim=lim,
           xlabel='predicted wall slowdown, 1 + f (local slowdown - 1)',
           ylabel='measured wall slowdown')
    ticks = [1, 1.5, 2, 3, 4, 5]
    ax.set_xticks(ticks, [str(t) for t in ticks])
    ax.set_yticks(ticks, [str(t) for t in ticks])
    ax.minorticks_off()
    ax.legend(loc='upper left')
    ax.text(3.6, 3.05, '±10%', color=MUTED, ha='left', fontsize=6)
    fig.tight_layout()
    fig.savefig(OUT / 'fig_hidden.pdf')


def level_x(exp, level):
    if level == 'none':
        return None
    if exp == 'cpu':
        return int(level.split('=')[1].split()[0]) / 100000
    if exp in ('disk', 'e2e_disk'):
        return int(re.search(r'(\d+)\}', level).group(1)) / 1048576
    if exp.startswith('memory') or exp == 'e2e_memory':
        v = level.split('=')[1]
        return 2048 if v == '2G' else int(v.rstrip('M'))
    if exp == 'pids':
        return int(level.split('=')[1])
    if exp == 'threads':
        return int(level.split()[0])


def fig_limits():
    """One panel per limit: wall and local slowdown against the limit level."""
    panels = [
        ('cpu', 't3_implement', 'CPU quota (cores)', True),
        ('disk', 't8_ioread', 'disk read limit (MB/s)', True),
        ('memory_soft', 't6_memtouch', 'soft memory limit (MB)', True),
        ('threads', 't4_parallel', 'workers on 4 vCPUs', False),
        ('e2e_disk', 't3_implement', 'disk limit, coding task (MB/s)', True),
        ('pids', 't3_implement', 'process limit', True),
    ]
    data = rows('rq2/curves.csv')
    fig, axs = plt.subplots(2, 3, figsize=(7.0, 3.6))
    for ax, (exp, task, title, reverse) in zip(axs.flat, panels):
        cells = [r for r in data if r['experiment'] == exp and r['task'] == task and r['model'] == 'opus-5-5']
        pts = sorted((level_x(exp, r['level']), r) for r in cells if level_x(exp, r['level']) is not None)
        if exp == 'pids':   # 16 and below abort in seconds; their ratio is not a slowdown
            pts = [p for p in pts if p[0] >= 17]
            ax.text(0.03, 0.08, '16 and below:' + chr(10) + 'the agent aborts', transform=ax.transAxes,
                    ha='left', va='bottom', fontsize=5.5, color=MUTED)
        xs = [p[0] for p in pts]
        for key, lo, hi, col, mk, lab in (('slowdown', 'ci_lo', 'ci_hi', C[0], 'o', 'wall'),
                                          ('local_slowdown', 'local_ci_lo', 'local_ci_hi', C[1], 's', 'local')):
            ys = [float(p[1][key]) for p in pts]
            err = [[y - float(p[1][lo]) for y, p in zip(ys, pts)], [float(p[1][hi]) - y for y, p in zip(ys, pts)]]
            ax.errorbar(xs, ys, yerr=err, color=col, marker=mk, capsize=1.5, elinewidth=0.7, label=lab)
        for x, r in pts:   # runs that aborted or were killed
            if int(r['failed']) and exp != 'pids':
                ax.annotate(f"{r['failed']}/{r['n']} failed", (x, float(r['local_slowdown'])),
                            textcoords='offset points', xytext=(0, 6), ha='center', fontsize=5.5, color=MUTED)
        ax.axhline(1, color=MUTED, lw=0.6)
        ax.set_title(title, loc='left')
        if reverse:
            ax.invert_xaxis()
        if exp in ('threads', 'pids'):
            ax.set_xscale('log', base=2)
            tk = xs if exp == 'threads' else [17, 20, 24, 32, 48, 64]
            ax.set_xticks(tk, [str(int(x)) for x in tk])
        ax.minorticks_off()
    axs[0, 0].set_ylabel('slowdown vs no limit')
    axs[1, 0].set_ylabel('slowdown vs no limit')
    axs[0, 0].legend(loc='upper left')
    fig.tight_layout()
    fig.savefig(OUT / 'fig_limits.pdf')


def fig_density():
    """Agents sharing one 4 vCPU machine: time per agent and agents finished per minute."""
    by_run = defaultdict(list)
    n_of = {}
    for r in rows('rq4/agents.csv'):
        by_run[r['run']].append(float(r['wall_s']))
        n_of[r['run']] = int(r['n_agents'])
    per_n = defaultdict(lambda: ([], []))
    for run, walls in by_run.items():
        n = n_of[run]
        per_n[n][0].append(statistics.median(walls))
        per_n[n][1].append(60 * n / max(walls))
    ns = sorted(per_n)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(3.3, 1.7))
    a1.plot(ns, [statistics.median(per_n[n][0]) for n in ns], color=C[0], marker='o')
    a1.set(ylabel='time per agent (s)', xlabel='agents')
    a2.plot(ns, [statistics.median(per_n[n][1]) for n in ns], color=C[0], marker='o')
    a2.set(ylabel='agents done per minute', xlabel='agents')
    for a in (a1, a2):
        a.set_xscale('log', base=2)
        a.set_xticks(ns, [str(n) for n in ns])
        a.axvline(4, color=MUTED, lw=0.6, ls=':')
        a.minorticks_off()
    a1.text(4.3, a1.get_ylim()[1] * 0.92, '= vCPUs', color=MUTED, fontsize=5.5)
    fig.tight_layout()
    fig.savefig(OUT / 'fig_density.pdf')


if __name__ == '__main__':
    fig_hidden()
    fig_limits()
    fig_density()
    print('wrote', ', '.join(p.name for p in sorted(OUT.glob('*.pdf'))))
