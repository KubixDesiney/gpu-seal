# Remaining work

**Snapshot:** 2026-09-04 · companion to [`STATUS.md`](STATUS.md)

This is a decision and validation queue, not a completion estimate. No
percentage is used because the remaining work is not interchangeable: some
items require the project owner, some require another party, and some require
hardware that is not present.

The engineering-owned release-gap implementation is now present and locally
validated: shared campaign terminal state, explicit signing sources and
fingerprints, the provider runtime boundary plus deterministic fake, cleanup
reconciliation and timeouts, mutable-action rejection, requested lockfile
advisory updates, a 77% branch floor, and current license metadata. The items
below are the remaining decisions, external validation, and release-artifact
checks; they are not evidence that the architecture is missing.

## Owner decisions

- Approve or reject the binding unknown-memory security guarantee.
- Review the current dirty tree and deliberately commit or discard its changes.
- Preserve the approved working name, product category, supported platforms,
  and trust model in any release record; the baseline is GPU-SEAL / tenant-side
  assurance / Windows CUDA plus Linux/WSL2 target path /
  integrity-plus-external-key verification.
- Sign the ethics protocol and authorize any provider launch.
- Supply cloud accounts, credentials, budget, billing alerts, and kill switches.
- Approve disclosure, domain, and public-release decisions. (The pre-alpha
  dashboard deployment was approved 2026-09-20; see the checklist.)
- Arrange an independent usability/accessibility review.

The complete checklist is [`OWNER-ACTION-CHECKLIST.md`](OWNER-ACTION-CHECKLIST.md).

## External provider work

- Select the first concrete provider and define the exact permitted API calls,
  regions, instance types, spend ceiling, kill switch, and disclosure path.
- Supply authorized credentials only after that scope is recorded; no adapter
  is included before selection and authorization.
- Obtain written permission for `provider-b` and `provider-d`, record the
  permission references, and re-run `lab/check-provider-policy.py`.
- Keep each provider pseudonymous in public material until the methodology,
  disclosure, and ethics gates allow anything stronger.
- Do not interpret the policy check's `GATE: lifted` output as universal
  authorization. It reflects the two complete records only; the other two
  remain blocked.

## Hardware and study validation

- Run the pinned CUDA/native conformance gate in a supported Linux environment.
- Repeat the memory controls on real Linux-driver hardware.
- Run MIG temporal-isolation boundaries on controlled A100/H100 MIG hardware.
- Run H100 confidential-computing attestation and application-channel-binding
  checks on H100 CC hardware.
- Run the pre-registered same-model die-separation study with multiple owned
  instances of one advertised model.
- Add independent usability/accessibility review before calling the public
  surface ready.

## Release housekeeping

- Re-run the full release gate after the owner has reviewed the tree.
- Build the wheel and dashboard from the exact release tree; run their install,
  asset, browser, lint, type, and dependency checks.
- Keep simulated, bare-metal, and managed-notebook outputs visibly separate
  from pinned publishable evidence.
- Record any provider finding through [`DISCLOSURE.md`](../DISCLOSURE.md)
  before publication.

The project is not release-ready yet because the owner/external queue and
release-artifact checks are still open. The current release-gate failure is the
intentional dirty-tree check, not a hidden Python or action-policy test failure.
