# F-001 — Linux driver memory residue: 2-host Phase 1 battery

**Instrument:** GPU-SEAL Phase 1 control battery (`lab/local-runner/run_phase1.py`), run independently on each host below. Every figure in this document is read directly from that host's signed result bundle; see each host's subsection for the exact bundle file and run ID.

## Headline

Across 2 independent Linux hosts (**colab-t4** (Tesla T4), **kaggle-t4x2** (Tesla T4)) and 20 total §9.3 driver-direct reuse cycles, **0/20 owned canaries were recovered**.

Zero canaries recovered is stated here exactly as plainly as a recovery would have been, and it is not read as either a disappointment or a guarantee: see each host's §9.4 detection-capability control below for why a null result here is informative, and see "What this does not show" for what it does not extend to.

## Known defects in these bundles

Both bundles behind this finding carry two defects from the version of
`lab/local-runner/run_phase1.py` that produced them, and this document is not
regenerated to correct them (see `examples/evidence/README.md`: the signed
bundles are never rewritten). Every figure quoted above and below is
unaffected by either defect -- both are metadata fields, not probe
measurements -- but the report-card line for §13.5 in each host's subsection
reads the way it does because of the first one.

- **`allocation_model.classification` is `"local_workstation"` in both
  bundles**, though neither `colab-t4` nor `kaggle-t4x2` is the researcher's
  own hardware. `run_phase1.py` wrote that value unconditionally, whatever
  host it ran on. This is why each host's §13.5 grade below is U with a basis
  naming the labelling gap rather than a real classification --
  `lab/summarize-findings.py`'s `build_host_report_card` special-cases exactly
  this sentinel for that reason. Fixed so that `run_phase1.py` and
  `lab/local-runner/run_native_local.py` detect the host first (reusing
  `lab/cloud-runner/bootstrap.sh`'s Kaggle/Colab/GCE environment-variable
  check via `gpu_seal.probes.host_environment.detect_host_kind`) and only
  record `local_workstation` when the host is not one of those; a recognised
  cloud host now gets a real §9.7 classification, or an explicit
  `not_classified` value with a reason when no real device backend is
  available to classify from.
- **`tool.version` is `"0.1.0.dev0"` in both bundles**, one alpha behind
  `pyproject.toml`'s `"0.1.0a1"` at the time of these runs.
  `probe/gpu_seal/__init__.py` hardcoded the stale literal instead of reading
  the installed distribution's metadata. Fixed to read
  `importlib.metadata.version("gpu-seal")`.

## Per-host results

### colab-t4

- **Bundle(s):** `run_20260916T140203Z` (`run_20260916T140203Z.result.json`)
- **Device:** Tesla T4, compute capability 7.5
- **Backend:** cupy, container profile `unspecified`
- **CUDA driver / runtime version:** `13000` / `12090`
- **CuPy version:** `14.0.1`
- **Tool version / commit:** `0.1.0.dev0` / `sha256:fc85315b2c0a065659678f4d03b42a5a368e3761`
- **Container digest:** none recorded
- **automatic_publication_allowed (as signed):** False

Baseline (fresh allocation, 10 cycles): zero_fraction min=1.000000 max=1.000000 mean=1.000000.

- **§9.4 detection-capability control:** PASS — 10/10 canaries recovered through the caching allocator (measurement_path: framework_pooled), zero_fraction range 1.000000–1.000000.

- **§9.3 driver-direct measurement (headline):** **0/10 owned canaries recovered** across §9.3 driver-direct reuse cycles (measurement_path: driver_direct). zero_fraction min=1.000000 max=1.000000 mean=1.000000. This null result is informative, not merely absent, because the §9.4 detection-capability control on this host PASSED (10/10 canaries recovered through the caching allocator): the harness is proven able to see a canary it planted, so a clean §9.3 result here means the driver did not hand this canary back, not that the harness is blind.

- **Negative (explicit zeroisation) control:** PASS — 0 false positive(s) of 10 cycles, zero_fraction min=1.000000 max=1.000000 mean=1.000000.

#### Per-probe record (zero_fraction, owned_canary_exact_matches, measurement_path)

| # | Phase | probe_name | boundary | measurement_path | zero_fraction | owned_canary_exact_matches | owned_canary_match |
|---|---|---|---|---|---|---|---|
| 0 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 1 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 2 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 3 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 4 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 5 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 6 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 7 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 8 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 9 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 10 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 11 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 12 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 13 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 14 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 15 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 16 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 17 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 18 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 19 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 20 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 21 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 22 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 23 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 24 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 25 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 26 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 27 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 28 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 29 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 30 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 31 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 32 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 33 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 34 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 35 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 36 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 37 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 38 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 39 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |

#### Report card (CHARTER.md §13) — basis carried through verbatim

- **§13.1 Memory lifecycle hygiene:** **U** — No owned canaries were recovered across 10 cycles, but both allocations advertised the same GPU model, and same-model die separation (§9.8b, contribution D5) is not yet validated — so the topology instrument cannot distinguish the same physical accelerator from a different one of the same model. A clean result on an unknown-possibly-different chip is not evidence of sanitisation. Capping at U rather than A (CHARTER.md §13.1).
- **§13.2 Tenant exposure:** **U** — No exposure observations were collected.
- **§13.3 Hardware claim consistency:** **U** — The topology certificate came from a model rather than silicon and is not evidence about hardware. Instrument: topology certificate reproduced from Alpay & Alpay 2026 (arXiv:2606.24934); it recovers a hardware *class* signature, does not recover a model number, and does not separate two dies of one model (contribution D5, open).
- **§13.4 Location claim consistency:** **U** — Observed network position is not testable with the advertised region over 0 measurement(s). Resolution bound: metropolitan-to-continental only. This grade cannot support a claim about a datacentre, a campus, or a rack.
- **§13.5 Allocation-model transparency:** **U** — allocation_model.classification is 'local_workstation' in this bundle. lab/local-runner/run_phase1.py writes that value unconditionally and does not attempt to classify a rented instance's allocation model, so this is a gap in what the tool attempted here, not evidence about colab-t4's real allocation model.
- **§13.6 Attestation (field report, not a grade):** CHARTER.md §13.6 reports separate fields, not a grade. Attestation assurance does not reduce to one value: evidence can be valid and still not bound to the application channel (CVE-2026-33697).

### kaggle-t4x2

- **Bundle(s):** `run_20260919T195043Z` (`run_20260919T195043Z.result.json`)
- **Device:** Tesla T4, compute capability 7.5
- **Backend:** cupy, container profile `unspecified`
- **CUDA driver / runtime version:** `13000` / `12090`
- **CuPy version:** `14.0.1`
- **Tool version / commit:** `0.1.0.dev0` / `sha256:fc85315b2c0a065659678f4d03b42a5a368e3761`
- **Container digest:** none recorded
- **automatic_publication_allowed (as signed):** False

Baseline (fresh allocation, 10 cycles): zero_fraction min=1.000000 max=1.000000 mean=1.000000.

- **§9.4 detection-capability control:** PASS — 10/10 canaries recovered through the caching allocator (measurement_path: framework_pooled), zero_fraction range 1.000000–1.000000.

- **§9.3 driver-direct measurement (headline):** **0/10 owned canaries recovered** across §9.3 driver-direct reuse cycles (measurement_path: driver_direct). zero_fraction min=1.000000 max=1.000000 mean=1.000000. This null result is informative, not merely absent, because the §9.4 detection-capability control on this host PASSED (10/10 canaries recovered through the caching allocator): the harness is proven able to see a canary it planted, so a clean §9.3 result here means the driver did not hand this canary back, not that the harness is blind.

- **Negative (explicit zeroisation) control:** PASS — 0 false positive(s) of 10 cycles, zero_fraction min=1.000000 max=1.000000 mean=1.000000.

#### Per-probe record (zero_fraction, owned_canary_exact_matches, measurement_path)

| # | Phase | probe_name | boundary | measurement_path | zero_fraction | owned_canary_exact_matches | owned_canary_match |
|---|---|---|---|---|---|---|---|
| 0 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 1 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 2 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 3 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 4 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 5 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 6 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 7 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 8 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 9 | baseline | memory_global_read_before_write | UNSPECIFIED | driver_direct | 1.000000 | 0 | False |
| 10 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 11 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 12 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 13 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 14 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 15 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 16 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 17 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 18 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 19 | detection_control_9_4 | framework_allocator_reuse | SEPARATE_LAUNCH | framework_pooled | 1.000000 | 16 | True |
| 20 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 21 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 22 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 23 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 24 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 25 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 26 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 27 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 28 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 29 | measurement_9_3 | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 30 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 31 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 32 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 33 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 34 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 35 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 36 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 37 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 38 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |
| 39 | negative_control | memory_global_read_before_write | SEPARATE_LAUNCH | driver_direct | 1.000000 | 0 | False |

#### Report card (CHARTER.md §13) — basis carried through verbatim

- **§13.1 Memory lifecycle hygiene:** **U** — No owned canaries were recovered across 10 cycles, but both allocations advertised the same GPU model, and same-model die separation (§9.8b, contribution D5) is not yet validated — so the topology instrument cannot distinguish the same physical accelerator from a different one of the same model. A clean result on an unknown-possibly-different chip is not evidence of sanitisation. Capping at U rather than A (CHARTER.md §13.1).
- **§13.2 Tenant exposure:** **U** — No exposure observations were collected.
- **§13.3 Hardware claim consistency:** **U** — The topology certificate came from a model rather than silicon and is not evidence about hardware. Instrument: topology certificate reproduced from Alpay & Alpay 2026 (arXiv:2606.24934); it recovers a hardware *class* signature, does not recover a model number, and does not separate two dies of one model (contribution D5, open).
- **§13.4 Location claim consistency:** **U** — Observed network position is not testable with the advertised region over 0 measurement(s). Resolution bound: metropolitan-to-continental only. This grade cannot support a claim about a datacentre, a campus, or a rack.
- **§13.5 Allocation-model transparency:** **U** — allocation_model.classification is 'local_workstation' in this bundle. lab/local-runner/run_phase1.py writes that value unconditionally and does not attempt to classify a rented instance's allocation model, so this is a gap in what the tool attempted here, not evidence about kaggle-t4x2's real allocation model.
- **§13.6 Attestation (field report, not a grade):** CHARTER.md §13.6 reports separate fields, not a grade. Attestation assurance does not reduce to one value: evidence can be valid and still not bound to the application channel (CVE-2026-33697).

## What this does not show

Taken verbatim from [`docs/STATUS.md`](../STATUS.md)'s "Open claim boundaries" table. These two Linux-host Phase 1 bundles do not close any of them except the first, and even that one only partially:

- **Linux-driver memory behaviour** — partially addressed, not closed. This finding *is* two independent real-hardware Linux runs with positive and negative controls, which is what STATUS.md asks for as the minimum evidence ("A real Linux CUDA run with the positive and negative controls on the target hardware."); it is still only two hosts, one run apiece, which is not exhaustive coverage of Linux driver/CUDA/CuPy version combinations.
- **MIG temporal isolation** — not addressed. Nothing in this bundle pair speaks to it. Minimum additional evidence per STATUS.md: "Researcher-controlled A100 or H100 MIG instances, with destroy/recreate boundaries recorded separately."
- **H100 confidential-computing attestation and channel binding** — not addressed. Nothing in this bundle pair speaks to it. Minimum additional evidence per STATUS.md: "H100 confidential-computing hardware plus valid evidence, freshness, reference-match, debug-status, and application-channel checks."
- **Same-model physical-die continuity / D5** — not addressed. Nothing in this bundle pair speaks to it. Minimum additional evidence per STATUS.md: "Multiple researcher-controlled instances of one advertised GPU model, with the pre-registered separability thresholds evaluated against known ground truth."
- **Provider isolation or policy compliance** — not addressed. Nothing in this bundle pair speaks to it. Minimum additional evidence per STATUS.md: "A permitted, bounded run on that provider's owned rental, with current written policy scope and disclosure handling."

## Why memory hygiene stays U

Every §13.1 grade above that shows U for that reason is not a weaker result than an A -- it is the correctly capped result. [`docs/scoring.md`](../scoring.md) explains why:

> **U means unproven.** It is the grade for a claim the evidence cannot support —
> often because the *method* cannot support it, not because the provider did
> anything wrong. A provider can score U on §13.1 while behaving perfectly,
> simply because same-model die separation is unsolved.
>
> That distinction is the whole point of the rubric, and it applies to the
> project as much as to a provider.

Concretely: every host below measures a single visible device end to end, so `same_advertised_model` is true for every cycle, but no §9.8 topology certificate exists in a Phase 1 bundle to supply `same_device_evidence`, and same-model die separation (§9.8b, contribution D5) has not landed in this checkout. Memory lifecycle hygiene stays capped at U on real hardware until D5 closes that gap, and [`tests/safety/test_report_card_gating.py`](../../tests/safety/test_report_card_gating.py) (CHARTER.md §16 test 16) is the CI test that stops this cap from being bypassed by a future edit that forgets it. [`tests/safety/test_measurement_path_gate.py`](../../tests/safety/test_measurement_path_gate.py) is the companion test guaranteeing that a §9.4 control result can never be graded as if it were a §9.3 provider finding.

