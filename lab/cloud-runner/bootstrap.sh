#!/usr/bin/env bash
# One command: bare Linux GPU host -> signed GPU-SEAL evidence bundle.
#
#   bash lab/cloud-runner/bootstrap.sh --signing-key ./my-ed25519-private.pem
#   bash lab/cloud-runner/bootstrap.sh --signing-key ./key.pem --cycles 20
#
# Written for Colab, Kaggle, and a GCP A100 VM -- any bare Linux host with an
# NVIDIA GPU and no assumptions about what is already installed. It:
#
#   1. refuses to continue unless nvidia-smi reports at least one real GPU;
#   2. creates a venv and installs the repo with the cuda extra;
#   3. runs the smoke check and hard-stops on anything but a real CuPy device;
#   4. runs Phase 1 (CHARTER.md Sec11/Sec17) with the caller's arguments;
#   5. requires a real signing key -- see "No default signing key" below;
#   6. writes an environment manifest beside the result bundle;
#   7. prints the exact `gpu-seal verify` command for that bundle.
#
# Everything after this script's own flags is forwarded verbatim to
# lab/local-runner/run_phase1.py, so any of its arguments (--simulate,
# --size-mib, --cycles, --max-runtime-s, --out, ...) work here too.
#
# No default signing key
# -----------------------
# This script will not fall back to run_phase1.py's
# --unsafe-development-ephemeral flag on your behalf. Provide
# --signing-key <path> to a real Ed25519 private-key PEM, or, if you
# specifically want a throwaway non-provenance bundle, type
# --unsafe-development-ephemeral yourself among the forwarded arguments.
# That flag must only ever be reachable by a human typing it, never by a
# script's idea of a helpful default.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

usage() {
  cat <<'USAGE' >&2
Usage: bash lab/cloud-runner/bootstrap.sh --signing-key <path> [run_phase1.py args...]

Required:
  --signing-key <path>   Caller-supplied Ed25519 private-key PEM. There is no
                          default; omitting this refuses to run rather than
                          silently signing with a development-ephemeral key.

Forwarded to lab/local-runner/run_phase1.py, with these defaults applied only
when the caller did not already pass them:
  --size-mib 64  --cycles 10  --max-runtime-s 900  --out out

To deliberately bypass the signing-key requirement, pass
--unsafe-development-ephemeral yourself instead of --signing-key.
USAGE
}

if [ "$#" -eq 0 ]; then
  usage
  exit 2
fi

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

# -- helpers over the raw forwarded argument list ---------------------------

has_flag() {
  local needle="$1"; shift
  local arg
  for arg in "$@"; do
    if [ "$arg" = "$needle" ]; then
      return 0
    fi
  done
  return 1
}

flag_value() {
  local needle="$1"; shift
  local prev=""
  local arg
  for arg in "$@"; do
    if [ "$prev" = "$needle" ]; then
      printf '%s' "$arg"
      return 0
    fi
    prev="$arg"
  done
  return 1
}

PHASE1_ARGS=("$@")

# -- 5. require a signing key path, fail fast before touching anything -----

HAS_SIGNING_KEY=0
if has_flag "--signing-key" "${PHASE1_ARGS[@]}"; then
  HAS_SIGNING_KEY=1
fi
HAS_EPHEMERAL=0
if has_flag "--unsafe-development-ephemeral" "${PHASE1_ARGS[@]}"; then
  HAS_EPHEMERAL=1
fi

if [ "$HAS_SIGNING_KEY" -eq 0 ] && [ "$HAS_EPHEMERAL" -eq 0 ]; then
  echo "ERROR: no signing key given. Refusing to run." >&2
  echo "Pass --signing-key <path-to-ed25519-private.pem>." >&2
  echo "If you deliberately want a non-provenance development bundle, type" >&2
  echo "--unsafe-development-ephemeral yourself -- this script will never" >&2
  echo "add it for you." >&2
  exit 1
fi

SIGNING_KEY_PATH=""
if [ "$HAS_SIGNING_KEY" -eq 1 ]; then
  SIGNING_KEY_PATH="$(flag_value "--signing-key" "${PHASE1_ARGS[@]}")"
  if [ -z "$SIGNING_KEY_PATH" ]; then
    echo "ERROR: --signing-key was given with no path." >&2
    exit 1
  fi
  if [ ! -f "$SIGNING_KEY_PATH" ]; then
    echo "ERROR: signing key not found: $SIGNING_KEY_PATH" >&2
    exit 1
  fi
fi
if [ "$HAS_EPHEMERAL" -eq 1 ]; then
  echo "WARNING: --unsafe-development-ephemeral was typed explicitly." >&2
  echo "The resulting bundle carries no provenance and cannot be verified" >&2
  echo "against an external key -- see docs/TRUST-MODEL.md." >&2
fi

# -- 1. refuse to continue unless a real GPU is visible ---------------------

echo
echo "GPU-SEAL cloud bootstrap"
echo "========================"
echo
echo "GPU check"
echo "---------"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi not found on PATH. This script requires an" >&2
  echo "NVIDIA GPU host with drivers installed (Colab/Kaggle GPU runtime," >&2
  echo "or a GPU-attached cloud VM)." >&2
  exit 1
fi

if ! nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi is on PATH but failed to run -- no driver or no" >&2
  echo "GPU is visible to this host/container." >&2
  exit 1
fi

GPU_ROWS="$(nvidia-smi --query-gpu=index,name,driver_version,compute_cap \
  --format=csv,noheader 2>/dev/null || true)"
GPU_COUNT="$(printf '%s\n' "$GPU_ROWS" | grep -c . || true)"

if [ -z "$GPU_ROWS" ] || [ "$GPU_COUNT" -lt 1 ]; then
  echo "ERROR: nvidia-smi reported zero GPUs. At least one is required." >&2
  exit 1
fi

CUDA_VERSION="$(nvidia-smi 2>/dev/null \
  | sed -n 's/.*CUDA Version: *\([0-9.]*\).*/\1/p' | head -n1)"

echo "  GPUs visible     : $GPU_COUNT"
printf '%s\n' "$GPU_ROWS" | while IFS=',' read -r idx name driver cc; do
  printf '    [%s] %s | driver %s | compute capability %s\n' \
    "$(printf '%s' "$idx" | sed 's/^ *//')" \
    "$(printf '%s' "$name" | sed 's/^ *//')" \
    "$(printf '%s' "$driver" | sed 's/^ *//')" \
    "$(printf '%s' "$cc" | sed 's/^ *//')"
done
echo "  CUDA version (nvidia-smi header): ${CUDA_VERSION:-unknown}"

# Fields for the environment manifest (Sec6), taken from GPU 0.
IFS=',' read -r _GPU0_IDX GPU_MODEL GPU_DRIVER GPU_CC <<<"$(printf '%s\n' "$GPU_ROWS" | head -n1)"
GPU_MODEL="$(printf '%s' "$GPU_MODEL" | sed 's/^ *//;s/ *$//')"
GPU_DRIVER="$(printf '%s' "$GPU_DRIVER" | sed 's/^ *//;s/ *$//')"
GPU_CC="$(printf '%s' "$GPU_CC" | sed 's/^ *//;s/ *$//')"

# -- 2. venv + install --------------------------------------------------

echo
echo "Install"
echo "-------"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 \
        && "$candidate" -c 'import sys' >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
fi
if [ -z "$PYTHON_BIN" ]; then
  echo "ERROR: no working Python interpreter found; set PYTHON_BIN." >&2
  exit 1
fi

VENV_DIR="$REPO_ROOT/.venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "  creating venv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR" || true
else
  echo "  reusing existing venv at $VENV_DIR"
fi
VENV_PY="$VENV_DIR/bin/python"

if [ ! -x "$VENV_PY" ] || ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
  # Observed on stock Colab Python: `python -m venv` either fails outright
  # or leaves a venv with no usable pip, because ensurepip's bootstrap is
  # broken there -- even though the system's own pip works fine. Rebuild the
  # venv borrowing the system's site-packages (and its pip) instead of
  # trying to bootstrap a private one; --without-pip skips the broken step.
  echo "  no usable pip in $VENV_DIR (broken ensurepip on this host);" >&2
  echo "  rebuilding with --system-site-packages --without-pip" >&2
  rm -rf "$VENV_DIR"
  "$PYTHON_BIN" -m venv --system-site-packages --without-pip "$VENV_DIR"
  if ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
    echo "ERROR: still no usable pip in $VENV_DIR after the" >&2
    echo "--system-site-packages fallback. This host's Python installation" >&2
    echo "cannot bootstrap pip; install it manually and rerun." >&2
    exit 1
  fi
fi

# A fresh venv on a sufficiently recent Python has no setuptools, and
# --no-build-isolation below needs it present in THIS environment rather
# than pip's disposable build one (see REPRODUCE.md Sec1). Doing this every
# run keeps the script idempotent regardless of how the venv was seeded.
"$VENV_PY" -m pip install --quiet --upgrade pip setuptools wheel

echo "  installing gpu-seal[dev,cuda] (--no-build-isolation)"
"$VENV_PY" -m pip install --no-build-isolation -e ".[dev,cuda]"

# -- 3. smoke check: hard-stop on anything but a real CuPy device -----------

echo
echo "Smoke check"
echo "-----------"

"$VENV_PY" lab/local-runner/smoke.py

if ! "$VENV_PY" -c '
import sys
from gpu_seal.cuda import BackendUnavailable, CupyBackend

try:
    backend = CupyBackend()
except BackendUnavailable as exc:
    print(f"ERROR: no real CUDA backend: {exc}", file=sys.stderr)
    raise SystemExit(1)

info = backend.device_info()
backend.close()
if info.get("backend") != "cupy" or info.get("backend_is_real") != "true":
    print(f"ERROR: backend is not a real CuPy device: {info}", file=sys.stderr)
    raise SystemExit(1)
'; then
  echo "ERROR: simulated backend is a hard stop, not a warning." >&2
  echo "This host is not producing hardware evidence -- see" >&2
  echo "docs/TRUST-MODEL.md and CHARTER.md Sec9.3." >&2
  exit 1
fi

echo "  OK: CupyBackend, backend_is_real=true"

CUPY_VERSION="$("$VENV_PY" -c 'import cupy; print(cupy.__version__)' 2>/dev/null || echo unknown)"
PYTHON_VERSION="$("$VENV_PY" -c 'import platform; print(platform.python_version())')"

# -- 4. Phase 1, caller args passed through with defaults filled in --------

echo
echo "Phase 1"
echo "-------"

PHASE1_DEFAULTS=()
if ! has_flag "--size-mib" "${PHASE1_ARGS[@]}"; then
  PHASE1_DEFAULTS+=(--size-mib 64)
fi
if ! has_flag "--cycles" "${PHASE1_ARGS[@]}"; then
  PHASE1_DEFAULTS+=(--cycles 10)
fi
if ! has_flag "--max-runtime-s" "${PHASE1_ARGS[@]}"; then
  PHASE1_DEFAULTS+=(--max-runtime-s 900)
fi
OUT_DIR="out"
if has_flag "--out" "${PHASE1_ARGS[@]}"; then
  OUT_DIR="$(flag_value "--out" "${PHASE1_ARGS[@]}")"
else
  PHASE1_DEFAULTS+=(--out "$OUT_DIR")
fi
mkdir -p "$OUT_DIR"

PHASE1_LOG="$(mktemp)"
trap 'rm -f "$PHASE1_LOG"' EXIT

set +e
"$VENV_PY" lab/local-runner/run_phase1.py \
  "${PHASE1_ARGS[@]}" "${PHASE1_DEFAULTS[@]}" 2>&1 | tee "$PHASE1_LOG"
PHASE1_STATUS="${PIPESTATUS[0]}"
set -e

if [ "$PHASE1_STATUS" -ne 0 ]; then
  echo
  echo "ERROR: Phase 1 exited with status $PHASE1_STATUS -- no manifest or" >&2
  echo "verify command will be produced for an incomplete/failed run." >&2
  exit "$PHASE1_STATUS"
fi

BUNDLE_PATH="$(sed -n 's/^ *written to *//p' "$PHASE1_LOG" | tail -n1)"
if [ -z "$BUNDLE_PATH" ] || [ ! -f "$BUNDLE_PATH" ]; then
  echo "ERROR: Phase 1 reported success but no bundle path was found in" >&2
  echo "its output; refusing to write a manifest against nothing." >&2
  exit 1
fi

# -- 6. environment manifest, written beside the bundle ---------------------

BUNDLE_DIR="$(dirname "$BUNDLE_PATH")"
BUNDLE_NAME="$(basename "$BUNDLE_PATH")"
RUN_ID="${BUNDLE_NAME%.result.json}"
MANIFEST_PATH="$BUNDLE_DIR/${RUN_ID}.environment.json"

case "$(uname -s 2>/dev/null || echo unknown)" in
  Linux)
    # Kaggle checked before Colab, and on env vars only -- confirmed live
    # on a Kaggle T4x2 notebook that Kaggle's own kernel images carry BOTH
    # a leftover COLAB_RELEASE_TAG and a /content directory from a shared
    # upstream base image, even though the host is genuinely Kaggle; the
    # same live check found /kaggle also exists on genuine Colab, so
    # neither directory is a safe signal for either platform. Only
    # KAGGLE_KERNEL_RUN_TYPE/KAGGLE_URL_BASE (confirmed set on Kaggle,
    # empty on Colab) and COLAB_GPU (confirmed empty on Kaggle) are
    # exclusive enough to trust.
    if [ -n "${KAGGLE_KERNEL_RUN_TYPE:-}${KAGGLE_URL_BASE:-}" ]; then
      HOST_KIND="kaggle"
    elif [ -n "${COLAB_GPU:-}" ] || [ -n "${COLAB_RELEASE_TAG:-}" ]; then
      HOST_KIND="colab"
    elif [ -r /sys/class/dmi/id/product_name ] \
        && grep -qi "Google Compute Engine" /sys/class/dmi/id/product_name 2>/dev/null; then
      HOST_KIND="gce"
    else
      HOST_KIND="other"
    fi
    ;;
  *)
    HOST_KIND="other"
    ;;
esac

if [ "${GPU_SEAL_CONTAINER_PROFILE:-}" = "pinned" ]; then
  RAN_IN_PINNED_CONTAINER=true
else
  RAN_IN_PINNED_CONTAINER=false
fi

TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

GPU_SEAL_MANIFEST_HOST_KIND="$HOST_KIND" \
GPU_SEAL_MANIFEST_GPU_MODEL="$GPU_MODEL" \
GPU_SEAL_MANIFEST_GPU_DRIVER="$GPU_DRIVER" \
GPU_SEAL_MANIFEST_CUDA_RUNTIME="${CUDA_VERSION:-unknown}" \
GPU_SEAL_MANIFEST_CUPY_VERSION="$CUPY_VERSION" \
GPU_SEAL_MANIFEST_PYTHON_VERSION="$PYTHON_VERSION" \
GPU_SEAL_MANIFEST_PINNED_CONTAINER="$RAN_IN_PINNED_CONTAINER" \
GPU_SEAL_MANIFEST_TIMESTAMP="$TIMESTAMP" \
GPU_SEAL_MANIFEST_BUNDLE="$BUNDLE_NAME" \
"$VENV_PY" - "$MANIFEST_PATH" <<'PY'
import json
import os
import sys

path = sys.argv[1]
manifest = {
    "host_kind": os.environ["GPU_SEAL_MANIFEST_HOST_KIND"],
    "gpu_model": os.environ["GPU_SEAL_MANIFEST_GPU_MODEL"],
    "gpu_driver_version": os.environ["GPU_SEAL_MANIFEST_GPU_DRIVER"],
    "cuda_runtime_version": os.environ["GPU_SEAL_MANIFEST_CUDA_RUNTIME"],
    "cupy_version": os.environ["GPU_SEAL_MANIFEST_CUPY_VERSION"],
    "python_version": os.environ["GPU_SEAL_MANIFEST_PYTHON_VERSION"],
    "ran_inside_pinned_container": os.environ["GPU_SEAL_MANIFEST_PINNED_CONTAINER"] == "true",
    "generated_at_utc": os.environ["GPU_SEAL_MANIFEST_TIMESTAMP"],
    "bundle": os.environ["GPU_SEAL_MANIFEST_BUNDLE"],
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY

echo
echo "Environment manifest"
echo "---------------------"
echo "  written to $MANIFEST_PATH"

# -- 7. print the exact verify command ---------------------------------

echo
echo "Verify"
echo "------"

if [ -n "$SIGNING_KEY_PATH" ]; then
  PUBLIC_KEY_HEX="$(GPU_SEAL_SIGNING_KEY_PATH="$SIGNING_KEY_PATH" "$VENV_PY" -c '
import os
from gpu_seal.evidence.signing import SigningKey

with open(os.environ["GPU_SEAL_SIGNING_KEY_PATH"], "rb") as fh:
    key = SigningKey.from_pem(fh.read())
print(key.verify_key.hex)
')"
  echo "  gpu-seal verify $BUNDLE_PATH --public-key $PUBLIC_KEY_HEX"
  echo
  echo "  (that hex string is the PUBLIC half of the key you supplied --"
  echo "  the private PEM at $SIGNING_KEY_PATH was never read by anything"
  echo "  other than this signing step. Obtain the key you actually trust"
  echo "  through a channel independent of this bundle before treating any"
  echo "  verify result as evidence -- see docs/TRUST-MODEL.md.)"
else
  echo "  No external public key to verify against: this run used"
  echo "  --unsafe-development-ephemeral, whose key existed only in-process"
  echo "  and was never persisted. This bundle is not provenance evidence."
fi

echo
echo "DONE"
echo "  bundle   : $BUNDLE_PATH"
echo "  manifest : $MANIFEST_PATH"
