# Local lab setup — RTX 3050 via Docker Desktop / WSL2

Target: **NVIDIA RTX 3050** (Ampere GA10x, compute capability 8.6), Windows
host, Docker Desktop with the WSL2 backend.

What this hardware can do: Memory Probe B (§9.3), environment inventory (§9.1),
device exposure (§9.6), topology fingerprint reproduction (§9.8), and the full
Phase 1 positive/negative control battery.

What it cannot do: **MIG** (§9.12 — needs A100/H100-class), **confidential
computing attestation** (§9.10 — needs H100+ with TDX/SEV-SNP/CCA),
**same-model die separation** (§9.8b — needs N rented instances of one model).
Those are Phase 2+ and require rented hardware.

---

## 1. Prerequisites on the Windows host

You already have Docker Desktop. You also need:

- **A recent NVIDIA Windows driver.** WSL2 CUDA support comes from the Windows
  driver, not from anything installed inside Linux. Do **not** install a Linux
  NVIDIA driver inside WSL — it will conflict.
- **WSL2 with a distro** (Ubuntu 22.04 recommended).
- **Docker Desktop → Settings → Resources → WSL Integration** enabled for that
  distro.

Verify from inside WSL:

```bash
nvidia-smi
```

If that prints your RTX 3050, the passthrough chain works and everything else
is downhill. If it does not, stop here — nothing below will work.

---

## 2. NVIDIA Container Toolkit inside WSL

Docker needs the toolkit to expose the GPU to containers:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
```

Restart Docker Desktop, then confirm:

```bash
docker run --rm --gpus all nvidia/cuda:12.6.2-base-ubuntu22.04 nvidia-smi
```

> **Keep the toolkit patched.** Three container-escape CVEs in 18 months —
> CVE-2024-0132, CVE-2025-23359, and CVE-2025-23266 ("NVIDIAScape", CVSS 9.0,
> which Wiz found in 37% of cloud environments). GPU-SEAL *inventories* that
> exposure surface in §9.6 and never touches it, but there is no reason to run
> a vulnerable toolkit on your own machine.

---

## 3. Build and run

```bash
cd /path/to/gpu-seal   # replace with the checkout path on this host

bash lab/docker/build.sh dev          # unpinned, works today
bash lab/docker/run.sh --gpu smoke    # what can this machine measure?
bash lab/docker/run.sh --gpu phase1   # the Phase 1 control battery
```

`smoke` prints a capability checklist. `phase1` runs the positive and negative
controls, writes a signed result bundle to `./out/`, and exits non-zero if the
week 3–4 exit criterion is not met.

Also useful:

```bash
bash lab/docker/run.sh --gpu sanitizer   # NVIDIA Compute Sanitizer initcheck
bash lab/docker/run.sh --gpu shell       # poke around
bash lab/docker/run.sh safety            # safety suite, no GPU needed
```

---

## 4. dev vs release image — this matters

| | `Dockerfile.dev` | `Dockerfile` |
|---|---|---|
| Dependencies | resolved at build time | pinned by hash (`--require-hashes`) |
| Reproducible | **no** | yes |
| Results publishable | **no** | yes |
| Use for | getting started, iterating | evidence, Phase 2+ |

The dev image sets `GPU_SEAL_CONTAINER_PROFILE=dev-unpinned`, which is stamped
onto every measurement. `ResultBundle.clear_for_publication()` refuses any
bundle carrying it. That is deliberate: an unreproducible measurement cannot
function as evidence, and "I'll remember to rebuild before publishing" is not
a control.

To move to the release image, generate a real lock file first:

```bash
pip install pip-tools
pip-compile --generate-hashes \
  --output-file=infrastructure/containers/requirements-lock.txt \
  infrastructure/containers/requirements.in
bash lab/docker/build.sh release
```

Then pin the base image by digest — see the comment at the top of the
Dockerfile.

---

## 4a. Running the pinned image on a GPU VM (publication-cleared evidence)

The pinned image (`infrastructure/containers/Dockerfile`) is built and pushed
to GHCR by digest on every change under `infrastructure/containers/`,
`native/`, `probe/`, `lab/`, `schemas/`, and `analysis/` (see
`.github/workflows/container.yml`). `ResultBundle.clear_for_publication()`
only accepts a bundle whose probes are stamped `container_profile: "pinned"`
**and** whose `tool.container_digest` is a well-formed `sha256:<64 hex>`
digest that matches the image that actually produced the run
(`probe/gpu_seal/evidence/result.py`, `probe/gpu_seal/safety/policy.py`). A
GHCR-pulled image, run with the digest wired through as shown below, is what
supplies both.

On a GPU VM where you have root and Docker — a rented instance, not Colab or
Kaggle (see §4b) — pull by digest and run:

```bash
# Replace <digest> with the value printed by the container.yml workflow run
# (job output "digest", or the container-provenance artifact it uploads).
docker pull ghcr.io/kubixdesiney/gpu-seal@sha256:<digest>

docker run --rm --gpus all \
  --cap-drop=ALL --security-opt=no-new-privileges \
  -e GPU_SEAL_CONTAINER_DIGEST="sha256:<digest>" \
  -v "$PWD/out:/opt/gpu-seal/out" \
  ghcr.io/kubixdesiney/gpu-seal@sha256:<digest> \
  lab/local-runner/run_phase1.py --out /opt/gpu-seal/out
```

(This is exactly what `lab/docker/run.sh --gpu phase1` does against a
locally built `gpu-seal:0.1.0` tag — pull by digest instead of building
locally when you want the exact image CI produced and attested, rather than
a local rebuild that merely claims to match it.)

**Prove a bundle produced this way is actually marked pinned** — the
one-liner that reads back what `clear_for_publication()` checks:

```bash
python3 -c "
import json, sys
b = json.load(open(sys.argv[1]))
profiles = [(p.get('driver_metadata') or p.get('operational_metadata') or {}).get('container_profile') for p in b['probes']]
print(profiles, b['tool']['container_digest'])
" out/<bundle>.json
```

Expect `['pinned', ...]` (one entry per probe, all `"pinned"`) and a
`container_digest` of the form `sha256:<64 hex>` matching the digest you
pulled. Any other output — `dev-unpinned`, `unspecified`, `None`, or a digest
mismatch — means the bundle cannot clear `clear_for_publication()`, by design.

**Colab and Kaggle cannot run this image.** Both platforms give you a
notebook kernel inside somebody else's already-running container — never
root, never a Docker daemon, no way to `docker run` anything. There is no
version of "pull the pinned image on Colab." Runs there use whatever CUDA
runtime and driver Google or Kaggle installed that week, are reported by
`probe/gpu_seal/cuda/backend.py` with `container_profile` left unset (or
whatever the notebook's own environment happens to report), and are refused
by the same publication gate for the same reason a bare-metal run is:
no reproducible image, no digest, nothing to rebuild against. **Notebook
runs are development-grade evidence only, and must be labelled that way in
any findings that use them.** Publication-cleared evidence begins on a host
where you have root and Docker — a rented GPU VM or your own workstation —
never on a notebook platform, regardless of which GPU it happens to hand you.

---

## 5. Running without Docker

Docker is not required for the safety suite or for simulated runs:

```bash
pip install --no-build-isolation -e ".[dev]"
pytest tests -q
python3 lab/local-runner/run_phase1.py --simulate --simulate-leaky
```

For real GPU work outside a container you need the CUDA toolkit and
`cupy-cuda12x`. The container exists so you do not have to care what version of
what is installed where — which is the point.

---

## 6. Troubleshooting

**`nvidia-smi` works in WSL but not in the container.** The toolkit is not
wired into Docker's runtime. Re-run `sudo nvidia-ctk runtime configure
--runtime=docker` and restart Docker Desktop.

**`could not select device driver "" with capabilities: [[gpu]]`.** Same cause.

**CuPy imports but `getDeviceCount()` is 0.** Container started without
`--gpus all`. Use `run.sh --gpu`.

**Safety suite fails inside the image but passes on the host.** Do not work
around this. The image build runs the safety suite precisely so a broken image
cannot reach a provider — investigate the failure.

**Phase 1 reports the positive control FAILED on real hardware.** This is
informative, not a crash. It means either the driver zeroes allocations on this
device, or the probe cannot detect reuse here. Either way, no negative result
from this setup means anything until it is understood — that is exactly what
the control is for.
