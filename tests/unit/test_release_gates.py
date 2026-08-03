"""CI-facing tests for release integrity gates."""

from __future__ import annotations

import importlib.util
import subprocess
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
