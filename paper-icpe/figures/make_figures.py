"""Paper figures (vector PDF, one column = 3.3 in wide).

    python paper-icpe/figures/make_figures.py     # -> paper-icpe/figures/*.pdf and *.png

Reads the result tables written by the RQ scripts; computes nothing new.
fig_timeline and fig_feedback read per-run tables from phase2/rev/fig_data.py.
Colors: validated categorical slots 1-4 (scripts/validate_palette.js, light,
all checks pass; slots 3 and 4 are under 3:1 contrast, so every series also
has its own marker and a legend or a direct label, which also keeps the
figures readable in black and white).
One encoding in every figure: wall = slot 1 (circle), local = slot 2 (square),
model wait = grey; machines M0 = slot 1 (circle), M1 = slot 3 (triangle),
M2 = slot 4 (diamond).
"""
import csv
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

P2 = Path(__file__).resolve().parents[2] / 'phase2'
OUT = Path(__file__).resolve().parent
C = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100']
INK, MUTED, GRID, WAIT = '#1f1f1e', '#6b6a64', '#e4e3df', '#c9c8c2'
MACH = {'M1': (C[2], '^', '2 vCPUs'), 'M0': (C[0], 'o', '4 vCPUs'), 'M2': (C[3], 'D', '8 vCPUs')}
KNEE = 1.10

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


def save(fig, name):
    fig.savefig(OUT / f'{name}.pdf')
    fig.savefig(OUT / f'{name}.png', dpi=180)
    plt.close(fig)


def fig_timeline():
    """One typical run with no limit and one at 0.25 core: the model wait keeps
    its length, the local parts stretch (rev/fig_timeline.csv)."""
    segs = defaultdict(list)
    for r in rows('rev/fig_timeline.csv'):
        segs[r['cond']].append((float(r['start']), float(r['dur']), r['kind']))
    fig, ax = plt.subplots(figsize=(3.3, 1.25))
    base = {k: sum(d for _, d, kk in segs['no limit'] if kk == k) for k in ('model', 'local')}
    for y, cond in enumerate(('no limit', '0.25 core')):
        tot = {k: sum(d for _, d, kk in segs[cond] if kk == k) for k in ('model', 'local')}
        for kind, col in (('model', WAIT), ('local', C[1])):
            ax.broken_barh([(a, d) for a, d, k in segs[cond] if k == kind], (y - 0.3, 0.6), color=col, linewidth=0)
        wall = tot['model'] + tot['local']
        note = f'{wall:.0f} s' if y == 0 else f'{wall:.0f} s  ({wall / (base["model"] + base["local"]):.1f}×)'
        ax.text(wall + 0.6, y, note, va='center', fontsize=6.5, color=INK)
        sub = f'local {tot["local"]:.0f} s' if y == 0 else f'local {tot["local"]:.0f} s  ({tot["local"] / base["local"]:.1f}×)'
        ax.text(0, y + 0.42, f'model wait {tot["model"]:.0f} s,  {sub}', va='top', fontsize=5.5, color=MUTED)
    ax.set_yticks([0, 1], ['no limit', '0.25 core'])
    ax.set(xlim=(0, 50), ylim=(1.75, -0.45), xlabel='time in the run (s)')
    ax.grid(axis='y', visible=False)
    ax.tick_params(axis='y', length=0)
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=WAIT), plt.Rectangle((0, 0), 1, 1, color=C[1])],
              labels=['waiting for the model', 'local (start-up, tools)'], ncol=2, loc='lower center',
              bbox_to_anchor=(0.45, 1.0), handlelength=1, columnspacing=1.0)
    fig.tight_layout(pad=0.4)
    save(fig, 'fig_timeline')


def fig_hidden():
    """Replay prediction from one unlimited run against measured wall slowdown,
    one point per cell with a CPU quota or read limit (rev/a1_cells.csv).
    Hollow: the model time changed by 2 s or more, so the agent did something else."""
    groups = {
        'M0, set 1': ([], C[0], 'o'),
        'M0, set 2': ([], C[1], 's'),
        'M1': ([], C[2], '^'),
        'M2': ([], C[3], 'D'),
    }
    name = {'M0 first pass': 'M0, set 1', 'M0 revision': 'M0, set 2', 'M1': 'M1', 'M2': 'M2'}
    design = []
    for r in rows('rev/a1_cells.csv'):
        p = (float(r['replay']), float(r['obs']), abs(float(r['d_model_s'] or 0)) >= 2)
        (design if r['role'] == 'design' else groups[name[r['set']]][0]).append(p)
    fig, ax = plt.subplots(figsize=(3.3, 2.6))
    lim = (0.8, 13)
    ax.plot(lim, lim, color=MUTED, lw=0.8, zorder=1)
    ax.fill_between(lim, [v * 0.9 for v in lim], [v * 1.1 for v in lim], color=GRID, lw=0, zorder=0)
    for g, (pts, col, mk) in groups.items():
        same = [(x, y) for x, y, ch in pts if not ch]
        moved = [(x, y) for x, y, ch in pts if ch]
        ax.scatter(*zip(*same), s=14, marker=mk, color=col, edgecolor='white', linewidth=0.5, label=f'{g} ({len(pts)})', zorder=3)
        if moved:
            ax.scatter(*zip(*moved), s=14, marker=mk, facecolor='white', edgecolor=col, linewidth=0.9, zorder=3)
    ax.scatter([x for x, *_ in design], [y for _, y, _ in design], s=14, marker='x', color=MUTED, linewidth=0.9,
               label=f'design settings ({len(design)})', zorder=3)
    ax.set(xscale='log', yscale='log', xlim=lim, ylim=lim,
           xlabel='predicted wall slowdown (replay)',
           ylabel='measured wall slowdown')
    ticks = [1, 1.5, 2, 3, 5, 10]
    ax.set_xticks(ticks, [str(t) for t in ticks])
    ax.set_yticks(ticks, [str(t) for t in ticks])
    ax.minorticks_off()
    h, lab = ax.get_legend_handles_labels()
    h.append(Line2D([], [], marker='o', ls='', markerfacecolor='white', markeredgecolor=MUTED, markersize=3.6))
    lab.append('hollow: model time changed')
    ax.legend(h, lab, loc='lower right', handletextpad=0.3, borderaxespad=0.2)
    ax.text(5.6, 7.4, '±10%', color=MUTED, ha='right', fontsize=6)
    fig.tight_layout(pad=0.4)
    save(fig, 'fig_hidden')


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
    """Five panels: wall and local slowdown against the limit level (set 1), with the
    breaking point marked. Sixth panel: share of runs in which the agent aborts under
    a process limit, on three machine sizes (rev/machines.csv)."""
    panels = [
        ('cpu', 't3_implement', 'CPU quota (cores)', 'smooth', True),
        ('disk', 't8_ioread', 'disk read limit (MB/s)', 'smooth', True),
        ('threads', 't4_parallel', 'workers on 4 vCPUs', 'smooth', False),
        ('memory_soft', 't6_memtouch', 'soft memory limit (MB)', 'cliff', True),
        ('e2e_disk', 't3_implement', 'coding task, disk (MB/s)', 'smooth', True),
    ]
    data = rows('rq2/curves.csv')
    fig, axs = plt.subplots(2, 3, figsize=(7.0, 3.6))
    for ax, (exp, task, title, shape, reverse) in zip(axs.flat, panels):
        cells = [r for r in data if r['experiment'] == exp and r['task'] == task and r['model'] == 'opus-5-5']
        pts = sorted((level_x(exp, r['level']), r) for r in cells if level_x(exp, r['level']) is not None)
        xs = [p[0] for p in pts]
        for key, lo, hi, col, mk, lab in (('slowdown', 'ci_lo', 'ci_hi', C[0], 'o', 'wall (what the user waits)'),
                                          ('local_slowdown', 'local_ci_lo', 'local_ci_hi', C[1], 's', 'local (wall minus model wait)')):
            ys = [float(p[1][key]) for p in pts]
            err = [[y - float(p[1][lo]) for y, p in zip(ys, pts)], [float(p[1][hi]) - y for y, p in zip(ys, pts)]]
            ax.errorbar(xs, ys, yerr=err, color=col, marker=mk, capsize=1.5, elinewidth=0.7, label=lab)
        loose_first = pts[::-1] if reverse else pts
        knee = next((x for x, r in loose_first if float(r['local_ci_lo']) > KNEE), None)
        if knee is not None:   # breaking point: loosest level whose local interval lies above 1.10
            ax.axvline(knee, color=INK, lw=0.6, ls=':')
            left = exp == 'memory_soft'   # keep the label off the curve
            ax.annotate('breaking\npoint', (knee, 1), xycoords=('data', 'axes fraction'), xytext=(-3 if left else 3, -2),
                        textcoords='offset points', ha='right' if left else 'left', va='top', fontsize=5.5, color=INK)
        for x, r in pts:   # runs that aborted or were killed
            if int(r['failed']):
                ax.annotate(f"{r['failed']}/{r['n']} failed", (x, float(r['local_slowdown'])),
                            textcoords='offset points', xytext=(0, 6), ha='center', fontsize=5.5, color=MUTED)
        ax.axhline(1, color=MUTED, lw=0.6)
        ax.set_title(title, loc='left')
        ax.set_title(shape, loc='right', color=MUTED, fontstyle='italic')
        if reverse:
            ax.invert_xaxis()
        if exp == 'threads':
            ax.set_xscale('log', base=2)
            ax.set_xticks(xs, [str(int(x)) for x in xs])
        ax.minorticks_off()
    axs[0, 0].set_ylabel('slowdown vs no limit')
    axs[1, 0].set_ylabel('slowdown vs no limit')

    # process limit: the crash, on three machine sizes
    ax = axs[1, 2]
    agg = defaultdict(lambda: [0, 0])
    for r in rows('rev/machines.csv'):
        lim = json.loads(r['level']) if r['experiment'].startswith('Process limit') else {}
        if 'pids_max' in lim:
            a = agg[(r['machine'].split()[0], lim['pids_max'])]
            a[0] += int(r['abnormal_exit'])
            a[1] += int(r['n'])
    for m, (col, mk, lab) in MACH.items():
        pts = sorted((x, 100 * k / n) for (mm, x), (k, n) in agg.items() if mm == m)
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, marker=mk, label=lab)
    ax.set_xscale('log', base=2)
    ax.set_xticks([8, 12, 16, 24, 32, 48, 64], ['8', '12', '16', '24', '32', '48', '64'])
    ax.invert_xaxis()
    ax.minorticks_off()
    ax.set(ylim=(-5, 105), ylabel='agent aborts (% of runs)')
    ax.set_title('process limit', loc='left')
    ax.set_title('crash', loc='right', color=MUTED, fontstyle='italic')
    ax.legend(loc='center left', title='machine', title_fontsize=6.5)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.legend(*axs[0, 0].get_legend_handles_labels(), loc='upper center', ncol=2, handlelength=2.2, columnspacing=2.0)
    save(fig, 'fig_limits')


def fig_density():
    """Many agents on one machine, on three machine sizes (rev/a11.csv). Both axes are
    per vCPU, so the machines fall on one curve. Dashed: the capacity computed from the
    CPU time of one agent alone."""
    sets = {'M1': 'M1', 'M0 revision': 'M0', 'M2': 'M2'}
    data = defaultdict(list)
    for r in rows('rev/a11.csv'):
        if r['set'] in sets:
            v = int(r['vcpu'])
            data[sets[r['set']]].append((int(r['n']) / v, float(r['agents_per_min']) / v, float(r['cpu_s_per_agent']),
                                         float(r['naive_capacity']) / v))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(3.3, 2.0))
    naive = []
    for m, (col, mk, lab) in MACH.items():
        pts = sorted(data[m])
        a1.plot([p[0] for p in pts], [p[1] for p in pts], color=col, marker=mk, label=lab)
        a2.plot([p[0] for p in pts], [p[2] for p in pts], color=col, marker=mk)
        naive.append(pts[0][3])
    a1.axhline(statistics.mean(naive), color=MUTED, lw=0.8, ls='--')
    a1.text(0.14, statistics.mean(naive) - 0.5, 'estimate from\none agent alone', fontsize=5.5, color=MUTED, va='top')
    a1.set(ylabel='agents per minute per vCPU', xlabel='agents per vCPU', ylim=(0, 11.5))
    a2.set(ylabel='CPU seconds per agent', xlabel='agents per vCPU', ylim=(0, 14.5))
    for a in (a1, a2):
        a.set_xscale('log', base=2)
        a.set_xticks([0.125, 0.5, 2, 8], ['1/8', '1/2', '2', '8'])
        a.axvline(4, color=INK, lw=0.6, ls=':')
        a.minorticks_off()
    a2.text(3.6, 1.0, 'full at 4\nper vCPU', fontsize=5.5, color=INK, ha='right')
    fig.tight_layout(rect=(0, 0, 1, 0.9), pad=0.4)
    fig.legend(*a1.get_legend_handles_labels(), loc='upper center', ncol=3, handlelength=1.8, columnspacing=1.2)
    save(fig, 'fig_density')


def fig_states():
    """Where the threads of the agent's group spend their time, from the kernel trace
    (set 1, Opus, medians; rq1/runs.csv). Thread time adds up over threads, so it can
    be longer than the wall time."""
    f = lambda r, k: float(r[k] or 0)
    states = [('running', lambda r: f(r, 'on_cpu_s'), MUTED),
              ('waiting: CPU quota', lambda r: f(r, 'wait_cpu_quota_s'), C[1]),
              ('waiting: busy core', lambda r: f(r, 'wait_cpu_busy_s'), C[3]),
              ('waiting: disk', lambda r: f(r, 'wait_disk_s') + f(r, 'wait_d_other_s') + f(r, 'reclaim_s'), C[2])]
    q = lambda v: json.dumps({'cpu_max': f'{v} 100000'})
    io = lambda mb: json.dumps({'io_max': {'rbps': mb * 1048576}})
    mh = lambda mb: json.dumps({'memory_high': f'{mb}M'})
    panels = [   # title, campaign, task, [(label, limits or None, task_arg or None)]
        ('CPU quota (cores)', 'cpu', 't3_implement',
         [('none', '', None), ('0.75', q(75000), None), ('0.5', q(50000), None), ('0.25', q(25000), None)]),
        ('workers on 4 vCPUs', 'threads', 't4_parallel', [(str(w), None, str(w)) for w in (2, 4, 8, 16)]),
        ('disk read limit (MB/s)', 'disk', 't8_ioread',
         [('none', '', None), ('100', io(100), None), ('50', io(50), None), ('20', io(20), None)]),
        ('soft memory limit (MB)', 'memory_soft', 't6_memtouch',
         [('none', '', None), ('1344', mh(1344), None), ('1152', mh(1152), None), ('768', mh(768), None)]),
    ]
    runs = [r for r in rows('rq1/runs.csv') if r['model'].endswith('opus-5-5')]
    fig, axs = plt.subplots(2, 2, figsize=(3.3, 2.5))
    for ax, (title, camp, task, levels) in zip(axs.flat, panels):
        for y, (label, lim, arg) in enumerate(levels):
            sel = [r for r in runs if r['campaign'] == camp and r['task'] == task
                   and (lim is None or r['limits'] == lim) and (arg is None or r['task_arg'] == arg)]
            assert sel, (camp, label)
            left = 0
            for name, fn, col in states:
                w = statistics.median(fn(r) for r in sel)
                ax.barh(y, w, left=left, color=col, edgecolor='white', linewidth=0.5, height=0.7,
                        label=name if y == 0 else None)
                left += w
        ax.set_yticks(range(len(levels)), [l[0] for l in levels])
        ax.invert_yaxis()
        ax.set_title(title, loc='left')
        ax.grid(axis='y', visible=False)
        ax.tick_params(axis='y', length=0)
    for ax in axs[1]:
        ax.set_xlabel('thread time (s)')
    fig.tight_layout(rect=(0, 0, 1, 0.86), pad=0.4)
    fig.legend(*axs[0, 0].get_legend_handles_labels(), loc='upper center', ncol=2, handlelength=1, columnspacing=1.0)
    save(fig, 'fig_states')


def fig_feedback():
    """RQ5 controls, Haiku, set 2: every run as a dot, median as a bar (rev/fig_feedback.csv)."""
    g = defaultdict(list)
    for r in rows('rev/fig_feedback.csv'):
        g[(r['limit'], r['label'])].append((int(r['after']), float(r['wall'])))
    order = [('0.25 core', 'time printed'), ('0.25 core', 'no time printed'), ('0.25 core', 'fixed fast time printed'),
             ('0.25 core', 'time printed + "not a goal"'), ('no limit', 'time printed'),
             ('no limit', 'fixed slow time printed')]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(3.3, 1.9), sharey=True, gridspec_kw={'width_ratios': [1, 1.25]})
    for y, k in enumerate(order):
        col = C[1] if y == 0 else MUTED
        for ax, i in ((a1, 0), (a2, 1)):
            v = [p[i] for p in g[k]]
            jit = [y + 0.26 * ((j * 0.618) % 1 - 0.5) for j in range(len(v))]   # fixed jitter, no random numbers
            ax.scatter(v, jit, s=5, color=col, alpha=0.55, linewidth=0, zorder=3)
            ax.plot([statistics.median(v)] * 2, [y - 0.32, y + 0.32], color=INK, lw=1.3, zorder=4)
    a1.set_yticks(range(len(order)), [k[1] for k in order])
    a1.set(ylim=(len(order) - 0.5, -0.5), xlabel='tool calls after\nthe tests pass')
    a2.set(xlabel='wall time (s)', xlim=(0, None))
    for ax in (a1, a2):
        ax.grid(axis='y', visible=False)
        ax.axhline(3.5, color=MUTED, lw=0.5)
        ax.tick_params(axis='y', length=0)
    a2.text(1.0, 0.99, '0.25 core', transform=a2.transAxes, ha='right', va='top', fontsize=5.5, color=MUTED)
    a2.text(1.0, 0.30, 'no limit', transform=a2.transAxes, ha='right', va='top', fontsize=5.5, color=MUTED)
    fig.tight_layout(pad=0.4)
    save(fig, 'fig_feedback')


def fig_split():
    """RQ1: mean share of wall time per part, runs with no limit."""
    runs = [r for r in rows('rq1/runs.csv') if r['unlimited'] == 'True']
    groups = [('t2, Opus', 'claude-opus-5-5', 't2_medium', None),
              ('t3, Opus', 'claude-opus-5-5', 't3_implement', None),
              ('t3, Haiku', 'claude-haiku-5-5', 't3_implement', None),
              ('t3, Fable', 'claude-fable-5-1', 't3_implement', None)]
    for proj in ('django', 'sympy', 'pydata', 'pytest-dev', 'pallets', 'psf'):
        label = {'pydata': 'xarray', 'pytest-dev': 'pytest', 'pallets': 'flask', 'psf': 'requests'}.get(proj, proj)
        groups.append((f'{label} (real)', 'claude-opus-5-5', 'swe', proj))
    # model wait is grey and local parts are warm, as in fig_timeline
    parts = [('start-up', ['startup_s'], C[3]), ('model wait', ['model_only_s', 'model_tool_s'], WAIT),
             ('tools', ['tool_only_s'], C[1]), ('other', ['agent_only_s', 'shutdown_s'], MUTED)]
    f = lambda r, k: float(r[k] or 0)
    fig, ax = plt.subplots(figsize=(3.3, 2.3))
    for y, (label, model, task, proj) in enumerate(groups):
        sel = [r for r in runs if r['model'] == model and r['task'] == task
               and (proj is None or (r['campaign'] == 'real' and r['task_arg'].startswith(proj + '__')))]
        left = 0
        for name, ks, col in parts:
            w = 100 * statistics.mean(sum(f(r, k) for k in ks) / f(r, 'wall_s') for r in sel)
            ax.barh(y, w, left=left, color=col, edgecolor='white', linewidth=0.8, height=0.7,
                    label=name if y == 0 else None)
            if name == 'model wait':
                ax.text(left + w / 2, y, f'{w:.0f}%', ha='center', va='center', fontsize=5.5, color=INK)
            left += w
        ax.text(101, y, f'{statistics.median(f(r, "wall_s") for r in sel):.0f} s', va='center', fontsize=5.5, color=MUTED)
    ax.set_yticks(range(len(groups)), [g[0] for g in groups])
    ax.invert_yaxis()
    ax.axhline(3.5, color=MUTED, lw=0.5)
    ax.set(xlim=(0, 100), xlabel='share of wall time (%)')
    ax.grid(axis='y', visible=False)
    ax.legend(ncol=4, loc='lower center', bbox_to_anchor=(0.45, 1.0), handlelength=1, columnspacing=0.8)
    fig.tight_layout()
    save(fig, 'fig_split')


if __name__ == '__main__':
    for f in (fig_timeline, fig_split, fig_limits, fig_states, fig_hidden, fig_density, fig_feedback):
        f()
    print('wrote', ', '.join(p.name for p in sorted(OUT.glob('*.pdf'))))
