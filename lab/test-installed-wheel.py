#!/usr/bin/env python3
"""Build and exercise GPU-SEAL from a non-editable wheel installation."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)  # noqa: S603


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpu-seal-wheel-") as raw_tmp:
        temp = Path(raw_tmp)
        wheelhouse = temp / "wheelhouse"
        wheelhouse.mkdir()
        run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(wheelhouse),
            ],
            cwd=REPO_ROOT,
        )
        wheels = sorted(wheelhouse.glob("gpu_seal-*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"expected exactly one wheel, found {wheels}")

        virtualenv = temp / "venv"
        run([sys.executable, "-m", "venv", str(virtualenv)], cwd=REPO_ROOT)
        python = virtualenv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                str(wheels[0]),
            ],
            cwd=temp,
        )

        outside_repo = temp / "outside-repository"
        outside_repo.mkdir()
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        code = """
from gpu_seal.controller import EvidenceStore
from gpu_seal.evidence import EphemeralDevelopmentKeySource, ResultBundle
from gpu_seal.evidence.result import ToolProvenance
from gpu_seal.resources import RUNTIME_SCHEMA_NAMES, load_schema
import os
from pathlib import Path
import subprocess
import sys

assert {
    name for name in RUNTIME_SCHEMA_NAMES if load_schema(name)
} == set(RUNTIME_SCHEMA_NAMES)
key = EphemeralDevelopmentKeySource(unsafe_development=True).load()
bundle = ResultBundle(
    experiment_id="wheel-test",
    run_id="outside-repository",
    provider_code="provider-a",
    region_claim="local",
    product_claim="test",
    tool=ToolProvenance(version="test", commit="test"),
)
stored = EvidenceStore("evidence").write(bundle, key)
assert EvidenceStore("evidence").read(stored.path)["run_id"] == "outside-repository"
verification = subprocess.run(
    [
        str(
            Path(sys.executable).with_name(
                "gpu-seal.exe" if os.name == "nt" else "gpu-seal"
            )
        ),
        "verify",
        str(stored.path),
        "--public-key",
        key.verify_key.hex,
    ],
    check=False,
    capture_output=True,
    text=True,
)
assert verification.returncode == 0, verification.stderr
assert "trusted verification: PASS" in verification.stdout
print("wheel install and package-resource evidence validation: PASS")
"""
        run([str(python), "-c", code], cwd=outside_repo, env=env)
        print(f"wheel contents and clean install: PASS ({wheels[0].name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
