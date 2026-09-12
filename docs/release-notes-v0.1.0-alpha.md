# GPU-SEAL v0.1.0-alpha — Release Notes

**No provider has been measured. No Linux, MIG, or H100 hardware run exists.
This release is the instrument only** — a tenant-side measurement framework
and its own local safety contract, not a study of any GPU cloud, provider, or
piece of datacentre hardware. Anything that reads like a security finding
about a named provider in this repository is either a pseudonym under
CHARTER.md §7.6 or a researcher-owned laptop GPU result explicitly marked as
non-generalisable. See [`docs/STATUS.md`](STATUS.md) for the authoritative,
line-by-line claim boundary.

## What this release is

GPU-SEAL (internal codename GHOSTMETER) is an open-source, tenant-side
assurance and measurement framework for evaluating *observable* GPU-cloud
isolation controls — memory sanitisation, allocation-model transparency,
device and namespace exposure, physical-hardware consistency, coarse
location, and confidential-computing attestation — using only ordinary
customer privileges, under a strict canary-only data policy. It is an
assurance and measurement instrument, not an exploitation toolkit and not yet
a measurement study of any provider.

## What is verified in this tag

Every check below ran from a clean worktree at commit
`fb05adf94b3e151db28787808cc459e32f87ade5`. Verbatim command output is in
`release-evidence-v0.1.0-alpha.txt` alongside this file.

- Full Python test suite: **430 passed**, 0 failed, 0 skipped.
- Mutation/negative-control battery: **38/38** injected policy violations
  turned the safety suite red (`lab/verify-safety-suite.sh`).
- Liveness scorecard: shell syntax, probe imports (44 modules), battery
  preflight, and provider-matrix loading all **PASS**.
- Provider policy matrix: 2 reviewed records (`provider-a`, `provider-c`),
  2 awaiting written permission (`provider-b`, `provider-d`), 0 incomplete.
- Documentation and link check: **PASS** — 45 Markdown files, 141 local links.
- GitHub Action pin policy: **PASS** — every workflow `uses:` reference is
  pinned to a full commit SHA.
- Release-readiness gate (`lab/check-release-readiness.py`): **9/9 checks
  pass** — citation metadata, container lock file, release base-image digest,
  GitHub Action pins, clean worktree, provider-policy completeness,
  no-named-providers, quarantined-evidence labelling, and measurement
  pre-registration. Gate verdict: **RELEASABLE**.

## What is explicitly NOT established by this release

- No provider measurement, provider validation, provider response, ethics
  approval, or independent usability/accessibility review.
- No Linux-native provider run, no MIG A100/H100 run, no H100
  confidential-computing run, and no same-model multi-instance run.
- No native-binary conformance run in this checkout: `nvcc` and a compiled
  native binary are unavailable on the Windows host this tag was built from.
  The pinned-container native-conformance gate remains an external/CI build
  requirement.
- No external trust-channel validation of an operator key registry. Signed
  bundles verify against a caller-supplied key; the out-of-band exchange of
  that key remains an operational control, not something this software can
  attest to on its own.
- The only local hardware evidence behind this instrument is a
  researcher-owned NVIDIA RTX 3050 Laptop GPU on Windows/WSL2
  (see `docs/findings/2026-07-31-rtx3050-baseline.md` and
  `docs/findings/2026-08-03-pinned-container-phase1.md`). It is one platform,
  measured on hardware the project owner controls, and is explicitly
  documented as not generalisable to Linux, datacentre silicon, or any cloud
  provider.

## Shared-provider use stays blocked

Per `docs/STATUS.md`, running GPU-SEAL against a shared/rented provider
requires, for that specific provider and exact reviewed artifact: a green
full suite and mutation battery, green liveness/release-artifact checks,
a passed native-conformance run in the pinned CUDA image, a current policy
classification with ownership confirmation and budget for that provider, and
the project owner's ethics and launch approval. None of those provider-level
approvals are granted by this tag. A green local or simulated run must never
be read as a provider result.

## How to reproduce this verification

```bash
python -m pytest tests -q
PYTHON_BIN="$(command -v python)" bash lab/verify-safety-suite.sh
python lab/scorecard.py
python lab/check-provider-policy.py
python lab/check-docs.py
python lab/check-github-actions.py
python lab/check-release-readiness.py
```

## Provenance

- Tag: `v0.1.0-alpha`
- Verification ran at commit `fb05adf94b3e151db28787808cc459e32f87ade5`.
- `CITATION.cff` and `pyproject.toml` were bumped from `0.1.0.dev0` to
  `0.1.0-alpha` / `0.1.0a0` (PEP 440 form) in this release commit, so the
  package version string matches the tag.
