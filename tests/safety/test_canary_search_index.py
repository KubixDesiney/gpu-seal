"""The indexed canary search must agree with the naive scan, exactly.

`CanarySet.search` was O(canaries ever minted × buffer). At pilot scale that
was fine; on the §11 Phase 3 campaign — 20 cycles over 64 MiB buffers, one
marker per MiB — it is hundreds of gigabytes of scanning.

The replacement is O(buffer + occurrences). Because it is an optimisation of a
*safety-relevant* function — the only search GPU-SEAL performs — it is tested
against the reference implementation rather than against hand-written
expectations. If the two can ever disagree, this finds it.
"""

from __future__ import annotations

import os
import random
import time

import pytest
from gpu_seal.safety.canary import Boundary, CanarySet, _longest_prefix_present

pytestmark = pytest.mark.safety


def naive_search(canaries: CanarySet, data: bytes) -> dict:
    """The original implementation, kept as the oracle."""
    out = {}
    for canary in canaries.emitted:
        prefix = _longest_prefix_present(data, canary.blob)
        exact = prefix == len(canary.blob)
        mac_ok = False
        if exact:
            idx = data.find(canary.blob)
            if idx >= 0:
                mac_ok = canaries.owns(data[idx : idx + len(canary.blob)])
        out[canary.allocation_id] = (prefix, exact and mac_ok)
    return out


def indexed_search(canaries: CanarySet, data: bytes) -> dict:
    return {
        m.allocation_id: (m.longest_prefix_bytes, m.exact)
        for m in canaries.search(data)
    }


def build(seed: int, *, count: int = 6, boundaries: int = 2):
    # Seeded, for reproducible layouts. Nothing here is a secret — the
    # canaries themselves are minted with os.urandom by CanarySet.
    rng = random.Random(seed)  # noqa: S311
    canaries = CanarySet.create()
    minted = [
        canaries.mint(Boundary(1 + (i % boundaries))) for i in range(count)
    ]
    return canaries, minted, rng


# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(12))
def test_indexed_search_matches_the_naive_scan_on_random_layouts(seed):
    """Whole markers, truncated markers, and noise, in random positions."""
    canaries, minted, rng = build(seed)
    buffer = bytearray(os.urandom(8192))

    for canary in minted:
        choice = rng.randrange(4)
        if choice == 0:
            continue  # absent entirely
        if choice == 1:
            length = len(canary.blob)  # whole marker
        elif choice == 2:
            length = rng.randrange(1, 16)  # less than the anchor survived
        else:
            length = rng.randrange(16, len(canary.blob))  # truncated
        at = rng.randrange(0, len(buffer) - len(canary.blob))
        buffer[at : at + length] = canary.blob[:length]

    data = bytes(buffer)
    assert indexed_search(canaries, data) == naive_search(canaries, data)


def test_agreement_on_an_empty_buffer():
    canaries, _, _ = build(1)
    data = bytes(4096)
    assert indexed_search(canaries, data) == naive_search(canaries, data)


def test_agreement_when_every_marker_is_present_whole():
    canaries, minted, _ = build(2, count=8)
    data = b"".join(c.blob for c in minted)
    indexed = indexed_search(canaries, data)
    assert indexed == naive_search(canaries, data)
    assert all(exact for _, exact in indexed.values())


def test_agreement_when_markers_overlap_the_same_region():
    """Two markers written at the same offset, the second clobbering the first."""
    canaries, minted, _ = build(3, count=2, boundaries=1)
    buffer = bytearray(1024)
    buffer[0 : len(minted[0].blob)] = minted[0].blob
    buffer[40 : 40 + len(minted[1].blob)] = minted[1].blob
    data = bytes(buffer)
    assert indexed_search(canaries, data) == naive_search(canaries, data)


def test_a_forged_marker_is_not_reported_as_exact():
    """A 128-byte blob that is not ours must not authenticate."""
    canaries, minted, _ = build(4, count=1)
    forged = bytearray(minted[0].blob)
    forged[-1] ^= 0xFF  # break the MAC
    data = bytes(2048) + bytes(forged)

    matches = canaries.search(data)
    assert len(matches) == 1
    assert matches[0].exact is False
    assert matches[0].mac_verified is False
    # The prefix is still measured — most of it really is there.
    assert matches[0].longest_prefix_bytes == len(forged) - 1


def test_search_is_sublinear_in_the_number_of_canaries():
    """The property the rewrite exists for.

    Twenty times the markers must not cost twenty times the search. Compared
    as a ratio rather than an absolute time so the assertion means the same
    thing on a slow machine.
    """
    haystack = bytes(4 << 20)

    def time_search(count: int) -> float:
        canaries = CanarySet.create()
        for _ in range(count):
            canaries.mint(Boundary.SEPARATE_LAUNCH)
        started = time.perf_counter()
        canaries.search(haystack)
        return time.perf_counter() - started

    small = time_search(10)
    large = time_search(200)
    # Naive scaling would be ~20x. Allow generous headroom for timer noise on
    # a buffer this small; the point is that it is not proportional.
    assert large < max(small * 8, 0.5)
