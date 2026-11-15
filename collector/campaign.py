#!/usr/bin/env python3
"""Run a whole experiment: every cell of a grid, several repetitions, in
random order.

  python3 campaign.py campaigns/cpu.json [--out RUNS_DIR] [--dry-run] [--list]

A campaign file (JSON):
  name      prefix of every run name
  reps      repetitions per cell
  seed      seed of the shuffle (the order is reproducible)
  base      spec keys shared by all runs (see collect.py SPEC_DEFAULTS)
  grid      {key: [values]}; one cell per combination. A dotted key reaches
            into a nested spec key, e.g. "limits.cpu_max"
  cells     optional explicit list of partial specs, used instead of grid
  cooldown_s  pause between runs (default 10)

The model of each agent is pinned in campaigns/models.json. A campaign can
name another model with a "model" key in base or grid.

Random order keeps time-of-day and model drift from lining up with one
condition. Resumable: a run whose folder already has result.json is skipped,
and a folder without one (an interrupted run) is removed and run again.
"""
import argparse, copy, itertools, json, random, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from collect import fill_spec

# the model each agent uses unless a campaign names another one
MODELS = json.loads((HERE / 'campaigns' / 'models.json').read_text())


def set_dotted(d, key, value):
    *path, last = key.split('.')
    for p in path:
        if d.get(p) is None:
            d[p] = {}
        d = d[p]
    d[last] = value


def label(value):
    """A short, file-name-safe label for one grid value."""
    if isinstance(value, dict):
        return '-'.join(f'{k}{label(v)}' for k, v in value.items()) or 'on'
    s = str(value)
    for a, b in ((' 100000', ''), ('.sh', ''), (' ', ''), ('/', ''), ('None', 'none')):
        s = s.replace(a, b)
    return s


def plan(camp):
    """-> list of full specs, shuffled with the campaign seed."""
    if camp.get('cells'):
        cells = [(c, '_'.join(label(v) for v in c.values())) for c in camp['cells']]
    else:
        keys = list(camp['grid'])
        cells = [(dict(zip(keys, combo)), '_'.join(label(v) for v in combo))
                 for combo in itertools.product(*(camp['grid'][k] for k in keys))]
    specs = []
    for cell, tag in cells:
        for rep in range(1, camp.get('reps', 5) + 1):
            raw = copy.deepcopy(camp.get('base', {}))
            for k, v in cell.items():
                set_dotted(raw, k, copy.deepcopy(v))
            raw['run'] = f"{camp['name']}_{tag}_r{rep}"
            spec = fill_spec(raw)
            if spec['model'] is None:              # pin the model, so an agent update cannot change it
                spec['model'] = MODELS.get(spec['agent'])
            specs.append(spec)
    names = [s['run'] for s in specs]
    if len(set(names)) != len(names):
        raise ValueError('two cells produce the same run name; make the grid values distinct')
    random.Random(camp.get('seed', 1)).shuffle(specs)
    return specs


MAX_SILENT = 4      # stop after this many runs in a row with no model answer


def model_answered(run_dir):
    """Did any agent of this run get at least one message back from the model?"""
    for f in Path(run_dir).glob('a*/events.jsonl'):
        for line in open(f):
            try:
                ev = json.loads(json.loads(line)['line'])
            except (ValueError, KeyError):
                continue
            if isinstance(ev, dict) and (ev.get('type') == 'assistant' or str(ev.get('type', '')).startswith('item')):
                return True
    return False


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('campaign')
    ap.add_argument('--out', default=str(Path.home() / 'osn-runs'))
    ap.add_argument('--dry-run', action='store_true', help='pass --dry-run to every run')
    ap.add_argument('--list', action='store_true', help='print the planned runs and stop')
    ap.add_argument('--agent', help='run only this agent (the order of the other runs is unchanged)')
    args = ap.parse_args()
    camp = json.loads(Path(args.campaign).read_text())
    try:
        specs = plan(camp)
    except ValueError as e:
        sys.exit(f'bad campaign: {e}')
    if args.agent:
        specs = [s for s in specs if s['agent'] == args.agent]
    out = Path(args.out) / camp['name']
    if args.list:
        for i, s in enumerate(specs, 1):
            print(f'{i:4d}  {s["run"]}')
        print(f'{len(specs)} runs -> {out}')
        sys.exit(0)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'campaign.json').write_text(json.dumps(camp, indent=1))
    silent = 0
    for i, spec in enumerate(specs, 1):
        run_dir = out / spec['run']
        if (run_dir / 'result.json').exists():
            print(f'[{i}/{len(specs)}] skip {spec["run"]} (done)')
            continue
        if run_dir.exists():                       # interrupted run: start it again from nothing
            subprocess.run(['sudo', '-n', 'rm', '-rf', str(run_dir)], check=True)
        spec_file = out / f'.{spec["run"]}.spec.json'
        spec_file.write_text(json.dumps(spec))
        print(f'[{i}/{len(specs)}] === {spec["run"]} ===', flush=True)
        t0 = time.time()
        rc = subprocess.run([sys.executable, str(HERE / 'collect.py'), str(spec_file), '--out', str(out)]
                            + (['--dry-run'] if args.dry_run else [])).returncode
        spec_file.unlink()
        if args.dry_run:
            continue
        ok = None
        if (run_dir / 'result.json').exists():
            ok = json.loads((run_dir / 'result.json').read_text())['ok']
        with open(out / 'manifest.jsonl', 'a') as f:
            f.write(json.dumps(dict(order=i, run=spec['run'], collector_exit=rc, task_ok=ok,
                                    seconds=round(time.time() - t0, 1),
                                    finished_at=datetime.now(timezone.utc).isoformat(), spec=spec)) + '\n')
        # Safety for unattended campaigns: an agent that never reaches the model (sign-in
        # expired, usage limit, no network) produces useless runs that still take time.
        # A hard memory or process limit can itself keep the agent from starting, so
        # those runs are not counted either way.
        if not (spec['limits'].get('memory_max') or spec['limits'].get('pids_max')):
            silent = 0 if model_answered(run_dir) else silent + 1
        if silent >= MAX_SILENT and spec['agent'] != 'fake':
            sys.exit(f'STOPPED: the last {silent} runs got no answer from the model. Check the agent '
                     f'by hand, remove those run folders, and start the campaign again.')
        time.sleep(camp.get('cooldown_s', 10))
    print(f'campaign {camp["name"]} complete -> {out}')
