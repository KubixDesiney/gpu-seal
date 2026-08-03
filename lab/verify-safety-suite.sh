#!/usr/bin/env bash
# Negative control on the safety suite itself.
#
# CHARTER.md §11 Phase 1: "Without positive controls you cannot prove a
# negative cloud result means the probe could detect a leak." The same logic
# applies one level up: a green safety suite proves nothing unless the suite
# demonstrably goes red when the policy is violated.
#
# This script copies the repo to a scratch directory, injects a series of
# known policy violations one at a time, and asserts that the suite catches
# each one. It never modifies the working tree.
#
# tests/safety and tests/unit are run per mutation. §16's rules all assert in
# tests/safety, but several safety properties belong to the probe families and
# assert in tests/unit — the D5 gate on same-device claims, the MIG probe's
# refusal to run where MIG cannot exist — and a negative control that cannot
# see them has holes in it. The CI batch matrix splits the cost.
#
# Every Python snippet below reads and writes with an explicit UTF-8 encoding.
# Without it the snippets pick up the platform default, and the ones anchored
# on comment lines containing an em-dash fail to find their anchor on a host
# whose locale is not UTF-8 — reporting a MISSED that is really an encoding
# bug in the harness.
#
# Usage:  bash lab/verify-safety-suite.sh
# Exit:   0 if every injected violation was caught, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PASS=0
FAIL=0

# Optional: run a subset. CASE_FILTER is a grep -E pattern matched against the
# case name. Useful for splitting the battery across CI jobs, or re-checking a
# single mutation after a fix.
#
#   CASE_FILTER='entropy|metadata' bash lab/verify-safety-suite.sh
CASE_FILTER="${CASE_FILTER:-}"
SKIPPED=0

# A missing pytest, a broken interpreter, and collection/import failures are
# harness failures. They must never be reported as a mutation being caught.
if ! preflight_output="$("$PYTHON_BIN" -m pytest --version 2>&1)"; then
  printf '\033[31mERROR\033[0m pytest is unavailable or cannot start:\n%s\n' \
    "$preflight_output" >&2
  exit 2
fi

run_case() {
  local name="$1"; shift
  local expect_test="$1"; shift
  local mutate="$1"; shift

  if [ -n "$CASE_FILTER" ] && ! echo "$name" | grep -qE "$CASE_FILTER"; then
    SKIPPED=$((SKIPPED + 1))
    return
  fi

  local work
  work="$(mktemp -d)"
  # docs/ comes along because the provider policy matrix is loaded from
  # docs/provider-policy-review/, and a mutation that admits unreviewed slot
  # files into the runtime matrix is only detectable if those files are there
  # to be admitted.
  cp -r "$REPO_ROOT/probe" "$REPO_ROOT/tests" "$REPO_ROOT/schemas" \
        "$REPO_ROOT/docs" "$REPO_ROOT/lab" "$REPO_ROOT/analysis" \
        "$REPO_ROOT/infrastructure" "$REPO_ROOT/pyproject.toml" \
        "$REPO_ROOT/CITATION.cff" "$work/" 2>/dev/null
  find "$work" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null

  ( cd "$work" && eval "$mutate" )

  local output
  # tests/unit as well as tests/safety. Several safety properties are asserted
  # by the probe families' own unit tests — the D5 gate on same-device claims,
  # the MIG probe's refusal to run on hardware that cannot host MIG — and a
  # negative control that cannot see them is a negative control with holes in
  # it. Running both roughly doubles each case's runtime, which the batch
  # matrix in .github/workflows/safety.yml absorbs.
  output="$(cd "$work" && "$PYTHON_BIN" -m pytest tests/safety tests/unit -q 2>&1)"
  local status=$?

  if [ $status -eq 0 ]; then
    printf '  \033[31mMISSED\033[0m  %-52s suite stayed green\n' "$name"
    FAIL=$((FAIL + 1))
  elif echo "$output" | grep -Eq \
      "(ERROR collecting|INTERNALERROR|ImportError|ModuleNotFoundError|No module named|file or directory not found)"; then
    printf '  \033[31mERROR\033[0m   %-52s pytest/environment failure\n' "$name"
    printf '%s\n' "$output" >&2
    FAIL=$((FAIL + 1))
  elif echo "$output" | grep -Eq "FAILED .*${expect_test}"; then
    printf '  \033[32mcaught\033[0m  %-52s -> %s\n' "$name" "$expect_test"
    PASS=$((PASS + 1))
  else
    printf '  \033[31mWRONG\033[0m   %-52s expected %s\n' "$name" "$expect_test"
    printf '%s\n' "$output" >&2
    FAIL=$((FAIL + 1))
  fi

  rm -rf "$work"
}

echo
echo "Injecting known policy violations into a scratch copy of the repo."
echo "Each one MUST turn the safety suite red."
echo

# --- §16 test 1: printing raw buffers -------------------------------------
run_case "print() added to probe source" \
  "test_no_print_calls_in_probe_source" \
  "printf '\n\ndef _debug(b):\n    print(b)\n' >> probe/gpu_seal/safety/policy.py"

# --- §16 test 4: text decoding --------------------------------------------
run_case "UTF-8 decode added to probe source" \
  "test_no_text_decoding_in_probe_source" \
  "printf '\n\ndef _as_text(b):\n    return b.decode(\"utf-8\", \"replace\")\n' >> probe/gpu_seal/safety/policy.py"

# --- §16 test 5: credential pattern search --------------------------------
run_case "regex import added to probe source" \
  "test_no_regex_module_used_against_unknown_memory" \
  "printf '\nimport re\n' >> probe/gpu_seal/safety/policy.py"

run_case "credential literal added to executable code" \
  "test_no_credential_patterns_in_string_literals" \
  "printf '\n_NEEDLE = \"password\"\n' >> probe/gpu_seal/safety/policy.py"

# --- §16 test 17: container escape ----------------------------------------
run_case "container-escape indicator added" \
  "test_no_container_escape_constructs" \
  "printf '\n_HOOK = \"LD_PRELOAD\"\n' >> probe/gpu_seal/safety/policy.py"

# --- §16 test 15: destructive naming --------------------------------------
run_case "offensively-named function added" \
  "test_no_destructive_or_offensive_symbol_names" \
  "printf '\n\ndef dump_vram_now():\n    return None\n' >> probe/gpu_seal/safety/policy.py"

# --- §7.2: buffer containment ---------------------------------------------
run_case "SafeBuffer.__repr__ made permissive" \
  "test_repr_is_refused" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/buffer.py')
s = p.read_text(encoding='utf-8')
s = s.replace('    __repr__ = _blocked(\"repr()\")',
              '    def __repr__(self): return f\"<SafeBuffer size={self._size}>\"')
p.write_text(s, encoding='utf-8')
PY"

# Note: pickling is blocked by BOTH __reduce__ and __reduce_ex__. Removing
# only one leaves the other in place and pickle is still refused — verified
# manually. The mutation therefore has to remove both to create a real hole,
# which is what defence in depth is supposed to feel like.
run_case "pickling re-enabled on SafeBuffer (both dunders)" \
  "test_pickling_is_refused" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/buffer.py')
s = p.read_text(encoding='utf-8')
s = s.replace('    __reduce__ = _blocked(\"pickling\", UnknownMemoryRetentionError)',
              '    def __reduce__(self): return (bytearray, (bytes(self._data or b\"\"),))')
s = s.replace('    __reduce_ex__ = _blocked(\"pickling\", UnknownMemoryRetentionError)',
              '    def __reduce_ex__(self, protocol): return (bytearray, (bytes(self._data or b\"\"),))')
p.write_text(s, encoding='utf-8')
PY"

# --- §7.1: canary ownership -----------------------------------------------
run_case "canary MAC verification disabled" \
  "test_tampered_canary_is_rejected" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/canary.py')
s = p.read_text(encoding='utf-8')
s = s.replace('if not hmac.compare_digest(mac, self._mac(header)):',
              'if False:')
p.write_text(s, encoding='utf-8')
PY"

# --- §7.2: egress allowlist -----------------------------------------------
run_case "unlisted field added to AggregateRecord" \
  "test_every_aggregate_field_is_on_the_allowlist" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/aggregation.py')
s = p.read_text(encoding='utf-8')
s = s.replace('    # Safety bookkeeping\n    sensitive_observation: bool = False',
              '    recovered_plaintext_sample: str = \"\"\n\n    # Safety bookkeeping\n    sensitive_observation: bool = False')
p.write_text(s, encoding='utf-8')
PY"

run_case "stable GPU/MIG UUID redaction removed" \
  "test_a_stable_gpu_uuid_is_hashed_before_recording" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/probes/device_exposure.py')
s = p.read_text(encoding='utf-8')
s = s.replace(
    'if var == "NVIDIA_VISIBLE_DEVICES" and _names_stable_gpu_identifiers(value):',
    'if False:',
)
s += '\n\ndef _names_stable_gpu_identifiers(value):\n    return False\n'
p.write_text(s, encoding='utf-8')
PY"

# --- §7.3: safety stop ----------------------------------------------------
run_case "automatic safety stop disabled" \
  "test_safety_stop_fires_on_unexpected_content" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/aggregation.py')
s = p.read_text(encoding='utf-8')
s = s.replace('    if not (unexpected_content or high_information or too_small_to_publish_exactly):\n        return',
              '    if True:\n        return')
p.write_text(s, encoding='utf-8')
PY"

# --- §16 test 7: publication gating ---------------------------------------
run_case "publication gate on sensitive runs removed" \
  "test_sensitive_bundle_cannot_be_cleared_for_publication" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/evidence/result.py')
s = p.read_text(encoding='utf-8')
s = s.replace('        if self.has_sensitive_observation:\n            raise EgressViolation(',
              '        if False:\n            raise EgressViolation(')
p.write_text(s, encoding='utf-8')
PY"

# --- §16 test 16 / amendment A3: same-device gate -------------------------
run_case "same-model die-separation gate removed" \
  "test_same_model_without_validated_classifier_caps_at_u" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/reporting/report_card.py')
s = p.read_text(encoding='utf-8')
s = s.replace('        if self.same_advertised_model and not self.same_model_classifier_validated:\n            return False',
              '        pass')
p.write_text(s, encoding='utf-8')
PY"

# --- A record must carry the identity of the probe that produced it -------
# Found in a signed, publication-cleared bundle from a real GPU run: §9.4's
# control records were stamped with §9.3's probe name, so a passing control
# read as a residue finding.
run_case "probe identity override removed (9.4 relabels as 9.3)" \
  "test_framework_probe_stamps_its_own_name" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/probes/framework_allocator.py')
s = p.read_text(encoding='utf-8')
s = s.replace('                probe_name=self.NAME,\n                probe_version=self.VERSION,\n', '')
p.write_text(s, encoding='utf-8')
PY"

run_case "backend measurement_path declaration removed" \
  "test_measurement_path_reaches_the_record" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/cuda/backend.py')
s = p.read_text(encoding='utf-8')
s = s.replace('            \"measurement_path\": self.measurement_path,\n', '')
p.write_text(s, encoding='utf-8')
PY"

# --- §9.4 control data must not be gradeable as a §9.3 finding ------------
# Found by inspection when §9.4 was promoted onto the critical path: feeding
# the framework-allocator control's counts into the §13.1 grader produced a
# grade D, i.e. a false accusation manufactured from a working control.
run_case "measurement-path gate removed" \
  "test_pooled_recovery_is_not_graded_d" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/reporting/report_card.py')
s = p.read_text(encoding='utf-8')
s = s.replace('    if ev.measurement_path is not MeasurementPath.DRIVER_DIRECT:',
              '    if False:')
p.write_text(s, encoding='utf-8')
PY"

run_case "measurement-path gate moved below the D branch" \
  "test_no_non_driver_path_can_ever_produce_d" \
  "python3 - <<'PY'
import pathlib, re
p = pathlib.Path('probe/gpu_seal/reporting/report_card.py')
s = p.read_text(encoding='utf-8')
# Relocate the gate to AFTER the D branch -- the ordering bug it guards against.
start = s.index('    # --- Measurement-path gate.')
end = s.index('    # D — the only grade that asserts a failure.')
gate = s[start:end]
s = s[:start] + s[end:]
anchor = '    if ev.inconsistent_across_runs:'
s = s.replace(anchor, gate + anchor, 1)
p.write_text(s, encoding='utf-8')
PY"

run_case "measurement_path default flipped to driver_direct" \
  "test_unstated_path_defaults_to_ungradeable" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/reporting/report_card.py')
s = p.read_text(encoding='utf-8')
s = s.replace('    measurement_path: MeasurementPath = MeasurementPath.UNKNOWN',
              '    measurement_path: MeasurementPath = MeasurementPath.DRIVER_DIRECT')
p.write_text(s, encoding='utf-8')
PY"

# --- §7.3: entropy trigger armed on shared infrastructure -----------------
# Found by running the Phase 1 battery: this trigger was originally armed
# unconditionally, which halted every baseline measurement. The fix scoped it
# to shared infrastructure. Both failure directions are now mutated.
run_case "entropy stop disarmed on shared infrastructure" \
  "test_entropy_trigger_fires_on_rented_infrastructure" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/aggregation.py')
s = p.read_text(encoding='utf-8')
s = s.replace('        shared_infrastructure and record.entropy_estimate > ENTROPY_STOP_THRESHOLD',
              '        False')
p.write_text(s, encoding='utf-8')
PY"

run_case "entropy stop re-armed on exclusive hardware" \
  "test_entropy_trigger_does_not_fire_on_exclusive_hardware" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/aggregation.py')
s = p.read_text(encoding='utf-8')
s = s.replace('        shared_infrastructure and record.entropy_estimate > ENTROPY_STOP_THRESHOLD',
              '        record.entropy_estimate > ENTROPY_STOP_THRESHOLD')
p.write_text(s, encoding='utf-8')
PY"

run_case "shared_infrastructure default flipped to unsafe" \
  "test_default_is_the_safe_value" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/aggregation.py')
s = p.read_text(encoding='utf-8')
s = s.replace('    shared_infrastructure: bool = True,', '    shared_infrastructure: bool = False,')
p.write_text(s, encoding='utf-8')
PY"

# --- Simulated results must never be publishable --------------------------
run_case "simulated-result publication guard removed" \
  "test_bundle_with_simulated_probe_cannot_be_published" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/evidence/result.py')
s = p.read_text(encoding='utf-8')
s = s.replace('        simulated = self.simulated_probes\n        if simulated:',
              '        simulated = self.simulated_probes\n        if False:')
p.write_text(s, encoding='utf-8')
PY"

# --- The one permitted decoder must stay narrow ---------------------------
run_case "ascii_metadata printable-ASCII check removed" \
  "test_refuses_random_memory" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/metadata.py')
s = p.read_text(encoding='utf-8')
s = s.replace('    offending = [b for b in value if b not in _PRINTABLE]', '    offending = []')
p.write_text(s, encoding='utf-8')
PY"

run_case "ascii_metadata length cap removed" \
  "test_refuses_anything_oversized" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/metadata.py')
s = p.read_text(encoding='utf-8')
s = s.replace('    if len(value) > MAX_METADATA_BYTES:', '    if False:')
p.write_text(s, encoding='utf-8')
PY"

# --- §16 test 9: signature verification -----------------------------------
run_case "signature verification stubbed to always pass" \
  "test_signature_fails_under_a_different_key" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/evidence/signing.py')
s = p.read_text(encoding='utf-8')
s = s.replace('    return key.verify(sig, canonical_bytes(payload))', '    return True')
p.write_text(s, encoding='utf-8')
PY"

# --- §16 test 13: provider allowlist enforced -----------------------------
run_case "prohibited provider downgraded to a returnable false" \
  "test_refuses_a_prohibited_provider_by_raising_not_returning" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/controller/policy_matrix.py')
s = p.read_text(encoding='utf-8')
s = s.replace('            if policy.classification == \"prohibited\":\n                raise ProviderProhibited(reason)\n', '')
p.write_text(s, encoding='utf-8')
PY"

run_case "unreviewed provider slots admitted to the runtime matrix" \
  "test_the_repository_policy_matrix_contains_only_reviewed_providers" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('docs/provider-policy-review/provider-b.json')
s = p.read_text(encoding='utf-8')
s = s.replace('\"status\": \"awaiting-review\"', '\"status\": \"reviewed\"', 1)
p.write_text(s, encoding='utf-8')
PY"

# --- §16 test 14: owned-account confirmation ------------------------------
run_case "ownership confirmation made optional" \
  "test_refuses_a_plan_with_no_ownership_confirmation" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/controller/scheduler.py')
s = p.read_text(encoding='utf-8')
s = s.replace('        if not self.ownership_confirmation.strip():', '        if False:')
p.write_text(s, encoding='utf-8')
PY"

# --- §16 test 11: max experiment duration ---------------------------------
run_case "duration ceiling removed from the plan" \
  "test_refuses_a_plan_asking_for_more_than_the_policy_ceiling" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/controller/scheduler.py')
s = p.read_text(encoding='utf-8')
s = s.replace('        if self.max_duration_s > MAX_EXPERIMENT_DURATION_S:', '        if False:')
p.write_text(s, encoding='utf-8')
PY"

run_case "duration constant made unbounded" \
  "test_experiment_duration_cap_is_defined_and_bounded" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/policy.py')
s = p.read_text(encoding='utf-8')
s = s.replace(
    'MAX_EXPERIMENT_DURATION_S: Final[int] = 60 * 60',
    'MAX_EXPERIMENT_DURATION_S: Final[int] = 0',
)
p.write_text(s, encoding='utf-8')
PY"

# --- §10: never-published identifiers -------------------------------------
run_case "never-published identifier check removed from observations" \
  "test_refuses_to_emit_an_unhashed_never_published_identifier" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/evidence/observation.py')
s = p.read_text(encoding='utf-8')
s = s.replace('        self._refuse_unhashed_identifier()\n', '')
p.write_text(s, encoding='utf-8')
PY"

# --- §10 / §14: only a reproducible container may publish -----------------
run_case "publication gate narrowed back to a dev-unpinned string match" \
  "test_a_real_record_outside_a_pinned_container_cannot_be_published" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/evidence/result.py')
s = p.read_text(encoding='utf-8')
s = s.replace('                not in PUBLISHABLE_CONTAINER_PROFILES',
              '                == \"there-is-no-such-profile\"')
p.write_text(s, encoding='utf-8')
PY"

# --- §13.6: attestation must not collapse to a grade ----------------------
run_case "attestation reduced to a single boolean grade" \
  "test_attestation_is_a_field_report_not_a_grade" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/reporting/report_card.py')
s = p.read_text(encoding='utf-8')
s = s.replace('    return {\n        \"note\": (', '    return {\n        \"grade\": \"A\",\n        \"note\": (')
p.write_text(s, encoding='utf-8')
PY"

# --- §7.5: disclosure sequence --------------------------------------------
run_case "disclosure step ordering no longer enforced" \
  "test_refuses_to_skip_a_step_in_the_disclosure_sequence" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/controller/disclosure.py')
s = p.read_text(encoding='utf-8')
s = s.replace('        if state in _ORDER:', '        if False:')
p.write_text(s, encoding='utf-8')
PY"

# --- §9.5 / §13.1: the D5 gate on physical continuity ---------------------
run_case "same-model gate removed from certificate comparison" \
  "test_refuses_same_device_claim_for_same_advertised_model_without_d5" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/probes/topology.py')
s = p.read_text(encoding='utf-8')
s = s.replace('    if same_advertised_model and not same_model_classifier_validated:', '    if False:')
p.write_text(s, encoding='utf-8')
PY"

# --- §9.12: MIG mechanisms must never be pooled ---------------------------
run_case "MIG probe allowed to run on hardware without MIG" \
  "test_refuses_to_run_on_hardware_without_mig" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/probes/mig_temporal.py')
s = p.read_text(encoding='utf-8')
s = s.replace('        if require_mig and not self._nvml.mig_enabled:', '        if False:')
p.write_text(s, encoding='utf-8')
PY"

# --- §7.1: the indexed canary search must stay exact ----------------------
# The regression the equivalence test caught during development: identifying
# a recovered marker by looking up its allocation id misses any marker that
# was truncated inside that field, and under-reports the surviving prefix.
run_case "canary search scores only one member per anchor occurrence" \
  "test_indexed_search_matches_the_naive_scan_on_random_layouts" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/canary.py')
s = p.read_text(encoding='utf-8')
s = s.replace('                for canary in members:\n                    length = _common_prefix_length',
              '                for canary in members[:1]:\n                    length = _common_prefix_length')
p.write_text(s, encoding='utf-8')
PY"

echo
echo "-------------------------------------------------------------------"
printf 'caught %d / %d injected violations' "$PASS" "$((PASS + FAIL))"
if [ "$SKIPPED" -gt 0 ]; then
  printf ' (%d skipped by CASE_FILTER=%s)' "$SKIPPED" "$CASE_FILTER"
fi
echo
if [ "$FAIL" -ne 0 ]; then
  echo "FAILED: the safety suite did not detect every violation."
  echo "A suite that cannot go red is not evidence of anything."
  exit 1
fi
echo "OK: every injected violation turned the suite red."
echo "-------------------------------------------------------------------"
echo
