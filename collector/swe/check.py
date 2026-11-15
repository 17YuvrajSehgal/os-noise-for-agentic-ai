#!/usr/bin/env python3
"""Task check for a SWE-bench task (the .check of swe.sh). Runs in the agent's
work copy after the agent ends, outside the measured cgroup.

  ~/osn-tools/bin/python check.py <instance_id>

Applies the hidden test patch (over the agent's version of those test files),
runs the task's tests with the work copy's .venv, and restores the agent's
files. Exit 0 when every FAIL_TO_PASS test and every kept PASS_TO_PASS test
passes. Prints the failing tests.
"""
import json, os, subprocess, sys
from pathlib import Path
from types import SimpleNamespace

from swebench.harness.log_parsers import MAP_REPO_TO_PARSER

iid = sys.argv[1]
src = Path.home() / 'osn-swe' / iid
inst = json.loads((src / 'instance.json').read_text())
tests = json.loads((src / 'tests.json').read_text())
work = Path.cwd()
venv = work / '.venv'
git = lambda *c, **k: subprocess.run(['git', *c], cwd=work, text=True, capture_output=True, **k)

# keep what the agent did to the test files, then put them back to the base version
files = [f for f in tests['test_files'] if (work / f).exists() or git('ls-files', '--error-unmatch', f).returncode == 0]
saved = git('diff', 'HEAD', '--binary', '--', *files).stdout
git('checkout', 'HEAD', '--', *[f for f in files if git('ls-files', '--error-unmatch', f).returncode == 0])
for f in tests['test_files']:                     # files the test patch adds must not exist yet
    if git('ls-files', '--error-unmatch', f).returncode and (work / f).exists():
        os.remove(work / f)
r = git('apply', str(src / 'test.patch'))
if r.returncode:
    sys.exit('test patch does not apply: ' + r.stderr)
try:
    env = dict(os.environ, VIRTUAL_ENV=str(venv), PATH=f'{venv}/bin:' + os.environ['PATH'],
               PYTHONDONTWRITEBYTECODE='1')
    run = subprocess.run(tests['cmd'], shell=True, cwd=work, env=env, text=True, capture_output=True, timeout=1200)
    ts = SimpleNamespace(repo=inst['repo'], version=inst['version'], instance_id=iid)
    res = MAP_REPO_TO_PARSER[inst['repo']](run.stdout + run.stderr, ts)
finally:
    git('apply', '-R', str(src / 'test.patch'))
    if saved:
        subprocess.run(['git', 'apply', '-'], cwd=work, input=saved, text=True)
ok = lambda t: res.get(t) in ('PASSED', 'XFAIL')
f2p_bad = [t for t in tests['fail_to_pass'] if not ok(t)]
p2p_bad = [t for t in tests['pass_to_pass'] if not ok(t)]
print(f'FAIL_TO_PASS {len(tests["fail_to_pass"]) - len(f2p_bad)}/{len(tests["fail_to_pass"])} pass, '
      f'PASS_TO_PASS {len(tests["pass_to_pass"]) - len(p2p_bad)}/{len(tests["pass_to_pass"])} pass')
for t in f2p_bad + p2p_bad:
    print('FAILED', t, res.get(t, 'not run'))
print('ALL PASS' if not (f2p_bad or p2p_bad) else 'NOT SOLVED')
sys.exit(0 if not (f2p_bad or p2p_bad) else 1)
