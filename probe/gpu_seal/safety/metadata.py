"""The only permitted bytes-to-text conversion in GPU-SEAL.

CHARTER.md §7.2 forbids attempting UTF-8 decoding, and
``tests/safety/test_static_analysis.py`` enforces that by rejecting every
``.decode()`` call in probe source. But the CUDA runtime returns some driver
metadata — notably the device name — as NUL-terminated byte strings, and a
result bundle that cannot say which GPU it measured is not much use.

Rather than exempt a whole module, the exemption is this one function, and it
is built so that it *structurally cannot* be used on unknown memory:

* input must be short (device names are, unknown buffers are not)
* every byte must be printable ASCII or NUL, or it refuses
* the result is truncated at the first NUL
* it never returns partial output on failure — it raises

Feed it a page of VRAM and it will refuse, because VRAM is not printable
ASCII. That refusal is the safety property, not a side effect.
"""

from __future__ import annotations

import hashlib

from .errors import UnknownMemoryRenderError

__all__ = ["ascii_metadata", "stable_hash", "MAX_METADATA_BYTES"]

#: Longest byte string accepted. CUDA device names are well under this.
#: Small enough that no meaningful quantity of memory can pass through.
MAX_METADATA_BYTES = 256

_PRINTABLE = frozenset(range(0x20, 0x7F)) | {0x00, 0x09}


def ascii_metadata(value: object, *, field: str = "metadata") -> str:
    """Convert driver-supplied bytes to text, or refuse.

    Args:
        value: bytes from a driver/runtime metadata call. Non-bytes values are
            passed through ``str()`` unchanged, since they were never bytes.
        field: name used in the error message, to make a refusal diagnosable.

    Raises:
        UnknownMemoryRenderError: the input was too long, or contained bytes
            that are not printable ASCII — i.e. it was not driver metadata.
    """
    if not isinstance(value, (bytes, bytearray)):
        return str(value)

    if len(value) > MAX_METADATA_BYTES:
        raise UnknownMemoryRenderError(
            f"Refusing to convert {len(value)} bytes for field {field!r}: "
            f"driver metadata is at most {MAX_METADATA_BYTES} bytes. Anything "
            f"larger is not metadata, and this function is not a decoder "
            f"(CHARTER.md §7.2)."
        )

    # Operate on the input directly. Both bytes and bytearray support split()
    # and decode(), so there is no need to materialise a copy — and not doing
    # so keeps this module outside the raw-byte allowlist entirely.
    offending = [b for b in value if b not in _PRINTABLE]
    if offending:
        raise UnknownMemoryRenderError(
            f"Refusing to convert field {field!r}: input contains "
            f"{len(offending)} non-printable byte(s). Driver metadata is "
            f"printable ASCII; arbitrary memory is not. This function will "
            f"not decode it (CHARTER.md §7.2)."
        )

    return value.split(b"\x00", 1)[0].decode("ascii")


#: Domain separator for :func:`stable_hash`. Without it, the same identifier
#: hashed for two different purposes produces the same digest, and a reader
#: who knows one mapping learns the other.
_HASH_DOMAIN = "gpu-seal/v1/"


def stable_hash(value: object, *, domain: str) -> str:
    """Hash an identifier that CHARTER.md §10 forbids publishing in the clear.

    Account IDs, GPU UUIDs, hostnames, and instance IDs are all *useful* —
    they let a reader confirm two observations came from the same allocation —
    and all *unpublishable*. Hashing keeps the join and drops the identifier.

    This is not anonymisation and does not pretend to be. The input space for
    a GPU UUID is small enough to enumerate if you hold the fleet, so the
    guarantee here is "not published in the clear", not "unrecoverable by the
    provider who issued it". Say that in the paper rather than implying more.

    Args:
        domain: what the identifier *is* (``"gpu_uuid"``, ``"account_id"``).
            Separates hash spaces so one disclosed mapping does not leak
            another.
    """
    material = f"{_HASH_DOMAIN}{domain}:{value}".encode()
    return "sha256:" + hashlib.sha256(material).hexdigest()[:32]
