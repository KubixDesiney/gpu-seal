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


def test_canary_body_is_structurally_non_semantic():
    """CHARTER.md §7.1: canaries must be non-semantic.

    A marker containing a readable sentence would be a liability if it ever
    surfaced in someone else's memory dump. The guarantee is structural, and
    this asserts it structurally: past the magic, every byte is either an
    identifier the operator did not choose the content of (UUID bytes), a
    32-byte `os.urandom` nonce, reserved zeros, or a keyed BLAKE2b MAC. There
    is nowhere in the layout for author-chosen text to live.
    """
    cs = CanarySet.create()
    c = cs.mint(Boundary.SEPARATE_PROCESS)

    assert c.blob[:8] == CANARY_MAGIC
    assert c.blob[16:32] == cs.experiment_id.bytes
    assert c.blob[32:48] == c.allocation_id.bytes
    assert c.blob[48:80] == c.nonce
    assert c.blob[80:96] == b"\x00" * 16, "reserved field must stay zero"
    assert len(c.blob[96:]) == 32, "MAC occupies the tail"
    # The two UUIDs and the nonce are the only variable regions, and none of
    # them is a place a contributor could put a sentence.
    assert len(c.nonce) == 32


def test_canary_body_shows_no_long_printable_run():
    """Statistical smoke test on top of the structural one above.

    Threshold note, and the reason it is 20 rather than 12. Roughly 37% of
    byte values are printable ASCII, so a run of length k appears with
    probability ~0.37^k per position. Over 50 canaries of ~109 candidate
    positions each, a 12-byte run turns up in about **3% of runs** — which is
    exactly what happened: this test was flaky from the day it was written and
    failed once during a routine suite run, having passed dozens of times.

    A flaky safety test is worse than no test. People learn to re-run it.

    At 20 the expected failure rate is ~3e-5 per run, and random bytes still
    cannot plausibly spell anything. The property that actually matters is
    asserted deterministically in the test above.
    """
    cs = CanarySet.create()
    for _ in range(50):
        c = cs.mint(Boundary.SEPARATE_PROCESS)
        body = c.blob[len(CANARY_MAGIC) :]
        run = _longest_printable_run(body)
        assert run < 20, (
            f"canary body contained a {run}-byte printable run; canaries must "
            f"be non-semantic (CHARTER.md §7.1)"
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
    # Fix the experiment IDs so the first byte after the shared 16-byte
    # header is guaranteed to differ; a random 1/256 collision here made the
    # boundary assertion flaky rather than testing the wire-format contract.
    mine = CanarySet.create(
        experiment_id=uuid.UUID("00000000-0000-0000-0000-000000000000")
    )
    theirs = CanarySet.create(
        experiment_id=uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    )
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


# ---------------------------------------------------------------------------
# allocation_id_scope — binding a match to one specific canary, not any
# canary the experiment ever minted. Closes the §9.5 self-vs-self gap: two
# canaries minted from the same CanarySet, and a stale one from elsewhere in
# the experiment landing in the buffer being searched must not be mistaken
# for the one actually planted there.
# ---------------------------------------------------------------------------


def test_unscoped_search_matches_any_owned_canary():
    """Baseline: without scope, a stale canary from elsewhere still matches —
    this is the behaviour allocation_id_scope exists to let a caller avoid."""
    cs = CanarySet.create()
    planted_here = cs.mint(Boundary.SEQUENTIAL_ALLOCATION)
    stale_elsewhere = cs.mint(Boundary.SEPARATE_PROCESS)
    # Only the *stale* canary actually landed in this buffer.
    haystack = os.urandom(512) + stale_elsewhere.blob + os.urandom(512)

    matches = {m.allocation_id: m for m in cs.search(haystack)}
    assert matches[stale_elsewhere.allocation_id].exact is True
    assert matches[planted_here.allocation_id].exact is False


def test_scoped_search_ignores_a_match_outside_the_scope():
    """The fix: scoping to the canary actually planted here means the stale
    match from elsewhere is not even reported as belonging to this pair."""
    cs = CanarySet.create()
    planted_here = cs.mint(Boundary.SEQUENTIAL_ALLOCATION)
    stale_elsewhere = cs.mint(Boundary.SEPARATE_PROCESS)
    haystack = os.urandom(512) + stale_elsewhere.blob + os.urandom(512)

    matches = cs.search(haystack, allocation_id_scope={planted_here.allocation_id})
    assert len(matches) == 1
    assert matches[0].allocation_id == planted_here.allocation_id
    assert matches[0].exact is False


def test_scoped_search_still_matches_the_canary_actually_in_scope():
    cs = CanarySet.create()
    planted_here = cs.mint(Boundary.SEQUENTIAL_ALLOCATION)
    cs.mint(Boundary.SEPARATE_PROCESS)  # unrelated, not in this buffer at all
    haystack = os.urandom(512) + planted_here.blob + os.urandom(512)

    matches = cs.search(haystack, allocation_id_scope={planted_here.allocation_id})
    assert len(matches) == 1
    assert matches[0].allocation_id == planted_here.allocation_id
    assert matches[0].exact is True


def test_scoped_search_with_an_empty_scope_matches_nothing():
    cs = CanarySet.create()
    c = cs.mint(Boundary.SEQUENTIAL_ALLOCATION)
    haystack = os.urandom(512) + c.blob + os.urandom(512)

    matches = cs.search(haystack, allocation_id_scope=set())
    assert matches == []


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
    # search() must take only a haystack, plus the one narrow, keyword-only
    # exception below — no caller-supplied needle.
    import inspect

    signature = inspect.signature(CanarySet.search)
    params = list(signature.parameters)
    # allocation_id_scope is deliberately allowed: it can only ever shrink
    # the set of already-owned, already-authenticated canaries considered —
    # every candidate it admits is still something `mint()` produced for
    # this experiment. That is a different kind of parameter from a
    # caller-supplied pattern, which could introduce content nobody minted.
    # It is asserted keyword-only and positioned last so it can never be
    # mistaken for, or misused as, a positional needle.
    assert params == ["self", "haystack", "allocation_id_scope"], (
        f"CanarySet.search must accept only a haystack and the allowlisted "
        f"allocation_id_scope narrowing parameter, got {params}. A "
        f"caller-supplied pattern parameter would defeat canary-only search."
    )
    assert (
        signature.parameters["allocation_id_scope"].kind
        is inspect.Parameter.KEYWORD_ONLY
    ), "allocation_id_scope must be keyword-only, never usable as a positional needle"
