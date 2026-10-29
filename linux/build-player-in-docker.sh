#!/usr/bin/env bash
# Build the bundled LGPL player runtime (scripts/build-linux-player.py) on Ubuntu 22.04, the oldest glibc we
# support, so the libraries also run on 24.04, Mint 22 and elementary OS 8. Run from the repository root on a
# Docker host:
#   docker run --rm -v "$PWD:/repo:ro" -v "<output folder>:/out" ubuntu:22.04 bash /repo/linux/build-player-in-docker.sh
# The result is /out/player (lib/, licenses/, player-build.json) and /out/sources (the pinned archives, which are
# also the corresponding source to publish with the release). Nothing from the network is trusted without its sha256.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends ca-certificates curl build-essential nasm pkg-config python3 python3-venv binutils \
  libass-dev liblcms2-dev libuchardet-dev libbluray-dev libgnutls28-dev libva-dev libdrm-dev libpulse-dev libpipewire-0.3-dev \
  libasound2-dev libx11-dev libxext-dev libxrandr-dev libxpresent-dev libxss-dev libxinerama-dev libegl-dev libgl-dev zlib1g-dev
python3 /repo/scripts/build-linux-player.py --download --sources /out/sources --output /out/player
