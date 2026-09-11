"""CI-facing tests for release integrity gates."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import zipfile
from pathlib import Path


def _release_module():
    path = Path(__file__).resolve().parents[2] / "lab" / "check-release-readiness.py"
    spec = importlib.util.spec_from_file_location("gpu_seal_release_readiness", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lock_and_base_image_gates_pass_for_repository_files():
    module = _release_module()
    assert module.check_lock_file().ok
    assert module.check_release_base_digest().ok
    assert module.check_github_action_pins().ok


def test_lock_gate_rejects_literal_backslash_n_continuations(tmp_path, monkeypatch):
    module = _release_module()
    lock = tmp_path / "infrastructure" / "containers" / "requirements-lock.txt"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        "pkg==1.0 " + "\\n    --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    check = module.check_lock_file()

    assert not check.ok
    assert "continuation" in check.problems[0]


def test_base_image_gate_rejects_mutable_tag(tmp_path, monkeypatch):
    module = _release_module()
    dockerfile = tmp_path / "infrastructure" / "containers" / "Dockerfile"
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text(
        "FROM nvidia/cuda:12.6.2-devel-ubuntu22.04\n", encoding="utf-8"
    )
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    check = module.check_release_base_digest()

    assert not check.ok
    assert "not pinned" in check.problems[0]


def test_github_action_gate_rejects_mutable_reference(tmp_path, monkeypatch):
    module = _release_module()
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    check = module.check_github_action_pins()

    assert not check.ok
    assert "mutable" in check.problems[0]


def test_dirty_worktree_gate_fails(monkeypatch):
    module = _release_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, " M changed.py\n", ""
        ),
    )

    check = module.check_worktree_clean()

    assert not check.ok
    assert "modified or untracked" in check.problems[0]


def test_git_status_failure_is_a_release_failure(monkeypatch):
    module = _release_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 128, "", "fatal"),
    )

    check = module.check_worktree_clean()

    assert not check.ok
    assert "exit code 128" in check.problems[0]


def test_named_provider_gate_rejects_a_real_name_in_a_tracked_file(
    tmp_path, monkeypatch
):
    module = _release_module()
    leaking = tmp_path / "docs" / "provider-policy-review" / "provider-a.json"
    leaking.parent.mkdir(parents=True)
    leaking.write_text('{"notes": "cites the AWS AUP directly"}', encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, "docs/provider-policy-review/provider-a.json\n", ""
        ),
    )

    check = module.check_no_named_providers()

    assert not check.ok
    assert "provider-a.json" in check.problems[0]
    assert "AWS" in check.problems[0]


def test_named_provider_gate_ignores_the_reviewed_allowlist(tmp_path, monkeypatch):
    module = _release_module()
    charter = tmp_path / "CHARTER.md"
    charter.write_text(
        "one EU-sovereign provider (Scaleway / Exoscale / STACKIT)",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, "CHARTER.md\n", ""
        ),
    )

    check = module.check_no_named_providers()

    assert check.ok


def test_named_provider_gate_passes_the_repository_as_it_stands():
    module = _release_module()
    assert module.check_no_named_providers().ok


def test_wheel_gate_requires_runtime_schemas(tmp_path):
    module = _release_module()
    wheel = tmp_path / "gpu_seal.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("gpu_seal/cli.py", "")
        archive.writestr("gpu_seal/schemas/result.schema.json", "{}")

    check = module.check_wheel_contents(wheel)

    assert not check.ok
    assert "experiment.schema.json" in check.problems[0]


def test_dashboard_asset_gate_checks_manifest_files(tmp_path):
    module = _release_module()
    dist = tmp_path / "dist" / "client"
    (dist / ".vite").mkdir(parents=True)
    (dist / "assets").mkdir()
    (dist / "assets" / "app.css").write_text("", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("", encoding="utf-8")
    (dist / ".vite" / "manifest.json").write_text(
        json.dumps({"index": {"file": "assets/app.js", "css": ["assets/app.css"]}}),
        encoding="utf-8",
    )

    assert module.check_dashboard_assets(dist).ok
