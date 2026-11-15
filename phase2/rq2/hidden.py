"""Hidden-cost model: does the local slowdown predict the wall slowdown?

    wall slowdown = 1 + f * (local slowdown - 1),   f = local / wall at baseline

It holds when the model time does not change. A cell that misses it is one
where the model time changed (network, the agent reacting, killed runs).

    python rq2/hidden.py          # -> rq2/hidden.txt, rq2/hidden.csv
"""
import csv
import statistics
from pathlib import Path

HERE = Path(__file__).parent
rows = list(csv.DictReader(open(HERE / 'curves.csv')))

base = {}
for r in rows:
    if float(r['slowdown']) == 1.0 and float(r['ci_lo']) == 1.0 and float(r['ci_hi']) == 1.0:
        base[(r['experiment'], r['model'], r['task'])] = r

out = []
for r in rows:
    b = base.get((r['experiment'], r['model'], r['task']))
    if b is None or r is b or int(r['failed']):
        continue
    f = float(b['local_med']) / float(b['wall_med'])
    pred = 1 + f * (float(r['local_slowdown']) - 1)
    obs = float(r['slowdown'])
    out.append(dict(experiment=r['experiment'], model=r['model'], task=r['task'], level=r['level'],
                    f=round(f, 2), local=float(r['local_slowdown']), wall_obs=obs,
                    wall_pred=round(pred, 3), err=round((pred - obs) / obs, 3),
                    d_model_s=float(r['d_model_s'])))

with open(HERE / 'hidden.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0]))
    w.writeheader()
    w.writerows(out)

lines = [f"{'experiment':16} {'model':10} {'task':14} {'level':28} {'f':>5} {'local':>6} "
         f"{'wall':>6} {'pred':>6} {'err':>6} {'dModel':>7}"]
for o in out:
    lines.append(f"{o['experiment']:16} {o['model']:10} {o['task']:14} {o['level'][:28]:28} {o['f']:5.2f} "
                 f"{o['local']:6.2f} {o['wall_obs']:6.2f} {o['wall_pred']:6.2f} {o['err']:+6.1%} {o['d_model_s']:+7.1f}")
errs = [abs(o['err']) for o in out]
stable = [abs(o['err']) for o in out if abs(o['d_model_s']) < 2]
lines += ['', f'cells {len(out)}: median |err| {statistics.median(errs):.1%}, '
              f'within 10% {sum(e <= .10 for e in errs)}/{len(errs)}',
          f'cells where model time moved < 2 s: {len(stable)}, median |err| {statistics.median(stable):.1%}, '
          f'within 10% {sum(e <= .10 for e in stable)}/{len(stable)}']
(HERE / 'hidden.txt').write_text('\n'.join(lines) + '\n')
print('\n'.join(lines))
