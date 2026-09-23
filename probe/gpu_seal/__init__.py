"""GPU-SEAL — Tenant-Observable Security and Isolation Assurance for GPU Clouds.

An assurance and measurement framework, not an exploitation toolkit.
See CHARTER.md.
"""

from __future__ import annotations

from importlib import metadata as _metadata

try:
    __version__ = _metadata.version("gpu-seal")
except _metadata.PackageNotFoundError:
    # Source checkout with no install present (editable or otherwise) --
    # e.g. running straight out of a git clone before `pip install -e .`.
    # Keep this in step with pyproject.toml's `version` by hand; every
    # bundle's tool.version is wrong until one of the two is installed, and
    # tests/unit/test_version.py catches that drift once it is.
    __version__ = "0.1.0a1"

__all__ = ["__version__"]
