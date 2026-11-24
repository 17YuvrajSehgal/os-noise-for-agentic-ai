#!/bin/bash
# Run several campaigns one after another, unattended.
#
#   bash run_queue.sh <agent> <campaign> [<campaign> ...]
#   e.g.  nohup bash run_queue.sh claude network threads disk > /dev/null 2>&1 &
#
# - Each campaign is resumable, so starting the queue again continues it.
# - After each campaign the measurement is verified and summarized.
# - The queue STOPS if a campaign stops itself (agent not answering) or if
#   the disk is nearly full. It does not go on producing bad runs.
# - Everything is logged to ~/osn-queue.log. The last line says how it ended.
# - `touch ~/osn-queue.stop` makes it stop after the current campaign.
set -u
cd "$(dirname "$0")"
AGENT=$1; shift
LOG=$HOME/osn-queue.log
say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }

say "QUEUE START agent=$AGENT campaigns: $*"
echo "$AGENT $*" > "$HOME/.osn-queue.args"       # lets a reboot hook start it again
for c in "$@"; do
    [ -e "$HOME/osn-queue.stop" ] && { say "QUEUE STOPPED by ~/osn-queue.stop before $c"; exit 0; }
    free_gb=$(df --output=avail -BG "$HOME" | tail -1 | tr -dc 0-9)
    [ "$free_gb" -lt 30 ] && { say "QUEUE STOPPED: only ${free_gb} GB free before $c"; exit 1; }
    # usage gate (set OSN_USAGE_MAX=1 to turn it off): stop before a campaign
    # when the account's 5-hour or 7-day usage is already high
    u=$(python3 usage.py --max "${OSN_USAGE_MAX:-0.85}"); urc=$?
    say "$u"
    [ $urc -ne 0 ] && { say "QUEUE STOPPED: usage too high or no answer before $c (switch account or wait)"; exit 1; }
    say "campaign $c start"
    python3 campaign.py "campaigns/$c.json" --agent "$AGENT" >> "$HOME/osn-campaign-$c.log" 2>&1
    rc=$?
    say "campaign $c ended rc=$rc: $(tail -1 "$HOME/osn-campaign-$c.log" | cut -c1-200)"
    python3 verify_campaign.py "$HOME/osn-runs/$c" > "$HOME/osn-verify-$c.txt" 2>&1
    say "verify $c: $(tail -1 "$HOME/osn-verify-$c.txt")"
    python3 summarize.py "$HOME/osn-runs/$c" --csv "$HOME/osn-summary-$c.csv" > "$HOME/osn-summary-$c.txt" 2>&1
    [ $rc -ne 0 ] && { say "QUEUE STOPPED: campaign $c did not finish cleanly"; exit 1; }
done
rm -f "$HOME/.osn-queue.args"
say "QUEUE DONE"
