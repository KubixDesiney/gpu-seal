"""Machine-readable encoding of the CHARTER.md §7 ethics model.

This module is the single source of truth for what GPU-SEAL is permitted to
do with memory it did not write. Every constant here maps to a specific
charter clause, cited inline. Changing a value in this file is an ethics
decision, not an engineering one, and should be reviewed as such.
"""

from __future__ import annotations

from typing import Final

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
SAFE_AGGREGATE_KEYS: Final[frozenset[str]] = frozenset(
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

#: Smallest buffer, in bytes, for which the allowlisted `byte_histogram`
#: (256 exact counts) and `measurement_hash` (unsalted SHA-256) are aggregate
#: statistics at all, rather than close to a full description of the content.
#: A low-entropy small buffer (a single repeated byte has zero measured
#: entropy) evades ENTROPY_STOP_THRESHOLD entirely, yet its exact histogram
#: alone reveals it and the digest confirms guesses over a tiny candidate
#: space. 256 bytes is chosen to match the histogram's own bin count: below
#: it, the "aggregate" carries no less information than the raw content in
#: the worst case. Armed only on shared infrastructure, for the same reason
#: as ENTROPY_STOP_THRESHOLD — see aggregation._check_safety_stop.
MIN_SAFE_MEASUREMENT_BYTES: Final[int] = 256

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
PROVIDER_POLICY_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "full-probe-ok",
        "self-canary-only",
        "needs-written-permission",
        "prohibited",
    }
)

#: Probe families that only ever touch the researcher's own marker data and
#: are therefore permitted under a `self-canary-only` provider policy.
SELF_CANARY_ONLY_SAFE_PROBES: Final[frozenset[str]] = frozenset(
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
PUBLICATION_BLOCKING_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "sensitive_observation",
        "manual_review_required",
        "disclosure_pending",
    }
)

#: Container profiles whose output is reproducible enough to publish.
#:
#: Everything else is refused by ``ResultBundle.clear_for_publication``. This
#: is an allowlist rather than a denylist of known-bad profiles, which closes
#: the gap recorded in PROGRESS.md: the original guard string-matched
#: ``dev-unpinned`` only, so a run outside any container at all
#: (``unspecified``) sailed through despite being equally unreproducible.
#:
#: ``unspecified`` is deliberately absent. That is a policy call, made here
#: rather than in the guard: CHARTER.md §10 requires a container digest among
#: the reproducibility fields, and a run that cannot name its image cannot
#: supply one. Local control runs still happen and are still signed — they are
#: simply not publishable evidence, which is the honest description of them.
PUBLISHABLE_CONTAINER_PROFILES: Final[frozenset[str]] = frozenset({"pinned"})

# --------------------------------------------------------------------------
# Non-memory observations — CHARTER.md §9.1, §9.6, §9.7, §9.9, §9.10
#
# The §7.2 allowlist above governs statistics over memory GPU-SEAL did not
# write. The inventory and classifier probes do not touch unknown memory at
# all; what they carry instead is *environment description*, which has its own
# disclosure hazard (§10 "never published": account IDs, public IPs, stable
# GPU UUIDs, hostnames, provider-internal IDs, exact coordinates).
#
# So they get their own allowlist, enforced the same way: a key absent from
# this set is refused on the way out, not filtered.
# --------------------------------------------------------------------------
SAFE_OBSERVATION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "probe_name",
        "probe_version",
        "subject",
        "category",
        "classification",
        "confidence",
        "evidence",
        "limitations",
        "value",
        "error_code",
        "timing_ns",
        "not_testable_reason",
        # Mirrors AggregateRecord.sensitive_observation — an observation that
        # requires manual disclosure review or is not itself evidence (e.g. a
        # modelled instrument reading) sets this so ResultBundle's publication
        # gate can see it. See ResultBundle.has_sensitive_observation.
        "blocks_publication",
    }
)

#: Field names that must never appear in a published bundle in raw form —
#: CHARTER.md §10 "Never published". Anything matching one of these fragments
#: has to be hashed through :func:`gpu_seal.safety.metadata.stable_hash`
#: before it can be recorded.
NEVER_PUBLISH_FIELD_FRAGMENTS: Final[frozenset[str]] = frozenset(
    {
        "account_id",
        "public_ip",
        "ip_address",
        "gpu_uuid",
        "hostname",
        "host_name",
        "instance_id",
        "serial",
        "mac_address",
        "coordinates",
        "latitude",
        "longitude",
    }
)

# --------------------------------------------------------------------------
# Interpretation categories — CHARTER.md §9.6
#
# "Not every unavailable interface is a failure — some restricted counters and
#  DCGM functions correctly require privilege."
#
# Recording the *interpretation* alongside the observation is what stops an
# exposure inventory from degenerating into a scanner that reports every
# difference as a finding.
# --------------------------------------------------------------------------
EXPOSURE_CLASSIFICATIONS: Final[frozenset[str]] = frozenset(
    {
        "secure_restriction",
        "expected_visibility",
        "unexpected_visibility",
        "ambiguous",
        "not_testable",
    }
)

# --------------------------------------------------------------------------
# Allocation models — CHARTER.md §9.7, contribution D3
# --------------------------------------------------------------------------
ALLOCATION_MODEL_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "dedicated_physical_passthrough",
        "dedicated_virtual_gpu",
        "time_sliced_full_gpu",
        "mps",
        "mig_instance",
        "mig_backed_vgpu",
        "software_fractional_gpu",
        "shared_unknown",
        "dedicated_unknown",
        "undocumented",
        # Not in the charter's rented-instance taxonomy: the researcher's own
        # workstation, where the question "which fraction did I rent?" has no
        # meaning. Kept distinct so a local control run is never counted as a
        # provider observation.
        "local_workstation",
    }
)

# --------------------------------------------------------------------------
# Consistency bands — CHARTER.md §9.9
#
# Ordered weakest-claim-first. Location evidence is metropolitan-to-
# continental (§3.3, inherited bound) and the band vocabulary has to make
# overclaiming awkward.
# --------------------------------------------------------------------------
CONSISTENCY_BANDS: Final[tuple] = (
    "not_testable",
    "ambiguous",
    "probably_inconsistent",
    "inconsistent",
    "probably_consistent",
    "consistent",
)
