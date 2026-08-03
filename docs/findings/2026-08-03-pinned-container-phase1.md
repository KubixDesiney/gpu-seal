# Finding 002 — pinned release container and Phase 1 controls

**Date:** 2026-08-03  
**Hardware:** researcher-owned NVIDIA GeForce RTX 3050 Laptop GPU  
**Image:** `gpu-seal:0.1.0`  
**Image digest:** `sha256:c6e1d75fb8d7fa360d6d82444f3b406666bff7fedfa5ef060c7063a39c6e69a5`  
**Container commit:** `b30d6735cc0a20df9a598fbd7c8126defa06f73c`

## Release validation

The image uses the digest-pinned CUDA 12.6 base and a Python 3.10 Linux
wheel lock containing 20 packages. Its internal safety gate passed 238 tests.
The image reports `container_profile=pinned` and CUDA 12.6 with one visible
RTX 3050 device.

## Bounded diagnostic battery

Configuration: 8 MiB allocation, 2 cycles per control. The result was signed,
schema-valid, and publishable after the image digest was injected into tool
provenance.

- §9.4 detection capability: **PASS**, 2/2 canaries recovered
- §9.3 driver reuse observation: 0/2 canaries recovered
- Negative zeroisation control: **PASS**, 0 false positives
- Signature verification: **PASS**
- Week 3–4 control criterion: **PASS**

The canonical 64 MiB × 10-cycle battery was started but stopped after more
than 17 minutes without producing a bundle. This is a runtime-performance
limitation of the current small-canary transfer path on Windows/WSL2, not a
control verdict. It must be optimized or rerun with an explicitly documented
longer operating window before being treated as the main Phase 1 bundle.
