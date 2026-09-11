#!/usr/bin/env bash
# Run the GPU-SEAL probe container with GPU passthrough.
#
#   bash lab/docker/run.sh                     # safety suite (no GPU needed)
#   bash lab/docker/run.sh --gpu smoke         # verify the GPU is visible
#   bash lab/docker/run.sh --gpu phase1        # run the Phase 1 control battery
#   bash lab/docker/run.sh --gpu shell         # interactive
#
# On Windows: run from WSL2 with Docker Desktop's WSL2 backend and the NVIDIA
# Container Toolkit. See lab/docker/README.md.

set -euo pipefail

# Git Bash / MSYS on Windows rewrites POSIX-looking absolute paths in argv
# (e.g. /opt/gpu-seal/out) into bogus Windows paths before docker ever sees
# them, which silently breaks the volume mount and --out argument below. This
# is a no-op under real Linux/WSL2 bash.
export MSYS_NO_PATHCONV=1

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

DOCKER_BIN="${DOCKER_BIN:-docker}"
if ! "$DOCKER_BIN" info --format='{{.ServerVersion}}' >/dev/null 2>&1; then
  if command -v docker.exe >/dev/null 2>&1 \
      && docker.exe info --format='{{.ServerVersion}}' >/dev/null 2>&1; then
    DOCKER_BIN=docker.exe
  else
    echo "ERROR: Docker daemon is unavailable through docker or docker.exe." >&2
    exit 1
  fi
fi

TAG="${GPU_SEAL_IMAGE:-gpu-seal:dev}"
CONTAINER_DIGEST="$("$DOCKER_BIN" image inspect --format='{{.Id}}' "$TAG")"
GPU_FLAGS=()

if [ "${1:-}" = "--gpu" ]; then
  shift
  GPU_FLAGS=(--gpus all)
fi

MODE="${1:-safety}"

mkdir -p "$REPO_ROOT/out"
if command -v cygpath >/dev/null 2>&1; then
  HOST_OUT_DIR="$(cygpath -w "$REPO_ROOT/out")"
elif command -v wslpath >/dev/null 2>&1; then
  # docker.exe is a Windows client. Give it a Windows mount source when this
  # script is running under WSL; passing /mnt/c/... can otherwise create a
  # root-owned or incorrectly resolved mount and the ordinary probe user
  # cannot write its result bundle.
  HOST_OUT_DIR="$(wslpath -w "$REPO_ROOT/out")"
else
  HOST_OUT_DIR="$REPO_ROOT/out"
fi

# Read-only root, no extra capabilities, no privilege escalation.
# The probe runs as an ordinary tenant (CHARTER.md §6) — granting the
# container more than a normal workload would get muddies every §9.6 result.
COMMON=(
  --rm
  --cap-drop=ALL
  --security-opt=no-new-privileges
  -e "GPU_SEAL_CONTAINER_DIGEST=$CONTAINER_DIGEST"
  -v "$HOST_OUT_DIR:/opt/gpu-seal/out"
)

case "$MODE" in
  safety)
    "$DOCKER_BIN" run "${COMMON[@]}" "${GPU_FLAGS[@]+"${GPU_FLAGS[@]}"}" "$TAG" \
      -m pytest tests/safety -q
    ;;
  smoke)
    "$DOCKER_BIN" run "${COMMON[@]}" "${GPU_FLAGS[@]+"${GPU_FLAGS[@]}"}" "$TAG" \
      lab/local-runner/smoke.py
    ;;
  phase1)
    "$DOCKER_BIN" run "${COMMON[@]}" "${GPU_FLAGS[@]+"${GPU_FLAGS[@]}"}" "$TAG" \
      lab/local-runner/run_phase1.py --out /opt/gpu-seal/out
    ;;
  sanitizer)
    # Independent validation of positive controls using NVIDIA's own tool.
    "$DOCKER_BIN" run "${COMMON[@]}" "${GPU_FLAGS[@]+"${GPU_FLAGS[@]}"}" \
      --entrypoint compute-sanitizer "$TAG" \
      --tool initcheck python3 lab/positive-controls/uninitialised_read.py
    ;;
  shell)
    "$DOCKER_BIN" run -it "${COMMON[@]}" "${GPU_FLAGS[@]+"${GPU_FLAGS[@]}"}" \
      --entrypoint /bin/bash "$TAG"
    ;;
  *)
    echo "Usage: $0 [--gpu] [safety|smoke|phase1|sanitizer|shell]"; exit 1 ;;
esac
