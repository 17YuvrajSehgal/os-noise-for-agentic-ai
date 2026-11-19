#!/bin/bash
# Start the revision collections (run from the repo root on the PC, Git Bash).
#
#   bash collector/start_revision.sh copy ["osn-m1 osn-m2"]  # start VMs (default all 3), copy the new collector files
#   bash collector/start_revision.sh smoke     # one t12 run at 768M on M0 (checks the silent kill)
#   bash collector/start_revision.sh usage     # 5-hour and 7-day usage of the account on each VM
#   bash collector/start_revision.sh go m1     # start one VM's queue (m1, m2 or m0); each campaign checks usage first
#   bash collector/start_revision.sh status    # last queue lines on every VM
set -u
P=project-ba99825a-df02-4405-af4; Z=us-east1-d
VMS="agentic-noise-2 osn-m1 osn-m2"
ssh_() { gcloud compute ssh "yuvraj@$1" --zone $Z --project $P --command "$2" 2>&1 | grep -v -E "^(Store key|The host key|The server|If you|You have no|connection|Update cached|  [0-9a-z])" ; }
M0="r_feedback r_feedback_ref r_cutout r_cpu r_overhead r_pids r_mem r_interact r_real r_density r_density_real r_overhead_density"
M1="m1_cpu m1_threads m1_memory m1_disk m1_pids m1_real m1_density"
M2="m2_cpu m2_threads m2_memory m2_disk m2_pids m2_real m2_density"

case "${1:-}" in
copy)
    TARGET=${2:-$VMS}
    gcloud compute instances start $TARGET --zone $Z --project $P
    tar -C collector -czf /tmp/osn-rev.tgz tasks campaigns campaign.py collect.py run_queue.sh sampler.py \
        summarize.py verify_campaign.py usage.py swe docker
    for vm in $TARGET; do
        gcloud compute scp /tmp/osn-rev.tgz "yuvraj@$vm:osn-rev.tgz" --zone $Z --project $P >/dev/null 2>&1
        ssh_ $vm 'cd ~/collector && tar -xzf ~/osn-rev.tgz && ls tasks/t11* tasks/t12* campaigns/r_cpu.json >/dev/null && echo "$(hostname): files ok"; python3 campaign.py campaigns/r_cpu.json --list | tail -1'
    done ;;
smoke)
    ssh_ agentic-noise-2 'cd ~/collector && cat > /tmp/smoke_rev.json <<EOF
{"name": "smoke_rev", "reps": 1, "seed": 1, "base": {"agent": "claude", "trace": "full", "cache": "cold"},
 "cells": [{"task": "t12_silent_kill.sh", "task_arg": 700, "limits": {"memory_max": "768M"}, "model": "claude-haiku-5-5"}]}
EOF
python3 campaign.py /tmp/smoke_rev.json > ~/osn-smoke-rev.log 2>&1; tail -2 ~/osn-smoke-rev.log
d=$(ls -d ~/osn-runs/smoke_rev/smoke_rev_*); grep -c oom_kill "$d/trace.txt.gz" 2>/dev/null; zgrep -c "oom" "$d/trace.txt.gz"
grep -o "\[ *[0-9]*%\][^\\\\]*" "$d/a1/events.jsonl" | tail -3; cat "$d/a1/task_check.txt" | tail -2; cat "$d/a1/exit_code"' ;;
go)
    case "${2:-}" in
        m0) vm=agentic-noise-2; q=$M0 ;; m1) vm=osn-m1; q=$M1 ;; m2) vm=osn-m2; q=$M2 ;;
        *) echo "go m0|m1|m2"; exit 1 ;;
    esac
    ssh_ $vm "cd ~/collector && setsid nohup bash run_queue.sh claude $q > /dev/null 2>&1 < /dev/null & echo started $2 on $vm" ;;
usage)
    for vm in ${2:-$VMS}; do echo "== $vm"; ssh_ $vm 'cd ~/collector && python3 usage.py'; done ;;
status)
    for vm in $VMS; do echo "== $vm"; ssh_ $vm 'tail -3 ~/osn-queue.log; df -h / | tail -1'; done ;;
*) sed -n 2,8p "$0" ;;
esac
