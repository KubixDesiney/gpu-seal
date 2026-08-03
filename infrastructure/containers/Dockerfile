# GPU-SEAL reproducible probe container
#
# CHARTER.md §11 Phase 1, §14 (reproducible containers), §16 test 10
# (tool + kernel hashes included in every result).
#
# Reproducibility is not a nice-to-have here. A measurement result is only
# evidence if a third party can rebuild the exact tool that produced it, so
# this image pins the base by digest, pins every Python dependency by hash,
# and records the resulting digests into the image itself at /etc/gpu-seal/.
#
# Target hardware for Phase 1: NVIDIA RTX 3050 (Ampere GA10x, compute 8.6).
# Built for sm_86 plus PTX so the same image runs on newer datacentre parts
# in Phase 2 without a rebuild.

# ---------------------------------------------------------------------------
# Base image
#
# Pin by digest, not tag. Tags are mutable; a rebuild six months from now
# against `12.6.2-devel-ubuntu22.04` may not produce the same CUDA toolkit.
#
# To (re)pin:
#   docker pull nvidia/cuda:12.6.2-devel-ubuntu22.04
#   docker inspect --format='{{index .RepoDigests 0}}' nvidia/cuda:12.6.2-devel-ubuntu22.04
# then paste the sha256 below and record it in docs/provenance.
#
# The amd64 manifest digest below is the immutable release input. Updating it
# is a deliberate release change, not something a mutable tag can do behind
# our backs.
# ---------------------------------------------------------------------------
FROM nvidia/cuda@sha256:5ca91f87d9b4e2f2ccdc271f69cf8dc02a6750887cd462a3f84c0fc0bdd7c4a2 AS base

ARG DEBIAN_FRONTEND=noninteractive
# Deterministic timestamps for anything we generate.
ARG SOURCE_DATE_EPOCH=1753747200

LABEL org.opencontainers.image.title="gpu-seal-probe"
LABEL org.opencontainers.image.description="Tenant-side GPU cloud isolation assurance probe. Measurement framework, not an exploitation toolkit."
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/gpu-seal/gpu-seal"

# ---------------------------------------------------------------------------
# System packages
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 \
        python3.10-venv \
        python3-pip \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Python dependencies, pinned by hash
#
# --require-hashes makes pip refuse anything whose artifact hash does not
# match the lock file. Without it, "pinned versions" still trusts PyPI to
# serve the same bytes. That includes pip's own bootstrap: `pip==24.2` alone
# still trusted PyPI to serve those exact bytes for the upgrade itself, ahead
# of the one command in this image actually enforcing hashes. The digest
# below is pip 24.2's published wheel hash
# (https://pypi.org/pypi/pip/24.2/json); pip declares no runtime dependencies
# of its own, so this one hash is the complete requirement set.
# ---------------------------------------------------------------------------
RUN printf 'pip==24.2 --hash=sha256:%s\n' \
        '2cd581cf58ab7fcfca4ce8efa6dcacd0de5bf8d0a3eb9ec927e07405f4d9e2a2' \
        > /tmp/pip-bootstrap.txt \
    && python3 -m pip install --no-cache-dir --require-hashes \
        -r /tmp/pip-bootstrap.txt \
    && rm /tmp/pip-bootstrap.txt

COPY infrastructure/containers/requirements-lock.txt /tmp/requirements-lock.txt
RUN python3 -m pip install --no-cache-dir --require-hashes \
        -r /tmp/requirements-lock.txt \
    && rm /tmp/requirements-lock.txt

# ---------------------------------------------------------------------------
# GPU-SEAL itself
# ---------------------------------------------------------------------------
WORKDIR /opt/gpu-seal
COPY pyproject.toml README.md ./
COPY analysis/ ./analysis/
COPY infrastructure/containers/ ./infrastructure/containers/
COPY probe/ ./probe/
COPY native/ ./native/
COPY schemas/ ./schemas/
COPY lab/ ./lab/
COPY docs/provider-policy-review/ ./docs/provider-policy-review/
COPY tests/ ./tests/
COPY CHARTER.md ETHICS.md DISCLOSURE.md SECURITY.md LICENSE ./

RUN python3 -m pip install --no-cache-dir --no-deps -e .

# ---------------------------------------------------------------------------
# Native probe slice (ADR-001)
#
# The memory-touching path is compiled in the pinned CUDA image. Its
# cross-language canary vector must agree with the Python implementation
# before the image is allowed to run the safety suite.
# ---------------------------------------------------------------------------
RUN mkdir -p /opt/gpu-seal/bin \
    && nvcc -std=c++17 -O2 -Xcompiler -Wall,-Wextra \
        native/gpu_seal_native.cu -o /opt/gpu-seal/bin/gpu-seal-native \
    && python3 lab/check-native-conformance.py \
        --binary /opt/gpu-seal/bin/gpu-seal-native \
        --full-suite

# ---------------------------------------------------------------------------
# CUDA target architectures
#
# 86  = Ampere GA10x  (RTX 3050 — the Phase 1 lab device)
# 80  = Ampere GA100  (A100 — Phase 2/3, MIG-capable)
# 90  = Hopper        (H100/H200 — Phase 3, confidential computing)
# +PTX = forward-compatible JIT for architectures newer than this image
# ---------------------------------------------------------------------------
ENV GPU_SEAL_CUDA_ARCHS="80;86;90"
ENV CUDAARCHS="80;86;90"
ENV TORCH_CUDA_ARCH_LIST="8.0;8.6;9.0+PTX"

# ---------------------------------------------------------------------------
# Build provenance, baked into the image
#
# Every result bundle records these (CHARTER.md §10 reproducibility fields).
# ---------------------------------------------------------------------------
ARG GIT_COMMIT=unknown
ARG BUILD_TIMESTAMP=unknown
RUN mkdir -p /etc/gpu-seal \
    && printf 'git_commit=%s\n' "${GIT_COMMIT}"            >  /etc/gpu-seal/provenance \
    && printf 'build_timestamp=%s\n' "${BUILD_TIMESTAMP}"  >> /etc/gpu-seal/provenance \
    && printf 'cuda_image=%s\n' "nvidia/cuda@sha256:5ca91f87d9b4e2f2ccdc271f69cf8dc02a6750887cd462a3f84c0fc0bdd7c4a2" >> /etc/gpu-seal/provenance \
    && printf 'cuda_archs=%s\n' "${GPU_SEAL_CUDA_ARCHS}"   >> /etc/gpu-seal/provenance \
    && (nvcc --version | tail -2 | tr '\n' ' ' \
        | sed 's/^/nvcc=/' >> /etc/gpu-seal/provenance || true) \
    && printf '\n' >> /etc/gpu-seal/provenance

# ---------------------------------------------------------------------------
# Drop privileges
#
# The probe runs with ordinary tenant privileges (CHARTER.md §6). Running it
# as root inside the container would not grant host access, but it would
# muddy the claim that everything measured is reachable by a normal customer.
# Run as a normal user so the device-exposure inventory (§9.6) reflects what
# an ordinary workload actually sees.
# ---------------------------------------------------------------------------
RUN useradd --create-home --uid 1000 --shell /bin/bash probe \
    && chown -R probe:probe /opt/gpu-seal
USER probe
ENV HOME=/home/probe
ENV PYTHONPATH=/opt/gpu-seal/probe
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONHASHSEED=0

# The one profile ResultBundle.clear_for_publication accepts. Every probe
# record is stamped with it, and a bundle whose probes are stamped anything
# else — the dev image's `dev-unpinned`, or a bare-metal run's `unspecified` —
# is refused for publication. This image is where publishable evidence comes
# from, so it has to say so; without the stamp the hash-pinned image would be
# just as unpublishable as the dev one. See gpu_seal.safety.policy.
# PUBLISHABLE_CONTAINER_PROFILES.
ENV GPU_SEAL_CONTAINER_PROFILE="pinned"

# Fail fast and loudly if someone builds a broken image.
RUN python3 -c "import gpu_seal, gpu_seal.safety; print(gpu_seal.__version__)"

# The safety suite runs inside the image, not just in CI. An image whose
# safety layer does not pass its own tests must never touch a provider.
RUN python3 -m pytest tests/safety -q

ENTRYPOINT ["python3"]
CMD ["-m", "pytest", "tests/safety", "-q"]
