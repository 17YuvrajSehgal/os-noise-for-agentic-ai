#!/bin/bash
# Real task: one SWE-bench Verified instance, TASK_ARG=<instance_id>.
# Prepared once by swe/setup_task.py in ~/osn-swe/<id>/. Every run gets a
# fresh copy of the repository and its Python environment (.venv); the paths
# inside the environment are rewritten to the copy, so the tests import the
# code the agent edits. The tests that decide success stay hidden in
# ~/osn-swe/<id>/ and are applied only by the check, after the agent ends.
set -euo pipefail
DIR=$1
SRC=$HOME/osn-swe/$TASK_ARG
HERE=$(cd "$(dirname "$0")/.." && pwd)
[ -f "$SRC/tests.json" ] || { echo "task $TASK_ARG is not prepared (swe/setup_task.py)" >&2; exit 1; }
mkdir -p "$(dirname "$DIR")"
cp -a "$SRC/repo" "$DIR"
cp -a "$SRC/venv" "$DIR/.venv"
grep -rlIF -e "$SRC/" "$DIR/.venv" | xargs -r sed -i "s#$SRC/venv#$DIR/.venv#g; s#$SRC/repo#$DIR#g"
cp "$SRC/prompt.txt" "$DIR/.prompt"
echo "$HOME/osn-tools/bin/python $HERE/swe/check.py $TASK_ARG" > "$DIR/.check"
