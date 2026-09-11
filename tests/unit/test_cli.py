from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

import gpu_seal.cli as cli
from gpu_seal.cli import verify_bundle
from gpu_seal.evidence import ResultBundle, SigningKey
from gpu_seal.evidence.result import ToolProvenance


def _bundle() -> ResultBundle:
    return ResultBundle(
        experiment_id="cli-test",
        run_id="cli-test-run",
        provider_code="provider-a",
        region_claim="local",
        product_claim="test",
        tool=ToolProvenance(version="test", commit="test"),
    )


def test_verify_bundle_requires_the_external_key_to_match():
    key = SigningKey.generate()
    signed = _bundle().sign(key)

    result = verify_bundle(signed, key.verify_key)

    assert result["schema_valid"] is True
    assert result["payload_hash_valid"] is True
    assert result["signature_valid"] is True
    altered_identity = dict(signed)
    altered_identity["integrity"] = dict(signed["integrity"])
    altered_identity["integrity"]["public_key"] = "0" * 64
    identity_result = verify_bundle(altered_identity, key.verify_key)
    assert identity_result["embedded_public_key_matches_trusted"] is False
    with pytest.raises(ValueError, match="signature verification failed"):
        verify_bundle(signed, SigningKey.generate().verify_key)


def test_verify_bundle_rejects_a_modified_canonical_payload():
    key = SigningKey.generate()
    signed = _bundle().sign(key)
    signed["run_id"] = "modified-after-signing"

    with pytest.raises(ValueError, match="canonical payload hash mismatch"):
        verify_bundle(signed, key.verify_key)


def test_verify_command_accepts_an_external_pem_public_key(tmp_path: Path, monkeypatch):
    key = SigningKey.generate()
    bundle_path = tmp_path / "bundle.result.json"
    key_path = tmp_path / "trusted-public.pem"
    bundle_path.write_text(json.dumps(_bundle().sign(key)), encoding="utf-8")
    key_path.write_bytes(
        Ed25519PublicKey.from_public_bytes(key.verify_key.raw).public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["gpu-seal", "verify", str(bundle_path), "--public-key", str(key_path)],
    )

    assert cli.main() == 0


def test_gpu_seal_verify_command_uses_a_hex_external_key(tmp_path: Path):
    key = SigningKey.generate()
    bundle_path = tmp_path / "bundle.result.json"
    bundle_path.write_text(json.dumps(_bundle().sign(key)), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "probe")

    result = subprocess.run(  # noqa: S603 - fixed module invocation
        [
            sys.executable,
            "-m",
            "gpu_seal",
            "verify",
            str(bundle_path),
            "--public-key",
            key.verify_key.hex,
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "trusted verification: PASS" in result.stdout
