# Current release status

**Assessed:** 2026-09-24
**Version:** `0.1.0a1`
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
hardware experiments, and several owner decisions on
[`OWNER-ACTION-CHECKLIST.md`](OWNER-ACTION-CHECKLIST.md) remain open. This is
no longer a gate the automated release check itself is failing: on this
assessment the checkout is clean and `lab/check-release-readiness.py` reports
**RELEASABLE** (see the measured-state table's "Release gate" row). What is
still missing is the owner/external decision queue, not an automated check.

The engineering-owned release-gap architecture is implemented in this
checkout: campaign-wide terminal state, explicit durable signing sources, the
provider runtime boundary with a deterministic fake, action-reference policy,
dependency updates, a branch-coverage margin now measured at 0.12 percentage
points over the required floor (see the coverage row below), and current
setuptools metadata. These are implementation and local-validation
statements, not provider or hardware claims.

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

First recorded 2026-09-20, after the 2026-09-11 assessment above and outside
its verification run; two further deployments followed, the latest on
2026-09-21. The 2026-09-02 baseline authorized no deployment on its own; on
2026-09-20 the project owner directed the dashboard deployed, and it now is,
as Cloudflare Worker `gpu-seal-dashboard` at
<https://gpu-seal-dashboard.gpu-seal.workers.dev>. Three deployments have
shipped from that direction, each adding a route: the home/safety/run pages,
then `/evidence-gallery`, then `/mutation-battery`, so the live site now
serves three routes. The full record of all three deployments -- source
commit, version ID, checks run before deploying, and what was verified
against the live URL for each -- is the deployment record in
[`dashboard/README.md`](../dashboard/README.md#deployment-record); it is not
restated here, and that file is the one to update when a further deployment
ships.

What this changes: a public URL now exists. It has no custom domain and no
Cloudflare Access, so anyone with the link can open it. It ships
`noindex, nofollow` and a disallow-all `robots.txt`, which asks crawlers to
stay away and does not restrict access.

What this does not change:

- it is not a public release: no tag, package, or GitHub Release was made from
  any of the three deployments, and the decision in "Decision in one line"
  above still stands;
- it is not a provider study or a disclosure, and the hosted portal never
  uploads an inspected bundle, runs probes, or presents simulations as
  provider evidence;
- the disclosure, domain, and public-release decisions on the
  [owner checklist](OWNER-ACTION-CHECKLIST.md) remain open. Only the initial
  deployment was approved and ticked there, as its own item;
- structural inspection in the portal is still not cryptographic verification,
  and the banner saying so is served on every page.

## Measured repository state

| Check | Measured result | Meaning |
|---|---|---|
| Full Python suite | **507 passed**, 0 failed, 0 skipped; 49.09 s on Python 3.14.2 | Current local contract is green. CI still exercises Python 3.10-3.12. |
| Test split | **273 safety** + **234 unit** tests collected | The two directories account for all 507 tests. |
| Mutation battery | **40/40 injected violations caught** across 16/16 safety files | `bash lab/verify-safety-suite.sh` run unfiltered, locally, under Git Bash on this Windows host: every injected violation turned the suite red, with 0 skipped and 0 missed. This is a clean local pass -- the pre-existing `%LOCALAPPDATA%\Temp\pytest-of-*` permission issue that previously depressed an unfiltered local run to 37/39 did not recur this time. `lab/check-mutation-coverage.py` confirms the same 40 cases are distributed across all 16/16 safety files and all 9 CI matrix batches. |
| Liveness scorecard | **PASS**: 15 shell scripts parsed, 46 package modules imported, battery preflight passed, 2 reviewed provider records loaded | The checks can start on this checkout. |
| Provider policy matrix | **2 complete**, **2 awaiting review/permission**, 0 incomplete | `provider-a` and `provider-c` are `full-probe-ok`; `provider-b` and `provider-d` remain `needs-written-permission` and are not runnable. |
| External-key CLI verification | **PASS** on a signed quarantined bundle | Schema, canonical payload hash, signature, fingerprint, and embedded-key match validated with a caller-supplied public key. |
| Campaign stop regression | **PASS** | A stop from one runner blocked a separately constructed runner before allocation, native execution, and memory copying; no process-global campaign state is used. |
| Provider runtime contract | **PASS** with deterministic fake | Success, timeout, cleanup reconciliation, signed storage, and skip-after-failure paths are locally validated; no real provider adapter is included. |
| Branch/line coverage | **77.12% branch**, **86.00% line**; required floor **77% branch / 80% line** | Meaningful tests cover CUDA/NVML adapters, memory-local paths, environment collection, device exposure, resources, topology, campaign control, and signing. The branch margin over the floor is now 0.12 percentage points, down from a previous 0.54 -- worth watching, not yet a failure. |
| GitHub Action pin policy | **PASS**; 9 `actions/setup-node` references use one verified full SHA | `actions/setup-node` is pinned to v4.4.0 commit `49933ea5288caeca8642d1e84afbd3f7d6820020`; all workflow action refs (now including `release.yml`'s) are full SHAs. |
| Development advisories | **PASS** (not re-verified this assessment) | Last measured: lockfile updates `browserslist` to 4.28.8, `fast-uri` to 3.1.7, and transitive `fflate` to patched 0.7.5; clean-install audit had 0 vulnerabilities in production or development dependencies. Not one of the checks re-run for this assessment; re-run `npm audit` in `dashboard/` before relying on this line. |
| Dashboard (3 deployments through 2026-09-21) | See the [Dashboard deployment](#dashboard-deployment) section and [`dashboard/README.md`](../dashboard/README.md#deployment-record) for the per-deployment checks and live-URL verification | Not restated here; the record now covers three deployments and three routes (home/safety/run, `/evidence-gallery`, `/mutation-battery`), all product-surface checks, not provider or hardware evidence. |
| Release gate | **RELEASABLE**: content, policy, provenance, quarantine, pre-registration, dist-info, and clean-worktree checks all pass | `lab/check-release-readiness.py` reports every one of its 10 checks passing on this checkout, including the clean-worktree check, which was the sole failure at the prior assessment. This is an engineering gate, not an owner decision; see "Decision in one line" above. |
| Current local smoke | **PASS** on Windows 11: RTX 3050 Laptop GPU, CC 8.6, CuPy 14.1.1, CUDA runtime 12.9, driver 13.010, 1 device | This is researcher-owned local hardware evidence, not provider evidence. |
| Native conformance (pinned container, clean tree) | **PASS**: native canary and safety conformance (10 vectors) + Python safety contract (273 passed) | `.github/workflows/safety.yml`'s `native-container` job built `infrastructure/containers/Dockerfile` from a clean checkout in CI (Ubuntu 24.04 runner, no GPU needed) and ran the identical nvcc/conformance step. Latest run [35985141538](https://github.com/KubixDesiney/gpu-seal/actions/runs/35985141538), job `native conformance container build`, at current `main` tip `51d90d1` (recorded container `git_commit=51d90d16a5f20cd1e76366731128e19196b2a5f1`, an exact match, not a merge commit), base image `nvidia/cuda@sha256:5ca91f87...`, `cuda_archs=80;86;90`. This job builds and conformance-tests the image in CI; it does not push to GHCR. **The separate `container.yml` workflow does that, and its GHCR push has now happened**: run [35914055057](https://github.com/KubixDesiney/gpu-seal/actions/runs/35914055057), built from `main` commit `fe07bc66ed29bdf8864e5e21ce52c75b2c1fb7aa` (the tree at that commit is identical to current `main` tip in every path the image build reads, confirmed by an empty `git diff`), pushed image digest `sha256:5b22604445f6d44680469644cae5dd00b306680740c6313a57db8a0c7fa83359` to `ghcr.io/kubixdesiney/gpu-seal` tagged `release` and `sha-fe07bc66ed29bdf8864e5e21ce52c75b2c1fb7aa`. The package is public: an anonymous, unauthenticated pull of that exact digest from `ghcr.io` returned HTTP 200 during this assessment, so a third party can now independently pull and re-verify the same image a CI log once only asserted. |

The full mutation battery passed under Git Bash on this Windows host. WSL is
not available in the current managed session; Git Bash is sufficient for the
repository harness but does not turn the local Windows GPU result into Linux
evidence.

The full-suite rerun used a workspace-local `--basetemp` because the managed
Windows temporary directory (`%LOCALAPPDATA%\Temp\pytest-of-*`) refused
pytest's own fixture setup with `PermissionError: [WinError 5]` -- an
unfiltered default-tmp run errors out at collection for every test needing
`tmp_path`, not a real test failure. With the workspace-local basetemp, the
rerun completed all 507 test bodies successfully.

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
  pass now (see the measured-state table), and as of this assessment the
  image has also been pushed to GHCR: `container.yml` is on `main`, has run,
  and its GHCR push has been independently confirmed (see the
  "Native conformance" row for the digest and the anonymous-pull check). What
  is still not established is a *Linux-driver hardware run performed inside
  that pinned, published image* -- the real Linux evidence that exists
  (below) ran ad hoc on Colab and Kaggle, not inside `container.yml`'s image,
  so it remains development-grade rather than pinned-image evidence. Four
  runs on 2026-09-15 established the
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
| Linux-driver memory behaviour | **Partially addressed** by [F-001](findings/F-001-linux-driver-residue.md): still needs more than two hosts, more than one GPU architecture, and a run inside the pinned, published `container.yml` image. |
| MIG temporal isolation | Researcher-controlled A100 or H100 MIG instances, with destroy/recreate boundaries recorded separately. |
| H100 confidential-computing attestation and channel binding | H100 confidential-computing hardware plus valid evidence, freshness, reference-match, debug-status, and application-channel checks. |
| Same-model physical-die continuity / D5 | Multiple researcher-controlled instances of one advertised GPU model, with the pre-registered separability thresholds evaluated against known ground truth. |
| Provider isolation or policy compliance | A permitted, bounded run on that provider's owned rental, with current written policy scope and disclosure handling. |

The topology instrument can report consistency with an advertised class; it
does not prove a unique serial, a physical die, a datacentre, or a provider's
truthfulness without the corresponding validation above.

**What "partially addressed" means for the Linux-driver row:** F-001 is two
independent real-hardware Linux runs (`colab-t4`, `kaggle-t4x2`), both Tesla
T4 (compute capability 7.5, the same GPU architecture), both CUDA 13.0
(driver/runtime `13000`/`12090`), on two different driver builds (`580.82.07`
on `colab-t4`, `580.159.04` on `kaggle-t4x2`). Both are development-grade,
not pinned-image evidence: neither ran inside a
`GPU_SEAL_CONTAINER_PROFILE=pinned` build of `container.yml`'s now-published
image, so neither bundle
carries a container digest (`Container digest: none recorded` in both
subsections). What still closes the rest of this row: more than two hosts,
more than one GPU architecture (T4 only so far), and at least one of those
runs executed inside the pinned, published image rather than an ad-hoc
notebook environment -- none of which is a claim this checkout or its CI can
manufacture on its own.

## Owner handoff

The decision list is in [`OWNER-ACTION-CHECKLIST.md`](OWNER-ACTION-CHECKLIST.md).
The tree is clean at this assessment, so the open items are the owner
decisions themselves -- ethics, provider selection, disclosure, and
public-release approval -- not a tree to review first.
