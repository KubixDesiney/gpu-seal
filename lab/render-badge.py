#!/usr/bin/env python3
"""Render a static SVG badge from the mutation-battery summary JSON.

README.md used to hand-type "injected violations caught: 38/38" as a badge
label, which drifts silently the moment a case is added or removed. This
script runs in CI (see the publish-mutation-badge job in
.github/workflows/safety.yml) against the real mutation-summary.json produced
by lab/summarize-mutation-results.py, and the resulting SVG is committed to
badges/mutation-battery.svg so README.md can reference it by relative path --
no third-party badge service, no place left for the number to drift.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

LABEL = "injected violations caught"
FONT_WIDTH = 6.5  # rough average glyph width in px at the badge's 11px font
PAD = 10  # horizontal padding on each side of a text block
HEIGHT = 20


def _text_width(text: str) -> float:
    return len(text) * FONT_WIDTH + PAD * 2


def render(label: str, message: str, color: str) -> str:
    label_w = _text_width(label)
    msg_w = _text_width(message)
    total_w = label_w + msg_w
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="{HEIGHT}" role="img" aria-label="{label}: {message}">
  <title>{label}: {message}</title>
  <rect width="{total_w:.0f}" height="{HEIGHT}" fill="#555"/>
  <rect x="{label_w:.0f}" width="{msg_w:.0f}" height="{HEIGHT}" fill="{color}"/>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{label_w / 2:.0f}" y="14">{label}</text>
    <text x="{label_w + msg_w / 2:.0f}" y="14">{message}</text>
  </g>
</svg>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_json", type=Path)
    parser.add_argument("output_svg", type=Path)
    args = parser.parse_args()

    summary = json.loads(args.summary_json.read_text(encoding="utf-8"))
    total = summary["total"]
    caught = summary["caught"]
    message = f"{caught}/{total}"
    color = "#4c1" if caught == total else "#e05d44"

    args.output_svg.parent.mkdir(parents=True, exist_ok=True)
    args.output_svg.write_text(render(LABEL, message, color), encoding="utf-8")
    print(f"wrote {args.output_svg} ({message})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
