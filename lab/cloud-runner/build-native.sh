#!/usr/bin/env bash
# Build the GPU-SEAL native canary binary on a Linux host with nvcc, and run
# the cross-language conformance gate (lab/check-native-conformance.py)
# against it.
#
#   bash lab/cloud-runner/build-native.sh
#   bash lab/cloud-runner/build-native.sh --full-suite
#
# Written because the native conformance gate has never actually run: the
# Windows development host has no nvcc, so native/gpu_seal_native.cu has only
# ever been read, never compiled. A Colab/Kaggle GPU runtime, or any rented
# Linux GPU box with the CUDA toolkit, can run this directly.
#
# What it does:
#   1. requires nvcc and nvidia-smi; detects the CUDA toolkit release, the
#      driver version, and GPU 0's compute capability;
#   2. compiles native/gpu_seal_native.cu into build/native/gpu-seal-native,
#      targeting the detected compute capability (see the note above the
#      build command below -- this file has no device kernels yet, so the
#      -arch flag is a no-op today and a correctness requirement later);
#   3. runs `python3 lab/check-native-conformance.py` against that binary.
#      Any extra arguments given to this script (e.g. --full-suite) are
#      forwarded to it verbatim;
#   4. on ANY conformance failure, additionally mints the ADR-002 vector
#      itself through the same check module and prints the Python-side
#      expected blob next to the binary's actual --mint output, so a
#      mismatch is visible without re-deriving anything by hand;
#   5. records the toolkit release, driver version, compute capability, the
#      binary's sha256, and the exact build/check command lines into a JSON
#      evidence file under out/native-conformance/.
#
# IMPORTANT -- an ad-hoc pass here is not the publication provenance gate
# -------------------------------------------------------------------------
# A PASS from this script on a bare notebook/VM is evidence that the source
# compiles and matches the Python reference implementation on THAT ad-hoc
# toolkit/driver/compute-capability combination, at THAT commit. It is not
# what CHARTER.md and docs/STATUS.md mean by "native conformance has passed
# in the pinned CUDA build". That gate is specifically: this exact check
# running as a build step *inside* a container built FROM the digest-pinned
# base image in infrastructure/containers/Dockerfile (see that file's
# "Native probe slice (ADR-001)" RUN step, which invokes the identical nvcc
# line and then this identical conformance script before the image is
# considered usable). Only that in-container run has a toolkit/driver/OS
# package set a third party can reproduce byte-for-byte from the pinned
# digest; an ad-hoc notebook's toolkit and driver are whatever that host
# happened to have installed that day.
#
# This script never lets the two be confused: it detects whether it is
# running inside that pinned image (GPU_SEAL_CONTAINER_PROFILE=pinned, set
# only by the Dockerfile) and says so plainly in its own output and in the
# evidence file, either way.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

case "${1:-}" in
  -h|--help)
    cat <<'USAGE'
Usage: bash lab/cloud-runner/build-native.sh [check-native-conformance.py args...]

Requires: nvcc and nvidia-smi on PATH (a CUDA-toolkit Linux host).

Any arguments given are forwarded verbatim to
lab/check-native-conformance.py after --binary <built path>, e.g.:

  bash lab/cloud-runner/build-native.sh --full-suite

Environment overrides:
  NVCC_BIN          nvcc executable to use (default: nvcc)
  GPU_SEAL_SM_ARCH  force the sm_XX target instead of detecting GPU 0's
                    compute capability from nvidia-smi (digits only, e.g. 86)
USAGE
    exit 0
    ;;
esac

NATIVE_SRC="native/gpu_seal_native.cu"
BUILD_DIR="$REPO_ROOT/build/native"
BINARY_PATH="$BUILD_DIR/gpu-seal-native"
EVIDENCE_DIR="$REPO_ROOT/out/native-conformance"
CHECK_ARGS=("$@")

echo
echo "GPU-SEAL native conformance build"
echo "=================================="

# -- 1. toolchain + GPU detection -------------------------------------------

echo
echo "Toolchain detection"
echo "--------------------"

NVCC_BIN="${NVCC_BIN:-nvcc}"
if ! command -v "$NVCC_BIN" >/dev/null 2>&1; then
  echo "ERROR: '$NVCC_BIN' not found on PATH." >&2
  echo "This script requires a Linux host with the CUDA toolkit installed" >&2
  echo "-- a Colab/Kaggle GPU runtime, or a GPU cloud VM. See native/README.md." >&2
  exit 1
fi

if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi not found on PATH, or found but failed to run." >&2
  echo "A visible NVIDIA GPU is required to detect the compute capability" >&2
  echo "to build for." >&2
  exit 1
fi

NVCC_VERSION_RAW="$("$NVCC_BIN" --version 2>/dev/null | tr '\n' ' ')"
TOOLKIT_VERSION="$(printf '%s' "$NVCC_VERSION_RAW" \
  | sed -n 's/.*[Rr]elease \([0-9][0-9.]*\).*/\1/p')"
TOOLKIT_VERSION="${TOOLKIT_VERSION:-unknown}"
echo "  nvcc             : $NVCC_BIN"
echo "  toolkit release  : $TOOLKIT_VERSION"

GPU_ROWS="$(nvidia-smi --query-gpu=index,name,driver_version,compute_cap \
  --format=csv,noheader 2>/dev/null || true)"
if [ -z "$GPU_ROWS" ]; then
  echo "ERROR: nvidia-smi reported zero GPUs. At least one is required." >&2
  exit 1
fi
GPU_COUNT="$(printf '%s\n' "$GPU_ROWS" | grep -c .)"

IFS=',' read -r _GPU0_IDX GPU_MODEL GPU_DRIVER GPU_CC \
  <<<"$(printf '%s\n' "$GPU_ROWS" | head -n1)"
GPU_MODEL="$(printf '%s' "$GPU_MODEL" | sed 's/^ *//;s/ *$//')"
GPU_DRIVER="$(printf '%s' "$GPU_DRIVER" | sed 's/^ *//;s/ *$//')"
GPU_CC="$(printf '%s' "$GPU_CC" | sed 's/^ *//;s/ *$//')"

echo "  GPUs visible     : $GPU_COUNT"
printf '%s\n' "$GPU_ROWS" | while IFS=',' read -r idx name driver cc; do
  printf '    [%s] %s | driver %s | compute capability %s\n' \
    "$(printf '%s' "$idx" | sed 's/^ *//')" \
    "$(printf '%s' "$name" | sed 's/^ *//')" \
    "$(printf '%s' "$driver" | sed 's/^ *//')" \
    "$(printf '%s' "$cc" | sed 's/^ *//')"
done
if [ "$GPU_COUNT" -gt 1 ]; then
  echo "  NOTE: building for GPU 0's compute capability only ($GPU_CC)." >&2
fi

DETECTED_SM_ARCH="$(printf '%s' "$GPU_CC" | tr -d '.')"
if [ -n "${GPU_SEAL_SM_ARCH:-}" ]; then
  SM_ARCH="$GPU_SEAL_SM_ARCH"
  echo "  overriding detected sm_$DETECTED_SM_ARCH with GPU_SEAL_SM_ARCH=$SM_ARCH"
else
  if ! printf '%s' "$DETECTED_SM_ARCH" | grep -qE '^[0-9]+$'; then
    echo "ERROR: could not parse a compute capability from nvidia-smi's" >&2
    echo "output ('$GPU_CC'). Set GPU_SEAL_SM_ARCH=<digits, e.g. 86> to" >&2
    echo "override." >&2
    exit 1
  fi
  SM_ARCH="$DETECTED_SM_ARCH"
fi
echo "  building for     : sm_$SM_ARCH (compute capability $GPU_CC)"

# -- 2. compile --------------------------------------------------------------

echo
echo "Build"
echo "-----"

mkdir -p "$BUILD_DIR"

# gpu_seal_native.cu has no __global__ kernels today -- every CUDA call it
# makes (cudaMalloc, cudaMemcpy, cudaGetDeviceProperties, ...) is host-side
# Runtime API, so -arch does not change what gets generated yet. It is
# included anyway so this build stays aligned with ADR-002's per-GPU-
# generation posture (see infrastructure/containers/Dockerfile's
# GPU_SEAL_CUDA_ARCHS) and so the flag is already correct the day a device
# kernel is added here.
BUILD_CMD=("$NVCC_BIN" -std=c++17 -O2 -Xcompiler -Wall,-Wextra \
  -arch="sm_$SM_ARCH" "$NATIVE_SRC" -o "$BINARY_PATH")
echo "  ${BUILD_CMD[*]}"
if ! "${BUILD_CMD[@]}"; then
  echo "ERROR: nvcc build failed -- see compiler output above." >&2
  exit 1
fi
echo "  built: $BINARY_PATH"

if command -v sha256sum >/dev/null 2>&1; then
  BINARY_SHA256="$(sha256sum "$BINARY_PATH" | awk '{print $1}')"
else
  BINARY_SHA256="$(python3 -c '
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
' "$BINARY_PATH")"
fi
echo "  sha256: $BINARY_SHA256"

# -- 3. conformance -----------------------------------------------------------

echo
echo "Conformance"
echo "-----------"

CHECK_CMD=(python3 lab/check-native-conformance.py --binary "$BINARY_PATH" "${CHECK_ARGS[@]}")
echo "  ${CHECK_CMD[*]}"
echo

CHECK_LOG="$(mktemp)"
trap 'rm -f "$CHECK_LOG"' EXIT
set +e
"${CHECK_CMD[@]}" 2>&1 | tee "$CHECK_LOG"
CHECK_STATUS="${PIPESTATUS[0]}"
set -e

CONFORMANCE_PASSED=true
if [ "$CHECK_STATUS" -ne 0 ]; then
  CONFORMANCE_PASSED=false
  echo
  echo "FAILED (exit $CHECK_STATUS)"
  echo "------------------------------------------------------------"
  echo "Re-minting the ADR-002 vector directly to show the Python-side"
  echo "expected blob next to the native binary's actual --mint output:"
  echo
  # Imports check-native-conformance.py as a module (rather than
  # re-declaring KEY/EXPERIMENT/ALLOCATION/NONCE here) so this comparison
  # can never drift from the actual fixture the gate checks against.
  python3 - "$REPO_ROOT" "$BINARY_PATH" <<'PY'
import importlib.util
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
binary = Path(sys.argv[2])

spec = importlib.util.spec_from_file_location(
    "check_native_conformance", repo_root / "lab" / "check-native-conformance.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

common = [
    "--key", module.KEY.hex(),
    "--experiment", module.EXPERIMENT.hex(),
    "--allocation", module.ALLOCATION.hex(),
    "--boundary", "2",
    "--flags", "0",
    "--nonce", module.NONCE.hex(),
]
expected = module.expected_blob()
try:
    minted = module.run(binary, "--mint", *common)
    actual = minted.get("blob_hex", "<no blob_hex in --mint output>")
except Exception as exc:  # noqa: BLE001 - reporting only, never re-raised
    actual = f"<binary invocation failed: {exc}>"

print(f"  expected (Python, blake2b-keyed, ADR-002) : {expected}")
print(f"  actual   (native binary --mint)           : {actual}")
print(f"  match                                     : {actual == expected}")
PY
  echo
  echo "(If the two match, the failure is elsewhere in the conformance"
  echo "output above -- authentication, SHA-256, or a safety vector -- not"
  echo "the mint vector itself.)"
fi

# -- 4. evidence file ---------------------------------------------------------

echo
echo "Evidence"
echo "--------"

# Same detection order as lab/cloud-runner/bootstrap.sh, deliberately: a
# prior version of that check misread Kaggle as Colab because Kaggle kernel
# images carry a leftover COLAB_RELEASE_TAG from their shared upstream base
# image. Kaggle's own KAGGLE_KERNEL_RUN_TYPE/KAGGLE_URL_BASE must be checked
# first.
case "$(uname -s 2>/dev/null || echo unknown)" in
  Linux)
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

GIT_COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
EVIDENCE_PATH="$EVIDENCE_DIR/native-conformance-$(date -u +%Y%m%dT%H%M%SZ).json"
mkdir -p "$EVIDENCE_DIR"

GPU_SEAL_EV_TOOLKIT="$TOOLKIT_VERSION" \
GPU_SEAL_EV_DRIVER="$GPU_DRIVER" \
GPU_SEAL_EV_CC="$GPU_CC" \
GPU_SEAL_EV_SM_ARCH="sm_$SM_ARCH" \
GPU_SEAL_EV_GPU_MODEL="$GPU_MODEL" \
GPU_SEAL_EV_HOST_KIND="$HOST_KIND" \
GPU_SEAL_EV_PINNED="$RAN_IN_PINNED_CONTAINER" \
GPU_SEAL_EV_SHA256="$BINARY_SHA256" \
GPU_SEAL_EV_BUILD_CMD="${BUILD_CMD[*]}" \
GPU_SEAL_EV_CHECK_CMD="${CHECK_CMD[*]}" \
GPU_SEAL_EV_PASSED="$CONFORMANCE_PASSED" \
GPU_SEAL_EV_COMMIT="$GIT_COMMIT" \
GPU_SEAL_EV_TIMESTAMP="$TIMESTAMP" \
python3 - "$EVIDENCE_PATH" <<'PY'
import json
import os
import sys

path = sys.argv[1]
evidence = {
    "generated_at_utc": os.environ["GPU_SEAL_EV_TIMESTAMP"],
    "git_commit": os.environ["GPU_SEAL_EV_COMMIT"],
    "cuda_toolkit_release": os.environ["GPU_SEAL_EV_TOOLKIT"],
    "gpu_driver_version": os.environ["GPU_SEAL_EV_DRIVER"],
    "gpu_compute_capability": os.environ["GPU_SEAL_EV_CC"],
    "built_for_arch": os.environ["GPU_SEAL_EV_SM_ARCH"],
    "gpu_model": os.environ["GPU_SEAL_EV_GPU_MODEL"],
    "host_kind": os.environ["GPU_SEAL_EV_HOST_KIND"],
    "ran_inside_pinned_container": os.environ["GPU_SEAL_EV_PINNED"] == "true",
    "binary_sha256": os.environ["GPU_SEAL_EV_SHA256"],
    "build_command": os.environ["GPU_SEAL_EV_BUILD_CMD"],
    "check_command": os.environ["GPU_SEAL_EV_CHECK_CMD"],
    "conformance_passed": os.environ["GPU_SEAL_EV_PASSED"] == "true",
    "satisfies_publication_provenance_gate": (
        os.environ["GPU_SEAL_EV_PASSED"] == "true"
        and os.environ["GPU_SEAL_EV_PINNED"] == "true"
    ),
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(evidence, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY

echo "  written to $EVIDENCE_PATH"

# -- 5. ad-hoc vs pinned-container banner ------------------------------------

echo
echo "Publication provenance gate"
echo "----------------------------"
if [ "$RAN_IN_PINNED_CONTAINER" = true ]; then
  echo "  GPU_SEAL_CONTAINER_PROFILE=pinned -- this ran inside the pinned"
  echo "  CUDA image built from infrastructure/containers/Dockerfile."
  if [ "$CONFORMANCE_PASSED" = true ]; then
    echo "  This PASS is the native conformance gate CHARTER.md and"
    echo "  docs/STATUS.md mean by 'native conformance has passed in the"
    echo "  pinned CUDA build'."
  fi
else
  echo "  This is an AD-HOC run: GPU_SEAL_CONTAINER_PROFILE is not 'pinned'"
  echo "  (host kind detected: $HOST_KIND)."
  echo
  echo "  A PASS here shows the source compiles and matches the Python"
  echo "  ADR-002 vector on THIS notebook's toolkit ($TOOLKIT_VERSION) /"
  echo "  driver ($GPU_DRIVER) / compute capability ($GPU_CC). It does NOT"
  echo "  satisfy the publication provenance gate. That gate requires this"
  echo "  identical check to run as a build step of the digest-pinned image"
  echo "  in infrastructure/containers/Dockerfile (its 'Native probe slice"
  echo "  (ADR-001)' RUN step runs the same nvcc line and this same"
  echo "  conformance script before the image is considered usable)."
  echo
  echo "  Build that image instead (bash lab/docker/build.sh release) or run"
  echo "  this script inside it before treating native conformance as"
  echo "  established in docs/STATUS.md."
fi

echo
if [ "$CONFORMANCE_PASSED" = true ]; then
  echo "DONE: conformance PASSED ($([ "$RAN_IN_PINNED_CONTAINER" = true ] && echo "pinned container" || echo "ad-hoc host"))."
else
  echo "DONE: conformance FAILED -- see above. Evidence file still written." >&2
fi
echo "  binary   : $BINARY_PATH"
echo "  evidence : $EVIDENCE_PATH"

if [ "$CONFORMANCE_PASSED" != true ]; then
  exit "$CHECK_STATUS"
fi
