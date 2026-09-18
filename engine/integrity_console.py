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
:root{color-scheme:dark;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--color-surface:#101313;--color-elevated:#171b19;--color-text:#e8eaed;--color-muted:#9099a6;--color-border:#2e3140;--color-healthy:#5fd68a;--color-warning:#e6b94f;--color-critical:#f07b7b;--color-focus:#9ec5ff;--spacing-4:4px;--spacing-8:8px;--spacing-12:12px;--spacing-16:16px;--spacing-24:24px;--spacing-32:32px;--radius-8:8px;--radius-10:10px;--radius-12:12px;--border-width-default:1px;--border-width-status-rail:6px;background:var(--color-surface);color:var(--color-text)}
*{box-sizing:border-box}
body{margin:0;padding:var(--spacing-32);background:var(--color-surface);color:var(--color-text);font-size:16px;line-height:1.5}
main{max-width:980px;margin:0 auto;overflow-wrap:anywhere}
.page-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-24);margin-bottom:var(--spacing-24)}
h1{font-size:26px;line-height:32px;margin:0 0 var(--spacing-4)}
h2{font-size:16px;line-height:24px;margin:0 0 var(--spacing-12)}
p{margin:0;color:var(--color-muted)}
.status-summary{display:grid;grid-template-columns:40px minmax(0,1fr);gap:var(--spacing-16);align-items:center;border:var(--border-width-default) solid var(--color-border);border-left:var(--border-width-status-rail) solid var(--color-warning);border-radius:var(--radius-12);padding:var(--spacing-24);margin-bottom:var(--spacing-24);background:var(--color-elevated)}
.status-summary.green{border-left-color:var(--color-healthy)}
.status-summary.red,.status-summary.unknown{border-left-color:var(--color-critical)}
.status-icon{display:grid;place-items:center;width:40px;height:40px;border:var(--border-width-default) solid currentColor;border-radius:50%;color:var(--color-warning);font-size:22px;font-weight:700}
.status-summary.green .status-icon{color:var(--color-healthy)}
.status-summary.red .status-icon,.status-summary.unknown .status-icon{color:var(--color-critical)}
.status{font-size:28px;line-height:34px;font-weight:800;margin:0 0 var(--spacing-4)}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--spacing-12);margin-bottom:var(--spacing-24)}
.card{border:var(--border-width-default) solid var(--color-border);border-radius:var(--radius-10);padding:var(--spacing-16);background:var(--color-elevated)}
.metric-label{color:var(--color-muted);font-size:13px;line-height:18px;font-weight:600}
.metric{font-size:28px;line-height:34px;font-weight:800;margin-top:var(--spacing-4)}
.action-form{display:grid;gap:var(--spacing-8);margin:0 0 var(--spacing-24)}
button{min-height:48px;min-width:127px;padding:var(--spacing-12) var(--spacing-16);border:var(--border-width-default) solid var(--color-border);border-radius:var(--radius-8);background:var(--color-text);color:var(--color-surface);font:inherit;font-weight:700;cursor:pointer}
button:focus-visible{outline:3px solid var(--color-focus);outline-offset:3px}
.action-help{font-size:13px;line-height:18px}
.notice{border:var(--border-width-default) solid var(--color-border);border-radius:var(--radius-10);padding:var(--spacing-16);margin:var(--spacing-24) 0 0;background:var(--color-elevated)}
.notice h2{margin-bottom:var(--spacing-8)}
code{display:block;margin-top:var(--spacing-8);padding:var(--spacing-12);border-radius:var(--radius-8);background:var(--color-surface);color:var(--color-text);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:normal}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:10px 8px;border-bottom:var(--border-width-default) solid var(--color-border);vertical-align:top}
th{color:var(--color-muted);font-weight:600}
.severity{font-weight:700;text-transform:uppercase}
.severity.green{color:var(--color-healthy)}.severity.degraded{color:var(--color-warning)}.severity.red,.severity.unknown{color:var(--color-critical)}
.history{margin-top:var(--spacing-24)}
.muted{color:var(--color-muted);font-size:13px}
@media (max-width:520px){body{padding:var(--spacing-16)}.page-header{display:block}.status-summary{grid-template-columns:40px minmax(0,1fr);padding:var(--spacing-16)}.metrics{grid-template-columns:1fr}.action-form button{width:100%;min-height:44px}table,thead,tbody,tr,th,td{display:block}thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}tr{padding:var(--spacing-8) 0;border-bottom:var(--border-width-default) solid var(--color-border)}td{display:grid;grid-template-columns:minmax(92px,35%) minmax(0,1fr);gap:var(--spacing-8);border:0;padding:var(--spacing-4) 0}td::before{content:attr(data-label);color:var(--color-muted);font-weight:600}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important}}
""".strip()

_RESTART_COMMAND = "awa-engine integrity console --serve --open"
_ACTION_HELP = "Checks may take a moment; this page returns when complete."


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


def _render_status_icon(state: str) -> str:
    glyph = "✓" if state == "green" else "?" if state == "no-status" else "!"
    return (
        '<span class="status-icon" data-component="StatusIcon" '
        f'aria-hidden="true">{glyph}</span>'
    )


def _render_status_summary(
    *,
    state: str,
    heading: object,
    supporting_copy: object,
    fresh_until: object | None = None,
) -> str:
    safe_state = html.escape(str(state), quote=True)
    detail = (
        '<p class="freshness">Checked <span id="checked-age">0s ago</span>'
        f" · Fresh until {html.escape(str(fresh_until))}</p>"
        if fresh_until is not None
        else f"<p>{html.escape(str(supporting_copy))}</p>"
    )
    return (
        f'<section class="status-summary {safe_state}" '
        'data-component="StatusSummary" aria-labelledby="overall-status">'
        f"{_render_status_icon(state)}"
        '<div class="status-content">'
        f'<h2 class="status" id="overall-status">{html.escape(str(heading))}</h2>'
        f"{detail}"
        "</div></section>"
    )


def _render_action_form() -> str:
    return (
        '<div class="action-form" data-component="ActionForm">'
        '<form method="post" action="run-checks-now">'
        '<button type="submit">Run checks now</button>'
        "</form>"
        f'<p class="action-help" id="action-help">{_ACTION_HELP}</p>'
        "</div>"
    )


def _render_metric_card(label: object, value: object) -> str:
    return (
        '<article class="card metric-card" data-component="MetricCard">'
        f'<div class="metric-label">{html.escape(str(label))}</div>'
        f'<div class="metric">{html.escape(str(value))}</div>'
        "</article>"
    )


def _render_notice() -> str:
    return (
        '<aside class="notice" data-component="Notice" aria-labelledby="idle-title">'
        '<h2 id="idle-title">This console closes after 5 minutes idle</h2>'
        "<p>Restart the console with:</p>"
        f"<code>{_RESTART_COMMAND}</code>"
        "</aside>"
    )


def _render_page(
    *,
    title: str,
    subtitle: str,
    content: str,
    served: bool,
    csp: str | None = None,
    data_attributes: str = "",
    clock_script: bool = False,
) -> str:
    csp_meta = (
        '<meta http-equiv="Content-Security-Policy" '
        f'content="{html.escape(csp, quote=True)}">'
        if csp is not None
        else ""
    )
    script = f"<script>{_CLOCK_SCRIPT}</script>" if clock_script else ""
    notice = _render_notice() if served else ""
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="dark">'
        f"{csp_meta}<title>{html.escape(title)}</title>"
        f"<style>{_STYLE}</style></head><body>"
        f'<main{data_attributes}><header class="page-header"><div>'
        "<h1>AWA integrity</h1>"
        f"<p>{html.escape(subtitle)}</p></div></header>"
        f"{content}{notice}{script}</main></body></html>\n"
    )


def render_no_status() -> str:
    """Render a token-free served-only first-run recovery page."""
    content = (
        _render_status_summary(
            state="no-status",
            heading="No status yet",
            supporting_copy=(
                "Run checks now to create the first private integrity status."
            ),
        )
        + _render_action_form()
    )
    return _render_page(
        title="AWA integrity — No status yet",
        subtitle="Private console",
        content=content,
        served=True,
    )


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
        f'<td data-label="Invariant">{html.escape(item["id"])}</td>'
        f'<td data-label="Severity" class="severity {html.escape(item["severity"])}">'
        f"{html.escape(item['severity'])}</td>"
        f'<td data-label="Reason">{html.escape(item["redacted_reason"])}</td>'
        "</tr>"
        for item in model["invariants"]
    )
    history = "".join(
        "<tr>"
        f'<td data-label="Generation">{item["generation"]}</td>'
        f'<td data-label="Overall" class="severity {html.escape(item["overall"])}">'
        f"{html.escape(item['overall'])}</td>"
        f'<td data-label="Generated">{html.escape(item.get("generated_at") or "unknown")}</td>'
        "</tr>"
        for item in model["recent_history"]
    )
    orphans = model["orphans"]
    recovery = model["recovery"]
    served = serve_action is not None
    heading = "AWA is healthy" if overall == "green" else overall.upper()
    summary = _render_status_summary(
        state=overall,
        heading=heading,
        supporting_copy="",
        fresh_until=fresh_until or "unknown",
    )
    metrics = (
        '<section class="metrics" aria-label="Integrity counts">'
        f"{_render_metric_card('Worktrees', orphans['worktrees'])}"
        f"{_render_metric_card('Unreconciled leases', orphans['leases_unreconciled'])}"
        f"{_render_metric_card('Dangling sessions', orphans['sessions_dangling'])}"
        f"{_render_metric_card('Recovery repairs', recovery['needs_repair'])}"
        "</section>"
    )
    action_form = _render_action_form() if served else ""
    content = (
        f"{summary}{metrics}{action_form}"
        '<section class="card"><h2>Invariants</h2><table>'
        "<thead><tr><th>Invariant</th><th>Severity</th><th>Reason</th></tr></thead>"
        f"<tbody>{invariants}</tbody></table></section>"
        '<section class="card history"><h2>Recent history</h2><table>'
        "<thead><tr><th>Generation</th><th>Overall</th><th>Generated</th></tr></thead>"
        f"<tbody>{history}</tbody></table></section>"
        f'<pre id="projection-data" hidden>{_json_embed(model)}</pre>'
    )
    data_attributes = (
        f' id="integrity" data-effective-overall="{html.escape(overall)}" '
        f"data-generated-at=\"{html.escape(generated_at, quote=True)}\" "
        f'data-fresh-until="{html.escape(fresh_until, quote=True)}"'
    )
    subtitle = (
        f"{'Private console' if served else 'Private snapshot'}"
        f" · generation {model['generation']}"
    )
    return _render_page(
        title=f"AWA integrity — {overall.upper()}",
        subtitle=subtitle,
        content=content,
        served=served,
        csp=csp,
        data_attributes=data_attributes,
        clock_script=True,
    )
