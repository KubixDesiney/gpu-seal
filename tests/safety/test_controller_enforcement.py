"""CHARTER.md §16 tests 11, 13, 14 — enforced at runtime, not just declared.

Before the controller existed these three rules were constants in
`gpu_seal.safety.policy` with tests asserting the constants had the right
values. A constant nothing consults is documentation. These tests exercise the
code that consults them.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from gpu_seal.controller import (
    BudgetExceeded,
    BudgetLedger,
    DisclosureGate,
    DisclosureRecord,
    DisclosureState,
    ExperimentPlan,
    OwnershipNotConfirmed,
    ProviderProhibited,
    Scheduler,
    SpendLimits,
    load_policy_matrix,
)
from gpu_seal.controller.disclosure import DisclosureNotComplete
from gpu_seal.controller.policy_matrix import (
    ProviderNotReviewed,
    ProviderPolicy,
    ProviderPolicyMatrix,
)
from gpu_seal.safety.errors import LimitExceeded, PolicyViolation
from gpu_seal.safety.policy import MAX_EXPERIMENT_DURATION_S

pytestmark = pytest.mark.safety

TODAY = date(2026, 8, 1)


def policy(classification: str, **overrides) -> ProviderPolicy:
    base = dict(
        provider_code="provider-a",
        classification=classification,
        policy_sources=["acceptable use policy — retrieved 2026-07-01"],
        reviewed_on=date(2026, 7, 1),
        reviewed_by="researcher",
        policy_version="2026-06-01",
    )
    base.update(overrides)
    return ProviderPolicy(**base)


def matrix(*policies: ProviderPolicy) -> ProviderPolicyMatrix:
    return ProviderPolicyMatrix(policies={p.provider_code: p for p in policies})


def plan(**overrides) -> ExperimentPlan:
    base = dict(
        experiment_id="exp_0001",
        provider_code="provider-a",
        probe_name="memory_global_read_before_write",
        ownership_confirmation="rented on our own account, order #12345",
        confirmed_by="researcher",
    )
    base.update(overrides)
    return ExperimentPlan(**base)


def scheduler(m: ProviderPolicyMatrix, ledger: BudgetLedger | None = None):
    return Scheduler(
        policy_matrix=m,
        ledger=ledger
        or BudgetLedger(
            limits=SpendLimits(
                per_run=10, per_provider=100, per_day=100, per_campaign=1000
            )
        ),
    )


# ---------------------------------------------------------------------------
# Test 13 — provider allowlists enforced
# ---------------------------------------------------------------------------


def test_refuses_a_provider_with_no_reviewed_policy_record():
    with pytest.raises(ProviderNotReviewed, match="No reviewed policy record"):
        matrix().check("provider-a", "memory_global_read_before_write")


def test_refuses_a_prohibited_provider_by_raising_not_returning():
    """A boolean can be ignored by a caller that forgot to check it."""
    with pytest.raises(ProviderProhibited):
        matrix(policy("prohibited")).check("provider-a", "environment_inventory")


def test_self_canary_only_permits_only_self_canary_probes():
    m = matrix(policy("self-canary-only"))
    # §9.12 is pure self-canary and survives this class — the practical
    # advantage CHARTER.md §9.12 calls out.
    assert m.check("provider-a", "mig_temporal_isolation", today=TODAY)
    with pytest.raises(PolicyViolation, match="self-canary"):
        m.check("provider-a", "memory_global_read_before_write", today=TODAY)


def test_needs_written_permission_refuses_until_permission_is_on_record():
    m = matrix(policy("needs-written-permission"))
    with pytest.raises(PolicyViolation, match="no written permission"):
        m.check("provider-a", "environment_inventory", today=TODAY)

    m = matrix(
        policy("needs-written-permission", permission_reference="email 2026-07-20")
    )
    assert "email 2026-07-20" in m.check(
        "provider-a", "environment_inventory", today=TODAY
    )


def test_refuses_a_stale_policy_review():
    """Provider terms change. A two-year-old classification is a guess."""
    m = matrix(policy("full-probe-ok", reviewed_on=date(2024, 1, 1)))
    with pytest.raises(PolicyViolation, match="older than"):
        m.check("provider-a", "environment_inventory", today=TODAY)


def test_rejects_a_classification_outside_the_charter_vocabulary():
    with pytest.raises(ValueError, match="§7.4"):
        policy("probably-fine")


def test_rejects_an_unsourced_classification():
    with pytest.raises(ValueError, match="at least one source"):
        policy("full-probe-ok", policy_sources=[])


def test_unreviewed_slot_files_do_not_enter_the_matrix(tmp_path):
    """The Phase 0 state: slot files exist, matrix stays empty.

    An empty matrix refuses everything, which is why loading unreviewed
    records — even with a cautious classification — would be the wrong choice.
    """
    (tmp_path / "provider-a.json").write_text(
        json.dumps(
            {
                "status": "awaiting-review",
                "provider_code": "provider-a",
                "classification": "needs-written-permission",
                "policy_sources": ["not yet read"],
                "policy_version": "not yet read",
                "reviewed_on": None,
                "reviewed_by": None,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "_template.json").write_text(
        json.dumps({"template": True, "provider_code": "provider-x"}), encoding="utf-8"
    )
    assert len(load_policy_matrix(tmp_path)) == 0


def test_the_repository_policy_matrix_contains_only_reviewed_providers():
    """The real matrix exposes reviewed records and skips pending providers."""
    matrix = load_policy_matrix()
    assert matrix.provider_codes == ["provider-a", "provider-c"]


def test_a_reviewed_record_does_enter_the_matrix(tmp_path):
    """Negative control on the loader: it must not reject everything."""
    (tmp_path / "provider-b.json").write_text(
        json.dumps(
            {
                "status": "reviewed",
                "provider_code": "provider-b",
                "classification": "full-probe-ok",
                "policy_sources": ["security testing policy — retrieved 2026-07-01"],
                "policy_version": "2026-06-01",
                "reviewed_on": "2026-07-01",
                "reviewed_by": "researcher",
            }
        ),
        encoding="utf-8",
    )
    loaded = load_policy_matrix(tmp_path)
    assert loaded.provider_codes == ["provider-b"]


# ---------------------------------------------------------------------------
# Test 14 — owned-account confirmation enforced
# ---------------------------------------------------------------------------


def test_refuses_a_plan_with_no_ownership_confirmation():
    with pytest.raises(OwnershipNotConfirmed, match="§4.1"):
        plan(ownership_confirmation="   ")


def test_refuses_an_unattributed_ownership_confirmation():
    with pytest.raises(OwnershipNotConfirmed, match="nobody is named"):
        plan(confirmed_by="")


def test_ownership_confirmation_reaches_the_run_record():
    """Its value is that it is recorded, not that it is cryptographic."""
    record, _ = scheduler(matrix(policy("full-probe-ok"))).run(
        plan(), lambda: 42, run_id="run_0001", today=TODAY
    )
    payload = record.to_dict()
    assert payload["ownership_confirmation"] == "rented on our own account, order #12345"
    assert payload["ownership_confirmed_by"] == "researcher"


# ---------------------------------------------------------------------------
# Test 11 — max experiment duration enforced
# ---------------------------------------------------------------------------


def test_refuses_a_plan_asking_for_more_than_the_policy_ceiling():
    with pytest.raises(LimitExceeded, match="§16 test 11"):
        plan(max_duration_s=MAX_EXPERIMENT_DURATION_S + 1)


def test_an_overrunning_run_is_marked_excluded():
    ticks = iter([0.0, 5.0])
    sched = Scheduler(
        policy_matrix=matrix(policy("full-probe-ok")),
        ledger=BudgetLedger(
            limits=SpendLimits(
                per_run=10, per_provider=100, per_day=100, per_campaign=1000
            )
        ),
        clock=lambda: next(ticks),
    )
    record, _ = sched.run(
        plan(max_duration_s=1), lambda: "done", run_id="run_0002", today=TODAY
    )
    assert record.excluded is True
    assert "exceeded max_duration_s" in record.aborted_reason


def test_a_run_inside_its_budget_of_time_is_not_excluded():
    """Negative control: the duration guard must not exclude everything."""
    record, result = scheduler(matrix(policy("full-probe-ok"))).run(
        plan(), lambda: "done", run_id="run_0003", today=TODAY
    )
    assert record.completed is True
    assert record.excluded is False
    assert result == "done"


# ---------------------------------------------------------------------------
# Budget — CHARTER.md §20
# ---------------------------------------------------------------------------


def test_a_run_over_the_per_run_cap_is_refused_before_it_starts():
    ledger = BudgetLedger(
        limits=SpendLimits(per_run=5, per_provider=100, per_day=100, per_campaign=1000)
    )
    with pytest.raises(BudgetExceeded, match="per-run cap"):
        ledger.reserve(
            run_id="r1", provider_code="provider-a", estimated_cost=6, today=TODAY
        )


def test_cost_is_reserved_before_the_run_not_billed_after_it():
    """Otherwise a hundred runs start simultaneously under a cap of one."""
    ledger = BudgetLedger(
        limits=SpendLimits(per_run=10, per_provider=15, per_day=100, per_campaign=1000)
    )
    ledger.reserve(
        run_id="r1", provider_code="provider-a", estimated_cost=10, today=TODAY
    )
    with pytest.raises(BudgetExceeded, match="per-provider"):
        ledger.reserve(
            run_id="r2", provider_code="provider-a", estimated_cost=10, today=TODAY
        )


def test_an_unsettled_run_keeps_counting_because_the_instance_may_still_exist():
    ledger = BudgetLedger(
        limits=SpendLimits(per_run=10, per_provider=100, per_day=100, per_campaign=1000)
    )
    ledger.reserve(
        run_id="r1", provider_code="provider-a", estimated_cost=7, today=TODAY
    )
    assert ledger.committed_total() == 7
    assert ledger.open_runs() == ["r1"]


def test_a_per_run_cap_above_the_campaign_cap_is_rejected_as_decorative():
    with pytest.raises(ValueError, match="makes the campaign cap decorative"):
        SpendLimits(per_run=100, per_provider=100, per_day=100, per_campaign=50)


# ---------------------------------------------------------------------------
# Disclosure — CHARTER.md §7.5
# ---------------------------------------------------------------------------


def finding() -> DisclosureRecord:
    return DisclosureRecord(
        finding_id="f-001",
        provider_code="provider-a",
        summary="owned canary recovered across a sequential allocation",
    )


def walk_to_contact(record: DisclosureRecord, contacted_on: date) -> None:
    record.record(DisclosureState.OBSERVED, contacted_on - timedelta(days=5))
    record.record(DisclosureState.REPRODUCED, contacted_on - timedelta(days=4))
    record.record(DisclosureState.METHODOLOGY_CHECKED, contacted_on - timedelta(days=3))
    record.record(DisclosureState.OWNERSHIP_CONFIRMED, contacted_on - timedelta(days=2))
    record.record(DisclosureState.REPORT_PREPARED, contacted_on - timedelta(days=1))
    record.record(DisclosureState.PROVIDER_CONTACTED, contacted_on)


def test_refuses_to_skip_a_step_in_the_disclosure_sequence():
    record = finding()
    with pytest.raises(DisclosureNotComplete, match="have not happened yet"):
        record.record(DisclosureState.REPORT_PREPARED, TODAY)


def test_refuses_publication_before_the_provider_is_contacted():
    gate = DisclosureGate()
    gate.track(finding())
    with pytest.raises(DisclosureNotComplete, match="not yet complete"):
        gate.require_publishable("f-001", today=TODAY)


def test_refuses_publication_inside_the_remediation_window():
    record = finding()
    walk_to_contact(record, TODAY - timedelta(days=10))
    gate = DisclosureGate()
    gate.track(record)
    with pytest.raises(DisclosureNotComplete, match="day\\(s\\) left"):
        gate.require_publishable("f-001", today=TODAY)


def test_permits_publication_after_documented_non_response():
    """A silent provider does not get an indefinite veto."""
    record = finding()
    walk_to_contact(record, TODAY - timedelta(days=200))
    gate = DisclosureGate()
    gate.track(record)
    assert "non-response" in gate.require_publishable("f-001", today=TODAY)


def test_a_responding_provider_requires_a_retest_before_publication():
    record = finding()
    walk_to_contact(record, TODAY - timedelta(days=200))
    record.provider_responded = True
    gate = DisclosureGate()
    gate.track(record)
    with pytest.raises(DisclosureNotComplete, match="re-tested"):
        gate.require_publishable("f-001", today=TODAY)

    record.record(DisclosureState.RETESTED, TODAY)
    assert "coordinated" in gate.require_publishable("f-001", today=TODAY)


def test_refuses_publication_of_an_untracked_finding():
    with pytest.raises(DisclosureNotComplete, match="No disclosure record"):
        DisclosureGate().require_publishable("f-999", today=TODAY)
