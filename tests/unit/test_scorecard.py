"""The repository scorecard must execute checks and retain history."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _scorecard_module():
    path = Path(__file__).resolve().parents[2] / "lab" / "scorecard.py"
    spec = importlib.util.spec_from_file_location("gpu_seal_scorecard", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_liveness_checks_pass_for_repository():
    module = _scorecard_module()

    results = [
        module.check_shell_syntax(),
        module.check_probe_imports(),
        module.check_battery_preflight(),
        module.check_provider_matrix(),
    ]

    assert all(result.ok for result in results), results


def test_history_is_append_only_jsonl(tmp_path):
    module = _scorecard_module()
    history = tmp_path / "scorecard.jsonl"
    results = [module.CheckResult("example", True, "ok")]

    module.append_history(history, results)
    module.append_history(history, results)

    records = [json.loads(line) for line in history.read_text().splitlines()]
    assert len(records) == 2
    assert all(record["ok"] for record in records)
    assert records[0]["checks"][0]["name"] == "example"
