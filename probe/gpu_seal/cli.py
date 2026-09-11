"""User-facing GPU-SEAL command line workflows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate

from .evidence.result import canonical_payload_hash
from .evidence.signing import (
    VerifyKey,
    key_source_from_options,
    verify_payload,
)
from .resources import load_schema

__all__ = ["main", "verify_bundle"]


def _load_trusted_key(value: str) -> VerifyKey:
    candidate = Path(value)
    if candidate.is_file():
        data = candidate.read_bytes()
        if b"BEGIN" in data:
            return VerifyKey.from_pem(data)
        value = str(data, encoding="ascii").strip()
    return VerifyKey.from_hex(value)


def verify_bundle(bundle: dict[str, Any], trusted_key: VerifyKey) -> dict[str, Any]:
    """Validate a result with a caller-supplied, out-of-band public key."""
    validate(bundle, load_schema("result.schema.json"))
    integrity = bundle["integrity"]
    body = {key: value for key, value in bundle.items() if key != "integrity"}
    payload_hash = canonical_payload_hash(body)
    if payload_hash != integrity["payload_hash"]:
        raise ValueError(
            "canonical payload hash mismatch: the signed body was modified"
        )
    if not verify_payload(body, integrity["signature"], trusted_key):
        raise ValueError(
            "Ed25519 signature verification failed with the supplied trusted key"
        )
    return {
        "schema_valid": True,
        "payload_hash_valid": True,
        "signature_valid": True,
        "trusted_public_key": trusted_key.hex,
        "trusted_public_key_fingerprint": trusted_key.fingerprint,
        "embedded_public_key_matches_trusted": integrity.get("public_key")
        == trusted_key.hex,
        "embedded_public_key_fingerprint_matches_trusted": (
            integrity.get("public_key_fingerprint") in {None, trusted_key.fingerprint}
        ),
        "run_id": bundle["run_id"],
    }


def _verify_command(args: argparse.Namespace) -> int:
    try:
        value = json.loads(args.bundle.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("result bundle must be a JSON object")
        result = verify_bundle(value, _load_trusted_key(args.public_key))
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as exc:
        sys.stderr.write(f"gpu-seal verify: FAILED: {exc}\n")
        return 1
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    sys.stdout.write(
        "trusted verification: PASS (schema, canonical hash, and Ed25519 "
        "signature validated with the supplied external key)\n"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gpu-seal")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser(
        "verify", help="verify a result bundle with an external public key"
    )
    verify.add_argument("bundle", type=Path, help="signed .result.json bundle")
    verify.add_argument(
        "--public-key",
        required=True,
        help="trusted Ed25519 public-key PEM file or 64-character hex key",
    )
    verify.set_defaults(handler=_verify_command)
    campaign = commands.add_parser(
        "campaign", help="run the repository-owned campaign harness"
    )
    campaign_commands = campaign.add_subparsers(dest="campaign_command", required=True)
    run = campaign_commands.add_parser(
        "run",
        help=(
            "run one deterministic fake-runtime campaign; no provider adapter "
            "integration is included"
        ),
    )
    run.add_argument("--provider-code", default="provider-a")
    run.add_argument("--experiment-id", default="cli-campaign")
    run.add_argument("--run-id", default="cli-campaign-run")
    run.add_argument("--probe-name", default="memory_global_read_before_write")
    run.add_argument("--ownership-confirmation", required=True)
    run.add_argument("--confirmed-by", required=True)
    run.add_argument("--binary", type=Path, default=Path("gpu-seal-native"))
    run.add_argument("--out", type=Path, default=Path("out"))
    run.add_argument(
        "--policy-dir", type=Path, default=Path("docs/provider-policy-review")
    )
    run.add_argument("--cycles", type=int, default=1)
    run.add_argument("--size-mib", type=int, default=1)
    run.add_argument("--stride-mib", type=int, default=1)
    run.add_argument("--max-duration-s", type=int, default=60)
    run.add_argument("--signing-key", type=Path)
    run.add_argument("--unsafe-development-ephemeral", action="store_true")
    run.add_argument(
        "--force-timeout",
        action="store_true",
        help="exercise deterministic timeout handling",
    )
    run.set_defaults(handler=_campaign_run_command)
    return parser


def _campaign_run_command(args: argparse.Namespace) -> int:
    from .controller import (
        BudgetLedger,
        CampaignOrchestrator,
        CampaignRunSpec,
        DeterministicFakeRuntime,
        EvidenceStore,
        ExperimentPlan,
        NativeRunConfig,
        SpendLimits,
        load_policy_matrix,
        Scheduler,
    )
    from .safety import CampaignControl

    try:
        source = key_source_from_options(
            args.signing_key,
            unsafe_development_ephemeral=args.unsafe_development_ephemeral,
        )
        matrix = load_policy_matrix(args.policy_dir)
        ledger = BudgetLedger(
            limits=SpendLimits(
                per_run=1.0,
                per_provider=10.0,
                per_day=10.0,
                per_campaign=10.0,
            )
        )
        scheduler = Scheduler(policy_matrix=matrix, ledger=ledger)
        plan = ExperimentPlan(
            experiment_id=args.experiment_id,
            provider_code=args.provider_code,
            probe_name=args.probe_name,
            ownership_confirmation=args.ownership_confirmation,
            confirmed_by=args.confirmed_by,
            max_duration_s=args.max_duration_s,
            estimated_cost=0.0,
        )
        config = NativeRunConfig(
            binary=args.binary,
            cycles=args.cycles,
            size_mib=args.size_mib,
            stride_mib=args.stride_mib,
            container_profile="simulated",
        )
        orchestrator = CampaignOrchestrator(
            scheduler,
            DeterministicFakeRuntime(force_timeout=args.force_timeout),
            campaign=CampaignControl.create(),
        )
        result = orchestrator.run_and_store(
            [CampaignRunSpec(plan=plan, config=config, run_id=args.run_id)],
            store=EvidenceStore(args.out),
            key_source=source,
        )
    except (OSError, TypeError, ValueError) as exc:
        sys.stderr.write(f"gpu-seal campaign: FAILED: {exc}\n")
        return 1
    sys.stdout.write(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n")
    sys.stdout.write(
        "campaign runtime: deterministic fake only; output is simulated and "
        "not provider evidence\n"
    )
    if not source.provenance_suitable:
        sys.stdout.write(
            "WARNING: UNSAFE DEVELOPMENT KEY; output is unsuitable for "
            "provenance claims\n"
        )
    sys.stdout.write(
        f"public-key fingerprint: {orchestrator.signing_fingerprint}\n"
    )
    return 1 if result.failed else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))
