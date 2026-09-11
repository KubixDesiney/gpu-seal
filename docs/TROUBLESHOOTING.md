# Troubleshooting and FAQ

## The test count differs from an older document

Use the current checkout, not a badge or an old finding. Run:

```bash
python -m pytest tests -q
```

The dated authoritative result is [`STATUS.md`](STATUS.md). Historic findings
retain the counts from the run they describe and are not current status.

## The simulation passes but is not evidence

That is expected. `--simulate` exercises control flow and publication guards;
its result is marked `backend_is_real=false` and cannot be cleared for
publication. Use `lab/local-runner/smoke.py` to see whether a real local CUDA
backend exists.

## CUDA is unavailable

Install the NVIDIA driver on the Windows host and expose it to WSL2 or Docker
as appropriate. Do not install a Linux NVIDIA driver inside WSL2. Without a
real NVIDIA runtime, use simulation only and do not infer hardware behaviour.

## The native build cannot start

The native slice requires the CUDA toolkit and `nvcc`, normally supplied by the
pinned development container or Linux CI. The current Windows development
path does not include `nvcc`; Python tests do not replace native conformance.

## The provider gate says `GATE: lifted`

That means the matrix has at least one complete record. It is not universal
permission and it is not provider validation. The current matrix has two
complete records and two `needs-written-permission` records that remain
blocked.

## `run_phase2_local.py --help` fails on Windows

Use the current source, where the command-line description is ASCII-safe. If a
different checkout still fails with a UnicodeEncodeError, update it before
running experiments; do not hide the failure by treating a partial run as a
result.

## The release gate reports a dirty tree

This is the expected result for an unreviewed worktree. Inspect `git status
--short`, then have the owner deliberately commit or discard the changes. Do
not bypass the check for convenience.

## What does a dashboard check prove?

It proves only that a browser can inspect the displayed structure. It does not
verify a signature with an external trust anchor or validate a provider. Use
[`TRUST-MODEL.md`](TRUST-MODEL.md) and `gpu-seal verify` with the expected
external Ed25519 public key.
