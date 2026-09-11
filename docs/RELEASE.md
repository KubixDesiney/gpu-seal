# Release process

GPU-SEAL releases are evidence-bearing research artifacts, not only package
versions. The owner makes the release decision; automation reports facts but
does not approve ethics, disclosure, provider access, or public claims.

## Required sequence

1. Review the [owner checklist](OWNER-ACTION-CHECKLIST.md), the dirty tree, and
   the intended public name/category/platform/trust model.
2. Run the full Python suite, mutation battery, liveness scorecard, link/docs
   check, and dashboard checks from the exact tree.
3. Build the wheel and dashboard artifact. Run
   `lab/check-release-readiness.py --wheel <wheel> --dashboard-dist
   dashboard/dist/client`.
4. Build the pinned CUDA image and run native conformance if the release
   includes native memory execution. A source file or mocked Python test is not
   a native binary validation.
5. Confirm provider policy, ownership, budget, ethics, disclosure, and
   hardware claims separately. Keep unresolved providers blocked.
6. Update [`CHANGELOG.md`](../CHANGELOG.md) and record exact commands/results
   in the release notes.
7. Only the project owner decides whether to tag, publish, deploy, or disclose.

## Automated gate meaning

`lab/check-release-readiness.py` checks citation metadata, lock hashes, the
release base-image digest, clean-tree integrity, provider-policy completeness,
public-tree provider pseudonymisation, quarantined evidence, pre-registration,
and—when paths are supplied—wheel and dashboard artifact integrity.

It does not verify ethics approval, cloud permission, provider measurements,
hardware coverage, independent usability review, billing controls, or the
owner's decision. A dirty-tree failure is intentional: resolve it by reviewing
the changes, then deliberately commit or discard them before a release.
