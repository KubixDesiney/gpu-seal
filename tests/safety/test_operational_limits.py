"""CHARTER.md §16 tests 8, 11, 13, 14 — operational limits and targeting.

These are the controls that keep a runaway experiment from becoming a
provider incident, and that keep GPU-SEAL pointed only at infrastructure the
researcher actually rents.
"""

from __future__ import annotations

import pytest

from gpu_seal.safety.policy import (
    MAX_ALLOCATION_BYTES,
    MAX_EXPERIMENT_DURATION_S,
    PROVIDER_POLICY_CLASSES,
    PUBLICATION_BLOCKING_MARKERS,
    SELF_CANARY_ONLY_SAFE_PROBES,
)

pytestmark = pytest.mark.safety


# ---------------------------------------------------------------------------
# Tests 11 and 12 — duration and allocation caps exist and are sane
# ---------------------------------------------------------------------------


def test_experiment_duration_cap_is_defined_and_bounded():
    assert 0 < MAX_EXPERIMENT_DURATION_S <= 24 * 3600, (
        "A run without a duration cap can accrue unbounded cost and look like "
        "abuse to a provider (CHARTER.md §16 test 11, §20)."
    )


def test_allocation_cap_is_defined_and_bounded():
    assert 0 < MAX_ALLOCATION_BYTES <= 64 * 1024**3, (
        "Allocation cap bounds how much unknown memory is ever resident "
        "(CHARTER.md §16 test 12)."
    )


# ---------------------------------------------------------------------------
# Test 13 — provider allowlists
# ---------------------------------------------------------------------------


def test_provider_policy_classes_match_the_charter():
    """§7.4 / §23: every provider is classified before it is probed."""
    assert PROVIDER_POLICY_CLASSES == {
        "full-probe-ok",
        "self-canary-only",
        "needs-written-permission",
        "prohibited",
    }


def test_self_canary_only_probe_set_excludes_unknown_memory_reads():
    """Probes safe under a restrictive provider policy must only touch our own data.

    Global VRAM read-before-write (§9.3) reads memory we did not write, so it
    can never be on this list. MIG temporal isolation (§9.12) only ever reads
    back our own marker, so it can.
    """
    assert "memory_global_read_before_write" not in SELF_CANARY_ONLY_SAFE_PROBES
    assert "local_memory_sanitisation" not in SELF_CANARY_ONLY_SAFE_PROBES
    assert "mig_temporal_isolation" in SELF_CANARY_ONLY_SAFE_PROBES
    assert "self_sequential_canary" in SELF_CANARY_ONLY_SAFE_PROBES


# ---------------------------------------------------------------------------
# Test 7 / 8 — publication gating markers
# ---------------------------------------------------------------------------


def test_publication_blocking_markers_include_sensitive_observation():
    assert "sensitive_observation" in PUBLICATION_BLOCKING_MARKERS
    assert "disclosure_pending" in PUBLICATION_BLOCKING_MARKERS


# ---------------------------------------------------------------------------
# Test 8 — stable provider identifiers are redacted
# ---------------------------------------------------------------------------


def test_never_published_fields_are_absent_from_the_result_schema():
    """§10: account IDs, hostnames, GPU UUIDs and coordinates never ship.

    The schema sets additionalProperties:false at every level, so this checks
    the declared properties rather than relying on runtime filtering.
    """
    import json
    import pathlib

    schema_path = (
        pathlib.Path(__file__).resolve().parents[2] / "schemas" / "result.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    forbidden = {
        "account_id",
        "public_ip",
        "gpu_uuid",
        "hostname",
        "provider_internal_id",
        "server_coordinates",
        "latitude",
        "longitude",
        "raw_traceroute",
    }

    found: list[str] = []

    def walk(node, path="root"):
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict):
                for key in props:
                    if key in forbidden:
                        found.append(f"{path}.{key}")
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(schema)
    assert not found, (
        f"Result schema declares never-publish fields {found} (CHARTER.md §10)."
    )


def test_schema_forbids_additional_properties_at_top_level():
    """Open schemas leak. A field nobody reviewed must not validate."""
    import json
    import pathlib

    schema_path = (
        pathlib.Path(__file__).resolve().parents[2] / "schemas" / "result.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema.get("additionalProperties") is False
    agg = schema["definitions"]["aggregateRecord"]
    assert agg.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# Test 14 — owned-account confirmation
# ---------------------------------------------------------------------------


def test_provider_code_is_required_by_the_schema():
    """Every result records which (pseudonymous) provider it came from.

    A result that cannot say where it was taken cannot be checked against the
    provider policy matrix, and cannot be disclosed to the right party.
    """
    import json
    import pathlib

    schema_path = (
        pathlib.Path(__file__).resolve().parents[2] / "schemas" / "result.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "provider_code" in schema["required"]
    assert "experiment_id" in schema["required"]
    assert "safety" in schema["required"]
    assert "integrity" in schema["required"]
