"""Controller — CHARTER.md §8, and the runtime half of §16.

The probe measures. The controller decides what the probe is *allowed* to
measure, for how long, at whose expense, and whether the result may leave the
machine.

Until now §16 rules 11, 13, and 14 existed only as constants in
:mod:`gpu_seal.safety.policy` with tests asserting the constants had the right
values. A constant nothing consults is documentation. This package is the
thing that consults them:

    rule 11  max experiment duration enforced   → :mod:`scheduler`
    rule 13  provider allowlists enforced       → :mod:`policy_matrix`
    rule 14  owned-account confirmation         → :mod:`scheduler`

plus the budget controls §20 requires and the disclosure gating §7.5 requires.

**Placement note.** CHARTER.md §15 draws ``controller/`` as a top-level
directory. It lives inside the installed package instead, because the
alternative is a second distribution root that the test suite, the static
analysis in ``tests/safety/test_static_analysis.py``, and the Phase 0
provider-name CI gate would each need teaching about separately. The
safety-critical property — that controller code is held to the same static
analysis as probe code — is worth more than the directory layout. The
top-level ``controller/`` directory holds the operator-facing configuration
it always did; see ``controller/README.md``.
"""

from .budget import (
    BudgetExceeded,
    BudgetLedger,
    CleanupState,
    SpendLimits,
    TerminationResult,
)
from .disclosure import DisclosureGate, DisclosureRecord, DisclosureState
from .evidence_store import EvidenceStore
from .native_runner import (
    NativeCommandResult,
    NativeExecution,
    NativeExecutionError,
    NativeProviderRunner,
    NativeRunConfig,
    ProviderRuntime,
    parse_native_output,
)
from .orchestrator import (
    CampaignExecution,
    CampaignOrchestrator,
    CampaignRunOutcome,
    CampaignRunSpec,
)
from .fake_runtime import DeterministicFakeRuntime, fake_native_output
from .policy_matrix import (
    ProviderPolicy,
    ProviderPolicyMatrix,
    ProviderProhibited,
    load_policy_matrix,
)
from .scheduler import (
    ExperimentPlan,
    ExperimentRun,
    CleanupReconciliationError,
    OwnershipNotConfirmed,
    Scheduler,
)

__all__ = [
    "SpendLimits",
    "BudgetLedger",
    "BudgetExceeded",
    "CleanupState",
    "TerminationResult",
    "ProviderPolicy",
    "ProviderPolicyMatrix",
    "ProviderProhibited",
    "load_policy_matrix",
    "ExperimentPlan",
    "ExperimentRun",
    "Scheduler",
    "OwnershipNotConfirmed",
    "CleanupReconciliationError",
    "EvidenceStore",
    "NativeCommandResult",
    "NativeExecution",
    "NativeExecutionError",
    "NativeProviderRunner",
    "NativeRunConfig",
    "ProviderRuntime",
    "parse_native_output",
    "CampaignRunSpec",
    "CampaignRunOutcome",
    "CampaignExecution",
    "CampaignOrchestrator",
    "DeterministicFakeRuntime",
    "fake_native_output",
    "DisclosureGate",
    "DisclosureRecord",
    "DisclosureState",
]
