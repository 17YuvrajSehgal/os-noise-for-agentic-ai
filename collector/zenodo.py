#!/usr/bin/env python3
"""Small Zenodo client for the artifact (standard library only).

  python collector/zenodo.py check
  python collector/zenodo.py create <metadata.json>            -> prints the deposition id
  python collector/zenodo.py upload <id> <file> [<file> ...]   (skips files already there)
  python collector/zenodo.py show <id>
  python collector/zenodo.py publish <id>

The token is read from ~/.zenodo_token. ponytail: one PUT per file, streamed from disk; no resume
inside a file, a failed file is uploaded again from the start.
"""
import json, sys, urllib.request, urllib.error
from pathlib import Path

API = 'https://zenodo.org/api'
TOKEN = (Path.home() / '.zenodo_token').read_text().strip()


def call(method, url, data=None, ctype='application/json', timeout=120):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Authorization', f'Bearer {TOKEN}')
    if data is not None:
        req.add_header('Content-Type', ctype)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        return e.code, {'error': e.read().decode('utf-8', 'replace')[:500]}


def dep(i):
    st, d = call('GET', f'{API}/deposit/depositions/{i}')
    assert st == 200, (st, d)
    return d


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'check':
        st, d = call('GET', f'{API}/deposit/depositions?size=5')
        print('status', st, 'depositions visible:', len(d) if st == 200 else d)
    elif cmd == 'create':
        meta = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
        st, d = call('POST', f'{API}/deposit/depositions', json.dumps({'metadata': meta}).encode())
        assert st == 201, (st, d)
        print('id', d['id'], 'doi', d['metadata'].get('prereserve_doi', {}).get('doi'), 'draft', d['links'].get('html'))
    elif cmd == 'upload':
        d = dep(sys.argv[2])
        have = {f['filename']: f['filesize'] for f in d.get('files', [])}
        for name in sys.argv[3:]:
            p = Path(name)
            if have.get(p.name) == p.stat().st_size:
                print('skip', p.name)
                continue
            req = urllib.request.Request(f"{d['links']['bucket']}/{p.name}", data=open(p, 'rb'), method='PUT')
            req.add_header('Authorization', f'Bearer {TOKEN}')
            req.add_header('Content-Type', 'application/octet-stream')
            req.add_header('Content-Length', str(p.stat().st_size))
            with urllib.request.urlopen(req, timeout=24 * 3600) as r:
                print('uploaded', p.name, p.stat().st_size, r.status, flush=True)
    elif cmd == 'show':
        d = dep(sys.argv[2])
        print('state', d['state'], 'submitted', d['submitted'], 'doi', d.get('doi') or d['metadata'].get('prereserve_doi', {}).get('doi'))
        print('title', d['metadata'].get('title'))
        print('creators', d['metadata'].get('creators'))
        for f in d.get('files', []):
            print(' ', f['filename'], f['filesize'])
        print('links', {k: v for k, v in d['links'].items() if k in ('html', 'record_html', 'doi', 'conceptdoi', 'latest_draft_html')})
    elif cmd == 'publish':
        st, d = call('POST', f'{API}/deposit/depositions/{sys.argv[2]}/actions/publish')
        print('status', st, d.get('doi'), d.get('conceptdoi'), d.get('links', {}).get('record_html') or d)
