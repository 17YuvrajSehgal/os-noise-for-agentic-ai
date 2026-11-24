#!/usr/bin/env python3
"""Review issue 4: does the cost of the full kernel trace change under limits?

t3 (Opus) with no trace and with the full trace, at 0.25 core, at memory.max
192 MB (r_overhead), and with 8 agents at once (r_overhead_density). The
unlimited pair comes from the first pass (overhead campaign). Per cell: wall
and group CPU seconds (sampler), full / none ratio with a 95% bootstrap
interval.

  python rev/overhead.py   -> rev/overhead.txt
"""
import json, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import FIRST, REV, boot_ratio, lim_key   # noqa: E402


def rec(run):
    spec = json.loads((run / 'spec.json').read_text())
    res = json.loads((run / 'result.json').read_text())
    s = [json.loads(l) for l in open(run / 'samples.jsonl')]
    cpu = (s[-1]['group']['cpu_usage_usec'] - s[0]['group']['cpu_usage_usec']) / 1e6
    return spec, res['wall_s'], cpu, res['ok']


lines = []
for title, root, camp, task in (('no limit (first pass)', FIRST, 'overhead', 't3_implement'),
                                ('limits (revision)', REV, 'r_overhead', 't3_implement'),
                                ('8 agents at once (revision)', REV, 'r_overhead_density', 't3_implement')):
    cells = defaultdict(lambda: defaultdict(list))
    for sp in sorted((root / camp).glob('*/spec.json')):
        spec, wall, cpu, ok = rec(sp.parent)
        if spec['task'].replace('.sh', '') != task or spec.get('agent', 'claude') != 'claude':
            continue
        cells[(lim_key(spec), spec.get('agents', 1))][spec.get('trace', 'full')].append((wall, cpu, ok))
    lines.append(f'\n== {title}')
    lines.append(f"{'limit':34}{'agents':>7}{'n':>6}{'wall none':>10}{'wall full':>10}{'full/none [95%]':>20}"
                 f"{'CPU none':>9}{'CPU full':>9}{'full/none [95%]':>20}{'solved':>8}")
    for (lim, n), t in sorted(cells.items()):
        if 'none' not in t or 'full' not in t:
            continue
        a, b = t['full'], t['none']
        w = boot_ratio([x[0] for x in a], [x[0] for x in b])
        c = boot_ratio([x[1] for x in a], [x[1] for x in b])
        wr = st.median(x[0] for x in a) / st.median(x[0] for x in b)
        cr = st.median(x[1] for x in a) / st.median(x[1] for x in b)
        lines.append(f'{lim[:33]:34}{n:>7}{len(b):>3}/{len(a):<2}{st.median(x[0] for x in b):>10.1f}{st.median(x[0] for x in a):>10.1f}'
                     f'{wr:>8.2f} [{w[0]:.2f}-{w[1]:.2f}]{st.median(x[1] for x in b):>9.1f}{st.median(x[1] for x in a):>9.1f}'
                     f'{cr:>8.2f} [{c[0]:.2f}-{c[1]:.2f}]{sum(x[2] for x in a + b):>5}/{len(a + b)}')
(HERE / 'overhead.txt').write_text('\n'.join(lines).lstrip() + '\n')
print('\n'.join(lines))
