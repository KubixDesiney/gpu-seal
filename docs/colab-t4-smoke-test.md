# Google Colab T4 development smoke test

> Historical development note. This page is not the current status source;
> see [`docs/STATUS.md`](STATUS.md). The managed notebook run does not count as
> provider validation or as a Linux provider experiment.

**Date:** 2026-08-02  
**Status:** development environment verified; not publication evidence

## Observation

A Google Colab Free notebook was configured for a T4 runtime. No project files were uploaded and no paid accelerator was selected.

| Field | Result |
|---|---|
| Runtime | Google Colab managed Python 3 |
| Python | 3.12.13 |
| GPU | NVIDIA Tesla T4 |
| VRAM | 15,360 MiB |
| Driver | 580.82.07 |
| CUDA reported by `nvidia-smi` | 13.0 |
| PyTorch | `cuda_available=True` |
| PyTorch device | `Tesla T4` |

The first automatic runtime was CPU-only and was reset before the T4 test. The final `nvidia-smi` and PyTorch checks passed.

The repository smoke check also passed after cloning the public repository and installing the CUDA extra:

| Check | Result |
|---|---|
| GPU-SEAL version | 0.1.0.dev0 |
| CuPy | 14.0.1 |
| GPU-SEAL backend | `CupyBackend` (`backend_is_real=true`) |
| CUDA runtime / driver | 12.90 / 13.00 |
| Smoke-check exit code | 0 |

The check reported the T4 as capable of exercising the global VRAM, allocator-reuse, environment, exposure, and topology code paths. It correctly left MIG temporal isolation, confidential-computing attestation, and same-model die separation unchecked.

## Interpretation

This provides a no-cost Linux/CUDA environment for smoke-testing CUDA paths and the Python controller. It is not a provider measurement and must not be represented as a publication-cleared evidence bundle.

Colab is a managed notebook runtime. This run does not establish bare-metal ownership, tenant isolation, allocator or driver behavior for a rented provider, MIG temporal isolation, or H100 confidential-computing attestation. Do not use it as evidence for the cross-tenant, temporal-isolation, or attestation claims in the project charter.

The smoke script's default `container profile none (bare metal)` line reflects a missing project environment variable; it is not proof that Colab is bare metal or dedicated.

## Phase 1 attempt

The Phase 1 command was started on the T4 but stopped before any GPU probe ran. The public GitHub clone does not contain the current local `gpu_seal.evidence` package, so `run_phase1.py` failed at import time with `ModuleNotFoundError`. No result bundle was produced and no measurement should be inferred from this attempt.

To run Phase 1 on the T4, the current local workspace must first be synchronized into Colab. The unfinished local changes should be uploaded privately or committed deliberately; they should not be treated as public source merely because the repository's older public clone is available.

The workspace was subsequently synchronized privately into Colab. Phase 1 recognized the real `CupyBackend` on the Tesla T4 and entered the fresh-allocation baseline, but it hung during the first global read-before-write cycle for more than a minute. It never reached the positive or negative controls. The run was interrupted to avoid consuming the free runtime quota; no result bundle or control verdict was produced.

## Minimal diagnostic

To isolate the cause, the same private workspace was rerun with a 1 MiB allocation and one cycle. This completed successfully on the real T4:

| Check | Result |
|---|---|
| Backend | `CupyBackend` (`real=true`) |
| Allocation / cycles | 1 MiB / 1 |
| Detection-capability control | PASS |
| Negative control | PASS |
| Diagnostic exit code | 0 |
| Bundle | `out-diag/run_20260802T122433Z.result.json` (Colab session) |

This narrows the issue to the default Phase 1 workload or its larger raw read path on Colab; it does not validate the full battery. The diagnostic bundle remains development-only because it ran outside the pinned release container and on a managed notebook runtime.

## Next use

Use this runtime for sanitized software checks only:

- run a minimal subset of the project's CUDA smoke tests;
- compare controller behavior under Linux, Python, and CUDA;
- keep all outputs marked development-only.

The pinned native/container conformance run, ethics sign-off, unresolved
provider permissions, and a real Linux/provider or institutional-GPU study
remain outstanding. Current policy counts are in [`docs/STATUS.md`](STATUS.md).
