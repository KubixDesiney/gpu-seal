"""gpu_seal.__version__ must track the installed package, not a stale literal.

probe/gpu_seal/__init__.py used to hardcode "0.1.0.dev0" while
pyproject.toml's ``version`` had already moved to "0.1.0a1", so every signed
bundle's ``tool.version`` carried the wrong value regardless of what was
actually installed.
"""

from __future__ import annotations

from importlib import metadata

import gpu_seal
from gpu_seal.evidence.result import ToolProvenance


def test_version_matches_the_installed_distribution_metadata():
    assert gpu_seal.__version__ == metadata.version("gpu-seal")


def test_a_fresh_bundle_tool_version_matches_the_installed_package():
    tool = ToolProvenance(version=gpu_seal.__version__, commit="sha256:" + "a" * 64)
    assert tool.version == metadata.version("gpu-seal")


def test_fallback_literal_is_used_only_when_no_distribution_is_installed(
    monkeypatch,
):
    def _raise(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", _raise)
    import importlib as importlib_module

    reloaded = importlib_module.reload(gpu_seal)
    try:
        assert reloaded.__version__ == "0.1.0a1"
    finally:
        # Restore the real, installed version for every other test in the
        # process -- this module must not leave gpu_seal in a fallback state.
        monkeypatch.undo()
        importlib_module.reload(gpu_seal)
