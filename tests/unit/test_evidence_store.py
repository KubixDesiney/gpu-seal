"""EvidenceStore path, schema, overwrite, and durability boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from gpu_seal.controller.evidence_store import EvidenceStore
from gpu_seal.evidence import ResultBundle, SigningKey
from gpu_seal.evidence.result import ToolProvenance
from gpu_seal.safety import (
    AggregateRecord,
    Boundary,
    EgressViolation,
    RedactedStopRecord,
)


def _bundle(run_id: str) -> ResultBundle:
    return ResultBundle(
        experiment_id="exp-test",
        run_id=run_id,
        provider_code="provider-a",
        region_claim="region-1",
        product_claim="gpu-product-x",
        tool=ToolProvenance(version="0.1.0", commit="sha256:" + "a" * 64),
    )


@pytest.mark.parametrize(
    "run_id",
    ["../escape", "..\\escape", "/absolute", "C:\\absolute", "", ".", ".."],
)
def test_run_id_cannot_escape_store(tmp_path, run_id):
    with pytest.raises(ValueError):
        EvidenceStore(tmp_path).write(_bundle(run_id), SigningKey.generate())

    assert list(tmp_path.iterdir()) == []


def test_duplicate_run_id_is_rejected_unless_explicitly_allowed(tmp_path):
    store = EvidenceStore(tmp_path)
    key = SigningKey.generate()
    first = store.write(_bundle("duplicate"), key)

    with pytest.raises(FileExistsError, match="allow_overwrite=True"):
        store.write(_bundle("duplicate"), key)

    replaced = store.write(_bundle("duplicate"), key, allow_overwrite=True)
    assert replaced.path == first.path
    assert store.read(replaced.path)["run_id"] == "duplicate"


def test_read_rejects_path_traversal_and_absolute_paths(tmp_path):
    store = EvidenceStore(tmp_path)
    (tmp_path / "safe.result.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        store.read(Path("..") / "safe.result.json")
    with pytest.raises(ValueError):
        store.read(Path(tmp_path.parent) / "safe.result.json")


def test_read_rejects_malformed_json(tmp_path):
    store = EvidenceStore(tmp_path)
    path = tmp_path / "malformed.result.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        store.read(path)
    assert store.verify_all()[path.name] is False


def test_verify_all_rejects_schema_invalid_json(tmp_path):
    store = EvidenceStore(tmp_path)
    path = tmp_path / "invalid.result.json"
    path.write_text(json.dumps({"not": "a bundle"}), encoding="utf-8")

    assert store.verify_all()[path.name] is False


def _full_report_card() -> dict:
    """A CHARTER.md §13 report card with all six required keys, matching the
    shape schemas/report-card.schema.json actually enforces."""
    category = {"grade": "A", "basis": "no residue observed across 10 cycles"}
    return {
        "provider_code": "provider-a",
        "note": "independent category grades, no composite score",
        "memory_lifecycle_hygiene": category,
        "tenant_exposure": category,
        "hardware_claim_consistency": category,
        "location_claim_consistency": category,
        "allocation_model_transparency": category,
        "attestation_assurance": {"note": "not a grade", "fields": {}},
    }


def test_write_accepts_a_bundle_with_no_report_card_yet(tmp_path):
    """report_card defaults to {} — a normal state before one is built."""
    store = EvidenceStore(tmp_path)
    stored = store.write(_bundle("no-card-yet"), SigningKey.generate())
    assert store.read(stored.path)["report_card"] == {}


def test_write_accepts_a_bundle_with_a_complete_report_card(tmp_path):
    store = EvidenceStore(tmp_path)
    bundle = _bundle("full-card")
    bundle.report_card = _full_report_card()
    stored = store.write(bundle, SigningKey.generate())
    written_card = store.read(stored.path)["report_card"]
    assert written_card["memory_lifecycle_hygiene"]["grade"] == "A"


def test_write_rejects_a_report_card_missing_required_categories(tmp_path):
    """schemas/report-card.schema.json exists specifically to enforce this
    shape; write() must actually apply it, not just result.schema.json's
    open `report_card: object`."""
    store = EvidenceStore(tmp_path)
    bundle = _bundle("partial-card")
    bundle.report_card = {
        "provider_code": "provider-a",
        "memory_lifecycle_hygiene": {"grade": "A", "basis": "x"},
        # every other required category is missing
    }
    with pytest.raises(jsonschema.ValidationError):
        store.write(bundle, SigningKey.generate())


def test_write_rejects_a_report_card_with_an_invalid_grade(tmp_path):
    store = EvidenceStore(tmp_path)
    bundle = _bundle("bad-grade")
    card = _full_report_card()
    card["memory_lifecycle_hygiene"] = {"grade": "F", "basis": "not a real grade"}
    bundle.report_card = card
    with pytest.raises(jsonschema.ValidationError):
        store.write(bundle, SigningKey.generate())


def test_write_rejects_a_report_card_with_a_composite_score():
    """CHARTER.md §13: "Avoid 62/100." additionalProperties:false at the
    report-card schema's root is what stops a `score` key riding along."""
    card = _full_report_card()
    card["score"] = 62
    schema_path = (
        Path(__file__).resolve().parents[2] / "schemas" / "report-card.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(card, schema)


def test_write_and_read_schema_validate(tmp_path):
    store = EvidenceStore(tmp_path)
    stored = store.write(_bundle("schema"), SigningKey.generate())
    payload = store.read(stored.path)
    assert payload["schema_version"] == "gpu-seal-result-v1"

    payload["safety"]["canary_only_search"] = False
    stored.path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(jsonschema.ValidationError):
        store.read(stored.path)


def test_sensitive_stop_is_stored_only_as_redacted_evidence(tmp_path):
    store = EvidenceStore(tmp_path)
    bundle = _bundle("redacted-stop")
    bundle.probes = [
        RedactedStopRecord(
            probe_name="memory_global_read_before_write",
            probe_version="0.1.0",
            reason_code="measurement_below_minimum",
            size_bucket="lt-256",
            boundary=Boundary.UNSPECIFIED.name,
            operational_metadata={"shared_infrastructure": "true"},
        )
    ]

    stored = store.write(bundle, SigningKey.generate())
    written = store.read(stored.path)
    probe = written["probes"][0]
    assert written["safety"]["sensitive_observation"] is True
    assert "measurement_hash" not in probe
    assert "byte_histogram" not in probe
    assert set(probe) == {
        "probe_name",
        "probe_version",
        "reason_code",
        "size_bucket",
        "boundary",
        "operational_metadata",
        "sensitive_observation",
        "unknown_raw_retained",
        "unknown_memory_rendered",
        "canary_only_search",
    }


def test_evidence_store_rejects_a_sensitive_aggregate_record(tmp_path):
    bundle = _bundle("sensitive-aggregate")
    bundle.probes = [
        AggregateRecord(
            probe_name="t",
            probe_version="0",
            buffer_size_bytes=1,
            block_size_bytes=16,
            measurement_hash="sha256:" + "0" * 64,
            zero_fraction=0.0,
            fixed_pattern_fraction=1.0,
            entropy_estimate=0.0,
            repeated_block_count=0,
            distinct_block_count=1,
            byte_histogram=[0, 1] + [0] * 254,
            owned_canary_match=False,
            owned_canary_exact_matches=0,
            owned_canary_longest_prefix=0,
            sensitive_observation=True,
        )
    ]
    with pytest.raises(EgressViolation, match="RedactedStopRecord"):
        EvidenceStore(tmp_path).write(bundle, SigningKey.generate())
