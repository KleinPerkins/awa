"""egress-gate: the SYSTEM-WIDE operator egress gate across ALL SEVEN PM-facing surfaces.

A0 proved the chat loop + render_block. This is the generalized gate: it renders the REAL output of
every surface a non-technical operator can see and asserts ZERO Tier A/B/C banned terms on each, with
the router UNINSTALLED (kernel-first). The seven surfaces (plan ~183):

  1. chat loop (operator loop)          — live loop over the golden set (FakeRouter), A0 subset.
  2. guard block / refuse message       — the REAL kernel guard hook, driven end-to-end.
  3. dashboard canvas                   — the seed's PM_COPY block + the emitter's plain_* fields.
  4. MCP consent-copy contract          — candidate host copy; not production-wired by AWA.
  5. discard / save confirmation        — render_confirmation over the REAL kernel consequence.
  6. doctor / status                    — emitter.render_status_lines() over a real emit.
  7. detection receipts / timeline      — a REAL afterFileEdit receipt through render_timeline().

Single source of truth: consumer/egress.py (+ egress-terms.json). Every surface's test scans through
that ONE matcher, so the banned-term set cannot drift per-surface.

BITES (non-tautological): for every surface, the real output is scanned clean, THEN one real string
inside that output is poisoned with a banned term and re-scanned — proving the gate actually covers
that surface's output shape and would turn red if a term were reintroduced.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from consumer import egress, operator_loop as L, translators
from engine import mcp_server

from .consumer_test_support import (FakeRouter, load_catalog, load_golden,
                                     load_kernel_consequence, make_proposal)

_REPO = Path(__file__).resolve().parents[2]
_GUARD = _REPO / "kernel" / "hooks" / "worktree-guard.sh"
_CANVAS = _REPO / "dashboard" / "seed.canvas.tsx"

sys.path.insert(0, str(_REPO / "dashboard"))
import emitter  # noqa: E402  (matches dashboard/test_emitter.py's import convention)

# A naturally-lowercase Tier A term: guaranteed in the set, matched case-insensitively. Used only to
# POISON a real output string and prove the scan bites.
_BITE_TERM = "worktree"

# Kernel target facts that maximize rendered confirmation copy (unshared work -> spells out risk),
# and a fully-shared benign counterpart (no confirmation nag).
F_UNSHARED = {"target": "/tmp/x", "exists": True, "disposition": "stale",
              "has_uncommitted_changes": True, "has_unshared_work": True, "branch_on_remote": False}
F_SHARED = {"target": "/tmp/x", "exists": True, "disposition": "clean",
            "has_uncommitted_changes": False, "has_unshared_work": False, "branch_on_remote": True}

_IDENT = ("-c", "user.email=49759187+KleinPerkins@users.noreply.github.com",
          "-c", "user.name=KleinPerkins")

_POLICY = """\
version: 1
governed_roots:
  - {root}
default: include
include:
  - '*'
exclude:
  - .
detectors:
  governed_markers:
    - _ops/POLICY.md
  foreign_hook_frameworks:
    - husky
"""


def _proposal_from_golden(expect: dict) -> dict:
    verdict = expect.get("verdict", "none")
    conf = {"strong": 1.0, "weak": 0.5}.get(verdict, 0.0)
    return make_proposal(
        verb=expect.get("verb", ""), safety_class=expect.get("safety_class", "read"),
        verdict=verdict, confidence=conf, missing_params=list(expect.get("missing_params", [])),
        requires_confirmation=expect.get("requires_confirmation", True))


def _poison_first_string(obj):
    """Deep-copy `obj`, corrupting the FIRST string found by appending a banned term. Returns
    (poisoned, hit) where `hit` is True iff a string was found to corrupt."""
    state = {"hit": False}

    def rec(o):
        if state["hit"]:
            return o
        if isinstance(o, str):
            state["hit"] = True
            return o + " " + _BITE_TERM
        if isinstance(o, list):
            return [rec(x) for x in o]
        if isinstance(o, dict):
            return {k: rec(v) for k, v in o.items()}
        return o

    return rec(copy.deepcopy(obj)), state["hit"]


class _EgressBase(unittest.TestCase):
    def assertCleanAndBites(self, obj, label: str):
        """Assert `obj` is jargon-free NOW, and that the SAME scan would bite if a banned term were
        embedded in it (non-tautological per-surface proof)."""
        self.assertEqual(egress.scan_object(obj), [], f"{label}: leaked banned term(s)")
        poisoned, hit = _poison_first_string(obj)
        self.assertTrue(hit, f"{label}: no string present to poison (cannot prove the gate bites)")
        self.assertNotEqual(egress.scan_object(poisoned), [],
                            f"{label}: gate did NOT bite on an injected banned term")


class TestEgressSurfaces(_EgressBase):
    # -- surface 1: chat loop (operator loop) --------------------------------------------------
    def test_surface1_chat_loop(self):
        catalog = load_catalog()
        golden = load_golden()
        mapping = {c["utterance"]: _proposal_from_golden(c["expect"]) for c in golden["cases"]}
        renders = []
        for case in golden["cases"]:
            loop = L.OperatorLoop(catalog, router=FakeRouter(mapping),
                                  executor=lambda v, p, t: {"ok": True, "verified": True,
                                                            "detail": "I checked afterwards and it worked."})
            for confirm in (None, True):
                r = loop.handle(case["utterance"], target="/tmp/x", facts=F_UNSHARED, confirm=confirm)
                # The A0 PM-facing render subset (NOT the raw utterance / decision enum).
                renders.append({k: r.get(k) for k in ("understanding", "confirmation", "narration",
                                                      "secondary_explicit_path")})
        self.assertCleanAndBites(renders, "surface1:chat-loop")

    # -- surface 2: guard block / refuse message -----------------------------------------------
    def _make_guarded_repo(self, tmp: Path):
        root = tmp
        repo = root / "proj"
        repo.mkdir()
        env = dict(os.environ)
        for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                  "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
            env.pop(k, None)
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True, env=env)
        (repo / "f").write_text("#\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "f"], check=True, capture_output=True, env=env)
        subprocess.run(["git", "-C", str(repo), *_IDENT, "commit", "-qm", "init"],
                       check=True, capture_output=True, env=env)
        subprocess.run(["git", "-C", str(repo), "branch", "-M", "main"], check=True,
                       capture_output=True, env=env)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                        "git@github.com:KleinPerkins/awa-egress-test.git"], check=True,
                       capture_output=True, env=env)
        policy = root / "policy.yml"
        policy.write_text(_POLICY.format(root=root), encoding="utf-8")
        return repo, policy

    def _run_guard(self, payload, root, policy, *, cwd=None, extra_env=None) -> dict:
        env = dict(os.environ)
        env["AWA_GOVERNED_ROOT"] = str(root)
        env["AWA_POLICY"] = str(policy)
        if extra_env:
            env.update(extra_env)
        data = payload if isinstance(payload, str) else json.dumps(payload)
        proc = subprocess.run([str(_GUARD)], input=data, capture_output=True, text=True,
                              env=env, cwd=cwd)
        return json.loads(proc.stdout)

    def test_surface2_guard_block(self):
        with tempfile.TemporaryDirectory(prefix="awa-egress-guard.") as td:
            root = Path(td)
            repo, policy = self._make_guarded_repo(root)
            messages = []
            # (a) confirmed mutation on an included primary -> enforced deny (the refuse message).
            deny = self._run_guard({"command": "git commit -am x", "cwd": str(repo)}, root, policy)
            self.assertEqual(deny.get("permission"), "deny")
            messages.append(deny["user_message"])
            # (b) unparseable payload on an included primary -> honest ask.
            ask = self._run_guard("{not valid json", root, policy, cwd=str(repo))
            self.assertEqual(ask.get("permission"), "ask")
            messages.append(ask["user_message"])
            # The PM reads `user_message`; `agent_message` is agent-facing and intentionally NOT scanned.
            self.assertCleanAndBites(messages, "surface2:guard-block")

    # -- surface 3: dashboard canvas -----------------------------------------------------------
    @staticmethod
    def _pm_copy_block() -> str:
        text = _CANVAS.read_text(encoding="utf-8")
        start = text.index("PM_COPY_START")
        end = text.index("PM_COPY_END")
        return text[start:end]

    @staticmethod
    def _plain_projection(doc: dict) -> dict:
        """The jargon-free PM subset of an emitter doc (the mechanism DATA fields are the technical
        view and are deliberately excluded — the dashboard renders only these plain values)."""
        proj = {"plain": doc.get("plain", {}),
                "engine_plain": (doc.get("environment", {}).get("engine", {}) or {}).get("plain", "")}
        repos = []
        for r in doc.get("repos", []):
            repos.append({
                "plain_next": r.get("plain_next", ""),
                "worktrees": [{"plain_status": w.get("plain_status", ""),
                               "plain_next": w.get("plain_next", ""),
                               "plain_size": w.get("plain_size", "")} for w in r.get("worktrees", [])],
                "orphan_branches": [{"plain_status": b.get("plain_status", ""),
                                     "plain_next": b.get("plain_next", "")}
                                    for b in r.get("orphan_branches", [])],
            })
        proj["repos"] = repos
        return proj

    def test_surface3_dashboard_pm_copy_block(self):
        block = self._pm_copy_block()
        self.assertEqual(egress.find_banned_terms(block), [],
                         "dashboard canvas PM_COPY block leaks a banned term")
        self.assertNotEqual(egress.find_banned_terms(block + " " + _BITE_TERM), [],
                            "canvas PM_COPY scan did not bite")

    def test_surface3_dashboard_plain_fields_exhaustive(self):
        # Every plain_worktree branch (status variants), plain_repo, plain_orphan, plain_summary —
        # rendered directly from the emitter's REAL functions, covering states a small git tree
        # cannot cheaply produce (detached / diverged / behind / no-base / locked / prunable).
        wt_variants = [
            {"is_primary": True, "is_linked": False},
            {"is_linked": True, "prunable": True},
            {"is_linked": True, "locked": True},
            {"is_linked": True, "detached": True, "dirty": True, "dirty_count": 3},
            {"is_linked": True, "ab_status": "no-base"},
            {"is_linked": True, "ab_status": "even"},
            {"is_linked": True, "ab_status": "even", "dirty": True, "dirty_count": 1},
            {"is_linked": True, "ab_status": "ahead", "ahead": 2},
            {"is_linked": True, "ab_status": "behind", "behind": 4},
            {"is_linked": True, "ab_status": "diverged", "ahead": 1, "behind": 1},
            {"is_linked": True, "ab_status": "unknown"},
        ]
        rendered = [emitter._plain_worktree(w) for w in wt_variants]
        rendered += [emitter._plain_repo(c, hb) for c in ("include", "exclude", "advisory")
                     for hb in (True, False)]
        rendered += [emitter._plain_orphan({"ab_status": s, "ahead": 2, "behind": 1})
                     for s in ("ahead", "even", "behind", "diverged", "no-base", "unknown")]
        rendered += [emitter._plain_summary({"included": 3, "excluded": 1, "dirty": 2, "orphan_branches": 1},
                                            {"engine": {"running": False, "plain": "I step in at each change."}})]
        self.assertCleanAndBites(rendered, "surface3:dashboard-plain-fields")

    def test_surface3_dashboard_real_emit(self):
        # The REAL render path: build() over a scratch tree attaches the plain_* fields + doc.plain.
        with tempfile.TemporaryDirectory(prefix="awa-egress-emit.") as td:
            root = Path(td) / "gov"
            (root / "proj").mkdir(parents=True)
            env = dict(os.environ)
            for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
                env.pop(k, None)
            repo = root / "proj"
            subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True, env=env)
            (repo / "r").write_text("#\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True, env=env)
            subprocess.run(["git", "-C", str(repo), *_IDENT, "commit", "-qm", "init"],
                           check=True, capture_output=True, env=env)
            subprocess.run(["git", "-C", str(repo), "branch", "-M", "main"], check=True,
                           capture_output=True, env=env)
            policy = Path(td) / "policy.yml"
            policy.write_text(_POLICY.format(root=root), encoding="utf-8")
            os.environ["AWA_POLICY"] = str(policy)
            try:
                doc = emitter.build(root, timeout=30.0)
            finally:
                os.environ.pop("AWA_POLICY", None)
            self.assertIn("plain", doc)
            self.assertCleanAndBites(self._plain_projection(doc), "surface3:dashboard-real-emit")

    # -- surface 4: contract-only MCP consent copy (not production-wired) -----------------------
    def test_surface4_mcp_consent_plain_intent(self):
        cases = [("awa_mode_set", {"rel": "repo", "mode": "off"}),
                 ("awa_mode_set", {"rel": "group/*", "mode": "off"}),
                 ("awa_mode_set", {"rel": "repo", "mode": "on"}),
                 ("awa_mode_set", {"rel": "group/*", "mode": "on"}),
                 ("awa_mode_set", {"rel": "repo", "mode": "advisory"}),
                 ("awa_mode_remove", {"rel": "repo"}),
                 ("awa_mode_remove", {"rel": "group/*"}),
                 ("awa_mode_repair", {}), ("awa_mode_sync", {}),
                 ("awa_mode_sync", {"default_mode": "off"})]
        prompts = []
        for name, args in cases:
            p = mcp_server.consent_prompt(name, args)
            self.assertIsInstance(p, str, f"{name}: mutating tool must have candidate copy")
            # Plain INTENT, never the tool name (nor any awa_* token).
            self.assertNotIn(name, p, f"{name}: candidate copy leaks the tool name")
            self.assertNotIn("awa_", p, f"{name}: candidate copy leaks a tool token")
            self.assertTrue(p.rstrip().endswith("?"), f"{name}: candidate copy should ask, plainly")
            prompts.append(p)
        # Read-only tools need no future mutating-action consent copy.
        for ro in ("awa_status", "awa_lease_read", "awa_guard_shell"):
            self.assertIsNone(mcp_server.consent_prompt(ro, {}), f"{ro}: read-only, expected no prompt")
        self.assertCleanAndBites(prompts, "surface4:mcp-consent")

    # -- surface 5: discard / save confirmation ------------------------------------------------
    def test_surface5_discard_save_confirmation(self):
        kc = load_kernel_consequence()
        catalog = load_catalog()
        entry = next((e for e in catalog.get("verbs", []) if e.get("verb") == "cleanup"), None)
        renders = []
        # Destructive discard on unshared work -> spells out the risk / undo / point-of-no-return.
        destructive = kc.describe_consequence(kc.ACTION_REMOVE, "/tmp/x", facts=F_UNSHARED,
                                              remove_saved_reference=False)
        renders.append(translators.render_confirmation(destructive, entry))
        # Benign save -> plain "safe to do", no nag.
        benign = kc.describe_consequence(kc.ACTION_RECORD, "/tmp/x", facts=F_SHARED)
        renders.append(translators.render_confirmation(benign, entry))
        # Benign remove (work fully shared) -> also no nag.
        benign_rm = kc.describe_consequence(kc.ACTION_REMOVE, "/tmp/x", facts=F_SHARED)
        renders.append(translators.render_confirmation(benign_rm, entry))
        self.assertTrue(destructive["requires_confirmation"])
        self.assertFalse(benign["requires_confirmation"])
        self.assertCleanAndBites(renders, "surface5:discard-save-confirmation")

    # -- surface 6: doctor / status ------------------------------------------------------------
    def test_surface6_doctor_status(self):
        # Build a status doc from exhaustive plain fields (a realistic multi-project shape) and
        # render the PM status lines the operator reads.
        doc = {
            "plain": emitter._plain_summary(
                {"included": 2, "excluded": 1, "dirty": 1, "orphan_branches": 1},
                {"engine": {"running": False, "plain": "I step in at each change."}}),
            "environment": {"engine": {"running": False, "plain": "I step in at each change."}},
            "repos": [
                {"name": "alpha", "classification": "include", "has_base": True,
                 **emitter._plain_repo("include", True),
                 "worktrees": [dict({"is_linked": True, "ab_status": "ahead", "ahead": 2},
                                    **emitter._plain_worktree({"is_linked": True, "ab_status": "ahead", "ahead": 2}))],
                 "orphan_branches": [dict({"ab_status": "even"}, **emitter._plain_orphan({"ab_status": "even"}))]},
                {"name": "beta", "classification": "exclude", "has_base": True,
                 **emitter._plain_repo("exclude", True), "worktrees": [], "orphan_branches": []},
            ],
        }
        lines = emitter.render_status_lines(doc)
        self.assertTrue(lines, "status render produced no lines")
        # HONEST CONFIDENCE: the status names BOTH what it checked and what it could not.
        self.assertTrue(doc["plain"].get("checked"), "status missing 'what I checked'")
        self.assertTrue(doc["plain"].get("not_checked"), "status missing 'what I can't promise'")
        self.assertIn(doc["plain"]["checked"], lines)
        self.assertIn(doc["plain"]["not_checked"], lines)
        self.assertCleanAndBites(lines, "surface6:doctor-status")

    # -- surface 7: detection receipts / timeline ----------------------------------------------
    def test_surface7_detection_receipts_timeline(self):
        with tempfile.TemporaryDirectory(prefix="awa-egress-receipt.") as td:
            root = Path(td)
            repo, policy = self._make_guarded_repo(root)
            statedir = Path(td) / "state"
            statedir.mkdir()
            resp = self._run_guard(
                {"hook_event_name": "afterFileEdit", "cwd": str(repo), "file_path": str(repo / "f")},
                root, policy, extra_env={"XDG_STATE_HOME": str(statedir)})
            self.assertEqual(resp.get("permission"), "allow")  # observation-only
            receipts = statedir / "awa" / "detections" / "receipts.jsonl"
            self.assertTrue(receipts.exists(), "afterFileEdit did not write a detection receipt")
            recs = [json.loads(ln) for ln in receipts.read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertTrue(recs, "empty detection receipt log")
            # The REAL receipt(s), plus recovery events + an unknown kind + a jargon-bearing raw
            # note (which must NOT be echoed) — all through the PM timeline renderer.
            events = list(recs) + [
                {"kind": "recovery_bundle", "time": "2026-07-09T00:00:00Z"},
                {"kind": "worktree_archive", "time": "2026-07-09T00:01:00Z"},
                {"kind": "some_future_kind", "time": "2026-07-09T00:02:00Z",
                 "note": "raw worktree/branch/lease mechanism note that must never reach the PM"},
            ]
            timeline = translators.render_timeline(events)
            self.assertCleanAndBites(timeline, "surface7:detection-timeline")

    # -- constitution egress machine-check: spec -> ACTIVE (declared + citations verified) -----
    def test_egress_gate_declaration_active_and_citations_resolve(self):
        """The AWA-side flip of the `egress` constitution machine-check to ACTIVE is machine-checked
        here: the declaration says active, covers all seven surfaces, and EVERY cited authoritative
        test actually exists (a citation that rots fails this test)."""
        import importlib
        gate = json.loads((_REPO / "consumer" / "egress-gate.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(gate["schema"], "awa-egress-gate/v1")
        self.assertEqual(gate["status"], "active", "egress gate must be flipped active (was spec)")
        self.assertEqual(gate["previous_status"], "spec")
        ids = sorted(s["id"] for s in gate["surfaces"])
        self.assertEqual(ids, [1, 2, 3, 4, 5, 6, 7], "all seven PM-facing surfaces must be declared")

        def _resolve(dotted: str) -> bool:
            mod_path, cls, meth = dotted.rsplit(".", 2)
            mod = importlib.import_module(mod_path)
            return hasattr(getattr(mod, cls, object), meth)

        cited: list[str] = []
        for s in gate["surfaces"]:
            self.assertTrue(s["authoritative_tests"], f"surface {s['id']} cites no test")
            cited += s["authoritative_tests"]
        cited += gate["honest_confidence"]["authoritative_tests"]
        cited += gate["mcp_consent"]["authoritative_tests"]
        for dotted in cited:
            self.assertTrue(_resolve(dotted), f"cited authoritative test does not exist: {dotted}")
        # The constitution cross-repo flip names the REAL router machine-check (egress_zero_banned_terms,
        # verified against the live router constitution) and points at the seam enforcement test.
        cc = gate["constitution_check"]
        self.assertEqual(cc["name"], "egress_zero_banned_terms")
        self.assertEqual(cc["router_field"], "machine_checks.egress_zero_banned_terms")
        self.assertEqual(cc["to"], "active")
        self.assertIn("test_constitution_egress_check_active_if_declared", cc["cross_repo_flip"])

    # -- honest confidence, asserted directly (plan ~187) --------------------------------------
    def test_honest_confidence_present_on_status_and_dashboard(self):
        p = emitter._plain_summary({"included": 1, "excluded": 0, "dirty": 0, "orphan_branches": 0},
                                   {"engine": {"running": False, "plain": "x"}})
        for key in ("checked", "not_checked"):
            self.assertTrue(p.get(key), f"honest-confidence summary missing {key!r}")
        # The confirmation renderer also always states it has changed nothing yet (never a bare pill).
        conf = translators._confidence("strong", [])
        self.assertIn("not_checked", conf)
        self.assertTrue(conf["not_checked"])


if __name__ == "__main__":
    unittest.main()
