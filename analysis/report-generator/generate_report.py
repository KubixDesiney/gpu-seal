#!/usr/bin/env python3
"""Turn signed bundles into a provider-neutral report — CHARTER.md §13, §21.

    python3 analysis/report-generator/generate_report.py out/ \\
        --trusted-keyring keys/reporting-keyring.txt --output report.md

Reads every signed bundle in a directory, verifies each one, and writes a
Markdown report grouped by provider code.

Three rules, enforced here rather than left to whoever writes the paper:

**Signature first.** A bundle whose signature does not verify is listed as
*excluded*, with its filename, and contributes nothing. It is not silently
skipped — a missing bundle and a tampered bundle must not look the same.

**Quarantined bundles are excluded and named.** `out/MISLABELLED-README.md`
lists bundles retained for honesty but not citable. The generator reads that
file and excludes what it names.

**No composite score, and no ranking.** Providers are listed in code order,
never sorted by grade. CHARTER.md §11: "No public ranking." A report generator
that sorts by outcome produces a league table whether or not it prints one.

Publishable reports require an out-of-band trusted public key or keyring. The
bundle's embedded key is only an internal consistency hint and is never enough
for publication. ``--unsafe-dev-allow-embedded-key`` is an explicit local
development escape hatch and marks the resulting report non-publishable.

The maths this report quotes lives in `gpu_seal.analysis`, which the test suite
exercises. A number that exists only inside a report generator is a number
nobody can reproduce.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "probe"))

from gpu_seal.analysis.statistics import ObservationCounts  # noqa: E402
from gpu_seal.evidence.result import ResultBundle  # noqa: E402
from gpu_seal.evidence.signing import VerifyKey  # noqa: E402


def _key_from_text(value: str) -> VerifyKey:
    """Load one configured Ed25519 public key from hex or a PEM/hex file."""
    candidate = Path(value)
    text = (
        candidate.read_text(encoding="utf-8").strip()
        if candidate.is_file()
        else value.strip()
    )
    if "BEGIN PUBLIC KEY" in text:
        return VerifyKey.from_pem(text.encode("ascii"))
    return VerifyKey.from_hex(text)


def load_trusted_keys(
    public_keys: list[str] | None = None, keyring: Path | None = None
) -> tuple[VerifyKey, ...]:
    """Load the out-of-band keys permitted to authenticate publishable evidence.

    A keyring is newline-delimited hex, with blank lines and ``#`` comments
    ignored. JSON ``["hex", ...]`` and ``{"keys": ["hex", ...]}`` are also
    accepted so deployments can keep one machine-readable trust file.
    """
    values = list(public_keys or [])
    if keyring is not None:
        raw = keyring.read_text(encoding="utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = [
                line.strip()
                for line in raw.splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
        if isinstance(parsed, dict):
            parsed = parsed.get("keys", [])
        if not isinstance(parsed, list) or not all(
            isinstance(item, str) for item in parsed
        ):
            raise ValueError(
                "trusted keyring must be a list or an object with a string "
                "'keys' list"
            )
        values.extend(parsed)
    return tuple(_key_from_text(value) for value in values)


def load_quarantined(directory: Path) -> set[str]:
    """Filenames named in the quarantine README, if there is one."""
    readme = directory / "MISLABELLED-README.md"
    if not readme.exists():
        return set()
    text = readme.read_text(encoding="utf-8")
    return {
        path.name
        for path in directory.glob("*.result.json")
        if path.name in text
    }


def collect(
    directory: Path,
    trusted_keys: tuple[VerifyKey, ...] | list[VerifyKey] | None = None,
    *,
    unsafe_dev: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Collect bundles only after external-key verification.

    Embedded-key verification is deliberately available only through the
    explicit unsafe development switch. It proves that a bundle is internally
    self-consistent, not that it was signed by a project-trusted signer.
    """
    trusted = tuple(trusted_keys or ())
    if not trusted and not unsafe_dev:
        raise ValueError(
            "no trusted public key configured; publishable reports require "
            "--trusted-public-key or --trusted-keyring (use "
            "--unsafe-dev-allow-embedded-key only for local development)"
        )
    quarantined = load_quarantined(directory)
    usable: list[dict[str, Any]] = []
    excluded: list[str] = []

    for path in sorted(directory.glob("*.result.json")):
        if path.name in quarantined:
            excluded.append(f"{path.name} — quarantined (see MISLABELLED-README.md)")
            continue
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            excluded.append(f"{path.name} — not valid JSON: {exc}")
            continue
        verified = (
            ResultBundle.verify(bundle)
            if unsafe_dev
            else any(ResultBundle.verify(bundle, key) for key in trusted)
        )
        if not verified:
            excluded.append(f"{path.name} — signature does not verify")
            continue
        bundle["_source"] = path.name
        usable.append(bundle)

    return usable, excluded


def probe_counts(bundle: dict[str, Any], probe_name: str) -> ObservationCounts:
    records = [p for p in bundle.get("probes", []) if p["probe_name"] == probe_name]
    positive = sum(1 for p in records if p.get("owned_canary_match"))
    return ObservationCounts(
        attempted=len(records), usable=len(records), positive=positive
    )


def _escape_md(text: object) -> str:
    """Make bundle-derived text safe to interpolate into the report.

    A signature authenticates who signed a bundle, not that its string
    fields are safe to render as Markdown/HTML — the schema leaves fields
    like a report-card `basis` or `provider_code` as arbitrary strings, and
    the schema explicitly says `basis` "goes straight into the report."
    Escapes HTML-significant characters (the concrete risk: stored XSS if
    this report is ever viewed through a permissive Markdown-to-HTML
    renderer) and collapses embedded newlines and table pipes so one field
    cannot inject new report lines or break a table row.
    """
    value = html.escape(str(text), quote=False)
    return value.replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def _escape_code_span(text: object) -> str:
    """Like `_escape_md`, for text that will be wrapped in `` `backticks` ``,
    where an embedded backtick would otherwise close the code span early."""
    return _escape_md(text).replace("`", "'")


def render(bundles: list[dict[str, Any]], excluded: list[str]) -> str:
    # A verified signature only proves who signed the bundle, not that it
    # cleared for publication — `automatic_publication_allowed` starts false
    # and a bundle carrying a sensitive_observation, a simulated probe, or an
    # unpinned/unbound container claim never sets it. Rendering such a
    # bundle's full probe detail and report-card table into this report
    # would put content CHARTER.md §7.3/§7.5 requires disclosure review for
    # into the "public" output, with only a buried bullet point noting it
    # was not actually cleared. Publishable and non-publishable bundles are
    # therefore kept structurally apart from here on: only the former gets
    # full detail, and the latter is named — not rendered — same as an
    # excluded bundle.
    publishable = [
        b for b in bundles if b.get("safety", {}).get("automatic_publication_allowed")
    ]
    not_publishable = [
        b
        for b in bundles
        if not b.get("safety", {}).get("automatic_publication_allowed")
    ]

    by_provider: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bundle in publishable:
        by_provider[_escape_md(bundle["provider_code"])].append(bundle)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lines = [
        "# GPU-SEAL assurance report",
        "",
        f"Generated {now} from {len(publishable)} publishable bundle(s) "
        f"({len(bundles)} verified, {len(not_publishable)} not cleared for "
        f"publication).",
        "",
        "> Provider codes are pseudonymous (CHARTER.md §7.6). Providers are",
        "> listed in code order, never sorted by outcome — §11 forbids public",
        "> ranking, and a generator that sorts by grade produces a league table",
        "> whether or not it prints one.",
        "",
        "> **U means unproven, not failing.** It is the grade for a claim the",
        "> evidence cannot support, often because the method cannot support it.",
        "",
    ]

    for provider in sorted(by_provider):
        runs = by_provider[provider]
        lines += [f"## {provider}", "", f"{len(runs)} verified run(s).", ""]

        for bundle in runs:
            lines.append(f"### `{_escape_code_span(bundle['run_id'])}`")
            lines.append("")
            env = bundle.get("environment", {})
            lines.append(
                f"- product claim: {_escape_md(bundle.get('product_claim', 'n/a'))}"
            )
            lines.append(
                f"- region claim: {_escape_md(bundle.get('region_claim', 'n/a'))}"
            )
            lines.append(
                f"- container profile: "
                f"{_escape_md(env.get('container_profile', '?'))}"
            )

            model = bundle.get("allocation_model", {})
            if model:
                lines.append(
                    f"- allocation model: "
                    f"{_escape_md(model.get('classification', '?'))} "
                    f"(confidence {model.get('confidence', 0):.2f})"
                )

            for probe_name in sorted(
                {p["probe_name"] for p in bundle.get("probes", [])}
            ):
                counts = probe_counts(bundle, probe_name)
                interval = counts.confidence_interval()
                band = (
                    f"[{interval[0]:.3f}, {interval[1]:.3f}]" if interval else "n/a"
                )
                lines.append(
                    f"- `{_escape_code_span(probe_name)}`: "
                    f"{counts.positive}/{counts.usable} "
                    f"recovered, 95% CI {band}"
                )

            card = bundle.get("report_card") or {}
            if card:
                lines += ["", "| Category | Grade | Basis |", "|---|:---:|---|"]
                for key, value in card.items():
                    if isinstance(value, dict) and "grade" in value:
                        basis = _escape_md(value["basis"])
                        lines.append(
                            f"| {_escape_md(key)} | **{_escape_md(value['grade'])}** "
                            f"| {basis} |"
                        )
            lines.append("")

    if not_publishable:
        lines += [
            "## Verified but not cleared for publication",
            "",
            "Signature-verified, but `automatic_publication_allowed` is false —",
            "a sensitive observation, a simulated probe, or an unpinned/unbound",
            "container claim. Named only, same as an excluded bundle: rendering",
            "probe detail or a report-card table here would put content",
            "CHARTER.md §7.3/§7.5 requires disclosure review for into this",
            "report.",
            "",
        ]
        for bundle in not_publishable:
            source = bundle.get("_source", bundle.get("run_id", "unknown"))
            provider = bundle.get("provider_code", "?")
            lines.append(
                f"- `{_escape_code_span(source)}` "
                f"(provider {_escape_md(provider)})"
            )
        lines.append("")

    if excluded:
        lines += [
            "## Excluded bundles",
            "",
            "Listed rather than skipped: a missing bundle and a tampered one",
            "must not look the same.",
            "",
        ]
        lines += [f"- {reason}" for reason in excluded]
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("directory", type=Path, nargs="?", default=Path("out"))
    ap.add_argument("--output", type=Path)
    ap.add_argument(
        "--trusted-public-key",
        action="append",
        default=[],
        metavar="HEX_OR_FILE",
        help="trusted Ed25519 public key hex or PEM/hex file (repeatable)",
    )
    ap.add_argument(
        "--trusted-keyring",
        type=Path,
        help="newline-delimited or JSON keyring of trusted public keys",
    )
    ap.add_argument(
        "--unsafe-dev-allow-embedded-key",
        action="store_true",
        help="UNSAFE local development mode; verify using each bundle's embedded key",
    )
    args = ap.parse_args()

    if not args.directory.is_dir():
        print(f"error: {args.directory} is not a directory", file=sys.stderr)
        return 1

    try:
        configured = load_trusted_keys(args.trusted_public_key, args.trusted_keyring)
        bundles, excluded = collect(
            args.directory, configured, unsafe_dev=args.unsafe_dev_allow_embedded_key
        )
    except (OSError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not bundles and not excluded:
        print(f"error: no bundles found in {args.directory}", file=sys.stderr)
        return 1

    report = render(bundles, excluded)
    if args.unsafe_dev_allow_embedded_key:
        report = (
            "<!-- UNSAFE DEV REPORT: embedded keys were accepted; this report "
            "is not publishable evidence. -->\n\n" + report
        )
    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(f"wrote {args.output} ({len(bundles)} verified, {len(excluded)} excluded)")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
