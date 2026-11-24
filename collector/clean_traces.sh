#!/bin/bash
# Clean the decoded kernel traces for the anonymous artifact and recompress them.
#   bash collector/clean_traces.sh <dataset root> <out dir> [jobs]
# For every <root>/{runs,runs-rev,runs-oh}/<campaign>/<run>/trace.txt.gz it writes
#   <out>/<set>/<campaign>/<run>.trace.txt.zst
# with the login name, the cloud project id and the account ids replaced.
# Resumable: a finished file is skipped. ponytail: sed on the text stream; the raw CTF traces are not converted.
ROOT=$1; OUT=$2; JOBS=${3:-20}
export LC_ALL=C OUT
one() {
    f=$1                                            # runs-rev/r_cpu/<run>/trace.txt.gz
    set_=$(echo "$f" | cut -d/ -f1 | sed 's/^runs$/m0-set1/; s/^runs-rev$/revision/; s/^runs-oh$/other-agents/')
    camp=$(echo "$f" | cut -d/ -f2); run=$(echo "$f" | cut -d/ -f3)
    o="$OUT/$set_/$camp/$run.trace.txt.zst"
    [ -s "$o" ] && return 0
    mkdir -p "$(dirname "$o")"
    gzip -dc "$f" \
      | sed -e 's#plugins/synced/[0-9a-f-]\{36\}_[0-9a-f-]\{36\}#plugins/synced/ACCOUNT#g' \
            -e 's/yuvraj/user/Ig' -e 's/gcp200106/user2/g' -e 's/project-ba99825a-df02-4405-af4/CLOUD-PROJECT/g' \
      | zstd -q -16 --long=27 -T1 -f -o "$o.tmp" && mv "$o.tmp" "$o"
}
export -f one
cd "$ROOT" || exit 1
find runs runs-rev runs-oh -mindepth 3 -maxdepth 3 -name trace.txt.gz 2>/dev/null | sort \
  | xargs -P "$JOBS" -I{} bash -c 'one {}'
echo "CLEAN DONE: $(find "$OUT" -name '*.zst' | wc -l) files"
