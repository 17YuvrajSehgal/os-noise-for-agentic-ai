#!/usr/bin/env python3
"""Build the anonymous review artifact: code and the run records without kernel traces.

  python collector/make_artifact.py <out dir>

  <out>/code/   collector, analysis scripts and their outputs, figure script
  <out>/data/   every run folder of the dataset without trace/ and trace.txt.gz
                (spec, result, agent event log, counter samples, counter snapshots, versions)

Every text file is scrubbed: the login name in paths, the cloud project id, the account
ids in plugin paths. The script ends with a scan for strings that could identify people
and fails if it finds one. ponytail: one pass, files read whole; fine for files under 100 MB.
"""
import re, shutil, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = Path('C:/workplace/microservice-trace-dataset/agentic-runs-phase2')
OUT = Path(sys.argv[1])
SETS = {'m0-set1': DATA / 'runs', 'revision': DATA / 'runs-rev', 'other-agents': DATA / 'runs-oh'}

USER = b'yuvraj'
SUBS = [   # (pattern, replacement), applied to bytes in this order
    (re.compile(rb'plugins/synced/[0-9a-f-]{36}_[0-9a-f-]{36}'), b'plugins/synced/ACCOUNT'),
    (re.compile(rb'-home-' + USER), b'-home-user'),
    (re.compile(USER, re.I), b'user'),
    (re.compile(rb'project-ba99825a-df02-4405-af4'), b'CLOUD-PROJECT'),
    (re.compile(rb'gcp200106'), b'user2'),
]
CODE_SUBS = SUBS + [(re.compile(rb'[Ww]orkshop'), lambda m: b'Pilot' if m.group(0)[0:1] == b'W' else b'pilot')]
# short names only count as whole words: random base64 text can contain any five letters
FORBIDDEN = re.compile(rb'yuvraj|sehgal|brocku|17yuv|gcp200106|project-ba99|@gmail|sk-ant-|sk-proj-|panahan|workshop'
                       rb'|\b(?:naser|mahsa)\b', re.I)
CODE_SKIP = ('phase2/workshop/', 'phase2/rev/REVIEW', 'phase2/PLAN.md', 'phase2/RESEARCH-QUESTIONS.md',
             'phase2/REVISION-PLAN.md', 'phase2/DATA.md', 'collector/start_revision.sh', 'collector/make_artifact.py')


def scrub(b, subs):
    for pat, rep in subs:
        b = pat.sub(rep, b)
    return b


def put(src, dst, subs):
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(scrub(src.read_bytes(), subs))


def code():
    files = subprocess.run(['git', '-C', str(REPO), 'ls-files', 'collector', 'phase2', 'paper-icpe/figures/make_figures.py'],
                           capture_output=True, text=True, check=True).stdout.split('\n')
    n = 0
    for f in filter(None, files):
        if f.startswith(CODE_SKIP):
            continue
        put(REPO / f, OUT / 'code' / f.replace('paper-icpe/figures/', 'figures/'), CODE_SUBS)
        n += 1
    return n


def data():
    n = runs = 0
    for name, root in SETS.items():
        for camp in sorted(p for p in root.iterdir() if p.is_dir()):
            for f in camp.rglob('*'):
                rel = f.relative_to(camp)
                if not f.is_file() or 'trace' in rel.parts[:-1] or f.name in ('trace.txt.gz', 'SHA256SUMS', 'out.fifo'):
                    continue
                put(f, OUT / 'data' / name / camp.name / rel, SUBS)
                n += 1
                runs += f.name == 'result.json'
    return n, runs


def scan():
    bad = []
    for f in OUT.rglob('*'):
        if f.is_file():
            m = FORBIDDEN.search(f.read_bytes())
            if m:
                bad.append((str(f.relative_to(OUT)), m.group(0).decode()))
    return bad


if __name__ == '__main__':
    if OUT.exists():
        shutil.rmtree(OUT)
    print('code files', code())
    print('data files, runs', data())
    bad = scan()
    for f, w in bad[:40]:
        print('FOUND', w, 'in', f)
    sys.exit(f'{len(bad)} files still hold a forbidden string' if bad else 0)
