# Lightning AI free-tier Studio smoke test

**Date:** 2026-08-03  
**Workspace:** `kubixdesiney-org/inference-optimization-project`  
**Studio:** `inference-devbox`  
**Provider:** Lightning AI

## Observed configuration

- Signed-in Lightning AI account was used.
- The Studio UI displayed the Free tier: one free active Studio, 15 credits, and $0 when nothing is running.
- The Studio UI displayed an interruptible H100 machine (`1 × H100`).
- The UI stated that free Studios become paid after four hours and that interruptible machines receive an 80% discount.

## Result

- **Provider access:** PASS — a real signed-in Lightning Studio was available.
- **Machine selection:** PASS — the UI showed `1 × H100`, interruptible.
- **GPU command verification:** NOT CAPTURED — the embedded terminal did not accept input reliably, so no `nvidia-smi` output is claimed.
- **Cost safety:** PASS — the Studio was explicitly put to sleep after inspection; the UI then showed that it was saving the environment and files.
- **Publishable provider evidence:** NO — this is managed Studio UI evidence, not a signed, pinned Ghost Meter bundle or a completed provider-policy review.

## Cost warning

This is not an unlimited free H100 provider. The Free tier includes limited credits, and leaving a free Studio running beyond the stated free window can become billable. Start the H100 only for a bounded check, then sleep it immediately.

## Follow-up

Before using Lightning data in the project, review its provider policy and classify the permitted probe scope in `docs/provider-policy-review/`. A future run should use the pinned Ghost Meter container and capture a signed result bundle.
