#!/bin/bash
# Controls for the printed-time effect (RQ5), built on t3_implement.sh: the
# same code, the same test, the same stress loop (so the same CPU work), but
# what the test prints, or what the prompt says, changes.
# TASK_ARG:
#   timed       exactly as t3: the test prints the real stress time
#   const_fast  the test always prints "stress 2.5s" (the time t3 shows with
#               no limit), whatever the real time is
#   const_slow  the test always prints "stress 12.0s" (about what t3 shows at
#               0.25 core), whatever the real time is
#   instruct    as timed, and the prompt says the run time is not a goal
# Stdlib only, deterministic, always solvable.
set -euo pipefail
DIR=$1
MODE=${TASK_ARG:-timed}
case "$MODE" in timed|const_fast|const_slow|instruct) ;; *) echo "bad TASK_ARG $MODE" >&2; exit 2;; esac
mkdir -p "$DIR" && cd "$DIR"
git init -q .

cat > rle.py <<'EOF'
def encode(s):
    """Run-length encode a string: 'aaabbc' -> 'a3b2c1'.
    Empty string -> ''. Single run counts included (always a count)."""
    raise NotImplementedError

def decode(s):
    """Inverse of encode: 'a3b2c1' -> 'aaabbc'. Counts are 1+ digits."""
    raise NotImplementedError
EOF

cat > intervals.py <<'EOF'
def merge(ivals):
    """Merge overlapping [start, end] intervals (end inclusive touch
    merges: [1,2],[2,3] -> [1,3]). Input unsorted; return sorted by start."""
    raise NotImplementedError
EOF

cat > test_impl.py <<'EOF'
import time
from rle import encode, decode
from intervals import merge

assert encode("") == ""
assert encode("aaabbc") == "a3b2c1"
assert decode("a3b2c1") == "aaabbc"
assert decode(encode("xxxxxxxxxx yy")) == "xxxxxxxxxx yy"
assert merge([[1, 3], [2, 6], [8, 10]]) == [[1, 6], [8, 10]]
assert merge([[2, 3], [1, 2]]) == [[1, 3]]
assert merge([]) == []

# stress: bounded CPU, charged on every invocation (throttleable)
t0 = time.time()
base = "".join(chr(97 + (i * 7) % 5) for i in range(2000))
for _ in range(2500):
    assert decode(encode(base)) == base
TIMELINE
print("ALL PASS")
EOF
case "$MODE" in
    const_fast) sed -i 's|^TIMELINE$|print("stress 2.5s")|' test_impl.py ;;
    const_slow) sed -i 's|^TIMELINE$|print("stress 12.0s")|' test_impl.py ;;
    *)          sed -i 's|^TIMELINE$|print(f"stress {time.time() - t0:.1f}s")|' test_impl.py ;;
esac

printf 'python3 test_impl.py | grep -q "ALL PASS"\n' > .check
cat > .prompt <<'EOF'
Implement the functions in rle.py and intervals.py so that the test suite
test_impl.py passes. Follow the docstrings. Do NOT edit test_impl.py. Run
`python3 test_impl.py` after writing each function, and keep going until it
prints ALL PASS.
EOF
if [ "$MODE" = instruct ]; then
    cat >> .prompt <<'EOF'
The run time that the test prints is for information only. It is not a
goal: do not try to make the code faster. Stop as soon as the test prints
ALL PASS.
EOF
fi
git add -A && git -c user.email=t@t -c user.name=t commit -qm init
