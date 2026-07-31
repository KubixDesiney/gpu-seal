"""SafeBuffer — the only legal container for memory GPU-SEAL did not write.

Design contract (CHARTER.md §7.2, §8 "safety is centralised"):

    All buffer handling passes through one enforced-safe layer;
    only statistics leave a probe.

A ``SafeBuffer`` is deliberately hostile to inspection. It cannot be printed,
formatted, decoded, indexed, iterated, copied, pickled, or converted to bytes.
Every one of those operations raises a :class:`PolicyViolation` rather than
returning a redacted placeholder — a placeholder would let a caller believe
the operation succeeded.

There are exactly two doors:

    ingress  ``SafeBuffer.fill_via(writer)``  — one shot, then sealed
    egress   ``gpu_seal.safety.aggregate.aggregate(buf, ...)`` — statistics only

Both are named, single-purpose, and enforced by the static analysis in
``tests/safety/test_static_analysis.py``.

Typical use::

    with SafeBuffer.acquire(n_bytes, provenance="cudaMalloc:device_global") as buf:
        buf.fill_via(lambda view: copy_device_to_host(view, device_ptr))
        record = aggregate(buf, owned_canaries=canary_set)
    # buffer is zeroed and released here, unconditionally

Leaving the context manager always destroys the buffer, including on the
exception path. There is no way to keep one alive past its ``with`` block.
"""

from __future__ import annotations

import ctypes
import hashlib
import threading
from types import TracebackType
from typing import Callable, Final, Optional, Type

from .errors import (
    BufferLifecycleError,
    LimitExceeded,
    UnknownMemoryRenderError,
    UnknownMemoryRetentionError,
)
from .policy import MAX_ALLOCATION_BYTES

__all__ = ["SafeBuffer", "live_buffer_count"]


_live_lock = threading.Lock()
_live_buffers = 0


def live_buffer_count() -> int:
    """Number of SafeBuffers currently holding unknown memory.

    Used by the safety test suite to assert no buffer outlives its scope.
    Should be zero between experiments.
    """
    with _live_lock:
        return _live_buffers


def _blocked(operation: str, error: Type[BaseException] = UnknownMemoryRenderError):
    """Build a dunder that refuses, loudly, with a charter citation."""

    def _refuse(self: "SafeBuffer", *_args: object, **_kwargs: object):
        raise error(
            f"SafeBuffer does not support {operation}. Unknown GPU memory may "
            f"never be rendered, decoded, serialised, or copied out of the safe "
            f"layer (CHARTER.md §7.2). Use "
            f"gpu_seal.safety.aggregate.aggregate() to obtain permitted "
            f"statistics instead."
        )

    _refuse.__name__ = operation
    return _refuse


class SafeBuffer:
    """An opaque, self-destructing container for unknown memory.

    Never construct directly — use :meth:`acquire` as a context manager.
    """

    __slots__ = (
        "_data",
        "_size",
        "_provenance",
        "_sealed",
        "_destroyed",
        "_entered",
        "__weakref__",
    )

    # ------------------------------------------------------------------
    # Construction and lifecycle
    # ------------------------------------------------------------------

    def __init__(self, size: int, provenance: str) -> None:
        if not isinstance(size, int) or size <= 0:
            raise ValueError(f"size must be a positive int, got {size!r}")
        if size > MAX_ALLOCATION_BYTES:
            raise LimitExceeded(
                f"Requested {size} bytes exceeds MAX_ALLOCATION_BYTES "
                f"({MAX_ALLOCATION_BYTES}). CHARTER.md §16 test 12."
            )
        if not provenance or not isinstance(provenance, str):
            raise ValueError(
                "provenance is required: record where this memory came from "
                "(e.g. 'cudaMalloc:device_global') so results are interpretable."
            )

        self._data: Optional[bytearray] = bytearray(size)
        self._size: int = size
        self._provenance: str = provenance
        self._sealed: bool = False
        self._destroyed: bool = False
        self._entered: bool = False

    @classmethod
    def acquire(cls, size: int, provenance: str) -> "SafeBuffer":
        """Allocate a buffer. Must be used as a context manager."""
        return cls(size, provenance)

    def __enter__(self) -> "SafeBuffer":
        if self._destroyed:
            raise BufferLifecycleError("Cannot re-enter a destroyed SafeBuffer.")
        if self._entered:
            raise BufferLifecycleError("SafeBuffer context is not re-entrant.")
        self._entered = True
        global _live_buffers
        with _live_lock:
            _live_buffers += 1
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> bool:
        # Unconditional. Destruction happens on the exception path too.
        self.destroy()
        return False  # never suppress

    def __del__(self) -> None:
        # Backstop only. Correct code uses the context manager; this exists so
        # that a buffer dropped by accident still gets zeroed rather than
        # sitting in the heap until GC reuses the pages.
        try:
            if not self._destroyed:
                self.destroy()
        except BaseException:  # noqa: BLE001 - never raise from __del__
            pass

    def destroy(self) -> None:
        """Zero the underlying memory and release it. Idempotent."""
        if self._destroyed:
            return
        data = self._data
        if data is not None:
            # Overwrite in place before dropping the reference, so the bytes
            # are gone rather than merely unreachable.
            ctypes.memset(
                (ctypes.c_char * len(data)).from_buffer(data), 0, len(data)
            )
        self._data = None
        self._destroyed = True
        if self._entered:
            global _live_buffers
            with _live_lock:
                _live_buffers -= 1
            self._entered = False

    # ------------------------------------------------------------------
    # Ingress — the single write door
    # ------------------------------------------------------------------

    def fill_via(self, writer: Callable[[memoryview], object]) -> None:
        """Populate the buffer exactly once, then seal it.

        ``writer`` receives a writable ``memoryview`` and is expected to copy
        device memory into it (e.g. ``cudaMemcpy`` D2H). This is the only
        place a raw view of unknown memory is ever handed out.

        Callers are restricted by static analysis: see
        ``tests/safety/test_static_analysis.py::test_fill_via_callers_allowlisted``.
        The writer must not retain the view — it is released on return.
        """
        self._check_usable()
        if self._sealed:
            raise BufferLifecycleError(
                "SafeBuffer is sealed; it may only be filled once. Allocate a "
                "new buffer for a new measurement."
            )
        assert self._data is not None  # narrowed by _check_usable
        view = memoryview(self._data)
        try:
            writer(view)
        finally:
            view.release()
            self._sealed = True

    # ------------------------------------------------------------------
    # Controlled internal access — safe layer only
    # ------------------------------------------------------------------

    def _unsafe_view(self, _caller_token: str) -> memoryview:
        """Read-only view, for the aggregation module ONLY.

        The token is a tripwire, not a security boundary — it exists so that
        a grep for ``_unsafe_view`` immediately shows every caller, and so
        that accidental use outside the safe layer fails loudly in review.
        """
        if _caller_token != "gpu_seal.safety.aggregation":
            raise UnknownMemoryRetentionError(
                f"_unsafe_view is restricted to the aggregation module; "
                f"called with token {_caller_token!r}. All other access must "
                f"go through aggregate() (CHARTER.md §7.2)."
            )
        self._check_usable()
        assert self._data is not None
        return memoryview(self._data).toreadonly()

    def _check_usable(self) -> None:
        if self._destroyed:
            raise BufferLifecycleError(
                "SafeBuffer has been destroyed. Its contents were zeroed on "
                "context exit and cannot be recovered — by design."
            )

    # ------------------------------------------------------------------
    # Permitted metadata (no content)
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """Size in bytes. Permitted: `buffer_size_bytes` is on the §7.2 allowlist."""
        return self._size

    @property
    def size(self) -> int:
        return self._size

    @property
    def provenance(self) -> str:
        return self._provenance

    @property
    def sealed(self) -> bool:
        return self._sealed

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def digest(self) -> str:
        """SHA-256 over the buffer. One-way; `measurement_hash` is allowlisted.

        Safe to publish: a digest of unknown memory reveals nothing about its
        content but lets an independent party confirm two measurements of the
        same buffer agree.
        """
        self._check_usable()
        assert self._data is not None
        return "sha256:" + hashlib.sha256(self._data).hexdigest()

    # ------------------------------------------------------------------
    # Everything below is refused — CHARTER.md §7.2
    # ------------------------------------------------------------------

    __repr__ = _blocked("repr()")
    __str__ = _blocked("str()")
    __format__ = _blocked("format()")
    __bytes__ = _blocked("bytes()", UnknownMemoryRetentionError)
    __iter__ = _blocked("iteration")
    __getitem__ = _blocked("indexing or slicing")
    __contains__ = _blocked("membership testing")
    __eq__ = _blocked("equality comparison")
    __hash__ = None  # type: ignore[assignment]  # unhashable: cannot key a dict/cache

    # Serialisation — CHARTER.md §7.2 "never store raw unknown buffers"
    __reduce__ = _blocked("pickling", UnknownMemoryRetentionError)
    __reduce_ex__ = _blocked("pickling", UnknownMemoryRetentionError)
    __getstate__ = _blocked("state extraction", UnknownMemoryRetentionError)
    __copy__ = _blocked("copying", UnknownMemoryRetentionError)
    __deepcopy__ = _blocked("deep copying", UnknownMemoryRetentionError)

    # Buffer protocol: refusing this blocks memoryview(), bytes(), np.frombuffer(),
    # socket.send(), file.write(), and every other zero-copy escape route.
    def __buffer__(self, flags: int) -> memoryview:  # Python 3.12+
        raise UnknownMemoryRetentionError(
            "SafeBuffer does not expose the buffer protocol. This deliberately "
            "blocks memoryview(), np.frombuffer(), file.write(), and socket "
            "sends (CHARTER.md §7.2, §16 tests 2 and 3)."
        )


# A defensive note for future maintainers, deliberately left in the module:
#
# Do not add a __repr__ that returns "<SafeBuffer size=N>". It seems harmless,
# and it is, right up until someone logs a container that holds one and the
# formatting machinery starts walking objects. The value of raising here is
# that the failure is loud, immediate, and in CI — not silent and in a log
# file on a provider's machine.
