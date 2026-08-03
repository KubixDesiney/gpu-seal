"""Report generation must use project trust, not a bundle's self-assertion."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from gpu_seal.evidence import ResultBundle, SigningKey
from gpu_seal.evidence.result import ToolProvenance


def _generator():
    path = (
        Path(__file__).resolve().parents[2]
        / "analysis"
        / "report-generator"
        / "generate_report.py"
    )
    spec = importlib.util.spec_from_file_location("gpu_seal_report_generator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _signed(run_id: str, key: SigningKey) -> dict:
    return ResultBundle(
        experiment_id="exp-test",
        run_id=run_id,
        provider_code="provider-a",
        region_claim="region-1",
        product_claim="gpu-product-x",
        tool=ToolProvenance(version="0.1.0", commit="sha256:" + "a" * 64),
    ).sign(key)


def test_forged_self_signed_bundle_is_rejected(tmp_path):
    generator = _generator()
    forged_key = SigningKey.generate()
    (tmp_path / "forged.result.json").write_text(
        json.dumps(_signed("forged", forged_key)), encoding="utf-8"
    )

    bundles, excluded = generator.collect(tmp_path, (SigningKey.generate().verify_key,))

    assert bundles == []
    assert any("signature does not verify" in reason for reason in excluded)


def test_configured_key_accepts_bundle_signed_by_that_key(tmp_path):
    generator = _generator()
    key = SigningKey.generate()
    (tmp_path / "trusted.result.json").write_text(
        json.dumps(_signed("trusted", key)), encoding="utf-8"
    )

    bundles, excluded = generator.collect(tmp_path, (key.verify_key,))

    assert [bundle["run_id"] for bundle in bundles] == ["trusted"]
    assert excluded == []


def test_embedded_key_requires_explicit_unsafe_dev_mode(tmp_path):
    generator = _generator()
    key = SigningKey.generate()
    (tmp_path / "local.result.json").write_text(
        json.dumps(_signed("local", key)), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="no trusted public key"):
        generator.collect(tmp_path)

    bundles, _ = generator.collect(tmp_path, unsafe_dev=True)
    assert [bundle["run_id"] for bundle in bundles] == ["local"]


def _signed_dict(run_id: str, key: SigningKey, **overrides) -> dict:
    bundle = ResultBundle(
        experiment_id="exp-test",
        run_id=run_id,
        provider_code="provider-a",
        region_claim="region-1",
        product_claim="gpu-product-x",
        tool=ToolProvenance(version="0.1.0", commit="sha256:" + "a" * 64),
        **overrides,
    ).sign(key)
    return bundle


def test_render_does_not_include_probe_detail_for_a_non_publishable_bundle():
    """A verified signature only proves who signed a bundle, not that it
    cleared for publication. Rendering full detail for one that did not
    would put content CHARTER.md §7.3/§7.5 requires disclosure review for
    into the report body."""
    generator = _generator()
    key = SigningKey.generate()
    # automatic_publication_allowed defaults False; clear_for_publication()
    # was never called, so this bundle is verified but not publishable.
    bundle = _signed_dict("unpublishable-run", key)
    assert bundle["safety"]["automatic_publication_allowed"] is False

    report = generator.render([bundle], [])
    assert "unpublishable-run" in report
    assert "not cleared for publication" in report
    assert "## provider-a" not in report
    assert "gpu-product-x" not in report


def test_render_includes_full_detail_for_a_publishable_bundle():
    generator = _generator()
    key = SigningKey.generate()
    result_bundle = ResultBundle(
        experiment_id="exp-test",
        run_id="publishable-run",
        provider_code="provider-a",
        region_claim="region-1",
        product_claim="gpu-product-x",
        tool=ToolProvenance(
            version="0.1.0",
            commit="sha256:" + "a" * 64,
            container_digest="sha256:" + "c" * 64,
        ),
    )
    result_bundle.clear_for_publication()
    bundle = result_bundle.sign(key)
    assert bundle["safety"]["automatic_publication_allowed"] is True

    report = generator.render([bundle], [])
    assert "## provider-a" in report
    assert "gpu-product-x" in report
    assert "publishable-run" in report
    assert "## Verified but not cleared for publication" not in report


def test_render_escapes_html_significant_characters_in_bundle_content():
    """A signature authenticates who signed a bundle, not that its string
    fields (report-card `basis`, `provider_code`, `run_id`, ...) are safe to
    interpolate into Markdown/HTML. schemas/report-card.schema.json leaves
    `basis` as an arbitrary string and says it "goes straight into the
    report" — this is the concrete stored-XSS shape a Codex review flagged
    for a permissive Markdown-to-HTML renderer."""
    generator = _generator()
    key = SigningKey.generate()
    payload = "<img src=x onerror=alert(1)>"
    result_bundle = ResultBundle(
        experiment_id="exp-test",
        run_id=f"run-{payload}",
        provider_code="provider-a",
        region_claim="region-1",
        product_claim=payload,
        tool=ToolProvenance(
            version="0.1.0",
            commit="sha256:" + "a" * 64,
            container_digest="sha256:" + "c" * 64,
        ),
        report_card={
            "provider_code": "provider-a",
            "note": "x",
            "memory_lifecycle_hygiene": {"grade": "A", "basis": payload},
            "tenant_exposure": {"grade": "A", "basis": "x"},
            "hardware_claim_consistency": {"grade": "A", "basis": "x"},
            "location_claim_consistency": {"grade": "A", "basis": "x"},
            "allocation_model_transparency": {"grade": "A", "basis": "x"},
            "attestation_assurance": {"note": "not a grade", "fields": {}},
        },
    )
    result_bundle.clear_for_publication()
    bundle = result_bundle.sign(key)

    report = generator.render([bundle], [])
    assert payload not in report, "raw HTML must never appear unescaped"
    assert "&lt;img src=x onerror=alert(1)&gt;" in report


def test_keyring_loader_accepts_json_keyring(tmp_path):
    generator = _generator()
    key = SigningKey.generate()
    keyring = tmp_path / "trusted.json"
    keyring.write_text(
        json.dumps({"keys": [key.verify_key.hex]}), encoding="utf-8"
    )

    loaded = generator.load_trusted_keys(keyring=keyring)

    assert [item.hex for item in loaded] == [key.verify_key.hex]
