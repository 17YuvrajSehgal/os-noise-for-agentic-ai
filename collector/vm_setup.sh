#!/bin/bash
# One-time setup of a fresh collection VM (Ubuntu 24.04, cgroup v2).
#
#   bash vm_setup.sh
#
# Installs the tracer and tools, removes the main sources of background
# activity, pins the kernel, checks that every counter the collector reads is
# available, proves kernel tracing works, and writes a snapshot of the
# machine to ~/osn-provenance/. Agent sign-in is manual, after this script.
set -euo pipefail
PROV=$HOME/osn-provenance
mkdir -p "$PROV"

echo "=== packages ==="
sudo add-apt-repository -y ppa:lttng/stable-2.15
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    lttng-tools lttng-modules-dkms babeltrace2 git python3 jq zstd \
    stress-ng iproute2 iptables util-linux linux-tools-common

echo "=== quiet the machine ==="
# Background package work showed up inside one workshop run (a 0.8 s stall
# in an apt helper). Nothing may update itself while we measure.
# One unit at a time: if any name in a list is unknown, systemctl changes none
# of them (the first version of this script silently disabled nothing).
# The Google guest agent's own timers are left alone; they keep SSH working.
for u in unattended-upgrades.service apt-daily.timer apt-daily-upgrade.timer man-db.timer \
         fwupd-refresh.timer motd-news.timer dpkg-db-backup.timer e2scrub_all.timer \
         fstrim.timer logrotate.timer update-notifier-download.timer update-notifier-motd.timer \
         sysstat-collect.timer sysstat-summary.timer ua-timer.timer apport-autoreport.timer \
         snapd.snap-repair.timer snapd.service snapd.socket snapd.seeded.service; do
    sudo systemctl disable --now "$u" 2>/dev/null || true
done
sudo systemctl mask apt-daily.service apt-daily-upgrade.service 2>/dev/null || true

echo "=== one kernel for the whole campaign ==="
# The workshop runs ended up on two kernels because the VM updated itself.
sudo apt-mark hold "linux-image-$(uname -r)" "linux-headers-$(uname -r)" \
    linux-image-gcp linux-headers-gcp linux-gcp 2>/dev/null || true

echo "=== no swap (memory pressure must end in reclaim or OOM, not swapping) ==="
sudo swapoff -a
[ -z "$(swapon --show)" ] || { echo "FATAL: swap still on"; exit 1; }

echo "=== cgroup v2 and its controllers ==="
[ "$(stat -fc %T /sys/fs/cgroup)" = cgroup2fs ] || { echo "FATAL: not cgroup v2"; exit 1; }
for c in cpu cpuset memory io pids; do
    grep -qw "$c" /sys/fs/cgroup/cgroup.controllers || { echo "FATAL: controller $c missing"; exit 1; }
done
echo "+cpu +cpuset +memory +io +pids" | sudo tee /sys/fs/cgroup/cgroup.subtree_control >/dev/null
[ -r /proc/pressure/cpu ] || { echo "FATAL: pressure files missing (boot with psi=1)"; exit 1; }

echo "=== kernel tracing ==="
# dkms drops the modules without refreshing the index; depmod before modprobe.
sudo depmod -a
sudo modprobe lttng-tracer || { echo "FATAL: lttng-tracer will not load on $(uname -r)"; exit 1; }
# the session daemon may have started before the modules were usable
sudo systemctl restart lttng-sessiond.service 2>/dev/null || true
sleep 2
sudo lttng destroy smoke 2>/dev/null || true
sudo rm -rf /tmp/smoke
sudo lttng create smoke --output=/tmp/smoke
sudo lttng enable-channel -k ch --subbuf-size=16M --num-subbuf=8
sudo lttng enable-event -k -c ch --syscall --all
sudo lttng enable-event -k -c ch --tracepoint --all
sudo lttng add-context -k -c ch -t pid -t tid -t procname
# Do NOT probe for hardware counters by adding a perf context. On a VM with
# no PMU that crashes the kernel inside the tracer (seen on 7.0.0-1017-gcp
# with LTTng 2.15.3: NULL pointer in perf_event_release_kernel, VM reboots).
# Look at what the kernel itself reports instead.
PMU=no
[ -d /sys/bus/event_source/devices/cpu ] && PMU=yes
sudo lttng start; sleep 3; sudo lttng stop
sudo lttng list smoke -k -c ch > "$PROV/smoke_channel_stats.txt" 2>&1 || true
sudo lttng destroy smoke
sudo babeltrace2 /tmp/smoke 2>"$PROV/smoke_babeltrace_stderr.txt" \
    | grep -oE ' [a-z0-9_]+: \{ cpu_id' | sed 's/: { cpu_id//' | sort | uniq -c | sort -rn \
    > "$PROV/smoke_event_types.txt"
sudo rm -rf /tmp/smoke
n=$(awk '{s+=$1} END{print s+0}' "$PROV/smoke_event_types.txt")
types=$(wc -l < "$PROV/smoke_event_types.txt")
[ "$n" -gt 1000 ] || { echo "FATAL: smoke trace empty"; exit 1; }
echo "smoke trace: $n events of $types types in 3 s (full profile)"

echo "=== what this machine can and cannot measure ==="
RAPL=no;  ls /sys/class/powercap/intel-rapl:* >/dev/null 2>&1 && RAPL=yes
FREQ=no;  [ -d /sys/devices/system/cpu/cpu0/cpufreq ] && FREQ=yes
echo "hardware counters in the trace (PMU): $PMU"
echo "energy counter (RAPL):                $RAPL"
echo "CPU frequency scaling visible:        $FREQ"

echo "=== machine snapshot -> $PROV ==="
{
    echo "date_utc: $(date -u +%FT%TZ)"
    echo "pmu: $PMU"; echo "rapl: $RAPL"; echo "cpufreq: $FREQ"
    for c in "uname -a" "lsb_release -a" "lttng --version" "babeltrace2 --version" "lscpu" \
             "free -h" "lsblk" "df -h /" "swapon --show" "cat /proc/cmdline" \
             "cat /sys/fs/cgroup/cgroup.controllers" "cat /sys/fs/cgroup/cgroup.subtree_control" \
             "ip -brief addr" "systemctl list-timers --all --no-pager" "python3 --version"; do
        echo "=== $c ==="; $c 2>&1 || true
    done
    echo "=== disk sequential read (1 GiB, cold) ==="
    dd if=/dev/zero of="$HOME/.osn_dd" bs=1M count=1024 status=none; sync
    echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null
    dd if="$HOME/.osn_dd" of=/dev/null bs=1M 2>&1 | tail -1; rm -f "$HOME/.osn_dd"
} > "$PROV/vm_env.txt"

cat <<'EOF'

=== SETUP DONE ===
Next, by hand, as this user:
  1. Install and sign in Claude Code:   curl -fsSL https://claude.ai/install.sh | bash ; claude
  2. Install and sign in Codex:         npm i -g @openai/codex ; put the key in ~/.codex-env
  3. Record the versions:               claude --version ; codex --version   (collect.py saves them per run)
  4. Test the collector without an agent:
       python3 campaign.py campaigns/smoke_fake.json
  5. Test one real run per agent:
       python3 campaign.py campaigns/smoke.json
  6. Look at one run folder before starting any campaign: raw trace present,
     meta/lttng_stats.txt shows no discarded events, a1/events.jsonl has lines.
EOF
