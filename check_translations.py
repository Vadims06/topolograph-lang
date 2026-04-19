#!/usr/bin/env python3
"""
Translation coverage checker for Topolograph.

Two checks:
  1. JSON key gaps  — keys present in en/ but missing in other locales.
  2. HTML hardcoded text — visible text / translatable attributes in Jinja2
     templates that are NOT driven by a {{ ... }} expression and therefore
     bypass the i18n system entirely.

Usage (from repo root):
    python lang/check_translations.py

Optional env vars:
    LANG_PACK_PATH   – path to the lang/ directory  (default: auto-detected)
    TEMPLATES_PATH   – path to the Flask templates/ dir (default: auto-detected)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent          # lang/
REPO_ROOT   = SCRIPT_DIR.parent                       # topolograph/

LANG_PACK_PATH = Path(
    os.environ.get("LANG_PACK_PATH", SCRIPT_DIR)
)
TEMPLATES_PATH = Path(
    os.environ.get(
        "TEMPLATES_PATH",
        REPO_ROOT.parent
        / "topolograph-docker-internal"
        / "app" / "src" / "flask-visual" / "templates",
    )
)

# Locales to check against English.
NON_EN_LOCALES = ["ru", "zh", "es", "pt"]

# HTML files whose content is intentionally static / non-i18n
HTML_EXCLUDE = {
    "base.html",          # structural chrome – nav items use common.*
    "test.html",
    "500.html",
    "confidentiality_policy_v1.html",
}

# Inline Jinja2 patterns we should treat as "already translated"
JINJA2_VAR = re.compile(r"\{\{.+?\}\}")          # {{ … }}
JINJA2_BLOCK = re.compile(r"\{%.+?%\}", re.S)   # {% … %}

# Tags whose *text content* is never user-visible
SKIP_TAGS = {
    "script", "style", "head", "meta", "link", "title",
    "svg", "path", "defs", "symbol",
    # Code / preformatted blocks are content not suitable for i18n keys
    "code", "pre", "kbd", "samp", "var",
}

# Attributes that carry user-visible text
TRANSLATABLE_ATTRS = {"placeholder", "title", "aria-label", "alt", "value"}

# Minimum length a string must have to be flagged (filters out "." "+", …)
MIN_TEXT_LEN = 3

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten(obj: Any, prefix: str = "") -> Iterator[tuple[str, str]]:
    """Yield (dot_path, value) for every string leaf in a JSON tree."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            yield from _flatten(v, path)
    elif isinstance(obj, str):
        yield prefix, obj


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


_JINJA_PLACEHOLDER = "\x00JINJA\x00"

def _is_translatable(text: str) -> bool:
    """Return True if text looks like a human-readable string worth flagging."""
    t = text.strip()
    # Filter out our own Jinja replacement artifacts
    if _JINJA_PLACEHOLDER in t:
        return False
    if len(t) < MIN_TEXT_LEN:
        return False
    # Skip strings that are pure code / templates
    if JINJA2_VAR.search(t):
        return False
    # Skip URL-like strings
    if t.startswith(("http://", "https://", "/", "#", "{", "{")):
        return False
    # Must contain at least one letter
    if not re.search(r"[A-Za-z]", t):
        return False
    return True


# ---------------------------------------------------------------------------
# Part 1: JSON key gaps
# ---------------------------------------------------------------------------

def check_json_gaps(lang_root: Path) -> dict[str, dict[str, list[str]]]:
    """
    Returns {locale: {page_file: [missing_key, ...]}}
    for every key in en/ that is absent from another locale's file.
    """
    en_pages_dir = lang_root / "en" / "pages"
    en_common     = lang_root / "en" / "common.json"

    results: dict[str, dict[str, list[str]]] = {}

    for locale in NON_EN_LOCALES:
        locale_dir = lang_root / locale
        if not locale_dir.is_dir():
            continue
        gaps: dict[str, list[str]] = {}

        # common.json
        loc_common = locale_dir / "common.json"
        if loc_common.exists() and en_common.exists():
            en_keys  = set(k for k, _ in _flatten(_load_json(en_common)))
            loc_keys = set(k for k, _ in _flatten(_load_json(loc_common)))
            missing  = sorted(en_keys - loc_keys)
            if missing:
                gaps["common.json"] = missing

        # pages/*.json
        loc_pages_dir = locale_dir / "pages"
        for en_page in sorted(en_pages_dir.glob("*.json")):
            loc_page = loc_pages_dir / en_page.name
            if not loc_page.exists():
                en_keys = [k for k, _ in _flatten(_load_json(en_page))]
                gaps[f"pages/{en_page.name}"] = en_keys
                continue
            en_flat  = dict(_flatten(_load_json(en_page)))
            loc_flat = dict(_flatten(_load_json(loc_page)))
            missing  = sorted(set(en_flat) - set(loc_flat))
            if missing:
                gaps[f"pages/{en_page.name}"] = missing

        if gaps:
            results[locale] = gaps

    return results


# ---------------------------------------------------------------------------
# Part 2: HTML hardcoded text
# ---------------------------------------------------------------------------

try:
    from bs4 import BeautifulSoup, Comment, NavigableString, Tag

    def _parse_html(html: str) -> list[tuple[str, str]]:
        """
        Return [(kind, text)] for every hardcoded, user-visible string.
        kind is either 'text' or 'attr:<name>'.
        """
        # Replace Jinja2 blocks with a placeholder so BS4 doesn't choke on them
        html = JINJA2_BLOCK.sub(_JINJA_PLACEHOLDER, html)

        soup = BeautifulSoup(html, "html.parser")
        hits: list[tuple[str, str]] = []

        def _walk(tag: Tag) -> None:
            for child in tag.children:
                if isinstance(child, Comment):
                    continue
                if isinstance(child, NavigableString):
                    txt = str(child)
                    if _is_translatable(txt):
                        hits.append(("text", txt.strip()))
                elif isinstance(child, Tag):
                    if child.name in SKIP_TAGS:
                        continue
                    # Check translatable attributes
                    for attr in TRANSLATABLE_ATTRS:
                        val = child.get(attr, "")
                        if isinstance(val, list):
                            val = " ".join(val)
                        if _is_translatable(val):
                            hits.append((f"attr:{attr}", val.strip()))
                    _walk(child)

        _walk(soup)
        return hits

    HAS_BS4 = True

except ImportError:
    HAS_BS4 = False

    _TAG_RE       = re.compile(r"<[^>]+>")
    _ATTR_RE      = re.compile(
        r'(?:placeholder|title|aria-label|alt)\s*=\s*["\']([^"\']*)["\']',
        re.I,
    )

    def _parse_html(html: str) -> list[tuple[str, str]]:
        """Fallback regex-based extractor (less accurate than BS4)."""
        html = JINJA2_BLOCK.sub(" ", html)
        hits: list[tuple[str, str]] = []

        # Attribute values
        for m in _ATTR_RE.finditer(html):
            val = m.group(1).strip()
            if _is_translatable(val):
                hits.append((f"attr:{m.group(0).split('=')[0].strip()}", val))

        # Strip all tags, collect remaining text chunks
        text_only = _TAG_RE.sub(" ", html)
        for chunk in text_only.split("\n"):
            chunk = chunk.strip()
            if _is_translatable(chunk):
                hits.append(("text", chunk))

        return hits


def check_html_hardcoded(templates_dir: Path) -> dict[str, list[tuple[str, str]]]:
    """
    Returns {template_name: [(kind, text), ...]}
    for every hardcoded translatable string found.
    """
    results: dict[str, list[tuple[str, str]]] = {}

    for html_file in sorted(templates_dir.rglob("*.html")):
        name = html_file.relative_to(templates_dir).as_posix()
        if html_file.name in HTML_EXCLUDE:
            continue

        raw = html_file.read_text(encoding="utf-8", errors="replace")
        hits = _parse_html(raw)

        # De-duplicate while preserving order
        seen: set[tuple[str, str]] = set()
        unique: list[tuple[str, str]] = []
        for h in hits:
            if h not in seen:
                seen.add(h)
                unique.append(h)

        if unique:
            results[name] = unique

    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _sep(char: str = "─", width: int = 78) -> str:
    return char * width


def report(lang_root: Path, templates_dir: Path) -> int:
    """Print report to stdout; return exit code (0 = clean, 1 = issues found)."""
    issues = 0

    # ── Part 1: JSON key gaps ──────────────────────────────────────────────
    print(_sep("═"))
    print("PART 1 — JSON translation key gaps (keys in EN missing from locale)")
    print(_sep("═"))

    gaps = check_json_gaps(lang_root)
    if not gaps:
        print("  ✓ No key gaps detected across all locales.\n")
    else:
        issues += 1
        for locale, files in sorted(gaps.items()):
            print(f"\n  Locale: {locale}")
            print(_sep())
            for fname, keys in sorted(files.items()):
                print(f"    File: {fname}  ({len(keys)} missing keys)")
                for k in keys:
                    print(f"      – {k}")

    # ── Part 2: HTML hardcoded text ────────────────────────────────────────
    print()
    print(_sep("═"))
    bs4_note = "" if HAS_BS4 else "  [BeautifulSoup not available – using regex fallback]"
    print(f"PART 2 — Hardcoded text in HTML templates (bypasses i18n){bs4_note}")
    print(_sep("═"))

    if not templates_dir.is_dir():
        print(f"  ✗ Templates directory not found: {templates_dir}")
        issues += 1
    else:
        hardcoded = check_html_hardcoded(templates_dir)
        if not hardcoded:
            print("  ✓ No hardcoded translatable text detected.\n")
        else:
            issues += 1
            for tpl, hits in sorted(hardcoded.items()):
                print(f"\n  Template: {tpl}  ({len(hits)} items)")
                print(_sep())
                for kind, text in hits:
                    label = "TEXT" if kind == "text" else kind.upper().replace("ATTR:", "ATTR ")
                    short = text.replace("\n", " ")
                    if len(short) > 120:
                        short = short[:117] + "…"
                    print(f"    [{label}]  {short!r}")

    print()
    print(_sep("═"))
    if issues:
        print(f"  {issues} issue group(s) found. See details above.")
    else:
        print("  All checks passed.")
    print(_sep("═"))
    return 1 if issues else 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not LANG_PACK_PATH.is_dir():
        print(
            f"ERROR: lang pack not found at {LANG_PACK_PATH}.\n"
            "       Set LANG_PACK_PATH to your lang/ directory.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(report(LANG_PACK_PATH, TEMPLATES_PATH))
