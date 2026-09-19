# Reproducing GPU-SEAL's claims

This page is for a reader who has not touched this repository and does not
believe a README. It gives the exact commands to independently check, on a
machine with **no GPU**, that:

1. the software installs and its test suite is green;
2. the safety suite's negative control actually catches known violations,
   rather than always passing;
3. the release and provider-policy gates say what this page says they say;
4. a signed evidence bundle can be verified with a public key *you* hold, not
   one the repository hands you; and
5. a "simulated" result is unambiguously marked as such and cannot pass the
   tool's own publication gate; and
6. a committed bundle from a **real GPU** verifies, and is guarded against
   being replaced by a simulated one.

Total time: about ten minutes, except step 3's full (unsharded) run, which is
slow by design and is called out separately.

This page does **not** verify any claim about a cloud provider or physical
GPU — see [What this does NOT prove](#what-this-does-not-prove) at the end,
and [`docs/STATUS.md`](docs/STATUS.md) for the dated, authoritative snapshot
this page's numbers are drawn from.

Commands below are Bash (Git Bash on Windows, or a real shell on Linux/macOS/
WSL2), because step 3's `verify-safety-suite.sh` needs Bash regardless of
platform. The `python`/`gpu-seal` invocations in every other step are shell-
agnostic and also work from PowerShell as-is; only the plain shell plumbing
around them (`.` to activate, `grep`) is Bash-specific — see
[README.md § Quickstarts](README.md#quickstarts) for the PowerShell forms of
steps 1, 2, and 4 if that's your only shell.

---

## 1. Clone and install into a fresh virtualenv

```bash
git clone https://github.com/KubixDesiney/gpu-seal.git
cd gpu-seal
python -m venv .venv
. .venv/Scripts/activate      # Linux/macOS/WSL2: . .venv/bin/activate
python -m pip install -e ".[dev]"
```

**Expected:** pip resolves and builds roughly two dozen packages, ending with
a line similar to:

```
Successfully installed ... gpu-seal-0.1.0a1 ...
```

Leave build isolation **on** (i.e. do not add `--no-build-isolation`, even
though you may see it elsewhere in this repo's own docs) unless you already
know your virtualenv has `setuptools` in it. A fresh `python -m venv` on a
sufficiently recent Python no longer bundles `setuptools` automatically, and
installing with `--no-build-isolation` into such a venv fails immediately
with `BackendUnavailable: Cannot import 'setuptools.build_meta'` —
reproduced on this page's own verification run, on a stock fresh venv,
Python 3.14.2. The plain command above sidesteps this entirely: pip builds
in its own disposable environment and fetches `setuptools` there regardless
of what your venv has.

## 2. Run the test suite

```bash
python -m pytest tests -q
```

**Expected:** `430 passed` in well under a minute (43–50 s on the machine
this page was verified on). No failures, no skips. This is the same figure
[`docs/STATUS.md`](docs/STATUS.md) records for the 2026-09-11/12 snapshot;
a later checkout may show a different count if tests were added.

If you instead get a `PermissionError` naming a stale `pytest-of-<you>`
directory under your OS temp folder, that is leftover state from an earlier
pytest run on *your* machine, not a repository problem — point pytest at a
clean directory and retry, e.g.:

```bash
TMP=/tmp/gpu-seal-pytest TEMP=/tmp/gpu-seal-pytest python -m pytest tests -q
```

## 3. Run the mutation battery (prove the safety suite can fail)

A green safety suite proves nothing by itself — a suite that always passes
isn't testing anything. `lab/verify-safety-suite.sh` copies the repo to a
scratch directory, injects 38 known policy violations one at a time, and
checks that every single one turns the suite red.

```bash
PYTHON_BIN="$(command -v python)" bash lab/verify-safety-suite.sh
```

**Expected**, as the final lines:

```
caught 38 / 38 injected violations
OK: every injected violation turned the suite red.
```

Exit code `0`.

This is slow **by design**: each of the 38 cases makes its own scratch copy
of the repo and reruns the safety + unit suites against it. On the Windows/
Git-Bash host this page was verified on, a single case takes 40–50 seconds,
so the unsharded run above takes roughly half an hour. CI gets its answer
faster only because it splits the same 38 cases across 9 parallel jobs (see
the `matrix.batch` list in
[`.github/workflows/safety.yml`](.github/workflows/safety.yml)) — the
per-case cost is the same, it's just spread out.

For a quick spot check, or if your machine is slow, shard with
`CASE_FILTER` — a `grep -E` pattern matched against the case name. This is
the exact mechanism CI's batch matrix uses; the pattern below is CI's own
batch `04-entropy-shared-infra-simulated-ascii`:

```bash
CASE_FILTER='entropy|shared_infrastructure|simulated-result|ascii_metadata' \
  PYTHON_BIN="$(command -v python)" bash lab/verify-safety-suite.sh
```

**Expected**, in under 5 minutes:

```
caught 6 / 6 injected violations (32 skipped by CASE_FILTER=entropy|shared_infrastructure|simulated-result|ascii_metadata)
OK: every injected violation turned the suite red.
```

A sharded run is real evidence for the cases it ran — it is not evidence for
the 32 it skipped. **All 38 must be caught** for the claim on the README
badge to hold; that is only established by the unfiltered command at the top
of this section, or by trusting that the `mutation-summary` and
`negative-control-coverage` jobs are green on the current `main` (the badge
itself is generated from that run's own artifact, not hand-typed — see
[`README.md`](README.md#prove-the-tests-can-fail)).

## 4. Run the repository's own liveness and readiness checks

```bash
python lab/scorecard.py
python lab/check-provider-policy.py
python lab/check-release-readiness.py
```

### `scorecard.py`

**Expected:**

```
GPU-SEAL liveness scorecard
==============================
[PASS] shell syntax: bash -n passed for 4 scripts
[PASS] probe imports: imported 44 gpu_seal modules
[PASS] battery preflight: pytest version and collection succeeded
[PASS] provider matrix: loaded 2 reviewed provider record(s): provider-a, provider-c
```

This is **not** a substitute for steps 2 or 3. It's a much cheaper check that
the machinery behind those checks can even start — shell scripts parse,
probe modules import, pytest can collect, the policy matrix loads. A pass
here means the project isn't obviously broken; it says nothing about whether
any individual probe or safety rule is correct.

### `check-provider-policy.py`

**Expected:**

```
  complete    2
  awaiting    2
  incomplete  0

GATE: lifted - 2 reviewed provider(s): ['provider-a.json', 'provider-c.json']
```

`GATE: lifted` means at least one provider has a *complete* policy record —
read, classified, sourced, dated, attributed, not stale. It is **not**
authorisation to test any provider you like: it is scoped to exactly the
named record(s) it lists, each of which is a pseudonym
(`provider-a`, `provider-c`) — the real name is never in the tracked tree
(enforced by `check-release-readiness.py`'s own
`check_no_named_providers`, below). Two other providers, `provider-b` and
`provider-d`, remain `awaiting-review` and stay blocked. Nothing in this
output tells you what testing, if any, was actually run against any
provider — see [What this does NOT prove](#what-this-does-not-prove).

### `check-release-readiness.py`

**Expected**, on a clean clone:

```
  [x] CITATION.cff author metadata       section 21, section 23
  [x] container lock file                section 10, section 14
  [x] release base image digest          section 10, section 14
  [x] GitHub Action commit pins          CI supply-chain integrity
  [x] clean git worktree                 release integrity
  [x] provider policy matrix             section 7.4, section 23
  [x] no named providers in publishable tree section 7.6
  [x] quarantined evidence               section 10
  [x] measurement pre-registration       section 12, section 19

RELEASABLE.
```

`RELEASABLE` means the checks this script knows how to automate all pass on
the tree in front of it, at this moment — dependency pins, no leaked provider
names, evidence quarantine explained, and so on. It does **not** mean a
provider study is authorised, ethics-approved, or that a human owner has
signed off on anything; those are separate, deliberately non-automatable
gates tracked in
[`docs/OWNER-ACTION-CHECKLIST.md`](docs/OWNER-ACTION-CHECKLIST.md).

**The `clean git worktree` line may fail on your machine even though nothing
is wrong.** It runs `git status --porcelain --untracked-files=all` and fails
if that prints anything at all. The check's whole point is that a release
tag must identify *exactly* the reviewed tree — so it is deliberately
intolerant of anything git considers a change, including things that have
nothing to do with this project's code: an editor dropping `.vscode/` or a
`.DS_Store` file, an OS writing `Thumbs.db`, or simply having edited a file
while poking around. None of that is a bug in the check; it is the check
doing its job. If you hit this, `git status` will show you exactly what it
saw.

## 5. Verify a signed evidence bundle with a key you supply

Per [`docs/TRUST-MODEL.md`](docs/TRUST-MODEL.md), inspecting a rendered
bundle — on the public dashboard or anywhere else — is **not**
cryptographic verification. The dashboard is a browser-only structural
viewer: it can show you the shape of a record, but it never runs Python,
never checks a signature, and never establishes that the bundle wasn't
tampered with. "Looks internally consistent on the dashboard" is a
readability property, not a trust property.

Actual verification requires a public key obtained through a channel you
trust *independently of the bundle itself* — a release page, a key registry,
a direct exchange — never the key embedded in the file you're checking. To
demonstrate the mechanism without a real distribution channel, generate a
throwaway keypair to stand in for "a key you already trust":

```bash
python -c "
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
priv = Ed25519PrivateKey.generate()
open('demo-ed25519-private.pem', 'wb').write(priv.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption()))
open('demo-ed25519-public.pem', 'wb').write(priv.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
"
```

Sign a bundle with the private half (this also covers step 6 below — one run
serves both):

```bash
python lab/local-runner/run_phase1.py --simulate --size-mib 1 --cycles 2 \
  --signing-key ./demo-ed25519-private.pem --out ./out-repro-demo
```

Then verify it with **only the public half** — the CLI never reads the
private key you just used to sign:

```bash
gpu-seal verify ./out-repro-demo/<run-id>.result.json \
  --public-key ./demo-ed25519-public.pem
```

(`<run-id>` is printed by the previous command as `written to
out-repro-demo\run_<timestamp>.result.json`.)

**Expected:**

```json
{
  "embedded_public_key_fingerprint_matches_trusted": true,
  "embedded_public_key_matches_trusted": true,
  "payload_hash_valid": true,
  "run_id": "run_...",
  "schema_valid": true,
  "signature_valid": true,
  "trusted_public_key": "...",
  "trusted_public_key_fingerprint": "sha256:..."
}
trusted verification: PASS (schema, canonical hash, and Ed25519 signature validated with the supplied external key)
```

Exit code `0`. This proves schema validity, that the canonical payload hash
matches, and that the Ed25519 signature verifies against **the key you
supplied** — not the key embedded in the file, which an attacker controls
just as easily as the payload. It does not prove the signer is a real
provider, that any provider approved anything, or that the hardware is what
the bundle claims — see `docs/TRUST-MODEL.md`'s "Cryptographically trusted
verification" section for exactly what is and isn't established.

Try tampering with the file (edit any value inside a `"probes"` entry, e.g.
change a `zero_fraction` number) and rerun the same `gpu-seal verify`
command against your edited copy — verified while writing this page:

```
gpu-seal verify: FAILED: canonical payload hash mismatch: the signed body was modified
```

Exit code `1`. The mismatch is caught before the signature is even checked,
because the canonical hash is recomputed from the bundle you handed it, not
trusted from a field inside the file.

## 6. See for yourself that a simulated result cannot pass as evidence

The run in step 5 used `--simulate`, which forces the simulated backend even
if a real GPU were present. Look at its own printed output:

```
  backend           simulated (real=False)
  ...
  publishable       no -- probes ['framework_allocator_reuse', 'memory_global_read_before_write'] ran against the simulated backend, which models a non-zeroing allocator on the host and measures nothing about real hardware
```

And in the bundle it wrote:

```bash
grep -n "backend_is_real" out-repro-demo/*.result.json
```

**Expected:** every match reads `"backend_is_real": "false"` — it appears
once for the run's own environment block and once per probe record,
because it is checked at the point each measurement is attributed, not
just printed once and trusted.

This is not merely a label a human is expected to notice. The tool's own
`clear_for_publication()` step, called before the bundle is signed, refuses
to mark a bundle publishable when any probe ran on a non-real backend — that
refusal is exactly what you saw as `"publishable no --"` above. That refusal
is itself one of the 38 mutations in step 3
(`"simulated-result publication guard removed"`): if someone deleted the
check, the mutation battery would catch it. A simulated result is a fixture
for exercising probe logic, not hardware or provider evidence, and the
tooling is built to say so on every bundle it produces, not just this one.

## 7. Verify a bundle from real hardware

Steps 5 and 6 ended on a simulated bundle. This step ends on a real one:
[`examples/evidence/`](examples/evidence/) holds a result bundle from a Tesla T4
on a Colab notebook, with its environment manifest and a public key. Verify it
from the repository root:

```bash
gpu-seal verify examples/evidence/colab-t4-run_20260916T140203Z/run_20260916T140203Z.result.json --public-key examples/evidence/colab-t4-run_20260916T140203Z/ed25519-public-key.hex
```

**Expected:** the same JSON block as step 5, with `"run_id": "run_20260916T140203Z"`
and `"trusted_public_key_fingerprint":
"sha256:16ed33e3681dbd0fcf4e13e6e25008821d44c9afd61d6fe17fea39e4bba115de"`,
ending `trusted verification: PASS (...)`. Exit code `0`.

**Read the key honestly.** In step 5 the key was one you generated, so you knew
where it came from. Here the key file is the repository's, and it was copied out
of the bundle it verifies. That makes this a check of **integrity, not
provenance**: the bundle is unaltered since it was signed, and nothing here says
whose key that is. [`examples/evidence/README.md`](examples/evidence/README.md)
quotes [`docs/TRUST-MODEL.md`](docs/TRUST-MODEL.md) on why, and on what to do
about it: obtain the key through a channel this repository does not control, and
pass that as `--public-key` instead.

`gpu-seal verify` never looks at `backend_is_real`. It passes a correctly signed
*simulated* bundle just as readily (this was checked: a step 5 bundle, with its
own key beside it, passes). Whether a bundle is real is a separate check:

```bash
grep -o '"backend_is_real": *"[a-z]*"' \
  examples/evidence/colab-t4-run_20260916T140203Z/run_20260916T140203Z.result.json | sort | uniq -c
```

**Expected:** exactly one line, `41 "backend_is_real": "true"` (the run's
environment block plus 40 probe records), and no `"false"`. The repository's own
test enforces this for everything in that directory, and fails if a simulated,
tampered, or unrecognised file is ever added there:

```bash
python -m pytest tests/unit/test_committed_evidence.py -q
```

**Expected:** all tests pass. Some of them deliberately build a validly signed
simulated bundle and check that the test rejects it, so a pass shows the guard
can fail, not only that the current file is clean.

What this shows, and what it does not: the bundle is a Tesla T4 run on a managed
Colab notebook, outside the pinned container. It is real-hardware evidence about
that host on that day. It is not a provider measurement (see below).

---

## What this does NOT prove

Everything above verifies claims about the *software*: it installs, its
tests pass, its safety suite can fail and doesn't, its release gates and
provider-policy gate report what this page says, and its signing/
verification path is genuinely cryptographic rather than cosmetic. None of
it is evidence about a GPU cloud provider. Specifically, this page — and,
as of this writing, this repository — does **not** show that:

- **any provider has been measured.** The provider policy matrix has two
  *complete policy reviews* (`provider-a`, `provider-c`); a complete review
  is Phase 0 paperwork — permission to plan probing — not a probe run, and
  no named-provider data exists anywhere in this repository.
- **MIG, H100, or provider-hardware evidence exists.** Every result you can
  *produce* by following steps 1-6 runs on the simulated backend, which is
  what "no GPU required" means. Step 7 verifies one committed bundle from a
  real Tesla T4 on a managed Colab notebook, outside the pinned container. The
  other real-silicon result in the project is a single RTX 3050 baseline on
  Windows
  ([`docs/findings/2026-07-31-rtx3050-baseline.md`](docs/findings/2026-07-31-rtx3050-baseline.md)).
  MIG temporal isolation and H100 confidential-computing attestation remain
  unvalidated for lack of that hardware, and neither run is a measurement of a
  cloud provider's fleet.
- **a clean local result distinguishes sanitisation from a different
  physical die.** Same-model die separation (contribution **D5** in
  `CHARTER.md`) is explicitly left open by the prior work this project
  builds on and is not yet validated here. Until the pre-registered D5
  separability evaluation passes against known ground truth
  ([`docs/pre-registration.md`](docs/pre-registration.md)), a report card
  that shows no canary recovered on a same-model claim caps at grade **U**
  (unproven) rather than a clean **A** — because "this driver sanitises" and
  "this is simply a different, cleaner chip than last time" produce the
  identical observation, and nothing in this repository can yet tell them
  apart.

For the full, dated accounting of what is and isn't validated, see
[`docs/STATUS.md`](docs/STATUS.md); for what a signature does and doesn't
establish, see [`docs/TRUST-MODEL.md`](docs/TRUST-MODEL.md).
