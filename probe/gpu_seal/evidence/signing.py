"""Ed25519 signing of result payloads — CHARTER.md §10, §14, §16 test 9.

Every measurement bundle is signed. A result that does not verify is not
evidence: it is a file. The verification path must be runnable by a third
party with nothing but the public key and the published bundle, which is what
makes "reproducible" mean something.

Canonicalisation matters more than the signature algorithm here. Two parties
must derive byte-identical input from the same logical payload, or signatures
will fail for uninteresting reasons. We use JSON with sorted keys, no
insignificant whitespace, and UTF-8 — see :func:`canonical_bytes`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

__all__ = [
    "Signer",
    "SigningKeySource",
    "SigningKey",
    "PemSigningKeySource",
    "EphemeralDevelopmentKeySource",
    "ExternalSigningKeySource",
    "key_source_from_options",
    "signing_metadata",
    "VerifyKey",
    "canonical_bytes",
    "sign_payload",
    "verify_payload",
]

SIGNATURE_ALGORITHM: Final[str] = "ed25519"


class Signer(Protocol):
    """Minimal signer contract shared by PEM, OS-key-store, and KMS adapters.

    An OS key store or KMS implementation can satisfy this protocol without
    exporting private key bytes. Its ``sign`` method receives only the
    canonical payload and its public key is used for the safe fingerprint.
    """

    @property
    def verify_key(self) -> VerifyKey: ...

    def sign(self, message: bytes) -> bytes: ...


class SigningKeySource(Protocol):
    """Explicit source of a signer for an operator-facing run."""

    @property
    def source_label(self) -> str: ...

    @property
    def provenance_suitable(self) -> bool: ...

    def load(self) -> Signer: ...


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Deterministic byte encoding of a payload, for signing and hashing.

    Sorted keys, compact separators, UTF-8, no NaN/Infinity (which JSON does
    not portably represent and which would make a bundle unverifiable in a
    different language).
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class SigningKey:
    """Wrapper around an Ed25519 private key."""

    __slots__ = ("_key",)

    def __init__(self, key: Ed25519PrivateKey) -> None:
        self._key = key

    @classmethod
    def generate(cls) -> SigningKey:
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_pem(cls, data: bytes, password: bytes | None = None) -> SigningKey:
        key = serialization.load_pem_private_key(data, password=password)
        if not isinstance(key, Ed25519PrivateKey):
            raise TypeError("Expected an Ed25519 private key.")
        return cls(key)

    def to_pem(self, password: bytes | None = None) -> bytes:
        enc = (
            serialization.BestAvailableEncryption(password)
            if password
            else serialization.NoEncryption()
        )
        return self._key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=enc,
        )

    @property
    def verify_key(self) -> VerifyKey:
        return VerifyKey(self._key.public_key())

    def sign(self, message: bytes) -> bytes:
        return self._key.sign(message)

    def __repr__(self) -> str:  # never print key material
        return f"<SigningKey ed25519 pub={self.verify_key.hex[:16]}...>"


class VerifyKey:
    """Wrapper around an Ed25519 public key."""

    __slots__ = ("_key",)

    def __init__(self, key: Ed25519PublicKey) -> None:
        self._key = key

    @classmethod
    def from_hex(cls, value: str) -> VerifyKey:
        return cls(Ed25519PublicKey.from_public_bytes(bytes.fromhex(value)))

    @classmethod
    def from_pem(cls, data: bytes) -> VerifyKey:
        key = serialization.load_pem_public_key(data)
        if not isinstance(key, Ed25519PublicKey):
            raise TypeError("Expected an Ed25519 public key.")
        return cls(key)

    @property
    def raw(self) -> bytes:
        return self._key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    @property
    def hex(self) -> str:
        return self.raw.hex()

    @property
    def fingerprint(self) -> str:
        """Stable, non-secret fingerprint suitable for operator display."""
        return "sha256:" + hashlib.sha256(self.raw).hexdigest()

    def verify(self, signature: bytes, message: bytes) -> bool:
        try:
            self._key.verify(signature, message)
            return True
        except InvalidSignature:
            return False

    def __repr__(self) -> str:
        return f"<VerifyKey ed25519 {self.hex[:16]}...>"


def sign_payload(payload: dict[str, Any], key: Signer) -> str:
    """Sign a payload dict, returning a hex signature."""
    return key.sign(canonical_bytes(payload)).hex()


def verify_payload(
    payload: dict[str, Any], signature_hex: str, key: VerifyKey
) -> bool:
    """Verify a payload dict against a hex signature."""
    try:
        sig = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    return key.verify(sig, canonical_bytes(payload))


@dataclass(frozen=True)
class PemSigningKeySource:
    """Load an Ed25519 private key from a caller-selected PEM file.

    The file is read only for the duration of ``load`` and is never copied to
    an evidence directory, printed, or included in result metadata.
    """

    path: Path
    password: bytes | None = None
    source_label: str = "caller-supplied-ed25519-pem"
    provenance_suitable: bool = True

    def load(self) -> SigningKey:
        return SigningKey.from_pem(self.path.read_bytes(), password=self.password)


class EphemeralDevelopmentKeySource:
    """Explicitly unsafe development signer; never a provenance key source."""

    source_label = "unsafe-development-ephemeral"
    provenance_suitable = False

    def __init__(self, *, unsafe_development: bool) -> None:
        if not unsafe_development:
            raise ValueError(
                "ephemeral signing requires the explicit unsafe_development flag"
            )
        self._key: SigningKey | None = None

    def load(self) -> SigningKey:
        if self._key is None:
            self._key = SigningKey.generate()
        return self._key


@dataclass(frozen=True)
class ExternalSigningKeySource:
    """Extension point for OS key stores and KMS-backed signers.

    ``loader`` should return a ``Signer`` whose private operation remains in
    the external system. GPU-SEAL never asks it for private-key material.
    """

    loader: Callable[[], Signer]
    source_label: str
    provenance_suitable: bool = True

    def load(self) -> Signer:
        signer = self.loader()
        if not hasattr(signer, "verify_key") or not hasattr(signer, "sign"):
            raise TypeError("external key source did not return a signer")
        return signer


def key_source_from_options(
    pem_path: Path | str | None,
    *,
    unsafe_development_ephemeral: bool = False,
) -> SigningKeySource:
    """Resolve the safe operator CLI choices without a hidden fallback."""
    if pem_path is not None and unsafe_development_ephemeral:
        raise ValueError(
            "choose either --signing-key or --unsafe-development-ephemeral, not both"
        )
    if pem_path is not None:
        return PemSigningKeySource(Path(pem_path))
    if unsafe_development_ephemeral:
        return EphemeralDevelopmentKeySource(unsafe_development=True)
    raise ValueError(
        "an operator signing key is required: pass --signing-key <Ed25519 PEM> "
        "or explicitly opt into --unsafe-development-ephemeral"
    )


def signing_metadata(source: SigningKeySource, signer: Signer) -> dict[str, object]:
    """Return safe bundle metadata; never include private-key material."""
    return {
        "key_source": source.source_label,
        "public_key_fingerprint": signer.verify_key.fingerprint,
        "provenance_suitable": source.provenance_suitable,
    }
