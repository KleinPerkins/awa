"""Deterministic, self-contained private HTML console for AWA integrity."""

from __future__ import annotations

import base64
import hashlib
import html
import json
from typing import Any
from urllib.parse import urlsplit

from . import integrity


_CLOCK_SCRIPT = """(()=>{"use strict";const root=document.getElementById("integrity");const status=document.getElementById("overall-status");const detail=document.getElementById("overall-detail");const icon=document.querySelector("[data-component=StatusIcon]");const age=document.getElementById("checked-age");const generated=Date.parse(root.dataset.generatedAt||"");const fresh=Date.parse(root.dataset.freshUntil||"");const now=Date.now();if(age){if(Number.isFinite(generated)){age.textContent=String(Math.max(0,Math.floor((now-generated)/1000)))+"s ago";}else{age.textContent="unknown";}}if(!Number.isFinite(fresh)||now>fresh){root.dataset.effectiveOverall="red";icon.textContent="ⓘ";status.textContent="Status is stale / critical";detail.textContent="The previous result has expired. A new check is required before relying on this status.";document.title="AWA integrity — Status is stale / critical";}})();"""

_STYLE = """
:root{color-scheme:dark;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--color-surface:#101313;--color-elevated:#171b19;--color-text:#e8eaed;--color-muted:#9099a6;--color-border:#2e3140;--color-healthy:#5fd68a;--color-warning:#fbbc04;--color-critical:#f28b82;--color-focus:#9ec5ff;--spacing-4:4px;--spacing-8:8px;--spacing-12:12px;--spacing-16:16px;--spacing-24:24px;--spacing-32:32px;--radius-8:8px;--radius-10:10px;--radius-12:12px;--border-width-default:1px;--border-width-status-rail:6px;background:var(--color-surface);color:var(--color-text)}
*{box-sizing:border-box}
body{margin:0;padding:var(--spacing-32);background:var(--color-surface);color:var(--color-text);font-size:16px;line-height:1.5}
main{max-width:980px;margin:0 auto;overflow-wrap:anywhere}
.page-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-24);margin-bottom:var(--spacing-24)}
h1{font-size:26px;line-height:32px;margin:0 0 var(--spacing-4)}
h2{font-size:16px;line-height:24px;margin:0 0 var(--spacing-12)}
p{margin:0;color:var(--color-muted)}
.status-summary{display:grid;grid-template-columns:40px minmax(0,1fr);gap:var(--spacing-12);align-items:center;min-height:260px;border:var(--border-width-default) solid var(--color-border);border-left:var(--border-width-status-rail) solid var(--color-muted);border-radius:var(--radius-12);padding:var(--spacing-16);margin-bottom:var(--spacing-24);background:var(--color-elevated)}
[data-effective-overall="green"] .status-summary{border-left-color:var(--color-healthy)}
[data-effective-overall="degraded"] .status-summary,[data-effective-overall="yellow"] .status-summary{border-left-color:var(--color-warning)}
[data-effective-overall="red"] .status-summary,[data-effective-overall="unknown"] .status-summary{border-left-color:var(--color-critical)}
.status-icon{display:grid;place-items:center;width:40px;height:40px;border:var(--border-width-default) solid currentColor;border-radius:50%;color:var(--color-muted);font-size:22px;font-weight:700}
[data-effective-overall="green"] .status-icon{color:var(--color-healthy)}
[data-effective-overall="degraded"] .status-icon,[data-effective-overall="yellow"] .status-icon{border:0;border-radius:0;color:var(--color-surface);background:var(--color-warning)}
[data-effective-overall="red"] .status-icon,[data-effective-overall="unknown"] .status-icon{border:0;border-radius:0;color:var(--color-surface);background:var(--color-critical)}
.status{font-size:28px;line-height:34px;font-weight:800;margin:0 0 var(--spacing-4)}
[data-effective-overall="green"] .status{color:var(--color-healthy)}
[data-effective-overall="degraded"] .status,[data-effective-overall="yellow"] .status{color:var(--color-warning)}
[data-effective-overall="red"] .status,[data-effective-overall="unknown"] .status{color:var(--color-critical)}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--spacing-16);margin-bottom:var(--spacing-24)}
.card{min-height:88px;border:var(--border-width-default) solid var(--color-border);border-radius:var(--radius-10);padding:14px var(--spacing-16);background:var(--color-elevated)}
.metric-label{color:var(--color-muted);font-size:13px;line-height:18px;font-weight:600}
.metric{font-size:28px;line-height:34px;font-weight:800;margin-top:var(--spacing-4)}
.action-form{display:grid;gap:var(--spacing-12);margin:0 0 var(--spacing-24)}
.action-form form{padding:var(--spacing-16);border:var(--border-width-default) solid var(--color-border);border-radius:var(--radius-12);background:var(--color-surface)}
button{width:100%;min-height:48px;padding:var(--spacing-12) var(--spacing-16);border:var(--border-width-default) solid var(--color-border);border-radius:var(--radius-10);background:var(--color-elevated);color:var(--color-text);font:inherit;font-size:13px;line-height:18px;font-weight:700;cursor:pointer}
button:focus-visible{outline:none;border-color:var(--color-focus)}
.action-help{font-size:16px;line-height:24px}
.notice{display:flex;flex-direction:column;gap:var(--spacing-12);min-height:200px;border:var(--border-width-default) solid var(--color-border);border-radius:var(--radius-12);padding:var(--spacing-16);margin:var(--spacing-24) 0 0;background:var(--color-elevated)}
.notice-fatal{min-height:240px}
.notice h2{margin:0}
code{display:block;padding:var(--spacing-12);border:var(--border-width-default) solid var(--color-border);border-radius:var(--radius-8);background:var(--color-surface);color:var(--color-text);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:normal}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:10px 8px;border-bottom:var(--border-width-default) solid var(--color-border);vertical-align:top}
th{color:var(--color-muted);font-weight:600}
.severity{font-weight:700;text-transform:uppercase}
.severity.green{color:var(--color-healthy)}.severity.degraded{color:var(--color-warning)}.severity.red,.severity.unknown{color:var(--color-critical)}
.history{margin-top:var(--spacing-24)}
.muted{color:var(--color-muted);font-size:13px}
@media (max-width:520px){body{padding:var(--spacing-8)}.page-header{display:block}.metrics{grid-template-columns:1fr;gap:var(--spacing-12)}table,thead,tbody,tr,th,td{display:block}thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}tr{padding:var(--spacing-8) 0;border-bottom:var(--border-width-default) solid var(--color-border)}td{display:grid;grid-template-columns:minmax(92px,35%) minmax(0,1fr);gap:var(--spacing-8);border:0;padding:var(--spacing-4) 0}td::before{content:attr(data-label);color:var(--color-muted);font-weight:600}}
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
        "worktrees": projection.get("worktrees"),
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
    glyph = "✓" if state == "green" else "ⓘ"
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
    detail = (
        '<p class="freshness" id="overall-detail">Checked '
        '<span id="checked-age">0s ago</span>'
        f" · Fresh until {html.escape(str(fresh_until))}</p>"
        if fresh_until is not None
        else (
            f'<p id="overall-detail">{html.escape(str(supporting_copy))}</p>'
        )
    )
    return (
        '<section class="status-summary" '
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
        '<button type="submit" aria-describedby="action-help">Run checks now</button>'
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


def _render_notice(kind: str = "idle") -> str:
    if kind == "fatal":
        return (
            '<aside class="notice notice-fatal" data-component="Notice" '
            'aria-labelledby="recovery-title">'
            '<h2 id="recovery-title">'
            "Restart the console, then run checks again.</h2>"
            "<p>The check did not complete. "
            "This private console has stopped.</p>"
            f"<code>{_RESTART_COMMAND}</code>"
            "</aside>"
        )
    if kind != "idle":
        raise ValueError("unknown notice kind")
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


def render_fatal_check_failure() -> str:
    """Render the token-free fatal page shown before server shutdown."""
    content = (
        _render_status_summary(
            state="red",
            heading="Checks could not complete",
            supporting_copy=(
                "The integrity evaluator or status commit failed. "
                "No check action remains on this stopped console."
            ),
        )
        + _render_notice("fatal")
    )
    return _render_page(
        title="AWA integrity — Checks could not complete",
        subtitle="Private console",
        content=content,
        served=False,
        csp=_csp("'none'"),
        data_attributes=' data-effective-overall="red"',
    )


def render_status_unavailable(
    served_form_action: str | None = None,
) -> str:
    """Render a recoverable, token-free unavailable-status page."""
    csp = (
        served_csp(served_form_action)
        if served_form_action is not None
        else _csp("'none'")
    )
    content = (
        _render_status_summary(
            state="degraded",
            heading="Status cannot be read",
            supporting_copy=(
                "The saved status is unavailable or corrupt. "
                "Run checks now to recover in this console."
            ),
        )
        + _render_action_form()
    )
    return _render_page(
        title="AWA integrity — Status cannot be read",
        subtitle="Private console",
        content=content,
        served=True,
        csp=csp,
        data_attributes=' data-effective-overall="yellow"',
    )


def error_csp() -> str:
    """Return the CSP for fatal token-free HTML responses."""
    return _csp("'none'")


def _affected_invariant(model: dict) -> str:
    return (
        integrity.reduction_driver(model["invariants"], model["overall"])
        or "integrity status"
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
    worktrees = model["worktrees"]
    served = serve_action is not None
    if overall == "green":
        heading = "AWA is healthy" if served else "Private snapshot"
        supporting_copy = (
            ""
            if served
            else (
                "Saved integrity status. This action-free snapshot can "
                "become critical when freshness expires."
            )
        )
        summary_fresh_until = (fresh_until or "unknown") if served else None
    elif overall == "degraded":
        heading = "AWA needs attention"
        supporting_copy = (
            "A check needs attention. Technical id: "
            f"{_affected_invariant(model)}. "
            "Run checks again to refresh this private status."
        )
        summary_fresh_until = None
    else:
        heading = "AWA needs immediate attention"
        supporting_copy = (
            "A critical integrity check failed. Technical id: "
            f"{_affected_invariant(model)}. "
            "Run checks again before continuing."
        )
        summary_fresh_until = None
    summary = _render_status_summary(
        state=overall,
        heading=heading,
        supporting_copy=supporting_copy,
        fresh_until=summary_fresh_until,
    )
    metric_value = (
        (lambda key: worktrees[key])
        if worktrees["checked"]
        else (lambda _key: "Not checked")
    )
    metrics = (
        '<section class="metrics" aria-label="Integrity counts">'
        f"{_render_metric_card('Linked worktrees', metric_value('discovered_linked'))}"
        f"{_render_metric_card('AWA-managed', metric_value('managed'))}"
        f"{_render_metric_card('Active', metric_value('active'))}"
        f"{_render_metric_card('Problems', metric_value('problems'))}"
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
        title=f"AWA integrity — {heading}",
        subtitle=subtitle,
        content=content,
        served=served,
        csp=csp,
        data_attributes=data_attributes,
        clock_script=True,
    )
