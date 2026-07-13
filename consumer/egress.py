"""egress.py — AWA's router-INDEPENDENT banned-term matcher.

Loads AWA's `egress-terms.json` snapshot (shared Tier A + Tier B + AWA's Tier C) and scans PM-facing
text for banned terms, so AWA's own `make verify` proves zero jargon WITH THE ROUTER UNINSTALLED.
The matching logic MIRRORS the router's intent_router.catalog matcher exactly (word/phrase-bounded;
case-insensitive for naturally-lowercase terms; case-sensitive for all-caps acronyms like PR/MCP/
HEAD). consumer/tests/test_consumer_seam.py proves this mirror AGREES with the router's authoritative
matcher on a battery of strings, and that AWA's snapshot is a superset of the router's tiers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TERMS_FILE = _HERE / "egress-terms.json"

_pattern_cache: dict[str, re.Pattern] = {}
_terms_cache: frozenset | None = None


def load_terms() -> frozenset:
    """Composed Tier A + Tier B + AWA Tier C from egress-terms.json (read-only, cached)."""
    global _terms_cache
    if _terms_cache is not None:
        return _terms_cache
    data = json.loads(_TERMS_FILE.read_text(encoding="utf-8"))
    terms: set[str] = set()
    terms.update(data.get("tier_a_mechanism", []))
    terms.update(data.get("tier_b_git_workflow", []))
    terms.update(data.get("tier_c_awa", []))
    _terms_cache = frozenset(terms)
    return _terms_cache


def _is_case_sensitive_term(term: str) -> bool:
    """All-caps acronym (uppercase, no lowercase) -> match case-SENSITIVELY (PR/MCP/HEAD), so it
    does not collide with ordinary English. Everything else matches case-INsensitively."""
    return any(c.isupper() for c in term) and not any(c.islower() for c in term)


def _pattern_for(term: str) -> re.Pattern:
    cached = _pattern_cache.get(term)
    if cached is not None:
        return cached
    left = r"\b" if term[:1].isalnum() else ""
    right = r"\b" if term[-1:].isalnum() else ""
    flags = 0 if _is_case_sensitive_term(term) else re.IGNORECASE
    pat = re.compile(left + re.escape(term) + right, flags)
    _pattern_cache[term] = pat
    return pat


def find_banned_terms(text: str, terms: frozenset | None = None) -> list[str]:
    """Return the banned terms present in `text` (sorted, deduped)."""
    if not text:
        return []
    terms = terms if terms is not None else load_terms()
    return sorted({t for t in terms if _pattern_for(t).search(text)})


def _walk_strings(obj, prefix=""):
    """Yield (path, text) for every string in a nested JSON-like structure."""
    if isinstance(obj, str):
        yield (prefix or "<root>", obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_strings(v, f"{prefix}[{i}]")


# Catalog keys that are documentation-only (not PM-facing / not proposal-bound) and therefore out of
# egress scope — they may describe the mechanism for maintainers.
_CATALOG_DOC_KEYS = {"_doc", "schema", "consumer"}


def scan_catalog(catalog: dict) -> list[str]:
    """Scan a catalog's PM-facing / proposal-bound strings for banned terms. Mirrors the router's
    _egress_strings coverage (verb, plain_label, consequence_copy, aliases, examples,
    start_point_rules values, param names) plus the `outcomes` copy. Doc-only keys are skipped.
    Returns a list of 'path: [hits]' offenders (empty = clean)."""
    terms = load_terms()
    offenders: list[str] = []
    for entry in catalog.get("verbs", []) or []:
        if not isinstance(entry, dict):
            continue
        for field in ("verb", "plain_label", "consequence_copy"):
            for hit_path, text in _walk_strings(entry.get(field, ""), field):
                hits = find_banned_terms(text, terms)
                if hits:
                    offenders.append(f"verb={entry.get('verb')!r} {hit_path}: {hits}")
        for field in ("aliases", "examples", "preconditions", "start_point_rules"):
            for hit_path, text in _walk_strings(entry.get(field, []), field):
                hits = find_banned_terms(text, terms)
                if hits:
                    offenders.append(f"verb={entry.get('verb')!r} {hit_path}: {hits}")
        for p in entry.get("param_schema", []) or []:
            if isinstance(p, dict) and isinstance(p.get("name"), str):
                hits = find_banned_terms(p["name"], terms)
                if hits:
                    offenders.append(f"verb={entry.get('verb')!r} param={p['name']!r}: {hits}")
    # outcomes copy (PM-facing summary)
    for hit_path, text in _walk_strings(catalog.get("outcomes", []), "outcomes"):
        hits = find_banned_terms(text, terms)
        if hits:
            offenders.append(f"{hit_path}: {hits}")
    return offenders


def scan_object(obj) -> list[str]:
    """Scan every string in an arbitrary nested structure (used for translator/loop output). Returns
    'path: [hits]' offenders."""
    terms = load_terms()
    offenders: list[str] = []
    for path, text in _walk_strings(obj):
        hits = find_banned_terms(text, terms)
        if hits:
            offenders.append(f"{path}: {hits}")
    return offenders


def scan_finish_warning(text: str) -> list[str]:
    """Narrow exception for the immutable finish warning plus escaped Phase-1 data rows.

    No other PM surface receives this exception. Import is local to avoid making the general
    matcher depend on the finish surface.
    """
    try:
        from .finish_current import WARNING_STATIC
    except ImportError:
        return ["<root>: finish warning template unavailable"]
    prefix = WARNING_STATIC + "\n"
    if not isinstance(text, str) or not text.startswith(prefix):
        return scan_object(text)
    rows = text[len(prefix):]
    if rows == "None | No operator work will be deleted.":
        return []
    lines = rows.splitlines()
    if not lines or any(not re.match(rf"^{idx}\. .+ \| .+$", line)
                        for idx, line in enumerate(lines, 1)):
        return ["<root>: malformed finish warning rows"]
    return []
