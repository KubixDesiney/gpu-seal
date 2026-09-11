#!/usr/bin/env python3
"""Check repository Markdown links and onboarding placeholders.

This is intentionally a local-link check. It does not make network requests or
claim that an external URL is live; provider policy sources remain operator
review material and are not fetched by a release check.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", "venv", "node_modules", "build", "dist", "out"}
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not SKIP_PARTS.intersection(path.relative_to(ROOT).parts)
    )


def check_links() -> tuple[int, list[str]]:
    problems: list[str] = []
    link_count = 0
    for source in markdown_files():
        text = source.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            raw_target = match.group(1).strip()
            target = raw_target.split("#", 1)[0].strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            link_count += 1
            candidate = (source.parent / unquote(target)).resolve()
            try:
                candidate.relative_to(ROOT.resolve())
            except ValueError:
                problems.append(
                    f"{source.relative_to(ROOT)}: link escapes repository: {target}"
                )
                continue
            if not candidate.exists():
                problems.append(
                    f"{source.relative_to(ROOT)}: missing link target: {target}"
                )
    return link_count, problems


def main() -> int:
    files = markdown_files()
    link_count, problems = check_links()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "<this-repo-url>" in readme:
        problems.append("README.md still contains the placeholder clone URL")
    if "https://github.com/KubixDesiney/gpu-seal.git" not in readme:
        problems.append("README.md does not contain the repository clone URL")

    print(f"documentation check: {len(files)} Markdown files, {link_count} local links")
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}")
        return 1
    print("documentation check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
