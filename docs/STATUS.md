# Current release status

**Assessed:** 2026-09-11
**Version:** `0.1.0.dev0`
**Working public name:** GPU-SEAL
**Internal codename:** GHOSTMETER
**Working product category:** tenant-side GPU-cloud assurance and measurement framework
**Repository:** https://github.com/KubixDesiney/gpu-seal

This is the authoritative status snapshot for the repository. Counts and gate
results below are from the verification run recorded on the assessed date;
they are not a promise that a later checkout has the same result. No composite
completion percentage is used.

## Decision in one line

The instrument and its local safety contract are in active pre-alpha
validation. The project is **not ready for a provider study or public release**
from the current checkout: provider permissions, ethics approval, external
hardware experiments, and owner decisions remain open, and the release gate
also correctly sees the current worktree as dirty.

The engineering-owned release-gap architecture is implemented in this
checkout: campaign-wide terminal state, explicit durable signing sources, the
provider runtime boundary with a deterministic fake, action-reference policy,
dependency updates, coverage margin, and current setuptools metadata. These
are implementation and local-validation statements, not provider or hardware
claims.

## Owner-approved working baseline

On 2026-09-02, the project owner approved the following working direction for
this snapshot:

- public name: **GPU-SEAL**; internal codename: **GHOSTMETER**;
- category: **tenant-side GPU-cloud assurance and measurement framework**;
- trust model: integrity and externally keyed verification of declared
  evidence, without a provider-attestation or generalized hardware-truth
  claim;
- platform posture: Windows CUDA is the currently exercised local path;
  Linux/WSL2 is documented as a target software path; provider, MIG, H100 CC,
  and same-model claims remain experimental until their evidence exists;
- release posture: pre-alpha development snapshot, with no public release,
  deployment, or provider study authorized by this approval alone;
- shared-provider use remains blocked pending the security, policy, ethics,
  ownership, budget, and launch gates.

This records the working direction selected by the owner. It does not record
ethics approval, provider permission, hardware validation, or a decision to
commit, publish, deploy, or disclose the current dirty tree.

## Measured repository state

| Check | Measured result | Meaning |
|---|---|---|
| Full Python suite | **430 passed**, 0 failed, 0 skipped; 47.24 s on Python 3.14.2 | Current local contract is green. CI still exercises Python 3.10-3.12. |
| Test split | **252 safety** + **178 unit** tests collected | The two directories account for all 430 tests. |
| Mutation battery | **38/38 injected violations caught** across 15/15 safety files | The full negative-control battery passed under Git Bash on this Windows host. |
| Liveness scorecard | **PASS**: 3 shell scripts parsed, 44 package modules imported, battery preflight passed, 2 reviewed provider records loaded | The checks can start on this checkout. |
| Provider policy matrix | **2 complete**, **2 awaiting review/permission**, 0 incomplete | `provider-a` and `provider-c` are `full-probe-ok`; `provider-b` and `provider-d` remain `needs-written-permission` and are not runnable. |
| External-key CLI verification | **PASS** on a signed quarantined bundle | Schema, canonical payload hash, signature, fingerprint, and embedded-key match validated with a caller-supplied public key. |
| Campaign stop regression | **PASS** | A stop from one runner blocked a separately constructed runner before allocation, native execution, and memory copying; no process-global campaign state is used. |
| Provider runtime contract | **PASS** with deterministic fake | Success, timeout, cleanup reconciliation, signed storage, and skip-after-failure paths are locally validated; no real provider adapter is included. |
| Branch/line coverage | **77.54% branch**, **86.00% line**; required floor **77% branch / 80% line** | Meaningful tests cover CUDA/NVML adapters, memory-local paths, environment collection, device exposure, resources, topology, campaign control, and signing. |
| GitHub Action pin policy | **PASS**; 8 `actions/setup-node` references use one verified full SHA | `actions/setup-node` is pinned to v4.4.0 commit `49933ea5288caeca8642d1e84afbd3f7d6820020`; all workflow action refs are full SHAs. |
| Development advisories | **PASS** | Lockfile updates `browserslist` to 4.28.8, `fast-uri` to 3.1.7, and transitive `fflate` to patched 0.7.5; clean-install audit has 0 vulnerabilities in production or development dependencies. |
| Release gate | All content, policy, provenance, quarantine, and pre-registration checks pass; **clean-worktree check fails** | The only failure in the gate is the owner-controlled dirty tree. A release tag must be made from a deliberately reviewed clean tree. |
| Current local smoke | **PASS** on Windows 11: RTX 3050 Laptop GPU, CC 8.6, CuPy 14.1.1, CUDA runtime 12.9, driver 13.010, 1 device | This is researcher-owned local hardware evidence, not provider evidence. |

The full mutation battery passed under Git Bash on this Windows host. WSL is
not available in the current managed session; Git Bash is sufficient for the
repository harness but does not turn the local Windows GPU result into Linux
evidence.

The latest full-suite rerun used a workspace-local temporary directory because
the managed Windows temporary directory refused pytest setup with
`WinError 5`. The rerun completed all 430 test bodies successfully.

## What is and is not validated

Implemented and covered by current source/tests:

- canary ownership, safe-buffer containment, aggregate-only egress, safety
  stops, signed result schemas, controller policy/ownership/budget gates,
  measurement-path labelling, report-card gates, external-key verification,
  campaign-wide terminal stop propagation, explicit signing-source handling,
  and provider-runtime orchestration;
- thirteen probe families are represented in the package, with unsupported
  families designed to refuse when their required hardware or experiment is
  absent;
- the C++/CUDA native memory-touching slice and Python controller boundary are
  present in source, and Python tests cover the controller contract.

The repository-owned provider functionality is provider-ready only at the
adapter boundary. The fake runtime validates sequencing and failure handling;
it does not simulate permission, credentials, billing, or provider hardware.

Not established by this checkout or by the local smoke:

- no provider measurement, provider validation, provider response, ethics
  approval, or independent usability/accessibility review;
- no Linux provider run, MIG A100/H100 run, H100 confidential-computing run,
  or same-model multi-instance run;
- native binary conformance now has two real passes, and neither is yet the
  official clean-tree release-provenance pass: `nvcc` and a compiled native
  binary are still not available on this Windows host directly, but two
  external builds exercised the real thing on 2026-09-15.
  1. **Ad-hoc GPU host** --
     [`lab/cloud-runner/build-native.sh`](../lab/cloud-runner/build-native.sh)
     ran on a Google Colab T4 runtime: detected the toolkit and GPU, compiled
     `native/gpu_seal_native.cu`, and ran `lab/check-native-conformance.py`:
     **native canary and safety conformance: PASS (10 vectors)**, CUDA
     toolkit 12.8, driver 580.82.07, Tesla T4 (compute capability 7.5, built
     for `sm_75`), binary sha256
     `1fbc2be33a347dbcb87518fd7a64a4a6e16489f9ae773759181358f9eda1ea56`. The
     script's own evidence file correctly records
     `ran_inside_pinned_container: false` and
     `satisfies_publication_provenance_gate: false`.
  2. **Local pinned-Dockerfile build** -- `docker build -f
     infrastructure/containers/Dockerfile` was run directly against this
     checkout (not through `lab/docker/build.sh release`, and not tagged as a
     release). Inside the pinned image's own build step, the identical nvcc
     line and conformance script produced **native canary and safety
     conformance: PASS (10 vectors)** plus **Python safety contract: PASS
     (449 passed in 21.48s)** on CUDA toolkit 12.6 (V12.6.77, from the
     pinned `nvidia/cuda@sha256:5ca91f...` base image, distinct from Colab's
     12.8), followed by the Dockerfile's separate final `pytest tests/safety`
     step passing 271 tests; `GPU_SEAL_CONTAINER_PROFILE=pinned` was
     confirmed set in the resulting image. **However, this checkout's
     working tree was dirty at build time** (this same STATUS.md edit and
     the new `build-native.sh` were both uncommitted and got copied into the
     build context), so the image's baked-in
     `git_commit=8f4c06e9ebcc27f69b43456855853cbfc9795142` does not exactly
     match the bytes it was built from -- precisely the provenance mismatch
     `lab/docker/build.sh release`'s dirty-tree refusal exists to prevent.
     This local image was deleted after inspection and is not kept as
     evidence; it demonstrates the pinned build mechanism and conformance
     gate work end-to-end, not a citable release artifact. A clean-tree
     build (commit first, then `bash lab/docker/build.sh release`) or the
     existing [`container.yml`](../.github/workflows/container.yml) GHCR
     workflow (`workflow_dispatch`, runs on a GPU-less GitHub runner by the
     same reasoning) is still needed for an artifact this document could
     cite as the publication-gate pass;
- no external trust-channel validation for an operator key registry; the
  fingerprint display and bundle binding are implemented, while the out-of-
  band exchange remains an operational control;
- no cryptographic trust in a dashboard screenshot or structural inspection
  alone. Use the CLI with a trusted public key as described in
  [`TRUST-MODEL.md`](TRUST-MODEL.md).

## Shared-provider stop rule

The policy checker saying `GATE: lifted` means only that at least one complete
policy record exists. It is not permission to run every provider, and it is
not provider validation. Shared-provider use stays **blocked** until all of
the following are true for the exact reviewed tree and artifact:

1. the full safety/unit suite is green;
2. the complete mutation battery catches every listed violation;
3. the liveness and release-artifact checks are green;
4. native conformance has passed in the pinned CUDA build where the native
   memory path is used;
5. the specific provider has a current policy classification, ownership
   confirmation, budget, and any required written permission; and
6. the project owner has approved the ethics and launch decision.

An owner must not infer a provider result from a green local or simulated run.

## Open claim boundaries

| Claim | Minimum additional evidence |
|---|---|
| Linux-driver memory behaviour | A real Linux CUDA run with the positive and negative controls on the target hardware. |
| MIG temporal isolation | Researcher-controlled A100 or H100 MIG instances, with destroy/recreate boundaries recorded separately. |
| H100 confidential-computing attestation and channel binding | H100 confidential-computing hardware plus valid evidence, freshness, reference-match, debug-status, and application-channel checks. |
| Same-model physical-die continuity / D5 | Multiple researcher-controlled instances of one advertised GPU model, with the pre-registered separability thresholds evaluated against known ground truth. |
| Provider isolation or policy compliance | A permitted, bounded run on that provider's owned rental, with current written policy scope and disclosure handling. |

The topology instrument can report consistency with an advertised class; it
does not prove a unique serial, a physical die, a datacentre, or a provider's
truthfulness without the corresponding validation above.

## Owner handoff

The decision list is in [`OWNER-ACTION-CHECKLIST.md`](OWNER-ACTION-CHECKLIST.md).
The owner should review the dirty tree before deciding whether any part of the
current implementation is release material.
