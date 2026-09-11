# Owner diff inclusion map

**Prepared:** 2026-09-02
**Repository:** `https://github.com/KubixDesiney/gpu-seal`

This is a review map, not a staging instruction. No path was staged, committed,
discarded, or deleted while preparing it.

At inventory time, Git reported 141 modified tracked entries and 34 untracked
entries. Content inspection found 79 tracked files with a real diff and 62
tracked files with no content diff (filesystem/index-stat noise). The map
itself is a new untracked file.

## Decision key

| Disposition | Meaning |
|---|---|
| **INCLUDE** | Recommended for the approved GPU-SEAL pre-alpha baseline. |
| **REVIEW** | The owner must make a deliberate choice before staging. The path is preserved. |
| **STATUS-ONLY** | Git reports the path as modified, but `git diff` found no content change. Do not stage it as a content change. |

The approved baseline is GPU-SEAL, tenant-side GPU-cloud assurance and
measurement, integrity plus external-key verification, Windows CUDA as the
exercised path, Linux/WSL2 as a documented target path, and no provider study
or deployment authorization.

## Owner decision required

| Disposition | Path | Reason |
|---|---|---|
| **REVIEW / recommended exclude** | `ghostmeter-project-charter (1).md` | Duplicate v1 charter. The current change replaces 471 lines with an archive pointer. Keep that pointer only if the owner intentionally wants the archival cleanup; otherwise leave the legacy file unchanged. |

## Real content changes: include

### Repository contract and public documentation

| Path | Why include |
|---|---|
| `.github/workflows/safety.yml` | CI safety, coverage, policy, documentation, artifact, and release checks. |
| `.gitignore` | Excludes keys, evidence, environments, build output, and scorecard history. |
| `CHARTER.md` | Governing scope, ethics, claim boundaries, and phase gates. |
| `CITATION.cff` | Correct author and citation metadata. |
| `ETHICS.md` | Enforced canary-only and disclosure rules. |
| `README.md` | Public name, tested onboarding, simulation/CUDA boundary, and first verification. |
| `SECURITY.md` | Security-reporting instructions. |
| `controller/README.md` | Controller refusal gates and operator boundaries. |
| `docs/INDEX.md` | Documentation routing. |
| `docs/PROGRESS.md` | Current implementation progress without stale counts or percentages. |
| `docs/REMAINING.md` | Owner, provider, hardware, and release queue. |
| `docs/adr/001-implementation-language.md` | Native memory-touching boundary and Phase 2 precondition. |
| `docs/colab-t4-smoke-test.md` | Historical managed-notebook record with limits stated. |
| `docs/ethics-review-packet.md` | Ethics material reconciled to the measured suite. |
| `docs/lightning-ai-free-studio-smoke-test.md` | Historical managed-provider inspection with no provider result claimed. |
| `docs/provider-policy-review/README.md` | Current 2-complete/2-awaiting policy explanation. |
| `native/README.md` | Native build/conformance requirements and hardware limits. |

### Packaging, containers, and verification

| Path | Why include |
|---|---|
| `dashboard/.gitignore` | Excludes dashboard build, environment, test, and Wrangler output. |
| `infrastructure/containers/Dockerfile` | Pinned release-container definition. |
| `lab/check-native-conformance.py` | Fail-closed native conformance gate. |
| `lab/check-provider-policy.py` | Provider record status checker. |
| `lab/check-release-readiness.py` | Release integrity gate and artifact checks. |
| `lab/docker/README.md` | Generic Docker/WSL2 setup without maintainer paths. |
| `lab/docker/build.sh` | Reproducible container build helper. |
| `lab/docker/run.sh` | Bounded container execution helper. |
| `lab/local-runner/instrument_check.py` | Local detection-capability check. |
| `lab/local-runner/run_framework_allocator.py` | Framework allocator control. |
| `lab/local-runner/run_phase1.py` | Phase 1 memory control battery. |
| `lab/local-runner/run_phase2_local.py` | Local probe runner with hardware refusals. |
| `lab/local-runner/smoke.py` | Local capability and CUDA smoke report. |
| `lab/verify-safety-suite.sh` | Negative-control mutation battery. |
| `pyproject.toml` | Package metadata, CUDA extra, test, lint, and type configuration. |

### Dashboard and portal

| Path | Why include |
|---|---|
| `dashboard/README.md` | Tested dashboard setup and product boundary. |
| `dashboard/app/dashboard.tsx` | Browser-only inspection surface with approved GPU-SEAL public labels. |
| `dashboard/app/globals.css` | Portal styling and reduced-motion support. |
| `dashboard/app/layout.tsx` | GPU-SEAL metadata and social-card descriptions. |
| `dashboard/package-lock.json` | Reproducible dashboard dependencies. |
| `dashboard/package.json` | Private package metadata and validated scripts; name is `gpu-seal-dashboard`. |
| `dashboard/tsconfig.json` | TypeScript configuration. |
| `dashboard/vite.config.ts` | Tested vinext/Cloudflare-compatible build configuration; inclusion does not authorize deployment. |
| `dashboard/worker/index.ts` | Tested production worker entry point; inclusion does not authorize deployment. |

### Native and Python implementation

| Path | Why include |
|---|---|
| `native/gpu_seal_native.cu` | Native memory-touching slice; source presence is not conformance. |
| `probe/gpu_seal/controller/__init__.py` | Controller exports. |
| `probe/gpu_seal/controller/budget.py` | Budget and duration enforcement. |
| `probe/gpu_seal/controller/disclosure.py` | Disclosure sequencing and publication boundary. |
| `probe/gpu_seal/controller/evidence_store.py` | Safe evidence paths and schema validation. |
| `probe/gpu_seal/controller/native_runner.py` | Native/provider execution boundary. |
| `probe/gpu_seal/controller/scheduler.py` | Bounded experiment scheduling. |
| `probe/gpu_seal/cuda/backend.py` | Real/simulated backend labeling. |
| `probe/gpu_seal/evidence/result.py` | Result bundle and publication gates. |
| `probe/gpu_seal/probes/__init__.py` | Probe exports. |
| `probe/gpu_seal/probes/framework_allocator.py` | Framework allocator control. |
| `probe/gpu_seal/probes/memory_global.py` | Device-global memory probe and controls. |
| `probe/gpu_seal/probes/memory_local.py` | Local/shared memory probe. |
| `probe/gpu_seal/probes/mig_temporal.py` | MIG refusal/reporting path. |
| `probe/gpu_seal/probes/topology.py` | Topology instrument without unique-die overclaim. |
| `probe/gpu_seal/safety/__init__.py` | Safety exports. |
| `probe/gpu_seal/safety/aggregation.py` | Aggregate-only egress and safety stops. |
| `probe/gpu_seal/safety/buffer.py` | Safe-buffer containment. |
| `probe/gpu_seal/safety/canary.py` | Owned-canary generation and exact search. |
| `probe/gpu_seal/safety/errors.py` | Safety error types and fail-closed behavior. |
| `probe/gpu_seal/safety/policy.py` | Safe aggregate allowlist and policy constants. |

### Schemas and tests

| Path | Why include |
|---|---|
| `schemas/experiment.schema.json` | Public experiment schema. |
| `schemas/provider-policy.schema.json` | Public provider-policy schema. |
| `schemas/report-card.schema.json` | Public report-card schema. |
| `schemas/result.schema.json` | Public result and trust fields. |
| `tests/safety/test_canary_ownership.py` | Canary ownership assertions. |
| `tests/safety/test_controller_enforcement.py` | Policy, ownership, budget, and disclosure gates. |
| `tests/safety/test_egress_and_publication.py` | Aggregate-only output and publication refusal. |
| `tests/safety/test_probe_identity_labelling.py` | Probe identity and path labeling. |
| `tests/safety/test_safety_stop_arming.py` | Entropy and safety-stop enforcement. |
| `tests/safety/test_simulated_results_unpublishable.py` | Simulation cannot become hardware evidence. |
| `tests/unit/test_evidence_store.py` | Evidence storage and path traversal behavior. |
| `tests/unit/test_memory_global_probe.py` | Global memory probe behavior. |
| `tests/unit/test_native_runner.py` | Native/provider runner contract. |
| `tests/unit/test_release_gates.py` | Release gate regressions. |
| `tests/unit/test_remaining_probe_families.py` | Unsupported-hardware refusal paths. |
| `tests/unit/test_safety_harness.py` | Fail-closed harness and Windows/WSL path handling. |

## Untracked paths: include

| Path | Why include |
|---|---|
| `.gitattributes` | Prevents Windows line endings from breaking Bash and Docker. |
| `.github/ISSUE_TEMPLATE/bug_report.md` | Structured bug reports. |
| `.github/ISSUE_TEMPLATE/ethics_or_provider.md` | Routes ethics/provider questions safely. |
| `.github/ISSUE_TEMPLATE/feature_request.md` | Structured feature requests. |
| `CHANGELOG.md` | Unreleased changes and release-note policy. |
| `CODE_OF_CONDUCT.md` | Participation standards. |
| `CONTRIBUTING.md` | Contribution workflow and required checks. |
| `dashboard/playwright.config.ts` | Browser verification configuration. |
| `dashboard/tests/browser.spec.ts` | Hydration, evidence inspection, navigation, and accessibility smoke tests. |
| `dashboard/tests/global-setup.ts` | Local production-server lifecycle for browser tests. |
| `dashboard/tests/production-smoke.test.mjs` | Production asset and worker response checks. |
| `dashboard/tools/sites-vite-plugin.ts` | Build-time packaging hook required by the current dashboard configuration; hosting remains unapproved. |
| `docs/OWNER-ACTION-CHECKLIST.md` | Human decisions and external inputs. |
| `docs/OWNER-DIFF-MAP.md` | This file-by-file review map. |
| `docs/RELEASE.md` | Release sequence and automation limits. |
| `docs/STATUS.md` | Measured status and approved working baseline. |
| `docs/TROUBLESHOOTING.md` | Setup, platform, and evidence troubleshooting. |
| `docs/TRUST-MODEL.md` | Structural inspection versus cryptographic verification. |
| `lab/check-coverage.py` | Line and branch coverage floors. |
| `lab/check-docs.py` | Markdown-link and onboarding-placeholder checks. |
| `lab/scorecard.py` | Liveness checks and optional provenance history. |
| `lab/test-installed-wheel.py` | Clean wheel-install validation helper. |
| `probe/gpu_seal/__main__.py` | Python module entry point. |
| `probe/gpu_seal/cli.py` | External-key verification CLI. |
| `probe/gpu_seal/resources.py` | Runtime schema loading from installed packages. |
| `probe/gpu_seal/safety/campaign.py` | Bounded campaign orchestration. |
| `probe/gpu_seal/schemas/experiment.schema.json` | Installed experiment schema. |
| `probe/gpu_seal/schemas/provider-policy.schema.json` | Installed provider-policy schema. |
| `probe/gpu_seal/schemas/report-card.schema.json` | Installed report-card schema. |
| `probe/gpu_seal/schemas/result.schema.json` | Installed result schema. |
| `stubs/cupy/__init__.pyi` | Optional CuPy type stubs. |
| `stubs/cupy/cuda/__init__.pyi` | CUDA type stubs. |
| `tests/unit/test_cli.py` | External-key CLI tests. |
| `tests/unit/test_resources.py` | Installed-schema resource tests. |
| `tests/unit/test_scorecard.py` | Scorecard provenance tests. |

## Status-only tracked paths: do not stage as content changes

These paths are reported by `git status`, but `git diff --name-only` does not
report them. They should not be included as content changes unless a later
owner review finds a deliberate edit. An index refresh may clear the status
after the owner confirms the files are unchanged.

| Path | Disposition |
|---|---|
| `.dockerignore` | **STATUS-ONLY** |
| `.provenance/container-dev.txt` | **STATUS-ONLY** |
| `.provenance/container-release.txt` | **STATUS-ONLY** |
| `analysis/report-generator/generate_report.py` | **STATUS-ONLY** |
| `dashboard/.openai/hosting.json` | **STATUS-ONLY**; hosting metadata remains unapproved |
| `dashboard/app/page.tsx` | **STATUS-ONLY** |
| `dashboard/eslint.config.mjs` | **STATUS-ONLY** |
| `dashboard/next.config.ts` | **STATUS-ONLY** |
| `dashboard/postcss.config.mjs` | **STATUS-ONLY** |
| `dashboard/tests/rendered-html.test.mjs` | **STATUS-ONLY** |
| `docs/adr/003-measurement-path-declared-by-the-backend.md` | **STATUS-ONLY** |
| `docs/architecture.md` | **STATUS-ONLY** |
| `docs/data-handling.md` | **STATUS-ONLY** |
| `docs/findings/2026-07-31-rtx3050-baseline.md` | **STATUS-ONLY** |
| `docs/findings/2026-08-03-pinned-container-phase1.md` | **STATUS-ONLY** |
| `docs/methodology.md` | **STATUS-ONLY** |
| `docs/pre-registration.md` | **STATUS-ONLY** |
| `docs/provider-policy-review/_template.json` | **STATUS-ONLY** |
| `docs/provider-policy-review/provider-a.json` | **STATUS-ONLY** |
| `docs/provider-policy-review/provider-b.json` | **STATUS-ONLY** |
| `docs/provider-policy-review/provider-c.json` | **STATUS-ONLY** |
| `docs/provider-policy-review/provider-d.json` | **STATUS-ONLY** |
| `docs/scoring.md` | **STATUS-ONLY** |
| `docs/threat-model.md` | **STATUS-ONLY** |
| `examples/experiment-cloud.yaml` | **STATUS-ONLY** |
| `examples/experiment-local.yaml` | **STATUS-ONLY** |
| `examples/sample-safe-result.json` | **STATUS-ONLY** |
| `infrastructure/containers/requirements-lock.txt` | **STATUS-ONLY** |
| `lab/check-mutation-coverage.py` | **STATUS-ONLY** |
| `lab/local-runner/run_native_local.py` | **STATUS-ONLY** |
| `lab/regenerate-lock.py` | **STATUS-ONLY** |
| `probe/gpu_seal/analysis/__init__.py` | **STATUS-ONLY** |
| `probe/gpu_seal/analysis/separability.py` | **STATUS-ONLY** |
| `probe/gpu_seal/analysis/statistics.py` | **STATUS-ONLY** |
| `probe/gpu_seal/controller/policy_matrix.py` | **STATUS-ONLY** |
| `probe/gpu_seal/cuda/__init__.py` | **STATUS-ONLY** |
| `probe/gpu_seal/cuda/nvml.py` | **STATUS-ONLY** |
| `probe/gpu_seal/evidence/__init__.py` | **STATUS-ONLY** |
| `probe/gpu_seal/evidence/observation.py` | **STATUS-ONLY** |
| `probe/gpu_seal/evidence/signing.py` | **STATUS-ONLY** |
| `probe/gpu_seal/probes/allocation_model.py` | **STATUS-ONLY** |
| `probe/gpu_seal/probes/attestation.py` | **STATUS-ONLY** |
| `probe/gpu_seal/probes/device_exposure.py` | **STATUS-ONLY** |
| `probe/gpu_seal/probes/environment.py` | **STATUS-ONLY** |
| `probe/gpu_seal/probes/location.py` | **STATUS-ONLY** |
| `probe/gpu_seal/probes/self_canary.py` | **STATUS-ONLY** |
| `probe/gpu_seal/reporting/__init__.py` | **STATUS-ONLY** |
| `probe/gpu_seal/reporting/report_card.py` | **STATUS-ONLY** |
| `probe/gpu_seal/safety/metadata.py` | **STATUS-ONLY** |
| `tests/safety/test_buffer_containment.py` | **STATUS-ONLY** |
| `tests/safety/test_canary_search_index.py` | **STATUS-ONLY** |
| `tests/safety/test_device_exposure_egress.py` | **STATUS-ONLY** |
| `tests/safety/test_measurement_path_gate.py` | **STATUS-ONLY** |
| `tests/safety/test_metadata_decoder.py` | **STATUS-ONLY** |
| `tests/safety/test_observation_and_report_card.py` | **STATUS-ONLY** |
| `tests/safety/test_report_card_gating.py` | **STATUS-ONLY** |
| `tests/safety/test_static_analysis.py` | **STATUS-ONLY** |
| `tests/unit/test_allocation_model_classifier.py` | **STATUS-ONLY** |
| `tests/unit/test_cuda_backend_ownership.py` | **STATUS-ONLY** |
| `tests/unit/test_framework_allocator_probe.py` | **STATUS-ONLY** |
| `tests/unit/test_report_generator_trust.py` | **STATUS-ONLY** |
| `tests/unit/test_topology_and_separability.py` | **STATUS-ONLY** |

## Recommended owner sequence

1. Review the one `REVIEW` path and decide whether its archive-pointer rewrite
   belongs in the baseline.
2. Confirm the `STATUS-ONLY` paths are unchanged; refresh Git's index metadata
   only after that review.
3. Stage only the desired `INCLUDE` paths in a deliberate review operation.
4. Rerun the full test, documentation, dashboard, policy, liveness, and release
   checks from the exact selected tree.
5. Make a separate decision before any commit, push, tag, publication,
   deployment, provider run, or disclosure.

The map does not change the release decision: local code validation is green,
while ethics, provider permission, native/Linux, MIG/H100 CC, same-model,
disclosure, deployment, and public-release decisions remain outside automation.
