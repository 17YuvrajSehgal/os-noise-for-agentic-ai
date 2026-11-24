#!/bin/bash
# Build the image for runtime=docker runs, with this user's uid/gid inside.
set -euo pipefail
cd "$(dirname "$0")"
sudo -n docker build -q -t osn-agent:1 --build-arg UID=$(id -u) --build-arg GID=$(id -g) --build-arg USER=$(id -un) .
