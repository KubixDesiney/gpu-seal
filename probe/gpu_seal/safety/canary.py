"""Authenticated researcher-owned canaries — CHARTER.md §7.1.

    "GPU-SEAL may search **only** for canaries the operator generated. A canary
     must be randomly generated, unique per controlled experiment, non-semantic,
     cryptographically identifiable, bound to an experiment ID, and free of
     personal information, real secrets, copyrighted content, and realistic
     prompts/messages."

Two properties do the ethical work here:

1. **Non-semantic.** The payload is a random nonce and a MAC. There is no
   readable text anywhere in a canary, so a canary recovered by a *third party*
   from *their* memory leaks nothing about us either. The marker is symmetric
   in its harmlessness.

2. **Cryptographically owned.** Every canary carries a keyed BLAKE2b MAC over
   its own header. Without the experiment key you cannot forge one, and the
   matcher will not accept one it cannot authenticate. This is what makes
   "we only searched for our own data" a checkable claim rather than a promise.

Wire format — 128 bytes, 16-byte aligned::

    offset  size  field
    0       8     magic          b'GPUSEALC'
    8       2     version        uint16 LE
    10      2     boundary_id    uint16 LE
    12      4     flags          uint32 LE
    16      16    experiment_id  UUID bytes
    32      16    allocation_id  UUID bytes
    48      32    nonce          os.urandom(32)
    80      16    reserved       zeros
    96      32    mac            BLAKE2b-256(key=experiment_key, data=bytes[0:96])
    ----    ---
    128
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
import uuid
from collections.abc import Container
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Final

from .errors import ForeignCanaryError
from .policy import (
    CANARY_KEY_SIZE,
    CANARY_MAC_SIZE,
    CANARY_MAGIC,
    CANARY_NONCE_SIZE,
    CANARY_SIZE,
    CANARY_VERSION,
)

__all__ = ["Boundary", "Canary", "CanarySet", "CanaryMatch"]

_HEADER_STRUCT: Final = struct.Struct("<8sHHI16s16s32s16s")
_MAC_OFFSET: Final = 96

# Wire-format invariants, checked at import. Deliberately `raise`, not
# `assert`: assertions are stripped under `python -O`, and a canary layout
# that silently drifts from ADR-002 under an optimised interpreter would
# produce markers the matcher cannot recognise — a detection failure that
# looks exactly like a clean provider result.
if _HEADER_STRUCT.size != _MAC_OFFSET:  # pragma: no cover - import-time invariant
    raise RuntimeError(
        f"canary header must be {_MAC_OFFSET} bytes, struct packs "
        f"{_HEADER_STRUCT.size} (ADR-002)"
    )
if _MAC_OFFSET + CANARY_MAC_SIZE != CANARY_SIZE:  # pragma: no cover
    raise RuntimeError(
        f"canary must be {CANARY_SIZE} bytes, layout gives "
        f"{_MAC_OFFSET + CANARY_MAC_SIZE} (ADR-002)"
    )


class Boundary(IntEnum):
    """The isolation boundary a canary is written across — CHARTER.md §9.2, §9.3.

    Recording this in the canary itself means a recovered marker tells you
    *which* boundary it crossed, without needing to correlate against a log
    that may have been written on a different machine.
    """

    UNSPECIFIED = 0
    SAME_KERNEL = 1
    SEPARATE_LAUNCH = 2
    SEPARATE_STREAM = 3
    SEPARATE_CONTEXT = 4
    SEPARATE_PROCESS = 5
    SEPARATE_CONTAINER = 6
    SEPARATE_VM = 7
    SEQUENTIAL_ALLOCATION = 8  # release and re-rent the cloud allocation
    MIG_SAME_PROFILE = 9  # §9.12
    MIG_DIFFERENT_PROFILE = 10  # §9.12
    GPU_RESET = 11
    DRIVER_RELOAD = 12
    HOST_REBOOT = 13


@dataclass(frozen=True)
class Canary:
    """A single emitted canary. Owned by this experiment, safe to retain."""

    blob: bytes
    experiment_id: uuid.UUID
    allocation_id: uuid.UUID
    boundary: Boundary
    nonce: bytes

    def __post_init__(self) -> None:
        if len(self.blob) != CANARY_SIZE:
            raise ValueError(f"canary must be {CANARY_SIZE} bytes")

    @property
    def label(self) -> str:
        """Short non-secret identifier for logs. Contains no payload bytes."""
        return f"{self.allocation_id.hex[:8]}/{self.boundary.name}"


@dataclass(frozen=True)
class CanaryMatch:
    """Result of matching one owned canary against a buffer. Metadata only."""

    allocation_id: uuid.UUID
    boundary: Boundary
    exact: bool
    longest_prefix_bytes: int
    mac_verified: bool

    @property
    def fraction_recovered(self) -> float:
        return self.longest_prefix_bytes / CANARY_SIZE


@dataclass
class CanarySet:
    """All canaries owned by one experiment, plus the key that authenticates them.

    The matcher searches for members of this set and nothing else. There is no
    API to search for an arbitrary byte pattern — that is the point.
    """

    experiment_id: uuid.UUID
    _key: bytes = field(repr=False)
    _emitted: dict[uuid.UUID, Canary] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------

    @classmethod
    def create(cls, experiment_id: uuid.UUID | None = None) -> CanarySet:
        """Start a new experiment with a fresh random key."""
        return cls(
            experiment_id=experiment_id or uuid.uuid4(),
            _key=os.urandom(CANARY_KEY_SIZE),
        )

    def __len__(self) -> int:
        return len(self._emitted)

    @property
    def emitted(self) -> tuple[Canary, ...]:
        return tuple(self._emitted.values())

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def mint(
        self,
        boundary: Boundary,
        allocation_id: uuid.UUID | None = None,
        flags: int = 0,
    ) -> Canary:
        """Generate and register a new canary for this experiment."""
        allocation_id = allocation_id or uuid.uuid4()
        nonce = os.urandom(CANARY_NONCE_SIZE)

        header = _HEADER_STRUCT.pack(
            CANARY_MAGIC,
            CANARY_VERSION,
            int(boundary),
            flags,
            self.experiment_id.bytes,
            allocation_id.bytes,
            nonce,
            b"\x00" * 16,  # reserved
        )
        mac = self._mac(header)
        canary = Canary(
            blob=header + mac,
            experiment_id=self.experiment_id,
            allocation_id=allocation_id,
            boundary=boundary,
            nonce=nonce,
        )
        self._emitted[allocation_id] = canary
        return canary

    def _mac(self, header: bytes) -> bytes:
        return hashlib.blake2b(
            header, digest_size=CANARY_MAC_SIZE, key=self._key
        ).digest()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self, blob: bytes) -> Canary:
        """Verify a 128-byte blob is a canary THIS experiment minted.

        Raises :class:`ForeignCanaryError` otherwise. This is the gate that
        makes "canary-only search" enforceable: a marker we cannot
        authenticate is not ours, and we do not look for it.
        """
        if len(blob) != CANARY_SIZE:
            raise ForeignCanaryError(
                f"Not a canary: expected {CANARY_SIZE} bytes, got {len(blob)}."
            )
        header, mac = blob[:_MAC_OFFSET], blob[_MAC_OFFSET:]

        magic, version, boundary_id, _flags, exp_bytes, alloc_bytes, nonce, _res = (
            _HEADER_STRUCT.unpack(header)
        )
        if magic != CANARY_MAGIC:
            raise ForeignCanaryError("Not a canary: bad magic.")
        if version != CANARY_VERSION:
            raise ForeignCanaryError(f"Unsupported canary version {version}.")
        if not hmac.compare_digest(mac, self._mac(header)):
            raise ForeignCanaryError(
                "Canary MAC does not verify under this experiment's key. This "
                "marker was not minted by this experiment and will not be "
                "searched for (CHARTER.md §7.1)."
            )
        exp_id = uuid.UUID(bytes=exp_bytes)
        if exp_id != self.experiment_id:
            raise ForeignCanaryError(
                f"Canary belongs to experiment {exp_id}, not {self.experiment_id}."
            )
        return Canary(
            blob=blob,
            experiment_id=exp_id,
            allocation_id=uuid.UUID(bytes=alloc_bytes),
            boundary=Boundary(boundary_id),
            nonce=nonce,
        )

    def owns(self, blob: bytes) -> bool:
        """Non-raising form of :meth:`authenticate`."""
        try:
            self.authenticate(blob)
            return True
        except ForeignCanaryError:
            return False

    # ------------------------------------------------------------------
    # Matching — the only search GPU-SEAL performs
    # ------------------------------------------------------------------

    def search(
        self,
        haystack: memoryview | bytes,
        *,
        allocation_id_scope: Container[uuid.UUID] | None = None,
    ) -> list[CanaryMatch]:
        """Find owned canaries in a buffer. Returns metadata; never bytes.

        Args:
            allocation_id_scope: when given, only these canaries are searched
                for — every other canary this experiment ever minted is
                excluded, from both the search and the returned matches.

                This is what makes "an owned canary matched" mean "*the*
                canary I planted here matched", not "some canary this
                experiment minted somewhere matched" — a distinction that
                matters whenever a caller reuses one CanarySet across
                multiple allocations (the §9.5 self-vs-self design does
                exactly this) and a stale marker from a different allocation
                could otherwise be misattributed. Pass the specific
                :attr:`Canary.allocation_id` (or ids) the buffer being
                searched is expected to contain; omit it only when any
                owned canary anywhere in the experiment is a valid answer.

        For each canary this experiment minted, reports whether it appears in
        full (MAC-verified) and the longest prefix of it that appears at all.
        Partial prefixes matter: a buffer that was overwritten part-way through
        retains a truncated marker, and the recovered fraction is itself a
        measurement.

        This function is the *entire* search surface of GPU-SEAL. There is
        deliberately no method that takes a caller-supplied pattern.

        **Cost.** The obvious implementation — scan the buffer once per canary
        — is O(canaries ever minted × buffer). That is fine at pilot scale and
        untenable on the §11 Phase 3 campaign: 20 cycles over 64 MiB buffers
        with one marker per MiB mints ~1280 canaries, and ~7 substring scans
        each puts the search into the hundreds of gigabytes of scanning.

        This implementation scans the buffer once per *boundary group* and
        gives **identical answers**, which is what
        ``tests/safety/test_canary_search_index.py`` asserts against the
        reference implementation below on randomised layouts. The equivalence
        argument:

        * Canaries minted for the same boundary share their first 16 bytes
          (magic, version, boundary, flags). Group them by that anchor.
        * If a canary's longest recovered prefix is **under 16 bytes**, it is
          a prefix of the shared anchor, so it is identical for every canary
          in the group and is computed once.
        * If it is **16 or more**, the anchor occurs at that position, so
          enumerating anchor occurrences finds every candidate site.

        The per-occurrence work compares against each group member rather than
        looking the owner up by allocation id. Identification by lookup was
        the first attempt and it is wrong: a marker truncated *inside* its own
        allocation-id field has no readable id, so the lookup misses and the
        surviving prefix is under-reported. The equivalence test caught it.

        Cost is therefore O(buffer + occurrences × group size), where
        occurrences is bounded by the markers physically present in **this**
        buffer — not by the number ever minted, which was the actual problem.

        Note: the ``bytes(haystack)`` conversion below makes one full
        immutable copy of the buffer for every canary-enabled call. Unlike
        ``SafeBuffer.destroy()``, an immutable ``bytes`` object cannot be
        explicitly zeroed — it is left to normal garbage collection. See the
        caveat in ``gpu_seal.safety.buffer``'s module docstring.
        """
        data = bytes(haystack) if not isinstance(haystack, bytes) else haystack

        canaries = (
            self._emitted.values()
            if allocation_id_scope is None
            else [
                c
                for c in self._emitted.values()
                if c.allocation_id in allocation_id_scope
            ]
        )

        groups: dict[bytes, list[Canary]] = {}
        for canary in canaries:
            groups.setdefault(canary.blob[:_ANCHOR_SIZE], []).append(canary)

        best: dict[uuid.UUID, int] = {}
        verified: set[uuid.UUID] = set()

        for anchor, members in groups.items():
            floor = _longest_prefix_present(data, anchor)
            for canary in members:
                best[canary.allocation_id] = floor
            if floor < _ANCHOR_SIZE:
                # Not even the shared header survived intact, so no anchor
                # occurs anywhere and there is nothing to enumerate.
                continue

            index = data.find(anchor)
            while index >= 0:
                candidate = data[index : index + CANARY_SIZE]
                for canary in members:
                    length = _common_prefix_length(candidate, canary.blob)
                    if length > best[canary.allocation_id]:
                        best[canary.allocation_id] = length
                    if length == CANARY_SIZE and self.owns(candidate):
                        # Re-authenticate the recovered instance rather than
                        # trusting the byte comparison alone.
                        verified.add(canary.allocation_id)
                index = data.find(anchor, index + 1)

        return [
            CanaryMatch(
                allocation_id=canary.allocation_id,
                boundary=canary.boundary,
                exact=canary.allocation_id in verified,
                longest_prefix_bytes=best.get(canary.allocation_id, 0),
                mac_verified=canary.allocation_id in verified,
            )
            for canary in canaries
        ]


#: Bytes shared by every canary of one boundary: magic, version, boundary id,
#: and flags. Long enough to be rare in random data, short enough that a
#: heavily-truncated marker still anchors on it.
_ANCHOR_SIZE: Final = 16

#: Bytes shared by every canary of one boundary in one experiment — the anchor
#: plus the experiment id. Beyond this, canaries diverge.
_SHARED_HEADER_SIZE: Final = 32

_ALLOCATION_ID_OFFSET: Final = 32
_ALLOCATION_ID_END: Final = 48


def _common_prefix_length(a: bytes, b: bytes) -> int:
    """Length of the longest common prefix of two byte strings."""
    limit = min(len(a), len(b))
    for i in range(limit):
        if a[i] != b[i]:
            return i
    return limit


def _longest_prefix_present(haystack: bytes, needle: bytes) -> int:
    """Length of the longest prefix of ``needle`` occurring in ``haystack``.

    Binary search over prefix length: ~7 substring scans for a 128-byte needle,
    rather than 128. Monotonic because if a prefix of length k is absent, every
    longer prefix is also absent.
    """
    if not needle or not haystack:
        return 0
    if haystack.find(needle[:1]) < 0:
        return 0

    lo, hi = 1, len(needle)  # lo is known-present, hi is candidate upper bound
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if haystack.find(needle[:mid]) >= 0:
            lo = mid
        else:
            hi = mid - 1
    return lo
