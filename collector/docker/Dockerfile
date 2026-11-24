# Image for runtime=docker runs. Same OS as the collection VM, so the task
# environments (built on the VM with uv) and the agent binary (mounted from
# the VM) run unchanged. The agent and the task copy are mounted, not baked in.
FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates git python3 procps ripgrep less curl \
    && rm -rf /var/lib/apt/lists/*
ARG UID=1001
ARG GID=1002
ARG USER=yuvraj
RUN groupadd -g $GID $USER && useradd -m -u $UID -g $GID -d /home/$USER -s /bin/bash $USER
