"""The one permitted decoder must refuse anything that is not driver metadata.

``ascii_metadata`` is the single exemption to the no-decoding rule
(CHARTER.md §7.2, §16 test 4). The exemption is only defensible if the helper
structurally cannot be turned into a general-purpose decoder — so that is what
these tests check.
"""

from __future__ import annotations

import os

import pytest

from gpu_seal.safety.errors import UnknownMemoryRenderError
from gpu_seal.safety.metadata import MAX_METADATA_BYTES, ascii_metadata

pytestmark = pytest.mark.safety


def test_decodes_a_device_name():
    assert ascii_metadata(b"NVIDIA GeForce RTX 3050") == "NVIDIA GeForce RTX 3050"


def test_truncates_at_nul():
    assert ascii_metadata(b"NVIDIA A100\x00\x00garbage") == "NVIDIA A100"


def test_passes_through_non_bytes_untouched():
    assert ascii_metadata(42) == "42"
    assert ascii_metadata("already text") == "already text"


def test_refuses_random_memory():
    """The property that justifies the exemption: VRAM will not go through."""
    with pytest.raises(UnknownMemoryRenderError):
        ascii_metadata(os.urandom(64), field="pretend_vram")


def test_refuses_anything_oversized():
    with pytest.raises(UnknownMemoryRenderError) as exc:
        ascii_metadata(b"A" * (MAX_METADATA_BYTES + 1))
    assert "not a decoder" in str(exc.value)


def test_refuses_a_page_of_memory():
    with pytest.raises(UnknownMemoryRenderError):
        ascii_metadata(b"\x00" * 4096)


def test_refuses_non_printable_bytes():
    with pytest.raises(UnknownMemoryRenderError):
        ascii_metadata(b"NVIDIA\x01\x02\x03")


def test_refuses_utf8_text():
    """Not even legitimate UTF-8 gets through. ASCII metadata only."""
    with pytest.raises(UnknownMemoryRenderError):
        ascii_metadata("café".encode("utf-8"))


def test_refusal_returns_nothing_partial():
    """A failed conversion must not leak a prefix of what it refused."""
    payload = b"READABLE_PREFIX" + os.urandom(32)
    with pytest.raises(UnknownMemoryRenderError) as exc:
        ascii_metadata(payload)
    assert "READABLE_PREFIX" not in str(exc.value)
