"""CHARTER.md §16 tests 1-4 — unknown memory cannot leave the safe layer.

These are the tests that make the ethics model checkable. Each one attempts a
plausible route by which raw unknown bytes could escape a SafeBuffer, and
asserts it is refused.

The design principle under test: refusal is loud. Nothing here should return
a redacted placeholder, because a placeholder lets a caller believe the
operation worked.
"""

from __future__ import annotations

import copy
import io
import json
import pickle

import pytest

from gpu_seal.safety import (
    BufferLifecycleError,
    LimitExceeded,
    SafeBuffer,
    UnknownMemoryRenderError,
    UnknownMemoryRetentionError,
    live_buffer_count,
)

pytestmark = pytest.mark.safety

UNKNOWN = bytes(range(256)) * 8  # stand-in for memory we did not write


def _filled(size: int = 2048) -> SafeBuffer:
    buf = SafeBuffer.acquire(size, provenance="test:synthetic")
    return buf


def _fill(buf: SafeBuffer, payload: bytes) -> None:
    def writer(view):
        n = min(len(payload), len(view))
        view[:n] = payload[:n]

    buf.fill_via(writer)


# ---------------------------------------------------------------------------
# Test 1 — no code path prints raw probe buffers
# ---------------------------------------------------------------------------


def test_repr_is_refused():
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        with pytest.raises(UnknownMemoryRenderError):
            repr(buf)


def test_str_is_refused():
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        with pytest.raises(UnknownMemoryRenderError):
            str(buf)


def test_fstring_interpolation_is_refused():
    """f-strings route through __format__, which is the sneakiest leak path."""
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        with pytest.raises(UnknownMemoryRenderError):
            f"{buf}"  # noqa: B018


def test_print_is_refused():
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        sink = io.StringIO()
        with pytest.raises(UnknownMemoryRenderError):
            print(buf, file=sink)
        assert sink.getvalue() == ""


def test_logging_a_container_holding_a_buffer_is_refused():
    """The realistic accident: someone logs a dict that happens to hold one."""
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        payload = {"probe": "memory_global", "buffer": buf}
        with pytest.raises(UnknownMemoryRenderError):
            "%s" % (payload,)


# ---------------------------------------------------------------------------
# Test 2 — no code path writes raw unknown VRAM to disk
# ---------------------------------------------------------------------------


def test_bytes_conversion_is_refused():
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        with pytest.raises(UnknownMemoryRetentionError):
            bytes(buf)


def test_buffer_protocol_is_refused(tmp_path):
    """Blocking __buffer__ closes file.write(), socket.send() and np.frombuffer()."""
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        target = tmp_path / "leak.bin"
        with open(target, "wb") as fh:
            with pytest.raises((UnknownMemoryRetentionError, TypeError)):
                fh.write(buf)  # type: ignore[arg-type]
        assert target.stat().st_size == 0


def test_memoryview_is_refused():
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        with pytest.raises((UnknownMemoryRetentionError, TypeError)):
            memoryview(buf)  # type: ignore[arg-type]


def test_pickling_is_refused():
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        with pytest.raises(UnknownMemoryRetentionError):
            pickle.dumps(buf)


def test_copy_and_deepcopy_are_refused():
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        with pytest.raises(UnknownMemoryRetentionError):
            copy.copy(buf)
        with pytest.raises(UnknownMemoryRetentionError):
            copy.deepcopy(buf)


# ---------------------------------------------------------------------------
# Test 3 — no network upload of raw probe buffers
# ---------------------------------------------------------------------------


def test_json_serialisation_is_refused():
    """The most likely exfil route is an ordinary API call."""
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        with pytest.raises((UnknownMemoryRenderError, TypeError)):
            json.dumps({"data": buf})


# ---------------------------------------------------------------------------
# Test 4 — no automatic UTF-8 / text decoding
# ---------------------------------------------------------------------------


def test_no_decode_method_exists():
    """SafeBuffer must not expose .decode(); §7.2 forbids UTF-8 decoding."""
    with _filled() as buf:
        assert not hasattr(buf, "decode")


def test_iteration_and_indexing_are_refused():
    """Both are precursors to reconstructing content byte by byte."""
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        with pytest.raises(UnknownMemoryRenderError):
            list(buf)
        with pytest.raises(UnknownMemoryRenderError):
            buf[0]
        with pytest.raises(UnknownMemoryRenderError):
            buf[0:16]


def test_membership_testing_is_refused():
    """`b'password' in buf` is a content oracle. Refuse it."""
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        with pytest.raises(UnknownMemoryRenderError):
            b"anything" in buf  # noqa: B015


def test_buffer_is_unhashable():
    """Hashability would allow caching unknown content keyed by itself."""
    with _filled() as buf:
        with pytest.raises(TypeError):
            hash(buf)


# ---------------------------------------------------------------------------
# Lifecycle — destruction is unconditional
# ---------------------------------------------------------------------------


def test_buffer_is_destroyed_on_context_exit():
    buf = SafeBuffer.acquire(1024, provenance="test:lifecycle")
    with buf:
        _fill(buf, UNKNOWN)
        assert not buf.destroyed
    assert buf.destroyed


def test_buffer_is_destroyed_even_when_body_raises():
    buf = SafeBuffer.acquire(1024, provenance="test:lifecycle")
    with pytest.raises(RuntimeError):
        with buf:
            _fill(buf, UNKNOWN)
            raise RuntimeError("probe blew up mid-measurement")
    assert buf.destroyed


def test_use_after_destroy_is_refused():
    buf = SafeBuffer.acquire(1024, provenance="test:lifecycle")
    with buf:
        _fill(buf, UNKNOWN)
    with pytest.raises(BufferLifecycleError):
        buf.digest()


def test_destroy_is_idempotent():
    buf = SafeBuffer.acquire(512, provenance="test:lifecycle")
    with buf:
        pass
    buf.destroy()
    buf.destroy()
    assert buf.destroyed


def test_no_buffers_leak_across_the_suite():
    """If this fails, some test left unknown memory resident."""
    assert live_buffer_count() == 0


def test_fill_via_is_refused_on_a_buffer_that_was_never_entered():
    """acquire() only constructs the buffer; `with` is what live-accounting
    and unconditional destruction on scope exit depend on. A caller who
    skips the context manager must not get a silently-usable buffer."""
    buf = SafeBuffer.acquire(1024, provenance="test:no-context")
    with pytest.raises(BufferLifecycleError):
        _fill(buf, UNKNOWN)
    assert live_buffer_count() == 0


def test_digest_is_refused_on_a_buffer_that_was_never_entered():
    buf = SafeBuffer.acquire(1024, provenance="test:no-context")
    with pytest.raises(BufferLifecycleError):
        buf.digest()


def test_buffer_may_only_be_filled_once():
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        with pytest.raises(BufferLifecycleError):
            _fill(buf, UNKNOWN)


def test_unsafe_view_rejects_callers_outside_the_aggregation_module():
    with _filled() as buf:
        _fill(buf, UNKNOWN)
        with pytest.raises(UnknownMemoryRetentionError):
            buf._unsafe_view("some.other.module")
        with pytest.raises(UnknownMemoryRetentionError):
            buf._unsafe_view("gpu_seal.probes.memory_global")


# ---------------------------------------------------------------------------
# Test 12 — max allocation size enforced
# ---------------------------------------------------------------------------


def test_oversized_allocation_is_refused():
    from gpu_seal.safety.policy import MAX_ALLOCATION_BYTES

    with pytest.raises(LimitExceeded):
        SafeBuffer.acquire(MAX_ALLOCATION_BYTES + 1, provenance="test:oversize")


def test_provenance_is_mandatory():
    """An unlabelled measurement is uninterpretable, so refuse to make one."""
    with pytest.raises(ValueError):
        SafeBuffer.acquire(1024, provenance="")
