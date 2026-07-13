"""_trial_phase1.py — Phase 1 (deterministic kernel core) transitions.

Driven through the REAL kernel entrypoints: ``kernel/lib/awa_finish.py`` CLI (preview /
finish-execute / challenge-* / branch-disposition), ``kernel/bin/dev-worktree.sh
clean --finish-current`` (shell), and ``kernel/lib/awa_roots.py heartbeat`` — all engine-OFF and
XDG-isolated, exactly as ``engine/tests/test_finish_kernel.py::FinishBase`` drives them. The real
destructive ``Close`` removal always operates on a THROWAWAY worktree provisioned in the sandbox.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from _trial_lib import (REPO, Row, Sandbox, TrialAssertion, UX, check, check_eq, transition)


# =====================================================================================
# (a) literal-Close authorization + content-addressed removal
# =====================================================================================
@transition(Row(
    id="P1-CLOSE-REMOVES", phase="P1", title="Exact Close removes the current worktree",
    precondition="ephemeral linked worktree, dirty draft, pending challenge from preview",
    inp="kernel finish-execute --answer Close", expected="outcome=removed; worktree gone; challenge consumed once",
    oracle="test_finish_kernel::IdenticalRefusalGateTest::test_replay_once_challenge_consumed_on_removal"))
def close_removes(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("close-removes", {"draft.txt": "discard"})
    sb.kernel_preview(wt, conv="cr")
    res = sb.kernel_execute(wt, "Close", conv="cr")
    check_eq(res.get("outcome"), "removed", "outcome")
    check(not Path(wt).exists(), "worktree must be physically removed")
    read = sb.run_kernel("challenge-read", "--conversation-id", "cr")
    status = json.loads(read.stdout)["status"]
    check_eq(status, "absent", "challenge status after removal (replay-safe)")
    return f"outcome=removed branch_action={res.get('branch_action')} challenge=absent (replay-safe)"


@transition(Row(
    id="P1-CONSUME-REPLAY", phase="P1", title="Challenge consumes exactly once (replay-safe)",
    precondition="pending challenge from preview",
    inp="challenge-consume x2", expected="first consumed=true, second consumed=false",
    oracle="test_finish_kernel::AuthorizeChallengeTest::test_challenge_replay_once"))
def consume_replay(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("consume-replay", {"a": "1"})
    sb.kernel_preview(wt, conv="c1")
    r1 = json.loads(sb.run_kernel("challenge-consume", "--conversation-id", "c1").stdout)
    r2 = json.loads(sb.run_kernel("challenge-consume", "--conversation-id", "c1").stdout)
    check_eq(r1.get("consumed"), True, "first consume")
    check_eq(r2.get("consumed"), False, "second consume (replay)")
    return "consume#1=true consume#2=false"


@transition(Row(
    id="P1-NONCLOSE-REFUSE", phase="P1", title="Every non-exact-Close answer refuses + preserves",
    precondition="pending challenge",
    inp="finish-execute with close/CLOSE/cLoSe/' Close '/'Close\\n'/'Close please'/yes/true/''",
    expected="outcome=refused reason=not_close; worktree preserved for every variant",
    oracle="test_finish_kernel::IdenticalRefusalGateTest::test_non_close_variants_all_refuse"))
def nonclose_refuse(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("nonclose", {"a": "1"})
    sb.kernel_preview(wt, conv="nc")
    variants = ("close", "CLOSE", "cLoSe", " Close ", "Close\n", "Close please", "yes", "true", "")
    for ans in variants:
        res = sb.kernel_execute(wt, ans, conv="nc")
        check_eq((res.get("outcome"), res.get("reason")), ("refused", "not_close"), f"variant {ans!r}")
        check(Path(wt).exists(), f"variant {ans!r} must preserve the worktree")
    return f"{len(variants)} non-Close variants all refused (not_close); worktree preserved"


@transition(Row(
    id="P1-NO-CHALLENGE", phase="P1", title="Close without a pending challenge refuses",
    precondition="no preview performed",
    inp="finish-execute --answer Close (never previewed)",
    expected="outcome=refused receipt_code=finish_no_challenge; preserved",
    oracle="test_finish_kernel::IdenticalRefusalGateTest::test_no_challenge_refuses"))
def no_challenge(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("nochal", {"a": "1"})
    res = sb.kernel_execute(wt, "Close", conv="never-previewed")
    check_eq(res.get("outcome"), "refused", "outcome")
    check_eq(res.get("receipt_code"), "finish_no_challenge", "receipt_code")
    check(Path(wt).exists(), "worktree preserved")
    return "refused finish_no_challenge; preserved"


@transition(Row(
    id="P1-FINGERPRINT-DRIFT", phase="P1", title="New work after preview invalidates the challenge",
    precondition="pending challenge, then a new untracked file appears",
    inp="finish-execute --answer Close after drift",
    expected="outcome=refused receipt_code=finish_fingerprint_mismatch; preserved",
    oracle="test_finish_kernel::IdenticalRefusalGateTest::test_fingerprint_drift_refuses"))
def fingerprint_drift(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("drift", {"a": "1"})
    sb.kernel_preview(wt, conv="d1")
    Path(wt, "surprise.txt").write_text("new work appeared", encoding="utf-8")
    res = sb.kernel_execute(wt, "Close", conv="d1")
    check_eq(res.get("outcome"), "refused", "outcome")
    check_eq(res.get("receipt_code"), "finish_fingerprint_mismatch", "receipt_code")
    check(Path(wt).exists(), "worktree preserved")
    return "refused finish_fingerprint_mismatch; preserved"


@transition(Row(
    id="P1-CROSS-ROOT", phase="P1", title="A challenge for worktree A cannot remove worktree B",
    precondition="preview A, execute B with the same conversation id",
    inp="finish-execute B --answer Close (challenge minted for A)",
    expected="outcome=refused receipt_code=finish_target_mismatch; A and B preserved",
    oracle="test_finish_kernel::IdenticalRefusalGateTest::test_cross_root_challenge_refuses"))
def cross_root(sb: Sandbox) -> str:
    _, wt_a, _ = sb.ephemeral_wt("rootA", {"a": "1"})
    _, wt_b, _ = sb.ephemeral_wt("rootB", {"b": "1"})
    sb.kernel_preview(wt_a, conv="shared")
    res = sb.kernel_execute(wt_b, "Close", conv="shared")
    check_eq(res.get("receipt_code"), "finish_target_mismatch", "receipt_code")
    check(Path(wt_a).exists() and Path(wt_b).exists(), "both worktrees preserved")
    return "refused finish_target_mismatch; both preserved"


@transition(Row(
    id="P1-STALE-TTL", phase="P1", title="Coarse staleness backstop discards an abandoned challenge",
    precondition="pending challenge aged far past the 15-min backstop",
    inp="challenge-read x2",
    expected="first read status=stale, second read status=absent (backstop discarded it)",
    oracle="test_finish_kernel::AuthorizeChallengeTest::test_challenge_stale_backstop_discards"))
def stale_ttl(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("stale", {"a": "1"})
    sb.kernel_preview(wt, conv="c2")
    fin = UX._load_finish()
    cp = Path(fin.challenge_path("c2"))
    rec = json.loads(cp.read_text(encoding="utf-8"))
    rec["created_at_epoch"] = fin._now_epoch() - 100_000
    rec["created_at"] = fin._iso_from_epoch(rec["created_at_epoch"])
    cp.write_text(json.dumps(rec), encoding="utf-8")
    first = sb.run_kernel("challenge-read", "--conversation-id", "c2")
    check_eq(first.returncode, 1, "stale read exit code")
    check_eq(json.loads(first.stdout)["status"], "stale", "first read status")
    second = sb.run_kernel("challenge-read", "--conversation-id", "c2")
    check_eq(json.loads(second.stdout)["status"], "absent", "second read status (discarded)")
    return "read#1=stale read#2=absent (abandoned challenge discarded)"


@transition(Row(
    id="P1-CANCEL-NOOP", phase="P1", title="challenge-delete (Cancel) is a literal no-op",
    precondition="pending challenge; a file present in the worktree",
    inp="challenge-delete then challenge-read",
    expected="challenge absent; the worktree file is untouched (no mutation)",
    oracle="test_finish_kernel::AuthorizeChallengeTest::test_challenge_delete_is_noop_cancel"))
def cancel_noop(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("cancel", {"a": "1"})
    sb.kernel_preview(wt, conv="c3")
    check(Path(wt, "a").exists(), "precondition file")
    sb.run_kernel("challenge-delete", "--conversation-id", "c3")
    read = sb.run_kernel("challenge-read", "--conversation-id", "c3")
    check_eq(json.loads(read.stdout)["status"], "absent", "challenge status")
    check(Path(wt, "a").exists(), "cancel performs no mutation")
    return "challenge=absent; worktree file intact"


@transition(Row(
    id="P1-CROSS-SESSION", phase="P1", title="A second fresh session blocks the finish (session gate)",
    precondition="another live session heartbeat recorded BEFORE preview",
    inp="finish-execute --answer Close from the confirming session",
    expected="outcome=refused receipt_code=finish_session_blocked; preserved",
    oracle="test_finish_kernel::IdenticalRefusalGateTest::test_cross_session_fresh_blocks"))
def cross_session(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("xsess", {"a": "1"})
    t = sb.targets(wt)
    sb.roots_heartbeat(wt, "OTHER-LIVE-SESSION", t["branch"], t["common_dir"])
    sb.kernel_preview(wt, conv="xs", session="CONFIRMING")
    res = sb.kernel_execute(wt, "Close", conv="xs", session="CONFIRMING")
    check_eq(res.get("receipt_code"), "finish_session_blocked", "receipt_code")
    check(Path(wt).exists(), "worktree preserved")
    return "refused finish_session_blocked; preserved"


# =====================================================================================
# (b) network-free local-ref branch disposition
# =====================================================================================
@transition(Row(
    id="P1-BRANCH-EPHEMERAL", phase="P1", title="Ephemeral branch, no local-only commits -> delete-eligible",
    precondition="cursor/worktree/* branch with no unshared commits",
    inp="branch-disposition", expected="action=delete_eligible",
    oracle="test_finish_kernel::BranchDispositionTest::test_ephemeral_no_local_only_is_delete_eligible"))
def branch_ephemeral(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("eph")
    t = sb.targets(wt)
    r = sb.run_kernel("branch-disposition", "--root", wt, "--branch", t["branch"],
                      "--head", t["head"], "--common-dir", t["common_dir"])
    check_eq(json.loads(r.stdout)["action"], "delete_eligible", "action")
    return "action=delete_eligible"


@transition(Row(
    id="P1-BRANCH-LOCALONLY", phase="P1", title="Local-only commits -> branch retained",
    precondition="ephemeral branch carrying an unshared commit",
    inp="branch-disposition", expected="action=retain_local_only",
    oracle="test_finish_kernel::BranchDispositionTest::test_local_only_commits_retained"))
def branch_localonly(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("lo")
    Path(wt, "work.txt").write_text("local\n", encoding="utf-8")
    sb.commit_all(wt, "local only")
    t = sb.targets(wt)
    r = sb.run_kernel("branch-disposition", "--root", wt, "--branch", t["branch"],
                      "--head", t["head"], "--common-dir", t["common_dir"])
    check_eq(json.loads(r.stdout)["action"], "retain_local_only", "action")
    return "action=retain_local_only"


@transition(Row(
    id="P1-BRANCH-NONEPHEMERAL", phase="P1", title="Non-ephemeral branch -> retained",
    precondition="feature/keep worktree branch",
    inp="branch-disposition", expected="action=retain",
    oracle="test_finish_kernel::BranchDispositionTest::test_non_ephemeral_branch_retained"))
def branch_nonephemeral(sb: Sandbox) -> str:
    repo = sb.make_repo("nonephem")
    wt = repo + ".wt"
    sb.git(repo, "worktree", "add", "-q", "-b", "feature/keep", wt, "main")
    t = sb.targets(wt)
    r = sb.run_kernel("branch-disposition", "--root", wt, "--branch", t["branch"],
                      "--head", t["head"], "--common-dir", t["common_dir"])
    check_eq(json.loads(r.stdout)["action"], "retain", "action")
    return "action=retain"


@transition(Row(
    id="P1-BRANCH-PROTECTED", phase="P1", title="Protected branches (main/master) are never ephemeral",
    precondition="branch names main and master",
    inp="_is_ephemeral_branch", expected="False for main and master (never delete-eligible)",
    oracle="test_finish_kernel::BranchDispositionTest::test_protected_branch_never_deleted"))
def branch_protected(sb: Sandbox) -> str:
    fin = UX._load_finish()
    check(not fin._is_ephemeral_branch("/x", "main", "/c"), "main must not be ephemeral")
    check(not fin._is_ephemeral_branch("/x", "master", "/c"), "master must not be ephemeral")
    return "main=protected master=protected (never delete-eligible)"


@transition(Row(
    id="P1-NO-NETWORK", phase="P1", title="Removal + branch delete perform ZERO network",
    precondition="PATH shim whose git/gh touch a sentinel on any network verb",
    inp="finish-execute --answer Close under the net-bomb PATH",
    expected="outcome=removed, branch deleted, sentinel NEVER created",
    oracle="test_finish_kernel::NoNetworkGateTest::test_removal_and_branch_delete_perform_no_network"))
def no_network(sb: Sandbox) -> str:
    real_git = shutil.which("git")
    check(bool(real_git), "git must be on PATH")
    shim = sb.data / "netbomb"
    shim.mkdir(parents=True, exist_ok=True)
    sentinel = shim / "NETWORK_WAS_CALLED"
    (shim / "git").write_text(
        "#!/usr/bin/env bash\n"
        'for a in "$@"; do case "$a" in\n'
        "  fetch|ls-remote|push|clone|remote-https|remote-http)\n"
        f'    echo net >> "{sentinel}"; echo "NETWORK GIT: $a" >&2; exit 97 ;;\n'
        "esac; done\n"
        f'exec "{real_git}" "$@"\n', encoding="utf-8")
    (shim / "git").chmod(0o755)
    (shim / "gh").write_text(
        "#!/usr/bin/env bash\n"
        f'echo gh >> "{sentinel}"; echo "NETWORK GH: $*" >&2; exit 98\n', encoding="utf-8")
    (shim / "gh").chmod(0o755)
    path = f"{shim}:{os.environ.get('PATH', '')}"
    env = sb.kernel_env(path=path)
    _, wt, _ = sb.ephemeral_wt("nonet", {"draft.txt": "x"})
    sb.kernel_preview(wt, conv="nn")
    res = sb.kernel_execute(wt, "Close", conv="nn", env=env)
    check_eq(res.get("outcome"), "removed", "outcome")
    check_eq(res.get("branch_action"), "deleted", "branch_action")
    check(not Path(wt).exists(), "worktree removed")
    check(not sentinel.exists(),
          "a network verb was invoked on the removal path: "
          + (sentinel.read_text() if sentinel.exists() else ""))
    return "outcome=removed branch=deleted network_sentinel=absent (zero network)"


# =====================================================================================
# (c) dev-worktree.sh shell entrypoint: authorization + spoofing + branch fallback + receipts
# =====================================================================================
@transition(Row(
    id="P1-CLI-REQUIRES-CLOSE", phase="P1", title="dev-worktree.sh requires an explicit Close to remove",
    precondition="ephemeral worktree",
    inp="clean --finish-current --preview  THEN  --authorization Close",
    expected="preview preserves (finish_preview); Close removes (finish_removed)",
    oracle="test_finish_kernel::HookIndependentGateTest::test_cli_requires_explicit_close_to_remove"))
def cli_requires_close(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("cliclose", {"a": "1"})
    pv = sb.run_dev_finish("--preview", cwd=wt)
    check_eq(pv.returncode, 0, f"preview rc ({pv.stderr})")
    check(Path(wt).exists(), "preview must preserve")
    check_eq(sb.last_receipt()["reason_code"], "finish_preview", "preview reason_code")
    rm = sb.run_dev_finish("--authorization", "Close", cwd=wt)
    check_eq(rm.returncode, 0, f"close rc ({rm.stderr})")
    check(not Path(wt).exists(), "Close must remove")
    rec = sb.last_receipt()
    check_eq((rec["disposition"], rec["reason_code"]), ("removed", "finish_removed"), "removed receipt")
    return "preview=finish_preview(preserved) close=finish_removed(removed)"


@transition(Row(
    id="P1-FLAG-ALONE", phase="P1", title="The --finish-current flag alone is not authorization",
    precondition="ephemeral worktree",
    inp="clean --finish-current (no --authorization)",
    expected="refused finish_no_authorization; worktree preserved",
    oracle="test_finish_kernel::HookIndependentGateTest::test_flag_alone_is_not_authorization"))
def flag_alone(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("noauth", {"a": "1"})
    r = sb.run_dev_finish(cwd=wt)
    check(r.returncode != 0, "flag alone must not succeed")
    check(Path(wt).exists(), "worktree preserved")
    check_eq(sb.last_receipt()["reason_code"], "finish_no_authorization", "reason_code")
    return "refused finish_no_authorization; preserved"


@transition(Row(
    id="P1-SPOOF-PRIMARY", phase="P1", title="Target spoof: primary checkout is refused",
    precondition="a primary (non-linked) checkout",
    inp="clean --finish-current --authorization Close in the primary",
    expected="refused finish_not_linked; preserved",
    oracle="test_finish_kernel::HookIndependentGateTest::test_target_spoof_primary_checkout_refused"))
def spoof_primary(sb: Sandbox) -> str:
    repo = sb.make_repo("primary")
    r = sb.run_dev_finish("--authorization", "Close", cwd=repo)
    check(r.returncode != 0, "primary must be refused")
    check(Path(repo).exists(), "primary preserved")
    check_eq(sb.last_receipt()["reason_code"], "finish_not_linked", "reason_code")
    return "refused finish_not_linked; primary preserved"


@transition(Row(
    id="P1-SPOOF-SUBDIR", phase="P1", title="Target spoof: a sub-directory (not top level) is refused",
    precondition="a nested subdir inside a linked worktree",
    inp="clean --finish-current --authorization Close in a subdir",
    expected="refused finish_not_linked; preserved",
    oracle="test_finish_kernel::HookIndependentGateTest::test_target_spoof_subdir_not_toplevel_refused"))
def spoof_subdir(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("subdir")
    sub = Path(wt, "nested")
    sub.mkdir()
    r = sb.run_dev_finish("--authorization", "Close", cwd=str(sub))
    check(r.returncode != 0, "subdir must be refused")
    check(Path(wt).exists(), "worktree preserved")
    check_eq(sb.last_receipt()["reason_code"], "finish_not_linked", "reason_code")
    return "refused finish_not_linked; preserved"


@transition(Row(
    id="P1-REJECT-PATH", phase="P1", title="--finish-current rejects a --path argument",
    precondition="ephemeral worktree",
    inp="clean --finish-current --path <wt> --authorization Close",
    expected="refused finish_bad_args; preserved",
    oracle="test_finish_kernel::HookIndependentGateTest::test_finish_current_rejects_path_arg"))
def reject_path(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("pathrej")
    r = sb.run_dev_finish("--path", wt, "--authorization", "Close", cwd=wt)
    check(r.returncode != 0, "explicit --path must be refused")
    check(Path(wt).exists(), "worktree preserved")
    check_eq(sb.last_receipt()["reason_code"], "finish_bad_args", "reason_code")
    return "refused finish_bad_args; preserved"


@transition(Row(
    id="P1-BRANCH-FALLBACK", phase="P1", title="Branch-cleanup failure still reports removed (never misreports survival)",
    precondition="git shim that fails update-ref; ephemeral worktree",
    inp="clean --finish-current --authorization Close",
    expected="removed; branch_action=delete_failed; branch survives (compare-and-delete, no force)",
    oracle="test_finish_kernel::HookIndependentGateTest::test_branch_delete_fallback_still_reports_removed"))
def branch_fallback(sb: Sandbox) -> str:
    real_git = shutil.which("git")
    shim = sb.data / "urefbomb"
    shim.mkdir(parents=True, exist_ok=True)
    (shim / "git").write_text(
        "#!/usr/bin/env bash\n"
        'for a in "$@"; do [ "$a" = "update-ref" ] && { echo "shim: no update-ref" >&2; exit 1; }; done\n'
        f'exec "{real_git}" "$@"\n', encoding="utf-8")
    (shim / "git").chmod(0o755)
    env = sb.kernel_env(path=f"{shim}:{os.environ.get('PATH', '')}")
    repo, wt, br = sb.ephemeral_wt("fallback", {"a": "1"})
    sb.run_dev_finish("--preview", cwd=wt, env=env)
    r = sb.run_dev_finish("--authorization", "Close", cwd=wt, env=env)
    check_eq(r.returncode, 0, f"close rc ({r.stderr})")
    check(not Path(wt).exists(), "worktree removed")
    rec = sb.last_receipt()
    check_eq((rec["disposition"], rec["reason_code"]), ("removed", "finish_removed"), "removed receipt")
    check_eq(rec["branch_action"], "delete_failed", "branch_action")
    survived = sb.git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{br}", check_rc=False)
    check_eq(survived.returncode, 0, "branch must survive a delete failure (no force-delete)")
    return "removed; branch_action=delete_failed; branch survives"


@transition(Row(
    id="P1-DIRTY-DISCARD", phase="P1", title="A dirty tree is discarded on an authorized Close",
    precondition="ephemeral worktree with a modified tracked file + a new untracked file",
    inp="clean --finish-current --preview then --authorization Close",
    expected="removed (dirty work discarded once authorized)",
    oracle="test_finish_kernel::HookIndependentGateTest::test_dirty_state_is_discarded_on_close"))
def dirty_discard(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("dirty", {"tracked.txt": "v1"})
    sb.commit_all(wt, "base")
    Path(wt, "tracked.txt").write_text("v2-uncommitted", encoding="utf-8")
    Path(wt, "new.txt").write_text("new", encoding="utf-8")
    sb.run_dev_finish("--preview", cwd=wt)
    r = sb.run_dev_finish("--authorization", "Close", cwd=wt)
    check_eq(r.returncode, 0, f"close rc ({r.stderr})")
    check(not Path(wt).exists(), "worktree removed")
    return "removed; dirty tracked+untracked discarded"


@transition(Row(
    id="P1-RECEIPT-FIELDS", phase="P1", title="Removed receipt carries the additive finish fields",
    precondition="ephemeral worktree with two discardable files",
    inp="clean --finish-current --preview then --authorization Close",
    expected="receipt: finish_current=true, branch_action=deleted, discard_count>=2, fingerprint+nonce present",
    oracle="test_finish_kernel::HookIndependentGateTest::test_removed_receipt_carries_finish_fields"))
def receipt_fields(sb: Sandbox) -> str:
    _, wt, _ = sb.ephemeral_wt("fields", {"a.txt": "1", "b.txt": "2"})
    sb.run_dev_finish("--preview", cwd=wt)
    sb.run_dev_finish("--authorization", "Close", cwd=wt)
    rec = sb.last_receipt()
    check_eq(rec["disposition"], "removed", "disposition")
    check_eq(rec["finish_current"], True, "finish_current")
    check_eq(rec["branch_action"], "deleted", "branch_action")
    check(int(rec["discard_count"]) >= 2, "discard_count>=2")
    check(bool(rec["challenge_fingerprint"]), "challenge_fingerprint present")
    check(bool(rec["authorization_nonce"]), "authorization_nonce present")
    return f"removed receipt: discard_count={rec['discard_count']} branch=deleted fingerprint+nonce present"


@transition(Row(
    id="P1-LITERAL-CLOSE", phase="P1", title="is_literal_close accepts only the exact standalone token",
    precondition="none (pure predicate)",
    inp="is_literal_close over an adversarial matrix",
    expected="True only for 'Close'; False for casing/trim/attachment/boolean/None variants",
    oracle="test_finish_kernel::AuthorizeChallengeTest::test_is_literal_close_exact_only"))
def literal_close(sb: Sandbox) -> str:
    fin = UX._load_finish()
    check(fin.is_literal_close("Close"), "'Close' must be accepted")
    bad = ("close", "CLOSE", "cLoSe", "Close\n", " Close ", "\tClose\t", "Close please",
           "please Close", "yes", "true", "", "Close.", "Closed", None, True, 1, ["Close"])
    for b in bad:
        check(not fin.is_literal_close(b), f"{b!r} must be rejected")
    return f"'Close'=accepted; {len(bad)} variants rejected"
