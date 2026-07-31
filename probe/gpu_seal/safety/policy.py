"""Machine-readable encoding of the CHARTER.md §7 ethics model.

This module is the single source of truth for what GPU-SEAL is permitted to
do with memory it did not write. Every constant here maps to a specific
charter clause, cited inline. Changing a value in this file is an ethics
decision, not an engineering one, and should be reviewed as such.
"""

from __future__ import annotations

from typing import Final, FrozenSet

# --------------------------------------------------------------------------
# Safe egress allowlist — CHARTER.md §7.2
#
# "It may retain only safe aggregate information: zero-byte percentage;
#  fixed-pattern percentage; byte-frequency histogram; estimated entropy;
#  repeated-block count; exact match against owned canaries; longest
#  owned-canary prefix match; measurement hash; probe version;
#  driver/environment metadata; error codes; timing measurements."
#
# This is an ALLOWLIST, not a denylist. A key absent from this set is refused,
# not filtered. Adding an entry requires an ethics review.
# --------------------------------------------------------------------------
SAFE_AGGREGATE_KEYS: Final[FrozenSet[str]] = frozenset(
    {
        # Distributional statistics over unknown bytes
        "zero_fraction",
        "fixed_pattern_fraction",
        "byte_histogram",
        "entropy_estimate",
        "repeated_block_count",
        "distinct_block_count",
        # Owned-canary matching only
        "owned_canary_exact_matches",
        "owned_canary_longest_prefix",
        "owned_canary_match",
        # Provenance and integrity
        "measurement_hash",
        "buffer_size_bytes",
        "block_size_bytes",
        "probe_version",
        "probe_name",
        # Environment / diagnostics
        "driver_metadata",
        "error_code",
        "timing_ns",
        # Safety bookkeeping
        "sensitive_observation",
        "unknown_raw_retained",
        "unknown_memory_rendered",
        "canary_only_search",
    }
)

# --------------------------------------------------------------------------
# Hard operational limits — CHARTER.md §16 tests 11 and 12
# --------------------------------------------------------------------------

#: Largest single buffer a probe may allocate and aggregate over.
#: Bounds both blast radius and the amount of unknown memory ever resident.
MAX_ALLOCATION_BYTES: Final[int] = 4 * 1024 * 1024 * 1024  # 4 GiB

#: Longest a single experiment may run before the controller aborts it.
MAX_EXPERIMENT_DURATION_S: Final[int] = 60 * 60  # 1 hour

#: Block size used for repeated-block analysis. Must divide evenly into
#: typical allocation granularity and be large enough that random collisions
#: are negligible.
ANALYSIS_BLOCK_SIZE: Final[int] = 16

# --------------------------------------------------------------------------
# Automatic safety stop thresholds — CHARTER.md §7.3
#
# These decide when a probe stops looking. They are deliberately conservative:
# a false stop costs one wasted run, a missed stop means GPU-SEAL kept
# analysing another tenant's data.
# --------------------------------------------------------------------------

#: If a buffer that should be freshly zeroed is less than this fraction zero,
#: something unexpected is present. Stop and escalate.
EXPECTED_ZERO_FRACTION_FLOOR: Final[float] = 0.99

#: Normalised Shannon entropy (0..1) above which unknown content is considered
#: structured/high-information rather than uninitialised noise or zeros.
#: We do NOT classify what it is — we only stop looking. See §7.2: classifying
#: unknown memory is explicitly forbidden.
ENTROPY_STOP_THRESHOLD: Final[float] = 0.85

# --------------------------------------------------------------------------
# Canary format — CHARTER.md §7.1
# --------------------------------------------------------------------------

CANARY_MAGIC: Final[bytes] = b"GPUSEALC"
CANARY_VERSION: Final[int] = 1
CANARY_SIZE: Final[int] = 128  # bytes, 16-byte aligned for GPU friendliness
CANARY_NONCE_SIZE: Final[int] = 32
CANARY_MAC_SIZE: Final[int] = 32
CANARY_KEY_SIZE: Final[int] = 32

# --------------------------------------------------------------------------
# Provider allowlist enforcement — CHARTER.md §16 test 13
#
# Empty by default. A provider must be explicitly added, with its policy
# classification recorded, before any probe may target it. Populated from
# docs/provider-policy-review, never hardcoded here.
# --------------------------------------------------------------------------
PROVIDER_POLICY_CLASSES: Final[FrozenSet[str]] = frozenset(
    {
        "full-probe-ok",
        "self-canary-only",
        "needs-written-permission",
        "prohibited",
    }
)

#: Probe families that only ever touch the researcher's own marker data and
#: are therefore permitted under a `self-canary-only` provider policy.
SELF_CANARY_ONLY_SAFE_PROBES: Final[FrozenSet[str]] = frozenset(
    {
        "environment_inventory",
        "device_exposure_inventory",
        "self_sequential_canary",
        "mig_temporal_isolation",
    }
)

# --------------------------------------------------------------------------
# Publication gating — CHARTER.md §7.3 and §16 test 7
# --------------------------------------------------------------------------

#: A run carrying any of these markers can never be auto-published.
PUBLICATION_BLOCKING_MARKERS: Final[FrozenSet[str]] = frozenset(
    {
        "sensitive_observation",
        "manual_review_required",
        "disclosure_pending",
    }
)
