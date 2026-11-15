#!/usr/bin/env python3
"""Prepare SWE-bench Verified tasks for the collector (task script swe.sh).

  ~/osn-tools/bin/python setup_task.py <instance_id> [<instance_id> ...]

Per task writes ~/osn-swe/<id>/:
  repo/          the project at the base commit, dependencies installed
  venv/          Python environment with the versions the SWE-bench harness pins
  instance.json  the SWE-bench row
  prompt.txt     what the agent is asked
  tests.json     test command, FAIL_TO_PASS, and the PASS_TO_PASS tests that pass
                 with the reference fix in this environment (the check uses these)

Validates every task: FAIL_TO_PASS must fail at the base commit and pass with
the reference fix. A task that does not validate is reported and not used.
Needs uv, git, and swebench==3.0.15 + pandas + pyarrow in ~/osn-tools, and
the dataset in ~/osn-swe/verified.parquet:
  curl -L -o ~/osn-swe/verified.parquet https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/resolve/main/data/test-00000-of-00001.parquet
"""
import json, os, re, shlex, subprocess, sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
from swebench.harness.log_parsers import MAP_REPO_TO_PARSER
from swebench.harness.test_spec.python import get_requirements, get_test_directives

ROOT = Path.home() / 'osn-swe'
DATA = ROOT / 'verified.parquet'
UV = str(Path.home() / '.local/bin/uv')

PROMPT = """Fix the following issue in this repository (the current directory).

{problem}

A Python environment with the project's dependencies is in .venv. Use
.venv/bin/python to run code and tests. Change the source code to fix the
issue; do not change the existing tests.
"""


def sh(cmd, cwd=None, env=None, check=True, timeout=1800):
    r = subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd, env=env, text=True,
                       capture_output=True, timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(f'FAILED: {cmd}\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}')
    return r


def venv_env(venv):
    return dict(os.environ, VIRTUAL_ENV=str(venv), PATH=f'{venv}/bin:' + os.environ['PATH'],
                PYTHONDONTWRITEBYTECODE='1')


def test_files(patch):
    return re.findall(r'diff --git a/.* b/(.*)', patch)


def run_tests(inst, spec, repo, venv, directives):
    """-> {test name: PASSED/FAILED/...} for the test files of the task."""
    cmd = spec['test_cmd'] + ' ' + ' '.join(shlex.quote(d) for d in directives)
    r = sh(cmd, cwd=repo, env=venv_env(venv), check=False, timeout=1200)
    ts = SimpleNamespace(repo=inst['repo'], version=inst['version'], instance_id=inst['instance_id'])
    return MAP_REPO_TO_PARSER[inst['repo']](r.stdout + r.stderr, ts), cmd


def setup(iid, rows):
    inst = rows[iid]
    spec = MAP_REPO_VERSION_TO_SPECS[inst['repo']][inst['version']]
    d = ROOT / iid
    repo, venv = d / 'repo', d / 'venv'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'instance.json').write_text(json.dumps(inst, indent=1))
    if not repo.exists():
        sh(['git', 'clone', '-q', f'https://github.com/{inst["repo"]}', str(repo)])
    sh(['git', 'reset', '-q', '--hard', inst['base_commit']], cwd=repo)
    sh(['git', 'clean', '-qfdx'], cwd=repo)
    for c in spec.get('pre_install', []):
        sh(c, cwd=repo)
    sh([UV, 'venv', '-q', '--clear', '--seed', '--python', spec['python'], str(venv)])
    pip = [UV, 'pip', 'install', '-q', '--python', str(venv / 'bin/python')]
    pk = spec.get('packages', '')
    if pk == 'requirements.txt':
        (d / 'requirements.txt').write_text(get_requirements(inst))
        sh(pip + ['-r', str(d / 'requirements.txt')])
    elif pk and pk != 'environment.yml':
        sh(pip + pk.split())
    if spec.get('pip_packages'):
        sh(pip + spec['pip_packages'])
    # always editable, so the tests import the copy the agent edits
    sh(pip + ['-e', str(repo)])
    if inst['repo'] not in ('pytest-dev/pytest', 'django/django', 'sympy/sympy'):
        sh(pip + ['pytest'])
    # files the install created are not the agent's work: hide them from git status
    extra = sh(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=repo).stdout
    with open(repo / '.git/info/exclude', 'a') as f:
        f.write('.venv\n.prompt\n.check\n' + ''.join(l[3:] + '\n' for l in extra.splitlines() if l.startswith('??')))
    sh(['git', 'reset', '-q', '--hard'], cwd=repo)    # pre_install may have edited tracked files

    f2p, p2p = json.loads(inst['FAIL_TO_PASS']), json.loads(inst['PASS_TO_PASS'])
    directives = get_test_directives(inst)
    patch_file = d / 'test.patch'
    patch_file.write_text(inst['test_patch'])
    (d / 'gold.patch').write_text(inst['patch'])
    sh(['git', 'apply', str(patch_file)], cwd=repo)
    try:
        base, cmd = run_tests(inst, spec, repo, venv, directives)
        sh(['git', 'apply', str(d / 'gold.patch')], cwd=repo)
        gold, _ = run_tests(inst, spec, repo, venv, directives)
        sh(['git', 'apply', '-R', str(d / 'gold.patch')], cwd=repo)
    finally:
        sh(['git', 'apply', '-R', str(patch_file)], cwd=repo)
    ok = lambda res, t: res.get(t) in ('PASSED', 'XFAIL')
    bad_base = [t for t in f2p if ok(base, t)]
    bad_gold = [t for t in f2p if not ok(gold, t)]
    p2p_ok = [t for t in p2p if ok(gold, t)]
    (d / 'tests.json').write_text(json.dumps(dict(cmd=cmd, test_files=test_files(inst['test_patch']),
                                                  fail_to_pass=f2p, pass_to_pass=p2p_ok,
                                                  pass_to_pass_dropped=sorted(set(p2p) - set(p2p_ok))), indent=1))
    (d / 'prompt.txt').write_text(PROMPT.format(problem=inst['problem_statement'].strip()))
    valid = not bad_base and not bad_gold
    print(f'{iid}: python {spec["python"]}, F2P {len(f2p)}, P2P kept {len(p2p_ok)}/{len(p2p)}, '
          f'{"VALID" if valid else "NOT VALID"}'
          + (f' (pass before fix: {bad_base})' if bad_base else '')
          + (f' (fail with fix: {bad_gold})' if bad_gold else ''), flush=True)
    return valid


if __name__ == '__main__':
    rows = {r['instance_id']: r for r in pd.read_parquet(DATA).to_dict('records')}
    bad = []
    for iid in sys.argv[1:]:
        try:
            if not setup(iid, rows):
                bad.append(iid)
        except Exception as e:                       # report and go on with the next task
            print(f'{iid}: SETUP FAILED: {e}', flush=True)
            bad.append(iid)
    sys.exit(1 if bad else 0)
