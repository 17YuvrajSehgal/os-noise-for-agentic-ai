#!/bin/bash
# Start the revision collections (run from the repo root on the PC, Git Bash).
#
#   bash collector/start_revision.sh copy      # start the 3 VMs, copy the new collector files
#   bash collector/start_revision.sh smoke     # one t12 run at 768M on M0 (checks the silent kill)
#   bash collector/start_revision.sh go        # start the three queues (see gen_revision.py for the order)
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
    gcloud compute instances start $VMS --zone $Z --project $P
    tar -C collector -czf /tmp/osn-rev.tgz tasks campaigns campaign.py collect.py run_queue.sh sampler.py \
        summarize.py verify_campaign.py swe docker
    for vm in $VMS; do
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
    ssh_ agentic-noise-2 "cd ~/collector && nohup bash run_queue.sh claude $M0 > /dev/null 2>&1 & echo started M0"
    ssh_ osn-m1 "cd ~/collector && nohup bash run_queue.sh claude $M1 > /dev/null 2>&1 & echo started M1"
    ssh_ osn-m2 "cd ~/collector && nohup bash run_queue.sh claude $M2 > /dev/null 2>&1 & echo started M2" ;;
status)
    for vm in $VMS; do echo "== $vm"; ssh_ $vm 'tail -3 ~/osn-queue.log; df -h / | tail -1'; done ;;
*) sed -n 2,8p "$0" ;;
esac
