"""Deterministic, self-contained private HTML console for AWA integrity."""

from __future__ import annotations

import base64
import hashlib
import html
import json
from typing import Any
from urllib.parse import urlsplit

from . import integrity


_CLOCK_SCRIPT = """(()=>{"use strict";const root=document.getElementById("integrity");const status=document.getElementById("overall-status");const age=document.getElementById("checked-age");const generated=Date.parse(root.dataset.generatedAt||"");const fresh=Date.parse(root.dataset.freshUntil||"");const now=Date.now();if(Number.isFinite(generated)){age.textContent=String(Math.max(0,Math.floor((now-generated)/1000)))+"s ago";}else{age.textContent="unknown";}if(!Number.isFinite(fresh)||now>fresh){root.dataset.effectiveOverall="red";status.textContent="STALE / RED";document.title="AWA integrity — STALE / RED";}})();"""

_STYLE = """
:root{color-scheme:dark;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#101313;color:#f5f7f6}
*{box-sizing:border-box}
body{margin:0;padding:32px;background:#101313}
main{max-width:980px;margin:0 auto}
header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:24px}
h1{font-size:26px;line-height:1.2;margin:0 0 6px}
h2{font-size:16px;margin:0 0 12px}
p{margin:0;color:#b8c1bd}
.verdict{border:1px solid #38413d;border-left:6px solid #b98500;border-radius:12px;padding:20px;margin-bottom:18px;background:#171b19}
[data-effective-overall="green"] .verdict{border-left-color:#3da66f}
[data-effective-overall="red"] .verdict{border-left-color:#e25858}
.status{font-size:28px;font-weight:750;letter-spacing:.02em;margin-bottom:7px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin-bottom:18px}
.card{border:1px solid #303936;border-radius:10px;padding:16px;background:#171b19}
.metric{font-size:24px;font-weight:700;margin-top:8px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #303936;vertical-align:top}
th{color:#b8c1bd;font-weight:600}
.severity{font-weight:700;text-transform:uppercase}
.green{color:#73cf9c}.degraded{color:#e6b94f}.red,.unknown{color:#f07b7b}
.history{margin-top:18px}
.muted{color:#8e9994;font-size:13px}
""".strip()


def _csp_hash(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def _closed_projection(projection: dict) -> dict:
    if not isinstance(projection, dict):
        raise TypeError("integrity projection must be a dict")
    if projection.get("schema") != integrity.PUBLIC_SCHEMA:
        raise ValueError("unexpected integrity projection schema")
    candidate = {
        "generation": projection.get("generation"),
        "generated_at": projection.get("generated_at"),
        "overall": projection.get("overall"),
        "invariants": [
            {
                "id": item.get("id"),
                "severity": item.get("severity"),
            }
            for item in projection.get("invariants", [])
            if isinstance(item, dict)
        ],
        "orphans": projection.get("orphans"),
        "recovery": projection.get("recovery"),
        "fresh_until": projection.get("fresh_until"),
        "_recent_history": projection.get("recent_history"),
    }
    return integrity.public_projection(candidate)


def _json_embed(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    for raw, escaped in (
        ("&", "\\u0026"),
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ):
        encoded = encoded.replace(raw, escaped)
    return encoded


def clock_state(
    projection: dict,
    *,
    now_epoch: float,
) -> dict[str, Any]:
    """Pure mirror of the page's clock-only stale presentation."""
    model = _closed_projection(projection)
    generated = integrity._parse_iso(model.get("generated_at"))
    fresh = integrity._parse_iso(model.get("fresh_until"))
    stale = fresh is None or now_epoch > fresh
    age = (
        max(0, int(now_epoch - generated))
        if generated is not None
        else None
    )
    return {
        "stale": stale,
        "effective_overall": "red" if stale else model["overall"],
        "age_s": age,
    }


def _served_form_csp(action: str | None, form_action: str | None) -> str:
    if action is None and form_action is None:
        return "'none'"
    if action != "run-checks-now" or not isinstance(form_action, str):
        raise ValueError("invalid served console form action")
    parsed = urlsplit(form_action)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port is None
        or parsed.port < 1
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/")
        or not parsed.path.endswith("/run-checks-now")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid served console form CSP")
    return form_action


def _csp(form_action: str) -> str:
    script_hash = _csp_hash(_CLOCK_SCRIPT)
    style_hash = _csp_hash(_STYLE)
    return (
        "default-src 'none'; "
        f"script-src 'sha256-{script_hash}'; "
        f"style-src 'sha256-{style_hash}'; "
        "img-src 'none'; connect-src 'none'; font-src 'none'; "
        "object-src 'none'; media-src 'none'; frame-src 'none'; "
        f"base-uri 'none'; form-action {form_action}; frame-ancestors 'none'"
    )


def served_csp(form_action: str) -> str:
    """Return the exact CSP shared by the served page meta tag and header."""
    return _csp(_served_form_csp("run-checks-now", form_action))


def render(
    projection: dict,
    *,
    serve_action: str | None = None,
    served_form_action: str | None = None,
) -> str:
    """Render a byte-stable page from a closed public projection."""
    model = _closed_projection(projection)
    form_csp = _served_form_csp(serve_action, served_form_action)
    csp = _csp(form_csp)

    overall = model["overall"]
    generated_at = model.get("generated_at") or ""
    fresh_until = model.get("fresh_until") or ""
    invariants = "".join(
        "<tr>"
        f"<td>{html.escape(item['id'])}</td>"
        f"<td class=\"severity {html.escape(item['severity'])}\">"
        f"{html.escape(item['severity'])}</td>"
        f"<td>{html.escape(item['redacted_reason'])}</td>"
        "</tr>"
        for item in model["invariants"]
    )
    history = "".join(
        "<tr>"
        f"<td>{item['generation']}</td>"
        f"<td class=\"severity {html.escape(item['overall'])}\">"
        f"{html.escape(item['overall'])}</td>"
        f"<td>{html.escape(item.get('generated_at') or 'unknown')}</td>"
        "</tr>"
        for item in model["recent_history"]
    )
    orphans = model["orphans"]
    recovery = model["recovery"]
    form = (
        "<form method=\"post\" action=\"run-checks-now\">"
        "<button type=\"submit\">Run checks now</button></form>"
        if serve_action is not None
        else ""
    )

    return (
        "<!doctype html>\n"
        "<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"color-scheme\" content=\"dark\">"
        f"<meta http-equiv=\"Content-Security-Policy\" content=\"{html.escape(csp, quote=True)}\">"
        f"<title>AWA integrity — {html.escape(overall.upper())}</title>"
        f"<style>{_STYLE}</style></head>"
        f"<body><main id=\"integrity\" data-effective-overall=\"{html.escape(overall)}\" "
        f"data-generated-at=\"{html.escape(generated_at, quote=True)}\" "
        f"data-fresh-until=\"{html.escape(fresh_until, quote=True)}\">"
        "<header><div><h1>AWA integrity</h1>"
        f"<p>Private snapshot · generation {model['generation']}</p></div></header>{form}"
        "<section class=\"verdict\" aria-labelledby=\"overall-status\">"
        f"<div class=\"status\" id=\"overall-status\">{html.escape(overall.upper())}</div>"
        "<p>Last checked <span id=\"checked-age\">0s ago</span>"
        f" · fresh until {html.escape(fresh_until or 'unknown')}</p></section>"
        "<section class=\"grid\" aria-label=\"Integrity counts\">"
        f"<article class=\"card\"><h2>Worktrees</h2><div class=\"metric\">{orphans['worktrees']}</div></article>"
        f"<article class=\"card\"><h2>Unreconciled leases</h2><div class=\"metric\">{orphans['leases_unreconciled']}</div></article>"
        f"<article class=\"card\"><h2>Dangling sessions</h2><div class=\"metric\">{orphans['sessions_dangling']}</div></article>"
        f"<article class=\"card\"><h2>Recovery repairs</h2><div class=\"metric\">{recovery['needs_repair']}</div></article>"
        "</section>"
        "<section class=\"card\"><h2>Invariants</h2><table>"
        "<thead><tr><th>Invariant</th><th>Severity</th><th>Reason</th></tr></thead>"
        f"<tbody>{invariants}</tbody></table></section>"
        "<section class=\"card history\"><h2>Recent history</h2><table>"
        "<thead><tr><th>Generation</th><th>Overall</th><th>Generated</th></tr></thead>"
        f"<tbody>{history}</tbody></table></section>"
        f"<pre id=\"projection-data\" hidden>{_json_embed(model)}</pre>"
        f"<script>{_CLOCK_SCRIPT}</script>"
        "</main></body></html>\n"
    )
