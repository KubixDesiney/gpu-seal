"""§9.7 allocation-model wiring in the local-runner scripts.

lab/local-runner/run_phase1.py and lab/local-runner/run_native_local.py used
to write allocation_model.classification = "local_workstation"
unconditionally, so a Colab or Kaggle bootstrap run was signed as if it ran on
the researcher's own hardware (docs/pre-registration.md §3 rule 5: the
allocation model must be classified, not assumed, before any memory result is
interpreted). These tests drive the two scripts' own
``build_allocation_model`` helpers directly -- loaded the same way
tests/unit/test_run_mig_isolation.py loads lab/cloud-runner/run_mig_isolation.py
-- with no GPU required, since both fall back to the simulated/no-signal path
on a host with none.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from gpu_seal.cuda.nvml import NvmlSnapshot
from gpu_seal.reporting import NOT_CLASSIFIED
from gpu_seal.safety import CampaignControl

REPO_ROOT = Path(__file__).resolve().parents[2]

EMPTY_NVML = NvmlSnapshot(available=False, unavailable_reason="test fixture")


def _load(relative_path: str, module_name: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def phase1():
    return _load("lab/local-runner/run_phase1.py", "gpu_seal_run_phase1")


@pytest.fixture(scope="module")
def native_local():
    return _load("lab/local-runner/run_native_local.py", "gpu_seal_run_native_local")


# ---------------------------------------------------------------------------
# run_phase1.build_allocation_model
# ---------------------------------------------------------------------------


def test_non_cloud_host_stays_local_workstation(phase1):
    model = phase1.build_allocation_model(
        "other",
        is_real=True,
        info={"device_name": "RTX 3050"},
        nvml=EMPTY_NVML,
        stall_ratio=None,
        campaign=CampaignControl.create(),
    )
    assert model["classification"] == "local_workstation"
    assert model["confidence"] == 1.0


@pytest.mark.parametrize("host_kind", ["kaggle", "colab", "gce"])
def test_cloud_host_is_never_recorded_as_local_workstation(phase1, host_kind):
    model = phase1.build_allocation_model(
        host_kind,
        is_real=True,
        info={"device_name": "Tesla T4", "total_memory_bytes": 16 * (1 << 30)},
        nvml=EMPTY_NVML,
        stall_ratio=None,
        campaign=CampaignControl.create(),
    )
    assert model["classification"] != "local_workstation"


def test_cloud_host_without_a_real_backend_is_not_classified(phase1):
    model = phase1.build_allocation_model(
        "colab",
        is_real=False,
        info={},
        nvml=EMPTY_NVML,
        stall_ratio=None,
        campaign=CampaignControl.create(),
    )
    assert model["classification"] == NOT_CLASSIFIED
    assert model["confidence"] == 0.0
    assert "colab" in model["not_classified_reason"]


def test_cloud_host_with_a_real_backend_runs_the_classifier(phase1):
    model = phase1.build_allocation_model(
        "kaggle",
        is_real=True,
        info={},
        nvml=EMPTY_NVML,
        stall_ratio=None,
        campaign=CampaignControl.create(),
    )
    # No NVML, no memory/device signal, and no documented model: nothing
    # separates any hypothesis, so the honest answer is the classifier's own
    # "undocumented" class -- attempted, not merely assumed -- never a value
    # the tool did not actually measure, and never NOT_CLASSIFIED (that is
    # reserved for "not attempted at all").
    assert model["classification"] == "undocumented"
    assert model["host_kind"] == "kaggle"


# ---------------------------------------------------------------------------
# run_native_local.build_allocation_model
# ---------------------------------------------------------------------------


def test_native_local_non_cloud_host_stays_local_workstation(native_local):
    model = native_local.build_allocation_model("other", reported_model="RTX 3050")
    assert model["classification"] == "local_workstation"


@pytest.mark.parametrize("host_kind", ["kaggle", "colab", "gce"])
def test_native_local_cloud_host_is_never_local_workstation(native_local, host_kind):
    model = native_local.build_allocation_model(host_kind, reported_model="Tesla T4")
    assert model["classification"] != "local_workstation"
    assert model["host_kind"] == host_kind
