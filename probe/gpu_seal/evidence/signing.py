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

import json
from typing import Any, Final

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

__all__ = [
    "SigningKey",
    "VerifyKey",
    "canonical_bytes",
    "sign_payload",
    "verify_payload",
]

SIGNATURE_ALGORITHM: Final[str] = "ed25519"


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

    def verify(self, signature: bytes, message: bytes) -> bool:
        try:
            self._key.verify(signature, message)
            return True
        except InvalidSignature:
            return False

    def __repr__(self) -> str:
        return f"<VerifyKey ed25519 {self.hex[:16]}...>"


def sign_payload(payload: dict[str, Any], key: SigningKey) -> str:
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
