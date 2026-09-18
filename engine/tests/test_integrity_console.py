"""M1-B.3: deterministic private static console and install boundary."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import html
import io
import json
import os
import re
import stat
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from engine import cli, integrity, integrity_console, paths
from engine.tests.helpers import EngineTestCase


_ROOT = Path(__file__).resolve().parents[2]
_INSTALL = _ROOT / "install.sh"


class TestIntegrityConsole(EngineTestCase):
    def _projection(self, **overrides) -> dict:
        value = {
            "schema": integrity.PUBLIC_SCHEMA,
            "generation": 7,
            "generated_at": "2026-08-25T00:00:00Z",
            "overall": "degraded",
            "invariants": [
                {
                    "id": "guard_safety",
                    "severity": "green",
                    "redacted_reason": "guard_safety is green",
                },
                {
                    "id": "surveillance_freshness",
                    "severity": "degraded",
                    "redacted_reason": "surveillance_freshness is degraded",
                },
                *[
                    {
                        "id": invariant_id,
                        "severity": "green",
                        "redacted_reason": f"{invariant_id} is green",
                    }
                    for invariant_id, (_, required, _safety, _profiles)
                    in integrity.REGISTRY.items()
                    if required
                    and invariant_id
                    not in {"guard_safety", "surveillance_freshness"}
                ],
            ],
            "orphans": {
                "worktrees": 2,
                "leases_unreconciled": 1,
                "sessions_dangling": 0,
                "husks": 0,
            },
            "recovery": {
                "last_status": "ok",
                "needs_repair": 0,
                "quarantine_count": 0,
            },
            "recent_history": [
                {
                    "generation": 6,
                    "overall": "green",
                    "generated_at": "2026-08-24T18:00:00Z",
                },
                {
                    "generation": 7,
                    "overall": "degraded",
                    "generated_at": "2026-08-25T00:00:00Z",
                },
            ],
            "last_checked_age_s": 0,
            "fresh_until": "2026-08-26T00:00:00Z",
        }
        value.update(overrides)
        return value

    def _script_and_csp(self, page: str) -> tuple[str, str]:
        script_matches = re.findall(
            r"<script>(.*?)</script>",
            page,
            flags=re.DOTALL,
        )
        self.assertEqual(len(script_matches), 1)
        csp_match = re.search(
            r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">',
            page,
        )
        self.assertIsNotNone(csp_match)
        return script_matches[0], html.unescape(csp_match.group(1))

    def _reduced_projection(
        self,
        severities: dict[str, str],
        *,
        fresh: bool = True,
        reverse_input: bool = False,
    ) -> dict:
        invariant_ids = [
            invariant_id
            for invariant_id, (_, required, _safety, _profiles)
            in integrity.REGISTRY.items()
            if required
        ]
        if reverse_input:
            invariant_ids.reverse()
        invariants = [
            {
                "id": invariant_id,
                "severity": severities.get(invariant_id, "green"),
                "redacted_reason": (
                    f"{invariant_id} is "
                    f"{severities.get(invariant_id, 'green')}"
                ),
            }
            for invariant_id in invariant_ids
        ]
        triggers = {
            "launchd": {
                "last_success": (
                    integrity._now_iso()
                    if fresh
                    else "2020-01-01T00:00:00Z"
                ),
            },
        }
        return self._projection(
            overall=integrity.reduce(invariants, triggers),
            invariants=invariants,
        )

    def _status(self) -> dict:
        generated = integrity._now_iso()
        fresh = integrity._iso_at(time.time() + 3600)
        return {
            "overall": "green",
            "generated_at": generated,
            "invariants": [
                {
                    "id": "guard_safety",
                    "severity": "green",
                    "evidence": "safe",
                    "checked_at": generated,
                    "profile": "deep",
                }
            ],
            "triggers": {
                "launchd": {
                    "last_attempt": generated,
                    "last_success": generated,
                    "last_error": None,
                    "generation": 1,
                }
            },
            "orphans": {
                "worktrees": 0,
                "leases_unreconciled": 0,
                "sessions_dangling": 0,
                "husks": 0,
            },
            "recovery": {
                "last_status": "ok",
                "needs_repair": 0,
                "quarantine_count": 0,
            },
            "alert": {
                "last_transition": None,
                "attempted": [],
                "delivered": {
                    "native": "accepted",
                    "slack": "opted_out",
                },
            },
            "fresh_until": fresh,
        }

    def test_render_deterministic(self):
        first = integrity_console.render(self._projection())
        second = integrity_console.render(
            json.loads(json.dumps(self._projection()))
        )
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("<!doctype html>"))
        self.assertTrue(first.endswith("\n"))

    def test_semantic_token_and_responsive_contract(self):
        page = integrity_console.render(self._projection())
        for token in (
            "--color-surface:",
            "--color-elevated:",
            "--color-text:",
            "--color-muted:",
            "--color-border:",
            "--color-healthy:",
            "--color-warning:",
            "--color-critical:",
            "--color-focus:",
            "--spacing-4:",
            "--spacing-8:",
            "--spacing-12:",
            "--spacing-16:",
            "--spacing-24:",
            "--spacing-32:",
            "--radius-8:",
            "--radius-10:",
            "--radius-12:",
            "--border-width-default:",
            "--border-width-status-rail:",
        ):
            self.assertIn(token, page)
        self.assertIn("@media (max-width:520px)", page)
        self.assertIn("overflow-wrap:anywhere", page)
        self.assertIn("min-height:44px", page)
        self.assertIn(":focus-visible", page)
        self.assertIn("@media (prefers-reduced-motion:reduce)", page)
        self.assertNotIn("@keyframes", page)

    def test_approved_m32c_responsive_geometry_contract(self):
        page = integrity_console.render(
            self._projection(overall="degraded"),
            serve_action="run-checks-now",
            served_form_action=(
                "http://127.0.0.1:54321/synthetic-token/run-checks-now"
            ),
        )
        self.assertIn(
            ".status-summary{display:grid;"
            "grid-template-columns:40px minmax(0,1fr);"
            "gap:var(--spacing-12);align-items:center;"
            "min-height:260px;",
            page,
        )
        self.assertIn(
            "padding:var(--spacing-16);"
            "margin-bottom:var(--spacing-24);"
            "background:var(--color-elevated)}",
            page,
        )
        self.assertIn(
            ".metrics{display:grid;"
            "grid-template-columns:repeat(4,minmax(0,1fr));"
            "gap:var(--spacing-16);",
            page,
        )
        self.assertIn(
            ".card{min-height:88px;"
            "border:var(--border-width-default) solid var(--color-border);",
            page,
        )
        self.assertIn(
            ".action-form{display:grid;gap:var(--spacing-12);",
            page,
        )
        self.assertIn(
            ".action-form form{padding:var(--spacing-16);"
            "border:var(--border-width-default) solid var(--color-border);"
            "border-radius:var(--radius-12);"
            "background:var(--color-surface)}",
            page,
        )
        self.assertIn(
            "button{width:100%;min-height:48px;",
            page,
        )
        self.assertIn(
            ".notice{display:flex;flex-direction:column;"
            "gap:var(--spacing-12);min-height:200px;",
            page,
        )
        self.assertIn(
            "@media (max-width:520px){"
            "body{padding:var(--spacing-8)}",
            page,
        )
        self.assertIn(
            ".metrics{grid-template-columns:1fr;"
            "gap:var(--spacing-12)}",
            page,
        )

    def test_fatal_notice_uses_approved_recovery_geometry_variant(self):
        page = integrity_console.render_fatal_check_failure()
        self.assertIn(
            '<aside class="notice notice-fatal" data-component="Notice" ',
            page,
        )
        self.assertIn(".notice-fatal{min-height:240px}", page)

    def test_semantic_text_colors_meet_aa_contrast(self):
        def luminance(value: str) -> float:
            channels = [
                int(value[index:index + 2], 16) / 255
                for index in (1, 3, 5)
            ]
            linear = [
                channel / 12.92
                if channel <= 0.04045
                else ((channel + 0.055) / 1.055) ** 2.4
                for channel in channels
            ]
            return (
                0.2126 * linear[0]
                + 0.7152 * linear[1]
                + 0.0722 * linear[2]
            )

        def contrast(first: str, second: str) -> float:
            lighter, darker = sorted(
                (luminance(first), luminance(second)),
                reverse=True,
            )
            return (lighter + 0.05) / (darker + 0.05)

        for foreground, background in (
            ("#e8eaed", "#101313"),
            ("#9099a6", "#101313"),
            ("#5fd68a", "#171b19"),
            ("#e6b94f", "#171b19"),
            ("#f07b7b", "#171b19"),
            ("#9ec5ff", "#101313"),
            ("#e8eaed", "#171b19"),
        ):
            self.assertGreaterEqual(contrast(foreground, background), 4.5)

    def test_healthy_component_mapping_and_landmarks(self):
        page = integrity_console.render(
            self._projection(overall="green"),
            serve_action="run-checks-now",
            served_form_action=(
                "http://127.0.0.1:54321/capability-token/run-checks-now"
            ),
        )
        self.assertEqual(page.count("<h1>"), 1)
        self.assertIn('<header class="page-header">', page)
        self.assertIn('<section class="status-summary"', page)
        self.assertIn('data-component="StatusIcon"', page)
        self.assertIn("AWA is healthy", page)
        self.assertIn('aria-label="Integrity counts"', page)
        self.assertEqual(page.count('data-component="MetricCard"'), 4)
        self.assertIn('data-component="ActionForm"', page)
        self.assertIn('data-component="Notice"', page)
        self.assertIn(
            "This console closes after 5 minutes idle",
            page,
        )
        self.assertIn(
            "awa-engine integrity console --serve --open",
            page,
        )

    def test_action_form_instruction_is_described_by_button(self):
        form = integrity_console._render_action_form()
        self.assertIn(
            '<button type="submit" aria-describedby="action-help">'
            "Run checks now</button>",
            form,
        )
        self.assertEqual(form.count('id="action-help"'), 1)
        self.assertIn(
            '<p class="action-help" id="action-help">'
            "Checks may take a moment; this page returns when complete.</p>",
            form,
        )
        self.assertIn(
            '<form method="post" action="run-checks-now">',
            form,
        )
        self.assertNotIn("<input", form)

    def test_approved_status_action_and_no_status_visual_contract(self):
        healthy = integrity_console.render(self._projection(overall="green"))
        self.assertIn(
            '[data-effective-overall="green"] .status{'
            "color:var(--color-healthy)}",
            healthy,
        )
        self.assertIn(
            '[data-effective-overall="red"] .status,'
            '[data-effective-overall="unknown"] .status{'
            "color:var(--color-critical)}",
            healthy,
        )
        self.assertIn(
            "button{min-height:48px;min-width:127px;"
            "padding:var(--spacing-12) var(--spacing-16);"
            "border:var(--border-width-default) solid var(--color-text);"
            "border-radius:var(--radius-8);"
            "background:var(--color-elevated);color:var(--color-text);",
            healthy,
        )
        no_status = integrity_console.render_no_status()
        self.assertIn(
            '<span class="status-icon" data-component="StatusIcon" '
            'aria-hidden="true">ⓘ</span>',
            no_status,
        )
        self.assertIn(
            '<section class="status-summary" '
            'data-component="StatusSummary" '
            'aria-labelledby="overall-status">',
            no_status,
        )
        self.assertIn(
            '<h2 class="status" id="overall-status">No status yet</h2>',
            no_status,
        )
        self.assertIn(
            ".status-icon{display:grid;place-items:center;width:40px;"
            "height:40px;border:var(--border-width-default) solid "
            "currentColor;border-radius:50%;color:var(--color-muted);",
            no_status,
        )

    def test_degraded_state_uses_approved_warning_contract(self):
        page = integrity_console.render(
            self._projection(overall="degraded"),
            serve_action="run-checks-now",
            served_form_action=(
                "http://127.0.0.1:54321/synthetic-token/run-checks-now"
            ),
        )
        self.assertIn("AWA needs attention", page)
        self.assertIn(
            "A check needs attention. Technical id: "
            "surveillance_freshness. "
            "Run checks again to refresh this private status.",
            page,
        )
        self.assertIn('data-effective-overall="degraded"', page)
        self.assertIn(">!</span>", page)
        self.assertIn("Run checks now", page)

    def test_critical_state_uses_approved_non_color_contract(self):
        page = integrity_console.render(
            self._projection(overall="red"),
            serve_action="run-checks-now",
            served_form_action=(
                "http://127.0.0.1:54321/synthetic-token/run-checks-now"
            ),
        )
        self.assertIn("AWA needs immediate attention", page)
        self.assertIn(
            "A critical integrity check failed. Technical id: "
            "integrity status. Run checks again before continuing.",
            page,
        )
        self.assertIn('data-effective-overall="red"', page)
        self.assertIn(">!</span>", page)
        self.assertNotIn('action="repair"', page)
        self.assertNotIn("Repair now", page)

    def test_safety_unknown_red_names_reducer_driving_invariant(self):
        page = integrity_console.render(
            self._reduced_projection({"guard_safety": "unknown"}),
        )
        self.assertIn(
            "A critical integrity check failed. Technical id: "
            "guard_safety. Run checks again before continuing.",
            page,
        )
        self.assertNotIn("Technical id: integrity status.", page)

    def test_noncritical_unknown_degraded_names_reducer_driver(self):
        page = integrity_console.render(
            self._reduced_projection({"hooks": "unknown"}),
        )
        self.assertIn(
            "A check needs attention. Technical id: hooks. "
            "Run checks again to refresh this private status.",
            page,
        )
        self.assertNotIn("Technical id: integrity status.", page)

    def test_red_driver_wins_over_earlier_lower_severity(self):
        page = integrity_console.render(
            self._reduced_projection(
                {
                    "entry_handshake": "degraded",
                    "release_identity": "red",
                },
            ),
        )
        self.assertIn(
            "A critical integrity check failed. Technical id: "
            "release_identity. Run checks again before continuing.",
            page,
        )
        self.assertNotIn("Technical id: entry_handshake.", page)

    def test_multiple_unknowns_follow_reducer_registry_order(self):
        cases = (
            (
                {"parity": "unknown", "guard_safety": "unknown"},
                "A critical integrity check failed. Technical id: "
                "guard_safety. Run checks again before continuing.",
            ),
            (
                {"hooks": "unknown", "entry_handshake": "unknown"},
                "A check needs attention. Technical id: entry_handshake. "
                "Run checks again to refresh this private status.",
            ),
        )
        for severities, expected in cases:
            with self.subTest(severities=severities):
                page = integrity_console.render(
                    self._reduced_projection(
                        severities,
                        reverse_input=True,
                    ),
                )
                self.assertIn(expected, page)
                self.assertNotIn("Technical id: integrity status.", page)

    def test_trigger_only_red_uses_generic_and_green_uses_no_fallback(self):
        trigger_red = integrity_console.render(
            self._reduced_projection({}, fresh=False),
        )
        self.assertIn(
            "A critical integrity check failed. Technical id: "
            "integrity status. Run checks again before continuing.",
            trigger_red,
        )
        healthy = integrity_console.render(
            self._reduced_projection({}),
            serve_action="run-checks-now",
            served_form_action=(
                "http://127.0.0.1:54321/synthetic-token/run-checks-now"
            ),
        )
        self.assertIn("AWA is healthy", healthy)
        self.assertNotIn("Technical id:", healthy)

    def test_stale_clock_uses_approved_critical_copy(self):
        page = integrity_console.render(self._projection(overall="green"))
        script, _csp = self._script_and_csp(page)
        self.assertIn('status.textContent="Status is stale / critical"', script)
        self.assertIn(
            'detail.textContent="The previous result has expired. '
            'A new check is required before relying on this status."',
            script,
        )
        self.assertIn('root.dataset.effectiveOverall="red"', script)

    def test_fatal_check_failure_page_has_exact_recovery_without_action(self):
        page = integrity_console.render_fatal_check_failure()
        self.assertIn("Checks could not complete", page)
        self.assertIn('<main data-effective-overall="red">', page)
        self.assertIn(
            '<span class="status-icon" data-component="StatusIcon" '
            'aria-hidden="true">!</span>',
            page,
        )
        self.assertIn("Restart the console, then run checks again.", page)
        self.assertIn(
            "awa-engine integrity console --serve --open",
            page,
        )
        self.assertNotIn('data-component="ActionForm"', page)
        self.assertNotIn("<form", page)
        self.assertIn('data-component="Notice"', page)

    def test_status_unavailable_page_is_recoverable_and_token_free(self):
        page = integrity_console.render_status_unavailable()
        self.assertIn("Status cannot be read", page)
        self.assertIn('<main data-effective-overall="yellow">', page)
        self.assertIn(
            '[data-effective-overall="degraded"] .status-summary,'
            '[data-effective-overall="yellow"] .status-summary{'
            "border-left-color:var(--color-warning)}",
            page,
        )
        self.assertIn(
            '[data-effective-overall="degraded"] .status-icon,'
            '[data-effective-overall="yellow"] .status-icon{'
            "color:var(--color-warning)}",
            page,
        )
        self.assertIn(
            '[data-effective-overall="degraded"] .status,'
            '[data-effective-overall="yellow"] .status{'
            "color:var(--color-warning)}",
            page,
        )
        self.assertIn(
            '<span class="status-icon" data-component="StatusIcon" '
            'aria-hidden="true">!</span>',
            page,
        )
        self.assertIn(
            "The saved status is unavailable or corrupt. "
            "Run checks now to recover in this console.",
            page,
        )
        self.assertIn('<form method="post" action="run-checks-now">', page)
        self.assertIn("Checks may take a moment", page)
        self.assertIn('data-component="Notice"', page)
        self.assertNotIn("synthetic-token", page)

    def test_static_snapshot_uses_approved_action_free_contract(self):
        page = integrity_console.render(self._projection(overall="green"))
        self.assertIn(
            '<h2 class="status" id="overall-status">Private snapshot</h2>',
            page,
        )
        self.assertNotIn(
            '<h2 class="status" id="overall-status">AWA is healthy</h2>',
            page,
        )
        self.assertIn(
            "Saved integrity status. This action-free snapshot can become "
            "critical when freshness expires.",
            page,
        )
        self.assertNotIn('data-component="ActionForm"', page)
        self.assertNotIn('data-component="Notice"', page)
        self.assertNotIn("awa-engine integrity console --serve --open", page)

    def test_component_content_is_escaped(self):
        card = integrity_console._render_metric_card(
            "<label>",
            "<script>value</script>",
        )
        self.assertIn("&lt;label&gt;", card)
        self.assertIn("&lt;script&gt;value&lt;/script&gt;", card)
        self.assertNotIn("<script>", card)
        summary = integrity_console._render_status_summary(
            state="green",
            heading="<healthy>",
            supporting_copy="<detail>",
        )
        self.assertIn("&lt;healthy&gt;", summary)
        self.assertIn("&lt;detail&gt;", summary)

    def test_static_output_omits_served_components_and_guidance(self):
        page = integrity_console.render(self._projection(overall="green"))
        self.assertNotIn('data-component="ActionForm"', page)
        self.assertNotIn('data-component="Notice"', page)
        self.assertNotIn("awa-engine integrity console --serve --open", page)
        self.assertNotIn("Checks may take a moment", page)

    def test_self_contained_no_remote_assets(self):
        page = integrity_console.render(self._projection())
        lowered = page.lower()
        self.assertNotIn("http://", lowered)
        self.assertNotIn("https://", lowered)
        self.assertNotIn("<script src", lowered)
        self.assertNotIn("<link ", lowered)
        self.assertNotIn("<form", lowered)
        self.assertNotIn("<button", lowered)
        self.assertNotIn("reload file", lowered)
        script, csp = self._script_and_csp(page)
        digest = base64.b64encode(
            hashlib.sha256(script.encode("utf-8")).digest()
        ).decode("ascii")
        self.assertIn(f"'sha256-{digest}'", csp)
        self.assertIn("default-src 'none'", csp)
        self.assertIn("connect-src 'none'", csp)
        self.assertIn("form-action 'none'", csp)
        self.assertNotIn("'unsafe-inline'", csp)

    def test_served_mode_adds_only_post_form_and_exact_form_csp(self):
        action = "http://127.0.0.1:54321/capability-token/run-checks-now"
        page = integrity_console.render(
            self._projection(),
            serve_action="run-checks-now",
            served_form_action=action,
        )
        script, csp = self._script_and_csp(page)
        self.assertIn(
            '<form method="post" action="run-checks-now">',
            page,
        )
        self.assertIn(
            '<button type="submit" aria-describedby="action-help">'
            "Run checks now</button>",
            page,
        )
        self.assertIn(
            "Checks may take a moment; this page returns when complete.",
            page,
        )
        self.assertIn(f"form-action {action}", csp)
        self.assertNotIn("form-action 'none'", csp)
        self.assertIn("Date.now()", script)
        for forbidden in (
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "document.cookie",
        ):
            self.assertNotIn(forbidden, page)

    def test_static_mode_remains_action_free_and_token_free(self):
        token = "capability-token-must-not-persist"
        page = integrity_console.render(self._projection())
        self.assertNotIn(token, page)
        self.assertNotIn("<form", page)
        self.assertNotIn("<button", page)
        self.assertIn("form-action 'none'", html.unescape(page))

    def test_served_no_status_page_is_closed_and_token_free(self):
        page = integrity_console.render_no_status()
        self.assertIn("No status yet", page)
        self.assertIn(
            "Run checks now to create the first private integrity status.",
            page,
        )
        self.assertIn(
            '<form method="post" action="run-checks-now">',
            page,
        )
        self.assertIn('data-component="StatusIcon"', page)
        self.assertIn('data-component="ActionForm"', page)
        self.assertIn('data-component="Notice"', page)
        self.assertIn(
            "awa-engine integrity console --serve --open",
            page,
        )
        self.assertNotIn("capability-token", page)
        self.assertNotIn("GREEN", page)
        self.assertNotIn("Recent history", page)
        self.assertNotIn("Invariants", page)
        self.assertNotIn("<script", page)

    def test_script_injection_escaped(self):
        projection = self._projection()
        projection["invariants"][1]["redacted_reason"] = (
            "</script><img src=x onerror=alert(1)>\u2028\u2029"
        )
        projection["unexpected"] = "<script>alert(2)</script>"
        page = integrity_console.render(projection)
        self.assertNotIn("</script><img", page)
        self.assertNotIn("<img", page)
        self.assertNotIn("alert(1)", page)
        self.assertNotIn("alert(2)", page)
        self.assertNotIn("\u2028", page)
        self.assertNotIn("\u2029", page)
        self.assertNotIn("</script><script", page)

    def test_no_absolute_paths_or_secrets(self):
        projection = self._projection()
        projection["invariants"][0]["redacted_reason"] = (
            "/Users/operator/private DO NOT DISCLOSE"
        )
        projection["raw_evidence"] = {
            "path": "/private/config",
            "credential": "DO NOT DISCLOSE",
        }
        page = integrity_console.render(projection)
        self.assertNotIn("/Users/", page)
        self.assertNotIn("/private/", page)
        self.assertNotIn("DO NOT DISCLOSE", page)
        self.assertNotIn("raw_evidence", page)

    def test_clock_only_script_forces_stale_red_after_expiry(self):
        projection = self._projection(overall="green")
        before = integrity_console.clock_state(
            projection,
            now_epoch=integrity._parse_iso(
                projection["fresh_until"]
            )
            - 1,
        )
        after = integrity_console.clock_state(
            projection,
            now_epoch=integrity._parse_iso(
                projection["fresh_until"]
            )
            + 1,
        )
        self.assertFalse(before["stale"])
        self.assertEqual(before["effective_overall"], "green")
        self.assertTrue(after["stale"])
        self.assertEqual(after["effective_overall"], "red")

        page = integrity_console.render(projection)
        script, _csp = self._script_and_csp(page)
        self.assertIn("Date.now()", script)
        self.assertIn("Status is stale / critical", script)
        self.assertIn(
            'document.querySelector("[data-component=StatusIcon]")',
            script,
        )
        self.assertIn('icon.textContent="!"', script)
        self.assertIn(
            'document.title="AWA integrity — Status is stale / critical"',
            script,
        )
        self.assertIn(
            '[data-effective-overall="green"] .status-summary{'
            "border-left-color:var(--color-healthy)}",
            page,
        )
        self.assertIn(
            '[data-effective-overall="red"] .status-summary,'
            '[data-effective-overall="unknown"] .status-summary{'
            "border-left-color:var(--color-critical)}",
            page,
        )
        self.assertIn(
            '[data-effective-overall="green"] .status-icon{'
            "color:var(--color-healthy)}",
            page,
        )
        self.assertIn(
            '[data-effective-overall="red"] .status-icon,'
            '[data-effective-overall="unknown"] .status-icon{'
            "color:var(--color-critical)}",
            page,
        )
        self.assertIn(
            'class="status-summary" data-component="StatusSummary" '
            'aria-labelledby="overall-status"',
            page,
        )
        self.assertNotIn('class="status-summary green"', page)
        self.assertIn(
            '<span class="status-icon" data-component="StatusIcon" '
            'aria-hidden="true">✓</span>',
            page,
        )
        self.assertIn(
            '[data-effective-overall="red"] .status,'
            '[data-effective-overall="unknown"] .status{'
            "color:var(--color-critical)}",
            page,
        )
        for forbidden in (
            "fetch(",
            "eval(",
            "XMLHttpRequest",
            "WebSocket",
            "localStorage",
            "document.cookie",
            "innerHTML",
        ):
            self.assertNotIn(forbidden, script)

    def test_console_file_is_0600(self):
        integrity._commit(
            self._status(),
            profile="deep",
            trigger="launchd",
        )
        status = integrity.read_status()
        console = (
            paths.integrity_dir()
            / status["artifacts"]["console"]["path"]
        )
        public = json.loads(
            (
                paths.integrity_dir()
                / status["artifacts"]["public"]["path"]
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(stat.S_IMODE(console.stat().st_mode), 0o600)
        self.assertEqual(
            console.read_text(encoding="utf-8"),
            integrity_console.render(public),
        )

    def test_cli_console_reports_referenced_private_file(self):
        integrity._commit(
            self._status(),
            profile="deep",
            trigger="launchd",
        )
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli.main(["integrity", "console"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            payload["schema"],
            "awa-integrity-console/v1",
        )
        self.assertEqual(payload["overall"], "green")
        console = Path(payload["path"])
        self.assertTrue(console.is_file())
        self.assertEqual(stat.S_IMODE(console.stat().st_mode), 0o600)

    def test_cli_console_open_uses_referenced_file_only(self):
        integrity._commit(
            self._status(),
            profile="deep",
            trigger="launchd",
        )
        stdout = io.StringIO()
        with mock.patch.object(
            cli,
            "_open_console",
            return_value=True,
        ) as opener, contextlib.redirect_stdout(stdout):
            code = cli.main(["integrity", "console", "--open"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["opened"])
        opener.assert_called_once_with(Path(payload["path"]))

    def test_install_ships_assets_without_host_activation_or_hook_touch(self):
        root = Path(self._tmp.name) / "install"
        home = root / "home"
        fake_bin = root / "bin"
        hooks = root / "selected-hooks" / "hooks.json"
        trace = root / "launchctl.trace"
        home.mkdir(parents=True)
        fake_bin.mkdir(parents=True)
        hooks.parent.mkdir(parents=True)
        hooks.write_text(
            '{"version":1,"hooks":{"beforeReadFile":'
            '[{"command":"/foreign/sentinel.sh","type":"command"}]}}\n',
            encoding="utf-8",
        )
        before = hooks.read_bytes()
        fake_launchctl = fake_bin / "launchctl"
        fake_launchctl.write_text(
            f"#!/usr/bin/env bash\nprintf called > {str(trace)!r}\nexit 93\n",
            encoding="utf-8",
        )
        fake_launchctl.chmod(0o755)
        data_home = home / ".local" / "share"
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "XDG_DATA_HOME": str(data_home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_STATE_HOME": str(home / ".local" / "state"),
                "AWA_HOOK_OWNER": "external",
                "AWA_HOOKS_JSON": str(hooks),
                "AWA_MCP_JSON": str(home / ".cursor" / "mcp.json"),
                "AWA_OPERATOR_RULE": str(
                    home / ".cursor" / "rules" / "awa-operator.mdc"
                ),
                "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        result = subprocess.run(
            ["bash", str(_INSTALL)],
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        runtime = data_home / "awa" / "current"
        self.assertTrue(
            (runtime / "kernel" / "bin" / "awa-integrity-sweep.sh").is_file()
        )
        self.assertTrue(
            (
                runtime
                / "contracts"
                / "awa-integrity-schedule.v1.json"
            ).is_file()
        )
        self.assertTrue(
            (runtime / "engine" / "integrity_console.py").is_file()
        )
        self.assertTrue(
            (runtime / "engine" / "integrity_server.py").is_file()
        )
        self.assertFalse(trace.exists())
        self.assertEqual(hooks.read_bytes(), before)
        self.assertFalse(any(runtime.rglob("*.plist")))

    def test_patch_version_recomputed_from_live_v171(self):
        self.assertEqual(
            (_ROOT / "engine" / "__init__.py")
            .read_text(encoding="utf-8")
            .count('__version__ = "1.7.3"'),
            1,
        )
        self.assertIn(
            'version = "1.7.3"',
            (_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
