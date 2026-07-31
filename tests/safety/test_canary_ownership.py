"""CHARTER.md §16 test 6 — the matcher accepts only experiment-owned canaries.

This is the test that makes "canary-only search" a checkable claim rather
than a promise in a README. If GPU-SEAL can be induced to search for a
pattern it did not mint, the entire ethics argument collapses.
"""

from __future__ import annotations

import os
import uuid

import pytest

from gpu_seal.safety import Boundary, CanarySet, ForeignCanaryError
from gpu_seal.safety.policy import CANARY_MAGIC, CANARY_SIZE

pytestmark = pytest.mark.safety


def test_minted_canary_has_correct_shape():
    cs = CanarySet.create()
    c = cs.mint(Boundary.SEPARATE_PROCESS)
    assert len(c.blob) == CANARY_SIZE
    assert c.blob.startswith(CANARY_MAGIC)


def test_canary_authenticates_under_its_own_key():
    cs = CanarySet.create()
    c = cs.mint(Boundary.SEPARATE_CONTAINER)
    recovered = cs.authenticate(c.blob)
    assert recovered.allocation_id == c.allocation_id
    assert recovered.boundary is Boundary.SEPARATE_CONTAINER


def test_canary_from_another_experiment_is_rejected():
    """The core ownership test: a different experiment's marker is foreign."""
    mine = CanarySet.create()
    theirs = CanarySet.create()
    foreign = theirs.mint(Boundary.SEPARATE_PROCESS)

    with pytest.raises(ForeignCanaryError):
        mine.authenticate(foreign.blob)
    assert not mine.owns(foreign.blob)


def test_forged_canary_with_correct_magic_is_rejected():
    """Magic bytes are not authentication. Only the MAC is."""
    cs = CanarySet.create()
    forged = CANARY_MAGIC + os.urandom(CANARY_SIZE - len(CANARY_MAGIC))
    with pytest.raises(ForeignCanaryError):
        cs.authenticate(forged)


def test_tampered_canary_is_rejected():
    cs = CanarySet.create()
    c = cs.mint(Boundary.SEQUENTIAL_ALLOCATION)
    tampered = bytearray(c.blob)
    tampered[50] ^= 0xFF  # flip a bit in the nonce
    with pytest.raises(ForeignCanaryError):
        cs.authenticate(bytes(tampered))


def test_canary_bound_to_experiment_id():
    """A canary minted under experiment X must not authenticate under Y,
    even if an attacker somehow had the key."""
    key_shared = os.urandom(32)
    exp_a, exp_b = uuid.uuid4(), uuid.uuid4()
    a = CanarySet(experiment_id=exp_a, _key=key_shared)
    b = CanarySet(experiment_id=exp_b, _key=key_shared)

    c = a.mint(Boundary.SEPARATE_VM)
    assert a.owns(c.blob)
    with pytest.raises(ForeignCanaryError):
        b.authenticate(c.blob)


def test_canary_contains_no_readable_text():
    """CHARTER.md §7.1: canaries must be non-semantic.

    A marker containing a readable sentence would be a liability if it ever
    surfaced in someone else's memory dump. The only ASCII permitted is the
    8-byte magic.
    """
    cs = CanarySet.create()
    for _ in range(50):
        c = cs.mint(Boundary.SEPARATE_PROCESS)
        body = c.blob[len(CANARY_MAGIC) :]
        printable_runs = _longest_printable_run(body)
        assert printable_runs < 12, (
            f"canary body contained a {printable_runs}-byte printable run; "
            f"canaries must be non-semantic (CHARTER.md §7.1)"
        )


def _longest_printable_run(data: bytes) -> int:
    best = run = 0
    for b in data:
        if 0x20 <= b <= 0x7E:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def test_canaries_are_unique_per_allocation():
    cs = CanarySet.create()
    blobs = {cs.mint(Boundary.SEPARATE_PROCESS).blob for _ in range(200)}
    assert len(blobs) == 200


# ---------------------------------------------------------------------------
# Searching
# ---------------------------------------------------------------------------


def test_search_finds_own_canary_exactly():
    cs = CanarySet.create()
    c = cs.mint(Boundary.SEPARATE_PROCESS)
    haystack = os.urandom(4096) + c.blob + os.urandom(4096)

    matches = cs.search(haystack)
    assert len(matches) == 1
    assert matches[0].exact
    assert matches[0].mac_verified
    assert matches[0].longest_prefix_bytes == CANARY_SIZE


def test_search_does_not_find_another_experiments_canary():
    """Even sitting in the buffer, a foreign marker is invisible to us."""
    mine = CanarySet.create()
    theirs = CanarySet.create()
    mine.mint(Boundary.SEPARATE_PROCESS)
    foreign = theirs.mint(Boundary.SEPARATE_PROCESS)

    haystack = os.urandom(2048) + foreign.blob + os.urandom(2048)
    matches = mine.search(haystack)
    assert all(not m.exact for m in matches)
    assert all(not m.mac_verified for m in matches)

    # The wire format puts everything identifying after byte 16: bytes 0-15 are
    # magic, version, boundary and flags, which two canaries minted for the same
    # boundary legitimately share. So a foreign marker can collide on at most
    # that 16-byte header, and never on the experiment ID, nonce, or MAC.
    assert max(m.longest_prefix_bytes for m in matches) <= 16, (
        "A foreign canary matched beyond the shared 16-byte header, which "
        "would mean experiment identity is not where the format says it is."
    )


def test_search_reports_partial_survival():
    """A half-overwritten marker is itself a measurement."""
    cs = CanarySet.create()
    c = cs.mint(Boundary.SEQUENTIAL_ALLOCATION)
    truncated = c.blob[:48]
    haystack = os.urandom(1024) + truncated + os.urandom(1024)

    matches = cs.search(haystack)
    assert len(matches) == 1
    assert not matches[0].exact
    assert matches[0].longest_prefix_bytes == 48
    assert matches[0].fraction_recovered == pytest.approx(48 / CANARY_SIZE)


def test_search_on_clean_buffer_finds_nothing():
    cs = CanarySet.create()
    cs.mint(Boundary.SEPARATE_PROCESS)
    matches = cs.search(bytes(8192))
    assert all(not m.exact for m in matches)


def test_there_is_no_arbitrary_pattern_search_api():
    """Structural check: CanarySet must not expose a general-purpose search.

    If someone adds `find(pattern)`, the canary-only guarantee is gone. This
    test exists so that addition fails CI rather than review.
    """
    public = {n for n in dir(CanarySet) if not n.startswith("_")}
    forbidden = {"find", "scan", "grep", "match_pattern", "search_bytes", "contains"}
    assert not (public & forbidden), (
        f"CanarySet exposes general-purpose search methods {public & forbidden}; "
        f"only owned-canary search is permitted (CHARTER.md §7.1)"
    )
    # search() must take only a haystack — no caller-supplied needle.
    import inspect

    params = list(inspect.signature(CanarySet.search).parameters)
    assert params == ["self", "haystack"], (
        f"CanarySet.search must accept only a haystack, got {params}. A "
        f"caller-supplied pattern parameter would defeat canary-only search."
    )
