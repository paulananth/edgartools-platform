#!/usr/bin/env bash
# One-time Colima setup for this repo on macOS.
#
# What it does:
#   1. Disables Docker's containerd image-store snapshotter.
#      Why: Docker 29+ defaults to it, but the legacy `docker build` path
#      (which CLAUDE.md mandates: "Colima plus plain docker build/docker push")
#      cannot use it — builds fail with "failed to restore cached image".
#      Switching to overlay2 makes legacy `docker build` work without
#      needing buildx (CLAUDE.md: "Do not introduce another container build/runtime stack").
#   2. Restarts Colima with adequate CPU/RAM/disk for warehouse + MDM image builds.
#   3. Verifies the daemon is no longer using the containerd snapshotter.
#
# Run once per workstation, and again whenever Colima or Docker is upgraded.
#
# Usage:
#   bash infra/scripts/setup-colima.sh           # apply config + restart
#   bash infra/scripts/setup-colima.sh --verify  # just check current state

set -euo pipefail

VERIFY_ONLY=false
CPU=4
MEMORY=8
DISK=80

while [[ $# -gt 0 ]]; do
    case "$1" in
        --verify) VERIFY_ONLY=true; shift ;;
        --cpu)    CPU="${2:?}"; shift 2 ;;
        --memory) MEMORY="${2:?}"; shift 2 ;;
        --disk)   DISK="${2:?}"; shift 2 ;;
        *) echo "Unknown flag: $1" >&2; exit 2 ;;
    esac
done

log() { echo "==> $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

command -v colima >/dev/null 2>&1 || fail "colima not installed (brew install colima)"
command -v docker >/dev/null 2>&1 || fail "docker CLI not installed (brew install docker)"

# ── Verify current daemon state ───────────────────────────────────────────────
check_daemon() {
    if ! colima status >/dev/null 2>&1; then
        echo "  ✗ Colima is not running"
        return 1
    fi
    export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"

    local snapshotter
    snapshotter=$(docker info --format '{{.DriverStatus}}' 2>/dev/null || echo "")
    if echo "$snapshotter" | grep -q "containerd.snapshotter"; then
        echo "  ✗ Docker daemon is using the containerd image-store snapshotter"
        echo "    Legacy 'docker build' will fail. Run setup-colima.sh (without --verify) to fix."
        return 1
    fi
    echo "  ✓ Docker daemon snapshotter is OK (no containerd image-store)"
    return 0
}

if [[ "$VERIFY_ONLY" == "true" ]]; then
    log "Verifying Colima daemon configuration"
    check_daemon
    exit $?
fi

# ── Configure colima.yaml ─────────────────────────────────────────────────────
COLIMA_DIR="$HOME/.colima/default"
COLIMA_YAML="$COLIMA_DIR/colima.yaml"

if [[ ! -f "$COLIMA_YAML" ]]; then
    log "No colima.yaml yet — Colima will create one on first start"
    mkdir -p "$COLIMA_DIR"
fi

# Stop Colima before editing config
if colima status >/dev/null 2>&1; then
    log "Stopping Colima before applying config"
    colima stop
fi

# ── Start Colima with the required flags ──────────────────────────────────────
# --docker-opt "features.containerd-snapshotter=false" disables the containerd
# image-store and uses the legacy overlay2 driver, which is what plain
# `docker build` needs.
log "Starting Colima (cpu=$CPU memory=$MEMORY disk=$DISK, containerd-snapshotter=false)"
colima start \
    --cpu "$CPU" \
    --memory "$MEMORY" \
    --disk "$DISK" \
    --runtime docker

# Colima 0.10.x doesn't always honour --docker-opt for nested keys, so write
# the daemon config directly inside the VM and restart Docker.
log "Disabling containerd image-store snapshotter inside the VM"
colima ssh -- sudo bash -c 'cat > /etc/docker/daemon.json' <<'JSON'
{
  "features": {
    "containerd-snapshotter": false
  }
}
JSON
colima ssh -- sudo systemctl restart docker

# Wait for daemon to come back up
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
for i in 1 2 3 4 5 6 7 8 9 10; do
    if docker info >/dev/null 2>&1; then break; fi
    sleep 2
done

# ── Verify ────────────────────────────────────────────────────────────────────
log "Verifying daemon configuration"
if check_daemon; then
    log "Colima is ready for plain 'docker build' (legacy builder path)"
    log "Add to your shell: export DOCKER_HOST=unix://\$HOME/.colima/default/docker.sock"
    exit 0
else
    fail "Colima did not come up with the required configuration. Check 'colima logs'"
fi
