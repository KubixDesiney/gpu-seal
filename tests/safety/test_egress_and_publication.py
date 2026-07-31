"""CHARTER.md §16 tests 7-10 and the §7.2 egress allowlist / §7.3 safety stop."""

from __future__ import annotations

import dataclasses
import os

import pytest

from gpu_seal.evidence import ResultBundle, SigningKey, VerifyKey
from gpu_seal.evidence.result import ToolProvenance
from gpu_seal.safety import (
    AggregateRecord,
    Boundary,
    CanarySet,
    EgressViolation,
    SafeBuffer,
    SensitiveObservation,
    aggregate,
)
from gpu_seal.safety.policy import SAFE_AGGREGATE_KEYS

pytestmark = pytest.mark.safety


def _buffer_containing(payload: bytes, size: int | None = None) -> SafeBuffer:
    size = size or max(len(payload), 4096)
    buf = SafeBuffer.acquire(size, provenance="test:synthetic")
    buf.__enter__()

    def writer(view):
        view[: len(payload)] = payload

    buf.fill_via(writer)
    return buf


# ---------------------------------------------------------------------------
# §7.2 egress allowlist
# ---------------------------------------------------------------------------


def test_every_aggregate_field_is_on_the_allowlist():
    """A field added to AggregateRecord without an ethics review fails here."""
    fields = {f.name for f in dataclasses.fields(AggregateRecord)}
    offending = fields - SAFE_AGGREGATE_KEYS
    assert not offending, (
        f"AggregateRecord declares fields {sorted(offending)} that are not on "
        f"SAFE_AGGREGATE_KEYS. CHARTER.md §7.2 enumerates exactly what may "
        f"leave a probe."
    )


def test_to_dict_refuses_unlisted_keys(monkeypatch):
    """Negative control on the allowlist itself: shrink it, and egress fails.

    Without this, ``test_every_aggregate_field_is_on_the_allowlist`` could pass
    trivially if the enforcement in ``to_dict`` were ever removed.
    """
    from gpu_seal.safety import aggregation as agg

    monkeypatch.setattr(agg, "SAFE_AGGREGATE_KEYS", frozenset({"probe_name"}))
    buf = _buffer_containing(bytes(4096))
    try:
        rec = aggregate(buf, None, probe_name="t", probe_version="0")
        with pytest.raises(EgressViolation):
            rec.to_dict()
    finally:
        buf.destroy()


def test_aggregate_returns_no_raw_bytes():
    """Nothing in the emitted record may be bytes-like."""
    secret = os.urandom(2048)
    buf = _buffer_containing(secret)
    try:
        rec = aggregate(buf, None, probe_name="memory_global", probe_version="0.1.0")
        payload = rec.to_dict()
    finally:
        buf.destroy()

    def _walk(obj, path="root"):
        if isinstance(obj, (bytes, bytearray, memoryview)):
            raise AssertionError(f"bytes-like object escaped at {path}")
        if isinstance(obj, dict):
            for k, v in obj.items():
                _walk(v, f"{path}.{k}")
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                _walk(v, f"{path}[{i}]")

    _walk(payload)
    # And the actual content must not be reconstructible from the histogram.
    assert len(payload["byte_histogram"]) == 256
    assert sum(payload["byte_histogram"]) == 4096


def test_aggregate_without_canaries_performs_no_search():
    buf = _buffer_containing(os.urandom(1024))
    try:
        rec = aggregate(buf, None, probe_name="t", probe_version="0")
    finally:
        buf.destroy()
    assert rec.owned_canary_match is False
    assert rec.owned_canary_exact_matches == 0
    assert rec.canary_only_search is True


def test_aggregate_finds_owned_canary():
    cs = CanarySet.create()
    c = cs.mint(Boundary.SEQUENTIAL_ALLOCATION)
    buf = _buffer_containing(bytes(1024) + c.blob + bytes(1024))
    try:
        rec = aggregate(buf, cs, probe_name="memory_global", probe_version="0.1.0")
    finally:
        buf.destroy()
    assert rec.owned_canary_match is True
    assert rec.owned_canary_exact_matches == 1


def test_statistics_are_correct_on_known_input():
    """Sanity: a zeroed buffer must read as zeroed, or every result is suspect."""
    buf = _buffer_containing(bytes(4096))
    try:
        rec = aggregate(buf, None, probe_name="t", probe_version="0")
    finally:
        buf.destroy()
    assert rec.zero_fraction == 1.0
    assert rec.entropy_estimate == pytest.approx(0.0)
    assert rec.fixed_pattern_fraction == 1.0
    assert rec.distinct_block_count == 1


# ---------------------------------------------------------------------------
# §7.3 automatic safety stop
# ---------------------------------------------------------------------------


def test_safety_stop_fires_on_unexpected_content():
    """A buffer that should be clean but isn't halts analysis immediately."""
    buf = _buffer_containing(os.urandom(4096))
    with pytest.raises(SensitiveObservation) as excinfo:
        aggregate(buf, None, probe_name="t", probe_version="0", expect_zeroed=True)

    assert buf.destroyed, "raw buffer must be destroyed when the stop fires"
    record = excinfo.value.aggregate_record
    assert record is not None
    assert record.sensitive_observation is True


def test_safety_stop_does_not_fire_for_our_own_canary():
    """Finding our own marker is the experiment succeeding, not an incident."""
    cs = CanarySet.create()
    c = cs.mint(Boundary.SEQUENTIAL_ALLOCATION)
    padding = bytes(4096 - len(c.blob))
    buf = _buffer_containing(c.blob + padding)
    try:
        rec = aggregate(
            buf, cs, probe_name="t", probe_version="0", expect_zeroed=True
        )
    finally:
        buf.destroy()
    assert rec.owned_canary_match is True
    assert rec.sensitive_observation is False


def test_safety_stop_survives_as_aggregate_only():
    """After a stop, statistics remain but the bytes are unrecoverable."""
    buf = _buffer_containing(os.urandom(2048))
    with pytest.raises(SensitiveObservation) as excinfo:
        aggregate(buf, None, probe_name="t", probe_version="0", expect_zeroed=True)
    rec = excinfo.value.aggregate_record
    payload = rec.to_dict()
    assert payload["sensitive_observation"] is True
    assert payload["unknown_raw_retained"] is False
    assert buf.destroyed


# ---------------------------------------------------------------------------
# Test 7 — public report generator rejects sensitive_observation runs
# ---------------------------------------------------------------------------


def _bundle(*probes: AggregateRecord) -> ResultBundle:
    return ResultBundle(
        experiment_id="exp_test_0001",
        run_id="run_test_0001",
        provider_code="provider-a",
        region_claim="region-1",
        product_claim="gpu-product-x",
        tool=ToolProvenance(version="0.1.0", commit="sha256:deadbeef"),
        probes=list(probes),
    )


def _clean_record(**overrides) -> AggregateRecord:
    base = dict(
        probe_name="memory_global",
        probe_version="0.1.0",
        buffer_size_bytes=4096,
        block_size_bytes=16,
        measurement_hash="sha256:" + "0" * 64,
        zero_fraction=1.0,
        fixed_pattern_fraction=1.0,
        entropy_estimate=0.0,
        repeated_block_count=255,
        distinct_block_count=1,
        byte_histogram=[4096] + [0] * 255,
        owned_canary_match=False,
        owned_canary_exact_matches=0,
        owned_canary_longest_prefix=0,
    )
    base.update(overrides)
    return AggregateRecord(**base)


def test_clean_bundle_can_be_cleared_for_publication():
    b = _bundle(_clean_record())
    b.clear_for_publication()
    assert b.sign(SigningKey.generate())["safety"]["automatic_publication_allowed"]


def test_sensitive_bundle_cannot_be_cleared_for_publication():
    b = _bundle(_clean_record(sensitive_observation=True))
    with pytest.raises(EgressViolation):
        b.clear_for_publication()


def test_publication_defaults_to_blocked():
    """Not clearing is the default. Publication must be an explicit act."""
    b = _bundle(_clean_record())
    assert b.sign(SigningKey.generate())["safety"]["automatic_publication_allowed"] is False


def test_bundle_refuses_to_emit_if_a_probe_declares_retention():
    b = _bundle(_clean_record(unknown_raw_retained=True))
    with pytest.raises(EgressViolation):
        b.payload()


def test_bundle_refuses_to_emit_if_a_probe_declares_rendering():
    b = _bundle(_clean_record(unknown_memory_rendered=True))
    with pytest.raises(EgressViolation):
        b.payload()


# ---------------------------------------------------------------------------
# Tests 9 and 10 — signatures verify, tool and kernel hashes present
# ---------------------------------------------------------------------------


def test_signature_verifies():
    key = SigningKey.generate()
    signed = _bundle(_clean_record()).sign(key)
    assert ResultBundle.verify(signed)
    assert ResultBundle.verify(signed, key.verify_key)


def test_signature_fails_after_tampering():
    key = SigningKey.generate()
    signed = _bundle(_clean_record()).sign(key)
    signed["probes"][0]["zero_fraction"] = 0.5
    assert not ResultBundle.verify(signed)


def test_signature_fails_under_a_different_key():
    signed = _bundle(_clean_record()).sign(SigningKey.generate())
    assert not ResultBundle.verify(signed, SigningKey.generate().verify_key)


def test_payload_hash_is_checked_independently_of_the_signature():
    key = SigningKey.generate()
    signed = _bundle(_clean_record()).sign(key)
    signed["integrity"]["payload_hash"] = "sha256:" + "1" * 64
    assert not ResultBundle.verify(signed)


def test_tool_provenance_is_present():
    signed = _bundle(_clean_record()).sign(SigningKey.generate())
    assert signed["tool"]["version"]
    assert signed["tool"]["commit"]


def test_signing_key_repr_leaks_no_private_material():
    key = SigningKey.generate()
    text = repr(key)
    assert "BEGIN" not in text
    assert key.to_pem().hex()[:32] not in text


def test_bundle_validates_against_the_published_schema():
    import json
    import pathlib

    import jsonschema

    schema_path = (
        pathlib.Path(__file__).resolve().parents[2] / "schemas" / "result.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    b = _bundle(_clean_record())
    b.clear_for_publication()
    jsonschema.validate(b.sign(SigningKey.generate()), schema)


def test_schema_rejects_a_bundle_claiming_raw_retention():
    """The schema is a second, independent gate on the same invariant."""
    import json
    import pathlib

    import jsonschema

    schema_path = (
        pathlib.Path(__file__).resolve().parents[2] / "schemas" / "result.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    signed = _bundle(_clean_record()).sign(SigningKey.generate())
    signed["safety"]["raw_unknown_memory_retained"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(signed, schema)


def test_schema_rejects_publication_of_a_sensitive_run():
    import json
    import pathlib

    import jsonschema

    schema_path = (
        pathlib.Path(__file__).resolve().parents[2] / "schemas" / "result.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    signed = _bundle(_clean_record()).sign(SigningKey.generate())
    signed["safety"]["sensitive_observation"] = True
    signed["safety"]["automatic_publication_allowed"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(signed, schema)
