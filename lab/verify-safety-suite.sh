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
# Only tests/safety is run per mutation: every rule in CHARTER.md §16 has
# its assertion there, and running the full suite 20 times took minutes.
#
# Usage:  bash lab/verify-safety-suite.sh
# Exit:   0 if every injected violation was caught, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0
FAIL=0

# Optional: run a subset. CASE_FILTER is a grep -E pattern matched against the
# case name. Useful for splitting the battery across CI jobs, or re-checking a
# single mutation after a fix.
#
#   CASE_FILTER='entropy|metadata' bash lab/verify-safety-suite.sh
CASE_FILTER="${CASE_FILTER:-}"
SKIPPED=0

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
  cp -r "$REPO_ROOT/probe" "$REPO_ROOT/tests" "$REPO_ROOT/schemas" \
        "$REPO_ROOT/pyproject.toml" "$work/" 2>/dev/null
  find "$work" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null

  ( cd "$work" && eval "$mutate" )

  local output
  output="$(cd "$work" && python3 -m pytest tests/safety -q 2>&1)"
  local status=$?

  if [ $status -eq 0 ]; then
    printf '  \033[31mMISSED\033[0m  %-52s suite stayed green\n' "$name"
    FAIL=$((FAIL + 1))
  elif echo "$output" | grep -q "$expect_test"; then
    printf '  \033[32mcaught\033[0m  %-52s -> %s\n' "$name" "$expect_test"
    PASS=$((PASS + 1))
  else
    printf '  \033[33mcaught*\033[0m %-52s (different test than expected)\n' "$name"
    PASS=$((PASS + 1))
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
s = p.read_text()
s = s.replace('    __repr__ = _blocked(\"repr()\")',
              '    def __repr__(self): return f\"<SafeBuffer size={self._size}>\"')
p.write_text(s)
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
s = p.read_text()
s = s.replace('    __reduce__ = _blocked(\"pickling\", UnknownMemoryRetentionError)',
              '    def __reduce__(self): return (bytearray, (bytes(self._data or b\"\"),))')
s = s.replace('    __reduce_ex__ = _blocked(\"pickling\", UnknownMemoryRetentionError)',
              '    def __reduce_ex__(self, protocol): return (bytearray, (bytes(self._data or b\"\"),))')
p.write_text(s)
PY"

# --- §7.1: canary ownership -----------------------------------------------
run_case "canary MAC verification disabled" \
  "test_canary_from_another_experiment_is_rejected" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/canary.py')
s = p.read_text()
s = s.replace('if not hmac.compare_digest(mac, self._mac(header)):',
              'if False:')
p.write_text(s)
PY"

# --- §7.2: egress allowlist -----------------------------------------------
run_case "unlisted field added to AggregateRecord" \
  "test_every_aggregate_field_is_on_the_allowlist" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/aggregation.py')
s = p.read_text()
s = s.replace('    # Safety bookkeeping\n    sensitive_observation: bool = False',
              '    recovered_plaintext_sample: str = \"\"\n\n    # Safety bookkeeping\n    sensitive_observation: bool = False')
p.write_text(s)
PY"

# --- §7.3: safety stop ----------------------------------------------------
run_case "automatic safety stop disabled" \
  "test_safety_stop_fires_on_unexpected_content" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/aggregation.py')
s = p.read_text()
s = s.replace('    if not (unexpected_content or high_information):\n        return',
              '    if True:\n        return')
p.write_text(s)
PY"

# --- §16 test 7: publication gating ---------------------------------------
run_case "publication gate on sensitive runs removed" \
  "test_sensitive_bundle_cannot_be_cleared_for_publication" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/evidence/result.py')
s = p.read_text()
s = s.replace('        if self.has_sensitive_observation:\n            raise EgressViolation(',
              '        if False:\n            raise EgressViolation(')
p.write_text(s)
PY"

# --- §16 test 16 / amendment A3: same-device gate -------------------------
run_case "same-model die-separation gate removed" \
  "test_same_model_without_validated_classifier_caps_at_u" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/reporting/report_card.py')
s = p.read_text()
s = s.replace('        if self.same_advertised_model and not self.same_model_classifier_validated:\n            return False',
              '        pass')
p.write_text(s)
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
s = p.read_text()
s = s.replace('        shared_infrastructure and record.entropy_estimate > ENTROPY_STOP_THRESHOLD',
              '        False')
p.write_text(s)
PY"

run_case "entropy stop re-armed on exclusive hardware" \
  "test_entropy_trigger_does_not_fire_on_exclusive_hardware" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/aggregation.py')
s = p.read_text()
s = s.replace('        shared_infrastructure and record.entropy_estimate > ENTROPY_STOP_THRESHOLD',
              '        record.entropy_estimate > ENTROPY_STOP_THRESHOLD')
p.write_text(s)
PY"

run_case "shared_infrastructure default flipped to unsafe" \
  "test_default_is_the_safe_value" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/aggregation.py')
s = p.read_text()
s = s.replace('    shared_infrastructure: bool = True,', '    shared_infrastructure: bool = False,')
p.write_text(s)
PY"

# --- Simulated results must never be publishable --------------------------
run_case "simulated-result publication guard removed" \
  "test_bundle_with_simulated_probe_cannot_be_published" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/evidence/result.py')
s = p.read_text()
s = s.replace('        simulated = self.simulated_probes\n        if simulated:',
              '        simulated = self.simulated_probes\n        if False:')
p.write_text(s)
PY"

# --- The one permitted decoder must stay narrow ---------------------------
run_case "ascii_metadata printable-ASCII check removed" \
  "test_refuses_random_memory" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/metadata.py')
s = p.read_text()
s = s.replace('    offending = [b for b in value if b not in _PRINTABLE]', '    offending = []')
p.write_text(s)
PY"

run_case "ascii_metadata length cap removed" \
  "test_refuses_anything_oversized" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/safety/metadata.py')
s = p.read_text()
s = s.replace('    if len(value) > MAX_METADATA_BYTES:', '    if False:')
p.write_text(s)
PY"

# --- §16 test 9: signature verification -----------------------------------
run_case "signature verification stubbed to always pass" \
  "test_signature_fails_after_tampering" \
  "python3 - <<'PY'
import pathlib
p = pathlib.Path('probe/gpu_seal/evidence/signing.py')
s = p.read_text()
s = s.replace('    return key.verify(sig, canonical_bytes(payload))', '    return True')
p.write_text(s)
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
