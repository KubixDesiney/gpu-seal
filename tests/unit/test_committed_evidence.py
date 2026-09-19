"""Every bundle committed under examples/evidence/ is real, signed, and verifiable.

That directory is what a reviewer is pointed at as hardware evidence
(REPRODUCE.md step 7). A simulated bundle in it would read, at a glance, as
hardware evidence while measuring nothing — the failure out/MISLABELLED-README.md
records for `run_20260731T012612Z`. So this test walks the directory and fails
on anything that is not a verifiable, real-backend bundle, including files that
merely *look* like they were meant to be skipped.

The audit is a plain function over a root path so the negative tests below can
prove it fails on doctored trees. A guard that has only ever been run against
good input is not known to be a guard.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate

import gpu_seal.cli as cli
from gpu_seal.evidence import SigningKey
from gpu_seal.evidence.result import canonical_payload_hash
from gpu_seal.evidence.signing import sign_payload
from gpu_seal.resources import load_schema

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = REPO_ROOT / "examples" / "evidence"
README = EVIDENCE_ROOT / "README.md"
TRUST_MODEL = REPO_ROOT / "docs" / "TRUST-MODEL.md"

KEY_NAME = "ed25519-public-key.hex"
RESULT_SUFFIX = ".result.json"
MANIFEST_SUFFIX = ".environment.json"


def _run_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


def _verify_command(run_dir: Path) -> str:
    """The README's command for a run, relative to the repository root."""
    result = next(run_dir.glob(f"*{RESULT_SUFFIX}"))
    base = f"examples/evidence/{run_dir.name}"
    return f"gpu-seal verify {base}/{result.name} --public-key {base}/{KEY_NAME}"


def audit_run(run_dir: Path) -> list[str]:
    """Return every reason this run directory is not acceptable evidence."""
    where = run_dir.name
    problems: list[str] = []

    # Closed set of files: an unrecognised name is a bundle the glob below
    # would silently skip, so it is a failure, not something to ignore.
    results = [p for p in run_dir.iterdir() if p.name.endswith(RESULT_SUFFIX)]
    manifests = [p for p in run_dir.iterdir() if p.name.endswith(MANIFEST_SUFFIX)]
    key_file = run_dir / KEY_NAME
    for entry in run_dir.iterdir():
        if entry.is_dir():
            problems.append(f"{where}: unexpected subdirectory {entry.name}/")
        elif entry not in results and entry not in manifests and entry != key_file:
            problems.append(
                f"{where}: unexpected file {entry.name} (only one *{RESULT_SUFFIX}, "
                f"one *{MANIFEST_SUFFIX} and {KEY_NAME} are allowed)"
            )
        elif entry.is_file() and b"PRIVATE KEY" in entry.read_bytes():
            problems.append(f"{where}: {entry.name} contains private key material")
    if len(results) != 1:
        problems.append(f"{where}: expected exactly 1 *{RESULT_SUFFIX}, found {len(results)}")
    if len(manifests) != 1:
        problems.append(f"{where}: expected exactly 1 *{MANIFEST_SUFFIX}, found {len(manifests)}")
    if not key_file.is_file():
        problems.append(f"{where}: missing {KEY_NAME}")
    if problems:
        return problems
    result_path, manifest_path = results[0], manifests[0]

    try:
        bundle = json.loads(result_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return [f"{where}: unreadable JSON: {exc}"]
    if not isinstance(bundle, dict) or not isinstance(manifest, dict):
        return [f"{where}: bundle and manifest must be JSON objects"]

    if manifest.get("bundle") != result_path.name:
        problems.append(
            f"{where}: manifest names bundle {manifest.get('bundle')!r}, "
            f"not {result_path.name!r}"
        )

    try:
        validate(bundle, load_schema("result.schema.json"))
    except ValidationError as exc:
        problems.append(f"{where}: schema-invalid: {exc.message}")

    # Same code path as the README's `gpu-seal verify`, with the key file
    # that sits in the run directory rather than the key embedded in the bundle.
    try:
        cli.verify_bundle(bundle, cli._load_trusted_key(str(key_file)))
    except (ValidationError, ValueError, TypeError) as exc:
        problems.append(f"{where}: verification failed: {exc}")

    # `backend_is_real` is the STRING "true"/"false" in this schema, and
    # driver_metadata may be null, so neither `if value:` nor `.get()` is safe.
    env = bundle.get("environment")
    if not isinstance(env, dict) or env.get("backend_is_real") != "true":
        problems.append(
            f"{where}: environment.backend_is_real is "
            f"{env.get('backend_is_real') if isinstance(env, dict) else None!r}, "
            'not "true" (simulated or unlabelled backend)'
        )
    probes = bundle.get("probes")
    if not isinstance(probes, list) or not probes:
        problems.append(f"{where}: bundle has no probe records")
    else:
        for index, probe in enumerate(probes):
            meta = probe.get("driver_metadata") if isinstance(probe, dict) else None
            flag = meta.get("backend_is_real") if isinstance(meta, dict) else None
            if flag != "true":
                problems.append(
                    f"{where}: probes[{index}].driver_metadata.backend_is_real is "
                    f'{flag!r}, not "true"'
                )
    return problems


def audit_evidence_tree(root: Path) -> list[str]:
    runs = _run_dirs(root)
    if not runs:
        return [f"{root}: no run directories found; an empty walk verifies nothing"]
    problems: list[str] = []
    for entry in root.iterdir():
        if entry.is_file() and entry.name != "README.md":
            problems.append(f"{entry.name}: stray file at the evidence root, outside a run directory")
    for run in runs:
        problems.extend(audit_run(run))
    return problems


# --- the committed tree -------------------------------------------------


def test_evidence_directory_has_runs():
    assert _run_dirs(EVIDENCE_ROOT), "examples/evidence/ contains no run directories"


@pytest.mark.parametrize("run_dir", _run_dirs(EVIDENCE_ROOT), ids=lambda p: p.name)
def test_committed_run_is_real_signed_and_verifiable(run_dir: Path):
    assert audit_run(run_dir) == []


def test_committed_tree_has_no_stray_files():
    assert audit_evidence_tree(EVIDENCE_ROOT) == []


# --- the guard must actually fail ---------------------------------------


def _first_real_run() -> Path:
    return _run_dirs(EVIDENCE_ROOT)[0]


def _resign(run_dir: Path, mutate) -> None:
    """Apply `mutate` to the bundle and re-sign it with a fresh key.

    The result is schema-valid, hash-valid and signature-valid against its own
    key file, so the ONLY thing left to catch is what `mutate` changed.
    """
    result = next(run_dir.glob(f"*{RESULT_SUFFIX}"))
    bundle = json.loads(result.read_text(encoding="utf-8"))
    body = {k: v for k, v in bundle.items() if k != "integrity"}
    mutate(body)
    key = SigningKey.generate()
    body["environment"]["signing"]["public_key_fingerprint"] = key.verify_key.fingerprint
    body["integrity"] = {
        "payload_hash": canonical_payload_hash(
            {k: v for k, v in body.items() if k != "integrity"}
        ),
        "signature_algorithm": "ed25519",
        "signature": sign_payload({k: v for k, v in body.items() if k != "integrity"}, key),
        "public_key": key.verify_key.hex,
        "public_key_fingerprint": key.verify_key.fingerprint,
    }
    result.write_text(json.dumps(body), encoding="utf-8")
    (run_dir / KEY_NAME).write_text(key.verify_key.hex + "\n", encoding="ascii")


def _mark_all_simulated(body: dict) -> None:
    body["environment"]["backend"] = "simulated"
    body["environment"]["backend_is_real"] = "false"
    for probe in body["probes"]:
        probe["driver_metadata"]["backend"] = "simulated"
        probe["driver_metadata"]["backend_is_real"] = "false"


def _mark_one_probe_simulated(body: dict) -> None:
    body["probes"][7]["driver_metadata"]["backend_is_real"] = "false"


def _null_one_probe_metadata(body: dict) -> None:
    body["probes"][3]["driver_metadata"] = None


def _drop_environment_flag(body: dict) -> None:
    del body["environment"]["backend_is_real"]


@pytest.fixture
def scratch_tree(tmp_path: Path) -> Path:
    """A private copy of the evidence tree that a test may damage."""
    root = tmp_path / "evidence"
    shutil.copytree(EVIDENCE_ROOT, root)
    return root


def test_scratch_copy_of_the_committed_tree_passes(scratch_tree: Path):
    # Baseline for the negative tests: the copy is clean until damaged.
    assert audit_evidence_tree(scratch_tree) == []


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_mark_all_simulated, id="fully-simulated"),
        pytest.param(_mark_one_probe_simulated, id="one-probe-simulated"),
        pytest.param(_null_one_probe_metadata, id="probe-metadata-null"),
        pytest.param(_drop_environment_flag, id="environment-flag-absent"),
    ],
)
def test_validly_signed_simulated_bundle_is_rejected(scratch_tree: Path, mutate):
    run = _run_dirs(scratch_tree)[0]
    _resign(run, mutate)

    problems = audit_evidence_tree(scratch_tree)

    assert any("backend_is_real" in p for p in problems), problems
    # Isolation: this bundle is well-formed and correctly signed, so the
    # backend_is_real check is what caught it, not a side effect.
    assert not any("verification failed" in p or "schema-invalid" in p for p in problems), problems


def test_bool_true_is_not_the_string_true(scratch_tree: Path):
    # `if flag:` would accept both; the schema types the field as a string.
    _resign(_run_dirs(scratch_tree)[0], lambda b: b["environment"].__setitem__("backend_is_real", True))

    problems = audit_evidence_tree(scratch_tree)

    assert any("schema-invalid" in p or "backend_is_real" in p for p in problems), problems


def test_tampered_bundle_is_rejected(scratch_tree: Path):
    result = next(_run_dirs(scratch_tree)[0].glob(f"*{RESULT_SUFFIX}"))
    bundle = json.loads(result.read_text(encoding="utf-8"))
    bundle["probes"][20]["zero_fraction"] = 0.5
    result.write_text(json.dumps(bundle), encoding="utf-8")

    assert any("canonical payload hash mismatch" in p for p in audit_evidence_tree(scratch_tree))


def test_wrong_key_file_is_rejected(scratch_tree: Path):
    (_run_dirs(scratch_tree)[0] / KEY_NAME).write_text(
        SigningKey.generate().verify_key.hex + "\n", encoding="ascii"
    )

    assert any("verification failed" in p for p in audit_evidence_tree(scratch_tree))


def test_manifest_for_a_different_bundle_is_rejected(scratch_tree: Path):
    run = _run_dirs(scratch_tree)[0]
    manifest = next(run.glob(f"*{MANIFEST_SUFFIX}"))
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["bundle"] = "run_00000000T000000Z.result.json"
    manifest.write_text(json.dumps(value), encoding="utf-8")

    assert any("manifest names bundle" in p for p in audit_evidence_tree(scratch_tree))


@pytest.mark.parametrize(
    "drop",
    [f"*{RESULT_SUFFIX}", f"*{MANIFEST_SUFFIX}", KEY_NAME],
    ids=["no-bundle", "no-manifest", "no-key"],
)
def test_incomplete_run_directory_is_rejected(scratch_tree: Path, drop: str):
    next(_run_dirs(scratch_tree)[0].glob(drop)).unlink()

    assert audit_evidence_tree(scratch_tree), "an incomplete run directory passed"


def test_bundle_hidden_under_an_unrecognised_name_is_rejected(scratch_tree: Path):
    # `*.result.json` globbing alone would skip this and pass vacuously.
    run = _run_dirs(scratch_tree)[0]
    shutil.copy(next(run.glob(f"*{RESULT_SUFFIX}")), run / "simulated-run.json")

    assert any("unexpected file simulated-run.json" in p for p in audit_evidence_tree(scratch_tree))


def test_bundle_at_the_evidence_root_is_rejected(scratch_tree: Path):
    run = _run_dirs(scratch_tree)[0]
    shutil.copy(next(run.glob(f"*{RESULT_SUFFIX}")), scratch_tree / "loose.result.json")

    assert any("stray file at the evidence root" in p for p in audit_evidence_tree(scratch_tree))


def test_private_key_material_is_rejected(scratch_tree: Path):
    run = _run_dirs(scratch_tree)[0]
    (run / KEY_NAME).write_text(
        "-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n", encoding="ascii"
    )

    assert any("private key material" in p for p in audit_evidence_tree(scratch_tree))


def test_empty_tree_is_rejected(tmp_path: Path):
    (tmp_path / "evidence").mkdir()

    assert audit_evidence_tree(tmp_path / "evidence")


# --- the README -----------------------------------------------------------


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_readme_gives_the_verify_command_for_every_run():
    text = README.read_text(encoding="utf-8")
    for run in _run_dirs(EVIDENCE_ROOT):
        assert _verify_command(run) in text, f"README.md lacks the verify command for {run.name}"


def test_readme_states_integrity_is_not_provenance():
    text = _normalise(README.read_text(encoding="utf-8")).lower()
    assert "integrity, not provenance" in text
    assert "independent channel" in text


def test_readme_blockquotes_are_verbatim_from_the_trust_model():
    """`> ` blocks in the README are quotations; they must not drift or be paraphrased."""
    quotes = [
        _normalise(re.sub(r"(?m)^>\s?", "", block))
        for block in re.findall(r"(?m)((?:^>.*\n?)+)", README.read_text(encoding="utf-8"))
    ]
    assert quotes, "README.md quotes nothing from docs/TRUST-MODEL.md"
    trust_model = _normalise(TRUST_MODEL.read_text(encoding="utf-8"))
    for quote in quotes:
        assert quote.strip('“”"') in trust_model, f"not in TRUST-MODEL.md verbatim: {quote!r}"
