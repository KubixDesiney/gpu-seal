# Finding 002 — pinned release container and Phase 1 controls

**Date:** 2026-08-03  
**Hardware:** researcher-owned NVIDIA GeForce RTX 3050 Laptop GPU  
**Image:** `gpu-seal:0.1.0`  
**Image digest:** `sha256:7e2f0161db995d8ffe7043a6a832a8e7f6eca926f5b43c5f61832745f3b76479`
**Container commit:** `0339eee9a3d901b878833d2cbaf16ddd47efbf9b`

## Release validation

The image uses the digest-pinned CUDA 12.6 base and a Python 3.10 Linux
wheel lock containing 20 packages. Its internal safety gate passed 238 tests
on 2026-08-03, under that image's own Python 3.10 Linux environment and
package lock — a different platform and scope from the Windows/Python 3.14
checkout total tracked in [`docs/STATUS.md`](../STATUS.md), and not expected
to match it. The image reports `container_profile=pinned` and CUDA 12.6 with
one visible RTX 3050 device.

The release image also includes the optimized real-CUDA canary planting path
and the fixed-width exact block-analysis path. The former batches each cycle's
marker placements into one contiguous host-to-device copy; the latter keeps
distinct-block counts exact without constructing a 4,096-field structured
NumPy record for every analysis block.

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
than 17 minutes without producing a bundle. This was a runtime-performance
limitation of the original small-canary transfer and block-analysis paths on
Windows/WSL2, not a control verdict.

## Canonical battery after optimization

Configuration: 64 MiB allocation, 10 cycles per control. Run ID:
`run_20260803T011804Z`. The signed result used the pinned image digest above,
contained 40 probe records, and was publishable.

- §9.4 detection capability: **PASS**, 10/10 canaries recovered
- §9.3 driver reuse observation: 0/10 canaries recovered
- Negative zeroisation control: **PASS**, 0 false positives
- Signature verification: **PASS**
- Week 3–4 control criterion: **PASS**
