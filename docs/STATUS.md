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

## Dashboard deployment

Recorded 2026-09-20, after the 2026-09-11 assessment above and outside its
verification run. The 2026-09-02 baseline authorized no deployment on its own;
on 2026-09-20 the project owner directed the dashboard deployed, and it now
is. The `dashboard/` tree at commit `3d50393` is live as Cloudflare Worker
`gpu-seal-dashboard` at <https://gpu-seal-dashboard.gpu-seal.workers.dev>.
The details are in the deployment record in
[`dashboard/README.md`](../dashboard/README.md#deployment-record).

What this changes: a public URL now exists. It has no custom domain and no
Cloudflare Access, so anyone with the link can open it. It ships
`noindex, nofollow` and a disallow-all `robots.txt`, which asks crawlers to
stay away and does not restrict access.

What this does not change:

- it is not a public release: no tag, package, or GitHub Release was made from
  it, and the decision in "Decision in one line" above still stands;
- it is not a provider study or a disclosure, and the hosted portal never
  uploads an inspected bundle, runs probes, or presents simulations as
  provider evidence;
- the disclosure, domain, and public-release decisions on the
  [owner checklist](OWNER-ACTION-CHECKLIST.md) remain open. Only the
  deployment was approved and ticked there, as its own item;
- structural inspection in the portal is still not cryptographic verification,
  and the banner saying so is served on every page.

## Measured repository state

| Check | Measured result | Meaning |
|---|---|---|
| Full Python suite | **430 passed**, 0 failed, 0 skipped; 47.24 s on Python 3.14.2 | Current local contract is green. CI still exercises Python 3.10-3.12. |
| Test split | **252 safety** + **178 unit** tests collected | The two directories account for all 430 tests. |
| Mutation battery | **39/39 injected violations caught** across 16/16 safety files | `lab/check-mutation-coverage.py` had flagged `tests/safety/test_run_budget.py` as the one safety file with zero mutation cases; a case disabling `RunBudget.check()`'s deadline branch was added and confirmed caught, both in isolation (`CASE_FILTER='run budget'`) and inside all 9 CI batches on 2026-09-15 (PR #5, all green). A full unfiltered local run under Git Bash on this Windows host still shows 37/39 -- traced to a pre-existing, access-denied `%LOCALAPPDATA%\Temp\pytest-of-*` directory (predates this session by weeks; `Remove-Item`/`Get-Acl` both denied) poisoning pytest's own tmp fixture for unrelated tests, not a real detection gap. CI's Linux runners do not have this problem, and their green run is the authoritative result. |
| Liveness scorecard | **PASS**: 3 shell scripts parsed, 44 package modules imported, battery preflight passed, 2 reviewed provider records loaded | The checks can start on this checkout. |
| Provider policy matrix | **2 complete**, **2 awaiting review/permission**, 0 incomplete | `provider-a` and `provider-c` are `full-probe-ok`; `provider-b` and `provider-d` remain `needs-written-permission` and are not runnable. |
| External-key CLI verification | **PASS** on a signed quarantined bundle | Schema, canonical payload hash, signature, fingerprint, and embedded-key match validated with a caller-supplied public key. |
| Campaign stop regression | **PASS** | A stop from one runner blocked a separately constructed runner before allocation, native execution, and memory copying; no process-global campaign state is used. |
| Provider runtime contract | **PASS** with deterministic fake | Success, timeout, cleanup reconciliation, signed storage, and skip-after-failure paths are locally validated; no real provider adapter is included. |
| Branch/line coverage | **77.54% branch**, **86.00% line**; required floor **77% branch / 80% line** | Meaningful tests cover CUDA/NVML adapters, memory-local paths, environment collection, device exposure, resources, topology, campaign control, and signing. |
| GitHub Action pin policy | **PASS**; 8 `actions/setup-node` references use one verified full SHA | `actions/setup-node` is pinned to v4.4.0 commit `49933ea5288caeca8642d1e84afbd3f7d6820020`; all workflow action refs are full SHAs. |
| Development advisories | **PASS** | Lockfile updates `browserslist` to 4.28.8, `fast-uri` to 3.1.7, and transitive `fflate` to patched 0.7.5; clean-install audit has 0 vulnerabilities in production or development dependencies. |
| Dashboard (deployed 2026-09-20) | **PASS**: `npm test` 3/3, `test:browser` 3/3, lint and typecheck clean, `npm audit --omit=dev --audit-level=high` 0 vulnerabilities; live URL returns 200 with every referenced asset 200 | Measured on 2026-09-20, after the assessed date. `test:browser` runs against a local production server, not the deployed URL, and uploading a bundle through the deployed UI was not exercised. This is a product-surface check, not provider or hardware evidence. |
| Release gate | All content, policy, provenance, quarantine, and pre-registration checks pass; **clean-worktree check fails** | The only failure in the gate is the owner-controlled dirty tree. A release tag must be made from a deliberately reviewed clean tree. |
| Current local smoke | **PASS** on Windows 11: RTX 3050 Laptop GPU, CC 8.6, CuPy 14.1.1, CUDA runtime 12.9, driver 13.010, 1 device | This is researcher-owned local hardware evidence, not provider evidence. |
| Native conformance (pinned container, clean tree) | **PASS**: native canary and safety conformance (10 vectors) + Python safety contract (449 passed) | `.github/workflows/safety.yml`'s `native-container` job built `infrastructure/containers/Dockerfile` from a clean checkout in CI (Ubuntu 24.04 runner, no GPU needed -- see that job's comment) and ran the identical nvcc/conformance step. [PR #5](https://github.com/KubixDesiney/gpu-seal/pull/5), run [34973650819](https://github.com/KubixDesiney/gpu-seal/actions/runs/34973650819), branch tip `1118bd3` (recorded container `git_commit=d048af5`, the `pull_request` event's merge commit), base image `nvidia/cuda@sha256:5ca91f87...`, `cuda_archs=80;86;90`. This is the citable clean-tree pass the ad-hoc/dirty-tree runs below were building toward; it does not push an image or use `container.yml`/GHCR. |

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
  present in source, Python tests cover the controller contract, and the
  native slice itself now has a confirmed clean-tree pinned-container
  conformance pass (see the measured-state table's "Native conformance"
  row) plus independent ad-hoc passes on real Colab T4 and Kaggle T4x2
  hardware -- all detailed below.

The repository-owned provider functionality is provider-ready only at the
adapter boundary. The fake runtime validates sequencing and failure handling;
it does not simulate permission, credentials, billing, or provider hardware.

Not established by this checkout or by the local smoke:

- no provider measurement, provider validation, provider response, ethics
  approval, or independent usability/accessibility review;
- no Linux provider run, MIG A100/H100 run, H100 confidential-computing run,
  or same-model multi-instance run;
- native binary conformance has a real, citable, clean-tree pinned-container
  pass now (see the measured-state table), but no *published* image: nothing
  has been pushed to GHCR yet. `.github/workflows/container.yml` exists
  (added on this branch, not yet on `main`) and can be dispatched once
  merged, but that step has not been run. Until then there is no image
  digest a third party could pull and independently re-verify -- only the
  CI log of the build above. Four runs on 2026-09-15 established the
  progression: an ad-hoc pass on a Colab T4 (CUDA 12.8, `sm_75`, binary
  sha256 `1fbc2be3...9eda1ea56`, correctly self-reporting
  `satisfies_publication_provenance_gate: false`), a local pinned-Dockerfile
  build from a *dirty* tree (CUDA 12.6, real PASS but non-citable provenance
  since the image's contents didn't match its baked-in `git_commit`), the
  clean-tree CI pass now in the table, and a second independent-host ad-hoc
  pass on a Kaggle T4x2 notebook (CUDA toolkit 12.8, driver 580.159.04,
  `sm_75`, binary sha256 `d548e0b9...3e26ccc`, again correctly
  self-reporting `satisfies_publication_provenance_gate: false`; full
  evidence recorded in
  [`.provenance/native-conformance-kaggle.json`](../.provenance/native-conformance-kaggle.json)).
  The
  Kaggle run used a different provider, host detection path
  (`KAGGLE_KERNEL_RUN_TYPE`/`KAGGLE_URL_BASE`), and driver build than the
  Colab run, so it is corroborating cross-host evidence that the native
  source matches the Python ADR-002 vector -- it is still an ad-hoc host
  pass, not a substitute for the pinned-container gate. `nvcc` and a
  compiled native binary are still not available on this Windows host
  directly;
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
