"""Signed, reproducible evidence bundles — CHARTER.md §10."""

from .result import ResultBundle, canonical_payload_hash
from .signing import (
    EphemeralDevelopmentKeySource,
    ExternalSigningKeySource,
    PemSigningKeySource,
    Signer,
    SigningKey,
    SigningKeySource,
    VerifyKey,
    key_source_from_options,
    sign_payload,
    signing_metadata,
    verify_payload,
)

__all__ = [
    "ResultBundle",
    "canonical_payload_hash",
    "SigningKey",
    "Signer",
    "SigningKeySource",
    "PemSigningKeySource",
    "EphemeralDevelopmentKeySource",
    "ExternalSigningKeySource",
    "key_source_from_options",
    "signing_metadata",
    "VerifyKey",
    "sign_payload",
    "verify_payload",
]
