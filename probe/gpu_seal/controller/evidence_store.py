"""Evidence store — CHARTER.md §8, §10.

    "Signed JSON bundles · No raw unknown VRAM · Tool & image digests ·
     Provider policy meta · Reproduction status · Disclosure status"

Thin on purpose. The store's job is to be the place where a bundle is written
*in the right order*, because getting that order wrong is not hypothetical
here: every bundle the Phase 1 lab script wrote before 2026-07-31 carried
``automatic_publication_allowed: false`` regardless of what the console said,
because ``clear_for_publication()`` ran after ``sign()`` and the field is
baked into the signed payload.

The fix was a reordering in one script. This class is so the next script
cannot make the same mistake: :meth:`write` is the only supported path, and it
does the gate check, then signs, then writes, then verifies what it wrote.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate

from ..evidence.result import ResultBundle
from ..evidence.signing import SigningKey
from ..safety.errors import EgressViolation

__all__ = ["EvidenceStore", "StoredBundle"]

@dataclass(frozen=True)
class StoredBundle:
    """What was written, and whether it may be published."""

    path: Path
    run_id: str
    publishable: bool
    #: Populated when the publication gate refused, with its reason.
    refusal: str | None
    signature_verified: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "run_id": self.run_id,
            "publishable": self.publishable,
            "refusal": self.refusal,
            "signature_verified": self.signature_verified,
        }


class EvidenceStore:
    """Writes signed bundles in the one order that is correct."""

    def __init__(
        self,
        directory: Path | str,
        schema_path: Path | str | None = None,
        report_card_schema_path: Path | str | None = None,
    ) -> None:
        self._directory = Path(directory)
        schemas_dir = Path(__file__).resolve().parents[3] / "schemas"
        self._schema_path = (
            Path(schema_path)
            if schema_path is not None
            else schemas_dir / "result.schema.json"
        )
        self._report_card_schema_path = (
            Path(report_card_schema_path)
            if report_card_schema_path is not None
            else schemas_dir / "report-card.schema.json"
        )

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
        if (
            not isinstance(run_id, str)
            or not run_id
            or len(run_id) > 128
            or run_id[0] not in allowed
            or any(character not in allowed for character in run_id)
        ):
            raise ValueError(
                "run_id must be a 1-128 character filename token containing "
                "only letters, digits, '.', '_' or '-'"
            )
        if run_id in {".", ".."}:
            raise ValueError("run_id may not be a path-navigation token")

    def _bundle_path(self, run_id: str) -> Path:
        self._validate_run_id(run_id)
        root = self._directory.resolve()
        path = (root / f"{run_id}.result.json").resolve()
        if path.parent != root:
            raise ValueError("bundle path escapes the evidence store")
        return path

    def _validate_schema(self, bundle: dict[str, Any]) -> None:
        """Validate the bundle, and — separately — its report card.

        `result.schema.json` deliberately leaves `report_card` as an open
        object (CHARTER.md §13 categories are built independently, and a
        bundle written before a report card exists must still validate). The
        restrictive shape lives in its own file,
        `schemas/report-card.schema.json`, and previously nothing applied it:
        an EvidenceStore.write() call validated the envelope but never the
        report card's own content, so an unreviewed key inside it would not
        be caught here even though a dedicated schema for exactly that shape
        already existed. Validated only when non-empty — an empty
        `report_card: {}` (no card built yet) is a normal, valid bundle
        state and is not required to satisfy the full five-category shape.
        """
        schema = json.loads(self._schema_path.read_text(encoding="utf-8"))
        validate(bundle, schema)
        report_card = bundle.get("report_card")
        if report_card:
            report_card_schema = json.loads(
                self._report_card_schema_path.read_text(encoding="utf-8")
            )
            validate(report_card, report_card_schema)

    def write(
        self,
        bundle: ResultBundle,
        key: SigningKey,
        *,
        allow_overwrite: bool = False,
    ) -> StoredBundle:
        """Gate, sign, write, verify. In that order, always.

        ``clear_for_publication()`` must run **before** ``sign()``:
        ``automatic_publication_allowed`` is part of the payload the signature
        covers, so clearing afterwards changes an in-memory flag and nothing
        on disk. Doing it the other way round produced bundles whose console
        output and whose contents disagreed.
        """
        path = self._bundle_path(bundle.run_id)
        self._directory.mkdir(parents=True, exist_ok=True)
        if path.exists() and not allow_overwrite:
            raise FileExistsError(
                f"evidence bundle already exists for run_id {bundle.run_id!r}; "
                "pass allow_overwrite=True to replace it explicitly"
            )

        refusal: str | None = None
        try:
            bundle.clear_for_publication()
        except EgressViolation as exc:
            # A refusal is a normal outcome, not an error. The bundle is still
            # written — unpublishable evidence is still evidence, and deleting
            # it because it cannot be published is how inconvenient results
            # disappear.
            refusal = str(exc)

        signed = bundle.sign(key)
        self._validate_schema(signed)
        encoded = json.dumps(signed, indent=2, ensure_ascii=False) + "\n"

        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._directory,
                prefix=f".{bundle.run_id}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = handle.name
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())

            if allow_overwrite:
                os.replace(temporary, path)
                temporary = None
            else:
                # A hard-link creation is atomic and fails if another writer
                # won the run_id first; unlike os.replace it cannot overwrite.
                os.link(temporary, path)
                os.unlink(temporary)
                temporary = None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

        # Read back and verify what actually landed on disk, not what we think
        # we wrote. The failure this catches is exactly the one that happened.
        on_disk = self.read(path)
        return StoredBundle(
            path=path,
            run_id=bundle.run_id,
            publishable=bool(
                on_disk["safety"]["automatic_publication_allowed"]
            ),
            refusal=refusal,
            signature_verified=ResultBundle.verify(on_disk),
        )

    def read(self, path: Path | str) -> dict[str, Any]:
        candidate = Path(path)
        root = self._directory.resolve()
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (root / candidate).resolve()
        )
        if resolved.parent != root or not resolved.name.endswith(".result.json"):
            raise ValueError("evidence path must be a bundle directly inside the store")
        run_id = resolved.name[: -len(".result.json")]
        self._validate_run_id(run_id)
        bundle = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(bundle, dict):
            raise ValueError("evidence bundle must be a JSON object")
        self._validate_schema(bundle)
        return bundle

    def verify_all(self) -> dict[str, bool]:
        """Verify every bundle in the store. Used by the reproducibility tests."""
        results: dict[str, bool] = {}
        for path in sorted(self._directory.glob("*.result.json")):
            try:
                results[path.name] = ResultBundle.verify(self.read(path))
            except (OSError, ValueError, KeyError, TypeError, ValidationError):
                results[path.name] = False
        return results
