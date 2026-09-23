# Committed hardware evidence

Result bundles produced by the GPU-SEAL Phase 1 battery on **real GPUs**
(`backend_is_real` is `"true"` in every one). One directory per run:

| Directory | Host | GPU | Files |
|---|---|---|---|
| [`colab-t4-run_20260916T140203Z/`](colab-t4-run_20260916T140203Z/) | Colab notebook | Tesla T4 | the signed bundle, its environment manifest, the public key |
| [`kaggle-t4x2-run_20260919T195043Z/`](kaggle-t4x2-run_20260919T195043Z/) | Kaggle notebook | Tesla T4 (device 0 of 2) | the signed bundle, its environment manifest, the public key |

The finding written from these two bundles is
[`docs/findings/F-001-linux-driver-residue.md`](../../docs/findings/F-001-linux-driver-residue.md).

`tests/unit/test_committed_evidence.py` walks this directory on every test run.
It verifies each bundle against the key in its own directory, checks each one
against the result schema, and requires `backend_is_real` to be `"true"` in the
environment block and in every probe record. It fails on a simulated bundle, an
unsigned or tampered one, an incomplete run directory, or any file it does not
recognise, so nothing lands here without passing.

## Verify a run

Run from the repository root, with `gpu-seal` installed
([REPRODUCE.md](../../REPRODUCE.md) step 1).

**`colab-t4-run_20260916T140203Z`**

```bash
gpu-seal verify examples/evidence/colab-t4-run_20260916T140203Z/run_20260916T140203Z.result.json --public-key examples/evidence/colab-t4-run_20260916T140203Z/ed25519-public-key.hex
```

**`kaggle-t4x2-run_20260919T195043Z`**

```bash
gpu-seal verify examples/evidence/kaggle-t4x2-run_20260919T195043Z/run_20260919T195043Z.result.json --public-key examples/evidence/kaggle-t4x2-run_20260919T195043Z/ed25519-public-key.hex
```

**Expected:** `trusted verification: PASS (...)` and exit code `0`, for each.

## What that command does and does not prove

**A public key committed next to a bundle in the same repository proves
integrity, not provenance.** The command above shows the bundle was not altered
after it was signed by the holder of the key beside it. It cannot show whose
key that is, because whoever could change the bundle could equally have changed
the key file.

Here that is literally the case: each `ed25519-public-key.hex` was **copied out
of the `integrity.public_key` field of the bundle it sits beside**. It is the
key the bundle embeds, put in a file so the CLI can be pointed at it. It did not
come from anywhere else.

The Kaggle run's signing key was generated inside that notebook session by the
run cell, and the private half is not in this repository. That makes it no more
provenance than the Colab key: nothing outside the session vouches for it.

[`docs/TRUST-MODEL.md`](../../docs/TRUST-MODEL.md) draws this distinction; its
words, not a paraphrase:

> For trust in a particular signed bundle, obtain the expected Ed25519 public
> key through an independent trusted channel and pass that key explicitly

> The embedded key alone is not an out-of-band trust anchor.

> A fingerprint read from the same untrusted output is not an out-of-band trust
> anchor.

Applying that to a key committed in this repository is this README's statement,
not a quotation: the key files here, and the fingerprint printed by `gpu-seal
verify`, are not independent anchors either. **A reviewer who wants provenance
must obtain the key through an independent channel**, meaning one that this
repository does not control, and pass that key as `--public-key` in place of the
file above. If it is not the key that signed the bundle, verification fails.
Comparing the fingerprint the command prints
(`trusted_public_key_fingerprint`) against a fingerprint received that way is
the equivalent check.

Even with an independently obtained key, the same document is explicit about
the limit:

> Verification proves integrity and signer-key agreement for the bundle. It does
> not prove that the signer is a provider, that the provider approved the test,
> that the hardware is the claimed model, or that the measurement generalises
> beyond its declared boundary.

## Known defects in these bundles

Both signed bundles in this directory were produced before two bugs in the
local runner were fixed. The bundles are signed, and rewriting them would
break exactly what they prove, so they are not corrected in place -- read
these two fields with the defect in mind rather than at face value.

- **`allocation_model.classification` is `"local_workstation"` in both
  bundles, even though neither host is the researcher's own hardware.**
  `lab/local-runner/run_phase1.py` wrote that value unconditionally,
  regardless of host, so a Colab notebook and a Kaggle notebook were signed as
  if they ran on a laptop. Fixed so that `run_phase1.py` (and
  `lab/local-runner/run_native_local.py`, which had the same defect) detects
  the host first -- reusing the same Kaggle/Colab/GCE environment-variable
  check `lab/cloud-runner/bootstrap.sh` already performs
  (`gpu_seal.probes.host_environment.detect_host_kind`) -- and only records
  `local_workstation` when the host is not one of those. On a recognised
  cloud host it now runs the §9.7 allocation-model classifier against
  whatever tenant-visible signals that host offers, or, if no real device
  backend is available to gather them from, records the explicit
  `not_classified` sentinel with a reason rather than guessing. `lab/summarize-findings.py`'s
  `build_host_report_card` already special-cased `local_workstation` to grade
  U with an honest basis for exactly these two bundles, which is why F-001's
  §13.5 grade below reads as it does; new runs no longer need that special
  case to be accurate.
- **`tool.version` is `"0.1.0.dev0"` in both bundles, while
  `pyproject.toml`'s `version` was already `"0.1.0a1"` by the time these runs
  were taken.** `probe/gpu_seal/__init__.py` hardcoded the stale literal
  instead of reading it from the installed distribution. Fixed to read
  `importlib.metadata.version("gpu-seal")`, with the literal kept only as a
  fallback for a source checkout with no installed distribution.

## Reading a bundle in this directory

- **`environment.json` is a host-side note, not signed.** It is written by
  `lab/cloud-runner/bootstrap.sh` on the machine that ran the battery (host
  kind, GPU driver, Python and CuPy versions, whether it ran in the pinned
  container). The signature covers the result bundle only, so treat the manifest
  as the operator's description of the run.
- **`allocation_model` says `local_workstation` and "researcher-owned
  hardware, not a rented allocation", and that is wrong for both notebook
  hosts** -- see "Known defects in these bundles" above for why, and what
  changed for runs taken after that fix. `provider_code` is likewise the
  fixed `local-lab`, unrelated to that defect. The bundles' `report_card` is
  empty.
- **A managed notebook is not a controlled environment.** For Colab, see the
  limits stated in
  [`docs/colab-t4-smoke-test.md`](../../docs/colab-t4-smoke-test.md); they
  apply equally to the Kaggle run. Each run here shows what the battery
  observed on that host on that day, not anything about a provider's fleet.
- **Both runs are outside the pinned container** (`ran_inside_pinned_container`
  is `false` in each manifest), so neither meets the release-container
  provenance gate.
