# Changelog

All notable changes to the public repository are recorded here.

## v0.1.0-alpha — 2026-09-12

First tagged release. This tag promotes the 0.1.0.dev0 development snapshot
once the release gate's only open item — a dirty worktree — was resolved; no
probe, safety, or signing source changed as part of the promotion.

**No provider has been measured. No Linux, MIG, or H100 hardware run exists.
This release is the instrument only.** See
[`docs/STATUS.md`](docs/STATUS.md) for the full claim boundary.

User-visible changes carried in from the 0.1.0.dev0 snapshot:

- Reconciled current status around the measured 2026-09-02 repository checks.
- Documented Linux/WSL2 and Windows/PowerShell onboarding, simulation limits,
  external-key verification, and hardware-specific claim boundaries.
- Added contributor, conduct, release, troubleshooting, and owner-handoff
  documentation.
- Corrected the provider-policy status to two complete records and two records
  awaiting written permission.
- Hardened the Windows/WSL safety-harness path handling and made release-check
  status output ASCII-readable on Windows consoles.

Security-impacting changes: none. This tag is a verification checkpoint, not
a code change.

Verification (from commit `fb05adf94b3e151db28787808cc459e32f87ade5`, a clean
worktree; exact commands and verbatim output recorded in
`release-evidence-v0.1.0-alpha.txt`):

| Command | Result |
|---|---|
| `python -m pytest tests -q` | 430 passed |
| `bash lab/verify-safety-suite.sh` | 38/38 injected violations caught |
| `python lab/scorecard.py` | PASS |
| `python lab/check-provider-policy.py` | 2 complete, 2 awaiting review |
| `python lab/check-docs.py` | PASS — 45 files, 141 local links |
| `python lab/check-github-actions.py` | PASS |
| `python lab/check-release-readiness.py` | 9/9 checks pass — RELEASABLE |

Known limits (unchanged from 0.1.0.dev0): no provider has been measured; no
Linux, MIG, or H100 hardware run exists; the native CUDA-container conformance
gate has not been run on this checkout (`nvcc` and a compiled native binary
are unavailable on this Windows host); no external trust-channel validation
of the operator key registry.

Owner gates that remain open before any provider or hardware claim can be
made: ethics approval, provider written permission beyond `provider-a` and
`provider-c`, native-container conformance, and the project owner's release
decision itself (this changelog entry records that the gate passed, not that
the owner has approved publishing, deploying, or disclosing).

## Release-note policy

Each release entry should state the version, date, user-visible changes,
security-impacting changes, verification commands and results, known limits,
and any owner or external-validation gates that remain open. Do not describe a
provider study, ethics approval, or hardware coverage unless the release record
contains the supporting evidence.
