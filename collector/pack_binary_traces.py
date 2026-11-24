#!/usr/bin/env python3
"""Repack one campaign archive so that it holds only the binary kernel traces.

  python collector/pack_binary_traces.py <in.tar.zst> <out.tar.zst>

Reads the archive as a stream, keeps every file under a run's trace/ folder (the raw LTTng
trace in CTF format) and drops the rest (the text copy of the trace and the run records, which
are published separately). ponytail: stream in, stream out, nothing unpacked to disk.
"""
import subprocess, sys, tarfile

src, dst = sys.argv[1], sys.argv[2]
zin = subprocess.Popen(['zstd', '-dc', '--long=31', src], stdout=subprocess.PIPE)
zout = subprocess.Popen(['zstd', '-q', '-10', '-T4', '--long=27', '-f', '-o', dst + '.tmp'], stdin=subprocess.PIPE)
kept = size = 0
with tarfile.open(fileobj=zin.stdout, mode='r|') as tin, tarfile.open(fileobj=zout.stdin, mode='w|') as tout:
    for m in tin:
        parts = m.name.split('/')
        if m.isfile() and 'trace' in parts[:-1]:
            tout.addfile(m, tin.extractfile(m))
            kept += 1
            size += m.size
zout.stdin.close()
assert zout.wait() == 0 and zin.wait() == 0, 'zstd failed'
import os
os.replace(dst + '.tmp', dst)
print(f'{os.path.basename(dst)}: {kept} files, {size / 1e9:.2f} GB raw -> {os.path.getsize(dst) / 1e9:.2f} GB', flush=True)
