"""The mutation summary must name the test file behind every case.

The dashboard's /mutation-battery page groups the battery by the file that
guards each case, and it reads that file from mutation-battery-summary.json
rather than searching the Python tests itself. So the summarizer has to resolve
it, and has to refuse rather than guess when it cannot.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _summarizer():
    path = ROOT / "lab" / "summarize-mutation-results.py"
    spec = importlib.util.spec_from_file_location("gpu_seal_summarize_mutation", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _battery_log(module) -> str:
    """The lines run_case prints when every case is caught."""
    return "\n".join(f"  caught  {name} -> {test}" for name, test in module.load_cases())


def test_every_battery_case_resolves_to_the_one_file_that_defines_its_test():
    module = _summarizer()
    test_files = module.load_test_files()

    for _name, test in module.load_cases():
        relative = module.resolve_test_file(test, test_files)
        defined = (ROOT / relative).read_text(encoding="utf-8")
        assert f"def {test}(" in defined
        assert relative.startswith(("tests/safety/", "tests/unit/"))


def test_a_test_that_resolves_to_no_file_or_to_two_is_refused():
    module = _summarizer()

    with pytest.raises(SystemExit, match="0 matches"):
        module.resolve_test_file("test_no_such_test", {})
    with pytest.raises(SystemExit, match="2 matches"):
        module.resolve_test_file(
            "test_x", {"test_x": ["tests/safety/test_a.py", "tests/unit/test_b.py"]}
        )


def test_the_written_summary_carries_test_file_and_its_arithmetic(tmp_path, monkeypatch):
    module = _summarizer()
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "battery.log").write_text(_battery_log(module), encoding="utf-8")
    output = tmp_path / "summary.json"
    monkeypatch.setattr(sys, "argv", ["summarize", str(logs), str(output)])

    assert module.main() == 0

    summary = json.loads(output.read_text(encoding="utf-8"))
    cases = module.load_cases()
    assert summary["total"] == len(cases) == len(summary["cases"])
    assert summary["caught"] == summary["total"]
    assert summary["missed"] == 0
    assert [c["name"] for c in summary["cases"]] == [name for name, _ in cases]
    assert all((ROOT / c["test_file"]).is_file() for c in summary["cases"])
