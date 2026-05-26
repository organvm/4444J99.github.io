#!/usr/bin/env python3
"""
sync-site — render the landing page's dynamic data from a single source.

Reads data/site.json and injects it into index.html:
  * inline `<!-- v:KEY -->...<!-- /v -->` markers  <- data["values"][KEY]
  * the `<!-- organs:start -->...<!-- organs:end -->` block  <- data["organs"]

Usage:
  python3 scripts/sync-site.py            # rewrite index.html in place
  python3 scripts/sync-site.py --check    # exit 1 if index.html is out of sync

Environment overrides:
  SITE_DATA   — path to the data file (default: data/site.json)
  SITE_HTML   — path to the HTML file (default: index.html)

Pure standard library — no third-party dependencies.
"""

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

VALUE = re.compile(r"(<!-- v:([A-Za-z0-9_]+) -->)(.*?)(<!-- /v -->)", re.DOTALL)
# Capture the leading indent on the start-marker line so the regenerated block
# matches the surrounding HTML's indentation rather than a hardcoded width.
ORGANS = re.compile(r"(?P<indent>[^\S\n]*)<!-- organs:start -->.*?<!-- organs:end -->",
                    re.DOTALL)


def render_organs(organs: list[dict], indent: str) -> str:
    """Render the nav <li> items at the given indent."""
    lines = []
    for o in organs:
        cls = "active" if o.get("active") else ""
        url = html.escape(str(o["url"]), quote=True)
        label = html.escape(str(o["label"]))
        lines.append(f'{indent}<li><a href="{url}" class="{cls}">{label}</a></li>')
    return "\n".join(lines)


def render(text: str, data: dict) -> tuple[str, list[str]]:
    warnings: list[str] = []
    values = {k: ("" if v is None else str(v)) for k, v in (data.get("values") or {}).items()}
    seen: set[str] = set()

    def vrepl(m: re.Match) -> str:
        key = m.group(2)
        seen.add(key)
        if key not in values:
            warnings.append(f"marker '{key}' has no entry in data['values']")
            return m.group(0)
        return f"{m.group(1)}{values[key]}{m.group(4)}"

    text = VALUE.sub(vrepl, text)
    for key in values:
        if key not in seen:
            warnings.append(f"value '{key}' has no matching marker in the HTML")

    if "organs" in data:
        if ORGANS.search(text):
            def repl(m: re.Match) -> str:
                indent = m.group("indent")
                items = render_organs(data["organs"], indent)
                return f"{indent}<!-- organs:start -->\n{items}\n{indent}<!-- organs:end -->"
            text = ORGANS.sub(repl, text)
        else:
            warnings.append("no <!-- organs:start/end --> block found in the HTML")

    return text, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="verify index.html is in sync; exit 1 on drift (no write)")
    args = parser.parse_args()

    data_path = Path(os.environ.get("SITE_DATA") or REPO_ROOT / "data/site.json")
    html_path = Path(os.environ.get("SITE_HTML") or REPO_ROOT / "index.html")

    data = json.loads(data_path.read_text(encoding="utf-8"))
    original = html_path.read_text(encoding="utf-8")
    new_text, warnings = render(original, data)
    for w in warnings:
        print(f"warn: {w}", file=sys.stderr)

    if args.check:
        if new_text != original:
            print("error: index.html is out of sync with data/site.json — "
                  "run `python3 scripts/sync-site.py`", file=sys.stderr)
            return 1
        print("index.html is in sync.")
        return 0

    if new_text != original:
        html_path.write_text(new_text, encoding="utf-8")
        print(f"updated {html_path.relative_to(REPO_ROOT)}")
    else:
        print("index.html already in sync — no change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
