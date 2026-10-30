#!/usr/bin/env bash
# Build the bundled LGPL player runtime (linux/build-linux-player.py) on Ubuntu 22.04, the oldest glibc we
# support, so the libraries also run on 24.04, Mint 22 and elementary OS 8. Run from the repository root on a
# Docker host:
#   docker run --rm -v "$PWD:/repo:ro" -v "<output folder>:/out" ubuntu:22.04 bash /repo/linux/build-player-in-docker.sh
# The result is /out/player (lib/, licenses/, player-build.json), /out/build.log and /out/sources (the pinned archives, which are
# also the corresponding source to publish with the release). Nothing from the network is trusted without its sha256.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends ca-certificates curl build-essential nasm pkg-config python3 python3-venv binutils patchelf \
  libass-dev liblcms2-dev libuchardet-dev libbluray-dev libgnutls28-dev libva-dev libdrm-dev libpulse-dev \
  libasound2-dev libegl-dev libgl-dev zlib1g-dev hwdata libvulkan-dev
# hwdata gives libdisplay-info its PNP ID table. libvulkan-dev is for headers only: libplacebo is built with -Dvulkan=disabled but still compiles its Vulkan stubs,
# which include vulkan/vulkan.h. The NEEDED check refuses libvulkan in the result.
# The build runs inside the container's own disk (a bind-mounted Windows folder makes it hours slower); only the
# result and the log are copied out.
status=0
python3 /repo/linux/build-linux-player.py --download --sources /out/sources --output /tmp/player || status=$?
rm -rf /out/player /out/build.log
cp /tmp/player.work/build.log /out/build.log 2>/dev/null || true
if [ "$status" -eq 0 ]; then cp -a /tmp/player /out/player; fi
exit "$status"
