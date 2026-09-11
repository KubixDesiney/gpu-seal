from pathlib import Path

import pytest

import gpu_seal.resources as resources
from gpu_seal.resources import RUNTIME_SCHEMA_NAMES, load_schema

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_all_runtime_schemas_are_loadable_from_package_resources():
    for name in RUNTIME_SCHEMA_NAMES:
        schema = load_schema(name)
        assert schema["$id"].endswith(f"/schemas/{name}")


def test_packaged_schema_sources_match_the_reviewed_repository_schemas():
    for name in RUNTIME_SCHEMA_NAMES:
        reviewed = (REPO_ROOT / "schemas" / name).read_bytes()
        packaged_source = (
            REPO_ROOT / "probe" / "gpu_seal" / "schemas" / name
        ).read_bytes()
        assert packaged_source == reviewed


def test_unknown_schema_name_is_rejected():
    with pytest.raises(ValueError, match="unknown GPU-SEAL schema"):
        load_schema("not-a-runtime-schema.json")


def test_missing_packaged_schema_is_reported(monkeypatch):
    class MissingResource:
        def joinpath(self, *names):  # type: ignore[no-untyped-def]
            del names
            return self

        def read_text(self, *, encoding):  # type: ignore[no-untyped-def]
            del encoding
            raise FileNotFoundError("test missing schema")

    monkeypatch.setattr(resources, "files", lambda package: MissingResource())
    with pytest.raises(RuntimeError, match="missing runtime schema"):
        load_schema("result.schema.json")


def test_non_object_packaged_schema_is_rejected(monkeypatch):
    class ArrayResource:
        def joinpath(self, *names):  # type: ignore[no-untyped-def]
            del names
            return self

        def read_text(self, *, encoding):  # type: ignore[no-untyped-def]
            del encoding
            return "[]"

    monkeypatch.setattr(resources, "files", lambda package: ArrayResource())
    with pytest.raises(ValueError, match="must contain a JSON object"):
        load_schema("result.schema.json")
