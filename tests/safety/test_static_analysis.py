"""CHARTER.md §16 tests 1, 4, 5, 15, 17 — enforced by reading the source.

Runtime tests prove the safe layer refuses bad operations. These tests prove
nobody wrote code that tries. They parse every module under ``probe/`` and
reject constructs that are forbidden by the ethics model, so a violation
fails CI at the point it is introduced rather than in review, or worse, in
front of a provider.

Two modules are held to different standards:

  * The safety layer itself is permitted low-level operations (it is the
    thing that contains them). It is listed in ``SAFE_LAYER_MODULES``.
  * Everything else in ``probe/`` is held to the strict rules.

That asymmetry is the "safety is centralised" principle from §8, expressed
as a lint rule.
"""

from __future__ import annotations

import ast
import pathlib
from typing import NamedTuple
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.safety

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBE_ROOT = REPO_ROOT / "probe"

#: Modules that constitute the enforced-safe layer. These may touch raw bytes.
SAFE_LAYER_MODULES = {
    "gpu_seal/safety/buffer.py",
    "gpu_seal/safety/aggregation.py",
    "gpu_seal/safety/canary.py",
}

#: Modules permitted to allocate raw host buffers, because their job is to
#: move bytes between device and host. They are held to every OTHER rule —
#: no printing, no decoding, no regex, no escape constructs — and they must
#: never retain what passes through them. Device-to-host copies write directly
#: into the writable view supplied by ``SafeBuffer.fill_via``.
#:
#: Keep this list as short as it can possibly be. Each entry is a place where
#: "all buffer handling passes through one enforced-safe layer" is being
#: stretched, and the stretch should be visible.
LOW_LEVEL_MEMORY_MODULES = {
    "gpu_seal/cuda/backend.py",
}

#: Modules permitted to call SafeBuffer.fill_via — the single write door.
#: Its writer callback receives a raw writable memoryview, and nothing at
#: runtime stops a writer from copying or retaining it (see the caveat in
#: gpu_seal.safety.buffer's module docstring); this allowlist is the
#: complementary static control, mirroring how _unsafe_view is restricted to
#: the aggregation module. Keep it as short as it can possibly be.
FILL_VIA_CALLER_MODULES = {
    "gpu_seal/probes/memory_global.py",
    "gpu_seal/probes/memory_local.py",
}

#: Symbols whose names describe a forbidden thing in order to forbid it.
#: A test called ``test_no_container_escape_constructs`` is the opposite of a
#: problem, but a naive substring check cannot tell it apart from the real
#: thing — so negative-assertion prefixes are exempted explicitly.
NEGATIVE_ASSERTION_PREFIXES = (
    "test_no_",
    "test_never_",
    "test_rejects_",
    "test_refuses_",
)


class Module(NamedTuple):
    path: pathlib.Path
    rel: str
    tree: ast.AST
    source: str

    @property
    def is_safe_layer(self) -> bool:
        return self.rel in SAFE_LAYER_MODULES

    @property
    def may_touch_raw_bytes(self) -> bool:
        return self.rel in SAFE_LAYER_MODULES or self.rel in LOW_LEVEL_MEMORY_MODULES


def _modules() -> Iterator[Module]:
    for path in sorted(PROBE_ROOT.rglob("*.py")):
        rel = path.relative_to(PROBE_ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        yield Module(path, rel, ast.parse(source, filename=str(path)), source)


def _all_modules() -> list[Module]:
    mods = list(_modules())
    assert mods, f"no Python modules found under {PROBE_ROOT}"
    return mods


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """ids() of every string Constant that is a docstring.

    Docstrings quote the charter, and the charter names the things GPU-SEAL
    must not do ("free of ... real secrets", "LD_PRELOAD", ...). Explaining a
    prohibition is not committing a violation, so prose is excluded from the
    literal scans below. Executable string literals are not.
    """
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            found.add(id(first.value))
    return found


def _code_string_literals(m: Module) -> Iterator[tuple[int, str]]:
    """Yield (lineno, value) for string literals that are NOT docstrings."""
    docstrings = _docstring_nodes(m.tree)
    for node in ast.walk(m.tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            yield node.lineno, node.value


def _getattr_literal_name(node: ast.Call) -> str | None:
    """If `node` is `getattr(obj, "name", ...)` with a literal string second
    argument, return "name". Both `getattr(x, "print")(...)` (called
    immediately) and `f = getattr(x, "print")` (aliased, resolved by
    `_simple_aliases` below) route through this."""
    f = node.func
    if isinstance(f, ast.Name) and f.id == "getattr" and len(node.args) >= 2:
        second = node.args[1]
        if isinstance(second, ast.Constant) and isinstance(second.value, str):
            return second.value
    return None


def _simple_aliases(tree: ast.AST) -> dict[str, str]:
    """Map `alias -> effective name` for the two simplest evasions of a
    literal-callee check: `alias = banned_name` and `alias = getattr(x,
    "banned_name")`. Not scope-aware, and not a sound alias analysis — same
    tripwire philosophy as the rest of this file (see the module docstring):
    it exists to catch an evasion attempt reaching CI, not to prove no
    evasion is possible. Multi-hop aliasing (`a = b; c = a`), attribute
    aliasing (`d = obj.decode`), and `exec`/`eval` are not covered.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            continue
        target = node.targets[0].id
        if isinstance(node.value, ast.Name):
            aliases[target] = node.value.id
        elif isinstance(node.value, ast.Call):
            literal = _getattr_literal_name(node.value)
            if literal is not None:
                aliases[target] = literal
    return aliases


def _call_names(tree: ast.AST) -> Iterator[tuple[ast.Call, str]]:
    """Yield (node, dotted-ish name) for every call in a tree.

    Beyond a literal `Name(...)` or `obj.attr(...)` callee, also resolves —
    best-effort, see `_simple_aliases` — a direct `getattr(obj, "name")(...)`
    call and a call through a simple same-shape alias assigned earlier in the
    module. Neither claims to be sound; both exist so an evasion attempt is
    more likely to be caught than not.
    """
    aliases = _simple_aliases(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Name):
            literal = _getattr_literal_name(node)
            if literal is not None:
                yield node, literal
            else:
                yield node, aliases.get(f.id, f.id)
        elif isinstance(f, ast.Attribute):
            yield node, f.attr
        else:
            yield node, ""


def _dynamic_import_module_names(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """Yield (lineno, top-level module name) for `__import__("module...")`
    calls with a literal first argument — the dynamic-import counterpart to
    `ast.Import`/`ast.ImportFrom`, which `__import__("re")` does not produce."""
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "__import__" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            yield node.lineno, first.value.split(".")[0]


# ---------------------------------------------------------------------------
# The resolvers above are themselves under test: a Codex review of this
# project found that the previous _call_names implementation resolved only a
# direct Name/Attribute callee, so `p = print; p(x)`, `getattr(x, "decode")()`,
# and `__import__("re")` were all invisible to every rule below. These pin
# that the improved resolvers actually catch what they claim to.
# ---------------------------------------------------------------------------


def _names_in(source: str) -> list[str]:
    return [name for _, name in _call_names(ast.parse(source))]


def test_call_names_resolves_a_simple_alias():
    names = _names_in("p = print\np('leaked')\n")
    assert "print" in names


def test_call_names_resolves_getattr_dispatch_called_immediately():
    names = _names_in("getattr(obj, 'decode')(x)\n")
    assert "decode" in names


def test_call_names_resolves_getattr_dispatch_aliased_then_called():
    names = _names_in("f = getattr(obj, 'decode')\nf(x)\n")
    assert "decode" in names


def test_call_names_still_resolves_an_ordinary_direct_call():
    """The improvement must not regress the base case."""
    names = _names_in("print('x')\n")
    assert names == ["print"]


def test_call_names_does_not_confuse_an_unrelated_getattr_call():
    """A getattr() call with a non-literal or missing name arg must not be
    misread as resolving to some other banned name. (ast.walk visits the
    inner `getattr(...)` call too, which legitimately resolves to the name
    "getattr" itself — that is not a banned name anywhere in this file.)"""
    names = _names_in("getattr(obj, field_name)(x)\n")
    assert "" in names
    assert "decode" not in names
    assert "print" not in names


def test_dynamic_import_module_names_resolves_dunder_import():
    tree = ast.parse("__import__('re')\n")
    assert list(_dynamic_import_module_names(tree)) == [(1, "re")]


def test_dynamic_import_module_names_resolves_submodule_import():
    tree = ast.parse("__import__('re.something')\n")
    assert list(_dynamic_import_module_names(tree)) == [(1, "re")]


def test_dynamic_import_module_names_ignores_a_non_literal_argument():
    tree = ast.parse("__import__(module_name)\n")
    assert list(_dynamic_import_module_names(tree)) == []


# ---------------------------------------------------------------------------
# Test 1 — no code path prints raw probe buffers
# ---------------------------------------------------------------------------


def test_no_print_calls_in_probe_source():
    """Probes emit structured signed results, never stdout.

    A print() in probe code is how unknown memory ends up in a provider's
    container logs.
    """
    offenders = [
        f"{m.rel}:{node.lineno}"
        for m in _all_modules()
        for node, name in _call_names(m.tree)
        if name == "print"
    ]
    assert not offenders, (
        f"print() found in probe source at {offenders}. Probes must emit "
        f"structured signed results (CHARTER.md §16 test 1)."
    )


# ---------------------------------------------------------------------------
# Test 4 — no automatic UTF-8 / text decoding
# ---------------------------------------------------------------------------

BANNED_DECODE_CALLS = {"decode", "decodebytes", "unhexlify"}
BANNED_TEXT_MODULES = {"codecs", "chardet", "charset_normalizer", "ftfy", "unicodedata"}


#: The single module permitted to call .decode(). CUDA returns some driver
#: metadata (device names) as NUL-terminated bytes, and a result that cannot
#: name the GPU it measured is of limited use. Rather than exempt a module
#: that also touches memory, the exemption is one narrow, tested helper that
#: refuses any input longer than 256 bytes or containing non-printable ASCII —
#: so it structurally cannot decode a VRAM buffer.
DECODE_PERMITTED_MODULES = {"gpu_seal/safety/metadata.py"}


def test_no_text_decoding_in_probe_source():
    offenders = [
        f"{m.rel}:{node.lineno} -> .{name}()"
        for m in _all_modules()
        if m.rel not in DECODE_PERMITTED_MODULES
        for node, name in _call_names(m.tree)
        if name in BANNED_DECODE_CALLS
    ]
    assert not offenders, (
        f"Text-decoding calls found at {offenders}. CHARTER.md §7.2 forbids "
        f"attempting UTF-8 decoding of unknown memory. Driver metadata must go "
        f"through gpu_seal.safety.metadata.ascii_metadata(), which refuses "
        f"anything that is not short printable ASCII."
    )


def test_decode_exemption_is_a_single_module():
    assert len(DECODE_PERMITTED_MODULES) == 1, (
        f"More than one module may decode: {sorted(DECODE_PERMITTED_MODULES)}. "
        f"Widening this defeats CHARTER.md §16 test 4."
    )


def test_no_text_decoding_imports():
    offenders = []
    for m in _all_modules():
        for node in ast.walk(m.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in BANNED_TEXT_MODULES:
                        offenders.append(f"{m.rel}:{node.lineno} import {a.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in BANNED_TEXT_MODULES:
                    offenders.append(f"{m.rel}:{node.lineno} from {node.module}")
        for lineno, name in _dynamic_import_module_names(m.tree):
            if name in BANNED_TEXT_MODULES:
                offenders.append(f"{m.rel}:{lineno} __import__({name!r})")
    assert not offenders, (
        f"Text-decoding library imports found at {offenders} (CHARTER.md §7.2)."
    )


# ---------------------------------------------------------------------------
# Test 5 — no regex search for credentials or secrets
# ---------------------------------------------------------------------------

CREDENTIAL_TOKENS = {
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "bearer",
    "authorization",
    "credential",
    "ssh-rsa",
    "begin rsa",
    "aws_secret",
    "token=",
}


def test_no_regex_module_used_against_unknown_memory():
    """`re` has no legitimate use in the probe path.

    Owned-canary matching is exact byte comparison against markers we minted.
    A regex over unknown memory is pattern-hunting in someone else's data.
    """
    offenders = []
    for m in _all_modules():
        for node in ast.walk(m.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in {"re", "regex"}:
                        offenders.append(f"{m.rel}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in {"re", "regex"}:
                    offenders.append(f"{m.rel}:{node.lineno}")
        for lineno, name in _dynamic_import_module_names(m.tree):
            if name in {"re", "regex"}:
                offenders.append(f"{m.rel}:{lineno} __import__({name!r})")
    assert not offenders, (
        f"Regex imports found in probe source at {offenders}. CHARTER.md §7.2 "
        f"forbids searching unknown bytes for patterns; only exact owned-canary "
        f"matching is permitted."
    )


def test_no_credential_patterns_in_string_literals():
    """A credential token in *executable* code is a search pattern.

    The same token inside a docstring is documentation — often documentation
    of the very prohibition being enforced. Only non-docstring literals are
    scanned; see :func:`_code_string_literals`.
    """
    offenders = []
    for m in _all_modules():
        for lineno, value in _code_string_literals(m):
            low = value.lower()
            for token in CREDENTIAL_TOKENS:
                if token in low:
                    offenders.append(f"{m.rel}:{lineno} {token!r}")
    assert not offenders, (
        f"Credential-like string literals found in executable code at "
        f"{offenders}. CHARTER.md §7.2 forbids searching unknown bytes for "
        f"credentials or keys."
    )


# ---------------------------------------------------------------------------
# Test 15 — destructive / privilege-escalation names prohibited
# ---------------------------------------------------------------------------

FORBIDDEN_NAME_FRAGMENTS = {
    "rowhammer",
    "hammer",
    "privesc",
    "escalate",
    "escalation",
    "container_escape",
    "vm_escape",
    "host_escape",
    "breakout",
    "exploit",
    "payload_inject",
    "shellcode",
    "backdoor",
    "bypass_auth",
    "dos_",
    "denial_of_service",
    "fault_inject",
    "glitch",
    "overwrite_host",
    "steal",
    "exfil",
    "dump_vram",
    "dump_memory",
    "recover_text",
    "reconstruct_prompt",
}


def test_no_destructive_or_offensive_symbol_names():
    """CHARTER.md §16 test 15, §4.3 non-goals.

    Naming is not cosmetic here. A repo containing `container_escape()` is a
    repo that cannot be handed to a provider's security team, whatever the
    function actually does.
    """
    offenders = []
    for m in _all_modules():
        for node in ast.walk(m.tree):
            name = None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                name = node.id
            if not name:
                continue
            low = name.lower()
            for frag in FORBIDDEN_NAME_FRAGMENTS:
                if frag in low:
                    offenders.append(f"{m.rel}:{node.lineno} {name!r} ~ {frag!r}")
    assert not offenders, (
        f"Forbidden symbol names found at {offenders} (CHARTER.md §16 test 15)."
    )


def test_no_destructive_test_names():
    """Same rule, applied to the test suite itself.

    Tests that *assert the absence* of a forbidden construct necessarily name
    it. Those are exempt via ``NEGATIVE_ASSERTION_PREFIXES``; a test called
    ``test_container_escape`` is not.
    """
    offenders = []
    for path in sorted((REPO_ROOT / "tests").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            low = node.name.lower()
            if low.startswith(NEGATIVE_ASSERTION_PREFIXES):
                continue
            for frag in FORBIDDEN_NAME_FRAGMENTS:
                if frag in low:
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{node.lineno} {node.name!r}"
                    )
    assert not offenders, f"Forbidden test names found at {offenders}."


# ---------------------------------------------------------------------------
# Test 17 — no container-escape or privilege-escalation techniques
# ---------------------------------------------------------------------------

ESCAPE_INDICATORS = {
    "LD_PRELOAD",
    "/proc/1/root",
    "/proc/self/exe",
    "nsenter",
    "setns",
    "unshare",
    "CAP_SYS_ADMIN",
    "docker.sock",
    "/var/run/docker",
    "release_agent",
    "core_pattern",
    "enable-cuda-compat",
}


def test_no_container_escape_constructs():
    """§9.6 is an inventory. It observes exposure; it never uses it.

    The NVIDIAScape class of bug (CVE-2025-23266) is exactly what §9.6
    catalogues, and exactly what GPU-SEAL must never perform.
    """
    offenders = []
    for m in _all_modules():
        for lineno, value in _code_string_literals(m):
            for ind in ESCAPE_INDICATORS:
                if ind.lower() in value.lower():
                    offenders.append(f"{m.rel}:{lineno} {ind!r}")
    assert not offenders, (
        f"Container-escape indicators found at {offenders}. CHARTER.md §9.6 is "
        f"inventory-only; §4.3 forbids escaping a container under any "
        f"circumstances."
    )


def test_no_privileged_subprocess_invocations():
    banned = {"setuid", "seteuid", "setgid", "system", "execv", "execve", "fork"}
    offenders = [
        f"{m.rel}:{node.lineno} {name}()"
        for m in _all_modules()
        for node, name in _call_names(m.tree)
        if name in banned
    ]
    assert not offenders, (
        f"Privileged process calls found at {offenders} (CHARTER.md §4.3)."
    )


# ---------------------------------------------------------------------------
# Safe-layer containment
# ---------------------------------------------------------------------------


def test_unsafe_view_is_only_called_from_the_aggregation_module():
    """The one read door must have exactly one caller."""
    offenders = []
    for m in _all_modules():
        if m.rel == "gpu_seal/safety/aggregation.py":
            continue
        for node in ast.walk(m.tree):
            if isinstance(node, ast.Attribute) and node.attr == "_unsafe_view":
                offenders.append(f"{m.rel}:{node.lineno}")
    assert not offenders, (
        f"_unsafe_view called outside the aggregation module at {offenders}. "
        f"All content access must go through aggregate() (CHARTER.md §8)."
    )


def test_fill_via_is_only_called_from_an_allowlisted_module():
    """The one write door must have a reviewed, short list of callers.

    Not a runtime boundary — a writer callback can still retain the view it
    is handed (see gpu_seal.safety.buffer's module docstring) — but a new,
    unreviewed caller of fill_via() is exactly the kind of change this catches
    before it reaches CI green.
    """
    offenders = []
    for m in _all_modules():
        if m.rel in FILL_VIA_CALLER_MODULES:
            continue
        for node in ast.walk(m.tree):
            if isinstance(node, ast.Attribute) and node.attr == "fill_via":
                offenders.append(f"{m.rel}:{node.lineno}")
    assert not offenders, (
        f"fill_via called outside {sorted(FILL_VIA_CALLER_MODULES)} at "
        f"{offenders}. If a new module genuinely needs to fill a SafeBuffer, "
        f"add it to FILL_VIA_CALLER_MODULES deliberately."
    )


def test_fill_via_allowlist_stays_small():
    assert len(FILL_VIA_CALLER_MODULES) <= 2, (
        f"FILL_VIA_CALLER_MODULES has grown to {len(FILL_VIA_CALLER_MODULES)}: "
        f"{sorted(FILL_VIA_CALLER_MODULES)}"
    )


def test_no_unsafe_raw_bytes_access_outside_the_safe_layer():
    """`SafeBuffer._unsafe_raw_bytes` is a plain slot attribute — single
    underscore is a convention, not access control, and `bytes(buf._unsafe_raw_bytes)`
    bypasses every blocked dunder. Same tripwire pattern as _unsafe_view,
    applied to the one other name that reaches raw content directly."""
    offenders = []
    for m in _all_modules():
        if m.rel == "gpu_seal/safety/buffer.py":
            continue
        for node in ast.walk(m.tree):
            if isinstance(node, ast.Attribute) and node.attr == "_unsafe_raw_bytes":
                offenders.append(f"{m.rel}:{node.lineno}")
    assert not offenders, (
        f"_unsafe_raw_bytes accessed outside buffer.py at {offenders}. All "
        f"content access must go through aggregate() (CHARTER.md §8)."
    )


def test_serialisation_modules_are_not_imported_in_probe_source():
    """pickle/marshal/shelve are how unknown bytes reach disk by accident."""
    banned = {"pickle", "cPickle", "marshal", "shelve", "dill", "joblib"}
    offenders = []
    for m in _all_modules():
        for node in ast.walk(m.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in banned:
                        offenders.append(f"{m.rel}:{node.lineno} {a.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in banned:
                    offenders.append(f"{m.rel}:{node.lineno} {node.module}")
        for lineno, name in _dynamic_import_module_names(m.tree):
            if name in banned:
                offenders.append(f"{m.rel}:{lineno} __import__({name!r})")
    assert not offenders, (
        f"Serialisation modules imported at {offenders} (CHARTER.md §16 test 2)."
    )


def test_non_safe_layer_modules_do_not_convert_buffers_to_bytes():
    """Only the safe layer may materialise raw bytes, and only internally."""
    offenders = []
    for m in _all_modules():
        if m.may_touch_raw_bytes:
            continue
        for node, name in _call_names(m.tree):
            if name in {"bytes", "bytearray", "frombuffer", "tobytes"}:
                offenders.append(f"{m.rel}:{node.lineno} {name}()")
    assert not offenders, (
        f"Raw byte materialisation outside the safe layer at {offenders}. "
        f"CHARTER.md §8: all buffer handling passes through one enforced-safe "
        f"layer. If a new module genuinely must move bytes, add it to "
        f"LOW_LEVEL_MEMORY_MODULES deliberately — do not widen this check."
    )


def test_raw_byte_allowlists_stay_small():
    """Guard against the exemption lists quietly growing.

    Every entry is a place the centralisation principle is stretched. Growth
    should require a conscious decision and a bump to these numbers, with a
    reason in the commit message.
    """
    assert len(SAFE_LAYER_MODULES) <= 3, (
        f"SAFE_LAYER_MODULES has grown to {len(SAFE_LAYER_MODULES)}: "
        f"{sorted(SAFE_LAYER_MODULES)}"
    )
    assert len(LOW_LEVEL_MEMORY_MODULES) <= 2, (
        f"LOW_LEVEL_MEMORY_MODULES has grown to {len(LOW_LEVEL_MEMORY_MODULES)}: "
        f"{sorted(LOW_LEVEL_MEMORY_MODULES)}"
    )


def test_low_level_modules_do_not_retain_buffers():
    """A byte-moving module must not keep module-level mutable byte storage.

    The simulated backend's pool is an instance attribute with a bounded
    lifetime, which is fine. A module-level bytearray would outlive every
    measurement and is not.
    """
    offenders = []
    for m in _all_modules():
        if m.rel not in LOW_LEVEL_MEMORY_MODULES:
            continue
        for node in m.tree.body:  # type: ignore[attr-defined]
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in {"bytearray", "bytes"}
            ):
                offenders.append(f"{m.rel}:{node.lineno}")
    assert not offenders, (
        f"Module-level byte storage in a low-level module at {offenders}. "
        f"Byte storage must not outlive a single measurement."
    )


def test_safe_layer_module_list_is_accurate():
    """Guard against the allowlist silently drifting from reality."""
    existing = {m.rel for m in _all_modules()}
    missing = SAFE_LAYER_MODULES - existing
    assert not missing, (
        f"SAFE_LAYER_MODULES names modules that no longer exist: {missing}. "
        f"A stale allowlist entry could exempt a future file with the same path."
    )
