#!/bin/bash
# On a VM: pack campaigns for download, one archive each, plus a file manifest and checksums.
#   bash pack_runs.sh <out_dir> <campaign> [<campaign> ...]
# The manifest ("size path" of every file) lets the PC check the archives file by file.
set -euo pipefail
OUT=$1; shift
mkdir -p "$OUT"
cd ~/osn-runs
for c in "$@"; do
    [ -e "$OUT/$c.tar.zst" ] && continue
    sudo tar -I "zstd -T0 -3" -cf "$OUT/$c.tar.zst.part" "$c" && sudo mv "$OUT/$c.tar.zst.part" "$OUT/$c.tar.zst"
    find "$c" -type f -printf "%s %p\n" >> "$OUT/manifest.part"
done
sudo chown "$USER" "$OUT"/*
LC_ALL=C sort -k2 "$OUT/manifest.part" > "$OUT/manifest.txt" && rm "$OUT/manifest.part"
cd "$OUT" && sha256sum *.tar.zst manifest.txt > SHA256SUMS && echo PACK DONE
