#!/usr/bin/env python3
"""Run the native CUDA slice and seal a local-only validation bundle.

This is intentionally not a provider runner. The native executable requires
the --local-only flag and this wrapper never calls clear_for_publication().
The bundle proves the native result path and remains local validation until
the full native safety/control campaign is complete.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "probe"))

from gpu_seal import __version__  # noqa: E402
from gpu_seal.evidence import (  # noqa: E402
    ResultBundle,
    key_source_from_options,
    signing_metadata,
)
from gpu_seal.evidence.result import ToolProvenance  # noqa: E402
from gpu_seal.safety.aggregation import AggregateRecord  # noqa: E402


def _provenance_value(name: str) -> str | None:
    path = Path("/etc/gpu-seal/provenance")
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key == name:
            return value
    return None


def _run_native(
    binary: Path, size_mib: int, cycles: int, stride_mib: int
) -> list[dict[str, Any]]:
    if not binary.is_file():
        raise SystemExit(f"native binary not found: {binary}")
    completed = subprocess.run(  # noqa: S603 - fixed local image artifact
        [
            str(binary),
            "--run",
            "--local-only",
            "--json",
            "--size-mib",
            str(size_mib),
            "--cycles",
            str(cycles),
            "--stride-mib",
            str(stride_mib),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    records: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        if not line:
            continue
        payload = json.loads(line)
        if payload.get("kind") == "aggregate":
            payload.pop("kind", None)
            metadata = payload.setdefault("driver_metadata", {})
            metadata["container_profile"] = os.environ.get(
                "GPU_SEAL_CONTAINER_PROFILE", "unspecified"
            )
            records.append(payload)
        elif payload.get("kind") != "summary":
            raise SystemExit("native output contained an unknown record kind")
    if len(records) != cycles:
        raise SystemExit(f"native returned {len(records)} aggregates, expected {cycles}")
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--binary", type=Path, default=Path("/opt/gpu-seal/bin/gpu-seal-native")
    )
    parser.add_argument("--size-mib", type=int, default=8)
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--stride-mib", type=int, default=4)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "out" / "native-local")
    parser.add_argument("--signing-key", type=Path,
                        help="caller-supplied Ed25519 private-key PEM")
    parser.add_argument(
        "--unsafe-development-ephemeral",
        action="store_true",
        help=(
            "explicitly use an ephemeral key; output is not provenance evidence"
        ),
    )
    args = parser.parse_args()

    try:
        key_source = key_source_from_options(
            args.signing_key,
            unsafe_development_ephemeral=args.unsafe_development_ephemeral,
        )
        signer = key_source.load()
    except (OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))

    records = _run_native(args.binary, args.size_mib, args.cycles, args.stride_mib)
    aggregates = [AggregateRecord(**record) for record in records]
    product = (aggregates[0].driver_metadata or {}).get("device_name", "local")
    digest = os.environ.get("GPU_SEAL_CONTAINER_DIGEST")
    commit = _provenance_value("git_commit") or "native-uncommitted"
    bundle = ResultBundle(
        experiment_id=f"exp_native_local_{uuid.uuid4().hex[:12]}",
        run_id=f"run_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
        provider_code="local-native",
        region_claim="n/a",
        product_claim=product,
        tool=ToolProvenance(
            version=__version__,
            commit=commit,
            container_digest=digest,
            cuda_runtime_version=(aggregates[0].driver_metadata or {}).get(
                "cuda_runtime_version"
            ),
            cuda_driver_version=(aggregates[0].driver_metadata or {}).get(
                "cuda_driver_version"
            ),
        ),
        probes=aggregates,
        environment=aggregates[0].driver_metadata or {},
        allocation_model={
            "classification": "local_workstation",
            "confidence": 1.0,
            "evidence": ["researcher-owned hardware; native slice local-only"],
        },
    )
    bundle.environment["signing"] = signing_metadata(key_source, signer)
    signed = bundle.sign(signer)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{bundle.run_id}.result.json"
    path.write_text(json.dumps(signed, indent=2), encoding="utf-8")
    print(f"public-key fingerprint={signer.verify_key.fingerprint}")
    if not key_source.provenance_suitable:
        print(
            "WARNING: UNSAFE DEVELOPMENT KEY; output is unsuitable for "
            "provenance claims"
        )
    print(f"native aggregates={len(aggregates)}")
    print(f"signature_valid={ResultBundle.verify(signed)}")
    print(f"written_to={path}")
    print("publication_cleared=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
