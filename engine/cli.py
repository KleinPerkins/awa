"""cli.py — AWA engine command-line surface (additive; backs the frozen kernel).

This is the engine's OWN CLI (distinct from the frozen `dev-worktree.sh` shim, whose
contract the engine only BACKS, never changes). Verbs are grouped: state/doctor,
lifecycle (adopt/attest/publish/retire), recovery (bundle/patch/restore/list), guard
(shell/can-clean — the engine-off kernel guarantee), and daemon (status/run-once).

All output is JSON on stdout (machine-consumable); human notes go to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import (
    daemon as daemon_mod,
    gitutil,
    guard as guard_mod,
    lease as lease_mod,
    lifecycle,
    modes as modes_mod,
    paths,
    recovery,
    state as state_mod,
)

# The HOST supplies the policy file (include/exclude globs + governed-marker literals); the
# engine ships none of its own (host-agnostic, §zero-link). Default to $AWA_POLICY when the host
# sets it, else the installed kernel's generic default template (parity with worktree-guard.sh).
_AWA_HOME = os.environ.get("AWA_HOME") or str(Path(__file__).resolve().parent.parent)
_DEFAULT_POLICY = os.environ.get("AWA_POLICY") or str(
    Path(_AWA_HOME) / "kernel" / "policy" / "default-worktree-policy.yml"
)


def _emit(obj: dict, *, code: int = 0) -> int:
    json.dump(obj, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    return code


def _note(msg: str) -> None:
    print(f"awa: {msg}", file=sys.stderr)


def cmd_doctor(args: argparse.Namespace) -> int:
    report: dict = {"ok": True, "checks": []}

    def check(name: str, ok: bool, detail: str) -> None:
        report["checks"].append({"check": name, "ok": ok, "detail": detail})
        if not ok:
            report["ok"] = False

    sd = paths.awa_state_dir()
    ok, why = paths.is_local_disk(sd)
    check("state-root-local-disk", ok, why)

    try:
        with state_mod.State() as st:
            check("sqlite-wal", st.wal_mode().lower() == "wal", f"journal_mode={st.wal_mode()}")
            check("sqlite-schema", st.get_meta("schema_version") is not None,
                  f"schema_version={st.get_meta('schema_version')}")
            perms = state_mod.perms_report()
            bad = {p: m for p, m in perms.items()
                   if (p.rstrip("/").endswith("awa") and m != "0o700")
                   or (p.endswith(("state.db", "-wal", "-shm")) and m != "0o600")}
            check("s4-perms", not bad, f"modes={perms}" + (f" BAD={bad}" if bad else ""))
    except Exception as exc:  # noqa: BLE001
        check("sqlite-open", False, str(exc))

    return _emit(report, code=0 if report["ok"] else 1)


def cmd_state_init(args: argparse.Namespace) -> int:
    with state_mod.State() as st:
        return _emit({"db": str(st.db_path), "wal": st.wal_mode(),
                      "schema_version": st.get_meta("schema_version")})


def cmd_adopt(args: argparse.Namespace) -> int:
    try:
        res = lifecycle.adopt(args.worktree, base_ref=args.base)
    except lifecycle.LifecycleError as exc:
        return _emit({"action": "adopt", "ok": False, "error": str(exc)}, code=1)
    return _emit({"action": "adopt", "ok": True, "lease_id": res.lease_id,
                  "lease_path": res.lease_path, "attested": res.attested, "reason": res.reason})


def cmd_attest(args: argparse.Namespace) -> int:
    ok, why = lifecycle.attest(args.worktree)
    return _emit({"action": "attest", "ok": ok, "reason": why}, code=0 if ok else 1)


def cmd_publish(args: argparse.Namespace) -> int:
    try:
        ref = lifecycle.publish(args.worktree, remote=args.remote,
                                retention_days=args.retention_days)
    except lifecycle.LifecycleError as exc:
        return _emit({"action": "publish", "ok": False, "error": str(exc)}, code=1)
    return _emit({"action": "publish", "ok": True, "quarantine_ref": ref})


def cmd_retire(args: argparse.Namespace) -> int:
    lifecycle.retire(args.worktree)
    return _emit({"action": "retire", "ok": True, "worktree": args.worktree})


def cmd_lease_read(args: argparse.Namespace) -> int:
    lz = lease_mod.read_lease(args.worktree)
    if not lz:
        return _emit({"ok": False, "error": "no lease.json"}, code=1)
    return _emit({"ok": True, "lease": lz, "valid": not lease_mod.validate(lz)})


def cmd_recover(args: argparse.Namespace) -> int:
    if args.what == "bundle":
        with state_mod.State(assert_local=False) as st:
            r = recovery.create_bundle(args.worktree, allow_secrets=args.allow_secrets, state=st)
        return _emit({"action": "bundle", "archive": r.archive, "manifest": r.manifest,
                      "included": r.included, "skipped_secrets": r.skipped_secrets,
                      "skipped_symlink_escape": r.skipped_symlink_escape})
    if args.what == "patch":
        with state_mod.State(assert_local=False) as st:
            r = recovery.create_patch(args.worktree, state=st)
        return _emit({"action": "patch", "patch": r.patch, "has_changes": r.has_changes,
                      "included_staged": r.included_staged})
    if args.what == "restore-patch":
        recovery.restore_patch(args.patch, args.worktree, index=args.index)
        return _emit({"action": "restore-patch", "ok": True})
    if args.what == "restore-bundle":
        restored = recovery.restore_bundle(args.archive, args.worktree)
        return _emit({"action": "restore-bundle", "ok": True, "restored": restored})
    if args.what == "list":
        return _emit({"artifacts": recovery.list_artifacts()})
    return _emit({"ok": False, "error": f"unknown recover subcommand: {args.what}"}, code=2)


def cmd_guard(args: argparse.Namespace) -> int:
    if args.what == "shell":
        allow_primary = os.environ.get("DEV_WORKTREE_GUARD_ALLOW_PRIMARY", "0") == "1"
        d = guard_mod.decide_shell(args.cwd, args.command, args.policy,
                                   allow_primary=allow_primary)
        out = {"permission": d.permission, "reason": d.reason,
               "classification": d.classification}
        return _emit(out)
    if args.what == "can-clean":
        ok, why = guard_mod.can_clean(args.worktree)
        return _emit({"can_clean": ok, "reason": why}, code=0 if ok else 1)
    return _emit({"ok": False, "error": f"unknown guard subcommand: {args.what}"}, code=2)


def _resolve_modes_path(args: argparse.Namespace) -> str:
    """Resolve the modes-file path: explicit --modes-file wins, else the host policy's
    `modes_file:` pointer (zero-link — the path is always host-supplied, never hardcoded)."""
    explicit = getattr(args, "modes_file", None)
    if explicit:
        return os.path.expanduser(explicit)
    mf = modes_mod.resolve_modes_file(args.policy)
    if not mf:
        raise modes_mod.ModesError(
            f"no modes_file configured in policy: {args.policy} "
            "(set `modes_file:` in the host policy or pass --modes-file)"
        )
    return mf


def cmd_mode(args: argparse.Namespace) -> int:
    try:
        path = _resolve_modes_path(args)
        if args.what == "list":
            return _emit(modes_mod.list_modes(path))
        if args.what == "get":
            return _emit(modes_mod.get_mode(path, args.rel))
        if args.what == "set":
            return _emit(modes_mod.set_mode(path, args.rel, args.mode))
        if args.what == "remove":
            # Idempotent: removing an absent entry is success (exit 0, removed=False).
            return _emit(modes_mod.remove_mode(path, args.rel))
        if args.what == "repair":
            return _emit(modes_mod.repair(path))
        if args.what == "sync":
            return _emit(modes_mod.sync(path, default_mode=args.default_mode))
    except modes_mod.ModesError as exc:
        return _emit({"action": f"mode {args.what}", "ok": False, "error": str(exc)}, code=2)
    return _emit({"ok": False, "error": f"unknown mode subcommand: {args.what}"}, code=2)


def cmd_daemon(args: argparse.Namespace) -> int:
    inst = daemon_mod.SingleInstance()
    if args.what == "status":
        return _emit({"daemon": inst.status()})
    if args.what == "run-once":
        try:
            with inst:
                with state_mod.State() as st:
                    summary = daemon_mod.run_once(st, delete_remote=args.delete_remote)
            return _emit({"action": "run-once", "ok": True, "summary": summary})
        except daemon_mod.AlreadyRunning as exc:
            return _emit({"action": "run-once", "ok": False, "error": str(exc),
                          "pid": exc.pid}, code=1)
    return _emit({"ok": False, "error": f"unknown daemon subcommand: {args.what}"}, code=2)


def cmd_apply_back(args: argparse.Namespace) -> int:
    if args.execute:
        # Phase-9 remote adapter: SHA-bound, recovery-before-mutation, S3 token split.
        # Read/write tokens come from the environment (least-privilege split); the LIVE
        # push/PR are operator/live steps (default_pusher/default_pr_opener use a real
        # remote + credential and are refused honestly when unavailable headless).
        from . import remote as remote_mod
        read_token = os.environ.get("AWA_GITHUB_READ_TOKEN") or None
        write_token = os.environ.get("AWA_GITHUB_WRITE_TOKEN") or None
        try:
            with state_mod.State(assert_local=False) as st:
                res = remote_mod.apply_back_execute(
                    args.worktree, base=args.base, confirm=args.confirm,
                    read_token=read_token, write_token=write_token, remote=args.remote,
                    pusher=remote_mod.default_pusher, pr_opener=remote_mod.default_pr_opener,
                    state=st,
                )
        except (lifecycle.LifecycleError, remote_mod.RemoteError) as exc:
            return _emit({"action": "apply-back", "ok": False, "execute": True,
                          "error": str(exc)}, code=1)
        return _emit({
            "action": "apply-back", "ok": res.ok, "execute": True, "mutated": res.mutated,
            "pushed": res.pushed, "pushed_ref": res.pushed_ref, "pr_url": res.pr_url,
            "branch": None, "head": res.head, "base_sha": res.base_sha,
            "recovery_patch": res.recovery_patch, "reason": res.reason,
        })
    try:
        with state_mod.State(assert_local=False) as st:
            plan = lifecycle.apply_back_preview(args.worktree, base=args.base, state=st)
    except lifecycle.LifecycleError as exc:
        return _emit({"action": "apply-back", "ok": False, "error": str(exc)}, code=1)
    return _emit({
        "action": "apply-back", "ok": True, "preview": plan.preview, "mutated": plan.mutated,
        "branch": plan.branch, "head": plan.head, "base_ref": plan.base_ref,
        "base_sha": plan.base_sha, "commits_ahead": plan.commits_ahead,
        "files_changed": plan.files_changed, "recovery_patch": plan.recovery_patch,
        "reason": plan.reason,
    })


def cmd_detect_ingest(args: argparse.Namespace) -> int:
    with state_mod.State(assert_local=False) as st:
        n = daemon_mod.ingest_detection_receipts(st)
        return _emit({"action": "detect-ingest", "ingested": n,
                      "detections": st.detections(limit=args.limit)})


def cmd_events(args: argparse.Namespace) -> int:
    with state_mod.State(assert_local=False) as st:
        return _emit({"events": st.events(limit=args.limit),
                      "leases": st.list_leases()})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="awa", description="AWA engine CLI (backs the frozen kernel)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="health check (WAL/local-disk/perms)").set_defaults(fn=cmd_doctor)
    sub.add_parser("state-init", help="initialize the durable state db").set_defaults(fn=cmd_state_init)

    a = sub.add_parser("adopt", help="adopt a native-window worktree (record lease + attest)")
    a.add_argument("--worktree", required=True)
    a.add_argument("--base", default=None)
    a.set_defaults(fn=cmd_adopt)

    at = sub.add_parser("attest", help="re-verify a worktree's lease")
    at.add_argument("--worktree", required=True)
    at.set_defaults(fn=cmd_attest)

    pu = sub.add_parser("publish", help="OPT-IN publish-then-move to a quarantine ref")
    pu.add_argument("--worktree", required=True)
    pu.add_argument("--remote", default="origin")
    pu.add_argument("--retention-days", type=int, default=7)
    pu.set_defaults(fn=cmd_publish)

    rt = sub.add_parser("retire", help="mark a lease retired")
    rt.add_argument("--worktree", required=True)
    rt.set_defaults(fn=cmd_retire)

    lr = sub.add_parser("lease-read", help="read + validate a worktree's lease.json")
    lr.add_argument("--worktree", required=True)
    lr.set_defaults(fn=cmd_lease_read)

    rc = sub.add_parser("recover", help="recovery manager (bundle/patch/restore/list)")
    rc.add_argument("what", choices=["bundle", "patch", "restore-patch", "restore-bundle", "list"])
    rc.add_argument("--worktree", default=".")
    rc.add_argument("--patch", default="")
    rc.add_argument("--archive", default="")
    rc.add_argument("--allow-secrets", action="store_true")
    rc.add_argument("--index", action="store_true")
    rc.set_defaults(fn=cmd_recover)

    g = sub.add_parser("guard", help="engine-off kernel guard (shell/can-clean)")
    g.add_argument("what", choices=["shell", "can-clean"])
    g.add_argument("--cwd", default=".")
    g.add_argument("--command", default="")
    g.add_argument("--worktree", default=".")
    g.add_argument("--policy", default=_DEFAULT_POLICY)
    g.set_defaults(fn=cmd_guard)

    md = sub.add_parser(
        "mode",
        help="manage the tool-owned per-repo modes file (list/get/set/remove/repair/sync)",
    )
    md.add_argument("what", choices=["list", "get", "set", "remove", "repair", "sync"])
    md.add_argument("rel", nargs="?", default=None,
                    help="repo path/glob relative to the governed root (get/set/remove)")
    md.add_argument("mode", nargs="?", default=None,
                    help="mode value on|off (set)")
    md.add_argument("--policy", default=_DEFAULT_POLICY,
                    help="host policy file whose modes_file pointer locates the modes file")
    md.add_argument("--modes-file", dest="modes_file", default=None,
                    help="explicit modes-file path (overrides the policy pointer)")
    md.add_argument("--default-mode", dest="default_mode", default=None,
                    help="seed default_mode when creating the file (sync)")
    md.set_defaults(fn=cmd_mode)

    d = sub.add_parser("daemon", help="watcher/enforcer (single-instance)")
    d.add_argument("what", choices=["status", "run-once"])
    d.add_argument("--delete-remote", action="store_true")
    d.set_defaults(fn=cmd_daemon)

    ab = sub.add_parser("apply-back", help="SHA-bound apply-back PREVIEW (recovery-before-mutation)")
    ab.add_argument("--worktree", required=True)
    ab.add_argument("--base", default=None)
    ab.add_argument("--execute", action="store_true",
                    help="run the remote adapter (S3 token split); live push is an operator step")
    ab.add_argument("--confirm", action="store_true",
                    help="with --execute, confirm the mutation (else preview-only)")
    ab.add_argument("--remote", default="origin")
    ab.set_defaults(fn=cmd_apply_back)

    di = sub.add_parser("detect-ingest", help="fold shell-gate detection receipts into state")
    di.add_argument("--limit", type=int, default=50)
    di.set_defaults(fn=cmd_detect_ingest)

    ev = sub.add_parser("events", help="recent audit events + leases")
    ev.add_argument("--limit", type=int, default=50)
    ev.set_defaults(fn=cmd_events)

    sub.add_parser("mcp-serve", help="run the local stdio MCP server (read-only state + path-scoped mode config tools)").set_defaults(fn=cmd_mcp_serve)

    return p


def cmd_mcp_serve(args: argparse.Namespace) -> int:
    from . import mcp_server
    return mcp_server.serve()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)
