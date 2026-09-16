#!/usr/bin/env bash
# awa-contract-freeze.sh — assert the live AWA kernel surfaces still satisfy the FROZEN
# BEHAVIOR contract (contracts/awa-contract.v1.json). Read-only. ROLE-RESOLVED: it finds the
# live shims relative to the AWA install root (AWA_HOME), NOT a hardcoded host path — the
# contract froze BEHAVIOR (verbs/flags/JSON shapes/lease shape), never file location.
#
# FAILS if a frozen surface is missing/renamed (a breaking change requires awa-contract.v2.json).
# Additive OPTIONAL fields are allowed. Invoked by `make verify`.
set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"   # kernel/checks
KERNEL_DIR="$(cd "$SELF_DIR/.." && pwd)"                        # kernel
AWA_HOME="${AWA_HOME:-$(cd "$KERNEL_DIR/.." && pwd)}"           # install root (role-resolved)

CONTRACT="$AWA_HOME/contracts/awa-contract.v1.json"
HOOK_OWNER_V2="$AWA_HOME/contracts/awa-hook-owner.v2.json"
DEV_WORKTREE="$AWA_HOME/kernel/bin/dev-worktree.sh"
GUARD="$AWA_HOME/kernel/hooks/worktree-guard.sh"
COMPOSITE_GUARD="$AWA_HOME/kernel/hooks/worktree-guard-with-integrity.sh"
INTEGRITY_OBSERVER="$AWA_HOME/kernel/hooks/awa-integrity-observer.sh"
SESSION_HANDOFF="$AWA_HOME/kernel/hooks/awa-session-handoff.sh"
HANDOFF_AUTHORITY="$AWA_HOME/kernel/lib/awa_handoff.py"
INTEGRITY_DETACHER="$AWA_HOME/engine/integrity_detach.py"
INSTALL_HOOKS="$AWA_HOME/kernel/hooks/install-hooks.sh"
EMITTER="$AWA_HOME/dashboard/emitter.py"

fail=0
pass() { printf '  PASS  %s\n' "$1"; }
bad()  { printf '  FAIL  %s\n' "$1"; fail=1; }
has_executable_mode() {
  python3 - "$@" <<'PY'
import os
import stat
import sys

for raw in sys.argv[1:]:
    try:
        mode = os.lstat(raw).st_mode
    except OSError:
        raise SystemExit(1)
    if not stat.S_ISREG(mode) or not os.access(raw, os.R_OK) or mode & 0o111 == 0:
        raise SystemExit(1)
PY
}

echo "== AWA kernel contract freeze (v1, behavior-only, role-resolved) =="
echo "   AWA_HOME=$AWA_HOME"

if [ ! -f "$CONTRACT" ]; then
  bad "frozen contract missing: $CONTRACT"; echo "awa-contract-freeze: FAILED"; exit 1
fi
if ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$CONTRACT" 2>/dev/null; then
  bad "frozen contract is not valid JSON: $CONTRACT"; echo "awa-contract-freeze: FAILED"; exit 1
fi
pass "frozen contract present + valid JSON"
if [ ! -f "$HOOK_OWNER_V2" ] ||
   ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$HOOK_OWNER_V2" 2>/dev/null; then
  bad "hook-owner v2 contract missing or invalid: $HOOK_OWNER_V2"
fi
for f in "$DEV_WORKTREE" "$GUARD" "$COMPOSITE_GUARD" \
    "$INTEGRITY_OBSERVER" "$SESSION_HANDOFF" "$HANDOFF_AUTHORITY" "$INTEGRITY_DETACHER" \
  "$INSTALL_HOOKS" "$EMITTER"; do
  [ -f "$f" ] || bad "role-resolved shim missing: $f"
done

# 0) awa-hook-owner/v2 is the preferred additive successor. The effective direct
# projection is frozen v1 minus superseded roles plus v2. External install/check
# must still exit before creating even the selected destination's parent.
owner_tmp="$(mktemp -d)"
owner_direct="$owner_tmp/direct-hooks.json"
owner_external="$owner_tmp/external-parent/hooks.json"
owner_install_rc=0
owner_check_rc=0
owner_external_install_rc=0
owner_external_check_rc=0
AWA_HOOK_OWNER=direct AWA_HOOKS_JSON="$owner_direct" \
  bash "$INSTALL_HOOKS" >/dev/null 2>&1 || owner_install_rc=$?
AWA_HOOK_OWNER=direct AWA_HOOKS_JSON="$owner_direct" \
  bash "$INSTALL_HOOKS" --check >/dev/null 2>&1 || owner_check_rc=$?
AWA_HOOK_OWNER=external AWA_HOOKS_JSON="$owner_external" \
  bash "$INSTALL_HOOKS" >/dev/null 2>&1 || owner_external_install_rc=$?
AWA_HOOK_OWNER=external AWA_HOOKS_JSON="$owner_external" \
  bash "$INSTALL_HOOKS" --check >/dev/null 2>&1 || owner_external_check_rc=$?
if [ "$owner_install_rc" -eq 0 ] && [ "$owner_check_rc" -eq 0 ] && \
   [ "$owner_external_install_rc" -eq 0 ] && [ "$owner_external_check_rc" -eq 0 ] && \
   [ ! -e "$owner_tmp/external-parent" ] && \
   CONTRACT="$CONTRACT" HOOK_OWNER_V2="$HOOK_OWNER_V2" \
   OWNER_DIRECT="$owner_direct" AWA_HOME="$AWA_HOME" python3 - <<'PY'
import json
import os
import pathlib
import sys

contract = json.load(open(os.environ["CONTRACT"], encoding="utf-8"))
v1 = contract.get("hook_ownership")
v2 = json.load(open(os.environ["HOOK_OWNER_V2"], encoding="utf-8"))
v1_ids = [
    "worktree.session-context",
    "worktree.shell-guard",
    "worktree.file-observer",
    "recovery.maintenance",
    "finish.prompt-recall",
]
v1_events = [
    "sessionStart",
    "beforeShellExecution",
    "afterFileEdit",
    "sessionStart",
    "beforeSubmitPrompt",
]
v1_classes = [
    "host-policy-delegator",
    "host-policy-delegator",
    "host-policy-delegator",
    "installed-awa",
    "installed-awa",
]
v2_ids = [
    "worktree.shell-guard-composite",
    "worktree.stop-observer",
    "worktree.session-handoff",
]
v2_events = ["beforeShellExecution", "stop", "sessionStart"]
v2_paths = [
    "kernel/hooks/worktree-guard-with-integrity.sh",
    "kernel/hooks/awa-integrity-observer.sh",
    "kernel/hooks/awa-session-handoff.sh",
]
errors = []
if not isinstance(v1, dict):
    errors.append("missing hook_ownership block")
    v1 = {}
else:
    required = {
        "schema", "modes", "default_mode", "selection_env",
        "selection_schema", "external_real_hook_file_writes", "roles",
    }
    if not required.issubset(v1):
        errors.append("v1 hook_ownership required field drift")
    if v1.get("schema") != "awa-hook-owner/v1":
        errors.append("v1 hook-owner schema drift")
    if v1.get("modes") != ["direct", "external"]:
        errors.append("v1 hook-owner mode vocabulary/order drift")
    if v1.get("default_mode") != "direct":
        errors.append("v1 hook-owner direct default drift")
    if v1.get("selection_env") != "AWA_HOOK_OWNER":
        errors.append("v1 hook-owner selection env drift")
    if v1.get("selection_schema") != "awa-hook-owner-selection/v1":
        errors.append("v1 hook-owner selection schema drift")
    if v1.get("external_real_hook_file_writes") is not False:
        errors.append("external hook-file write boundary drift")
v1_roles = v1.get("roles")
if not isinstance(v1_roles, list) or len(v1_roles) != 5:
    errors.append("v1 hook-owner role count drift")
    v1_roles = []
if [role.get("id") for role in v1_roles] != v1_ids:
    errors.append("v1 hook-owner role identity/order drift")
if [role.get("event") for role in v1_roles] != v1_events:
    errors.append("v1 hook-owner event order drift")
if [role.get("external_command_path_class") for role in v1_roles] != v1_classes:
    errors.append("v1 hook-owner external path-class drift")

required_v2 = {
    "schema", "version", "successor_of", "v1_contract", "modes",
    "default_mode", "selection_env", "selection_schema",
    "external_real_hook_file_writes", "supersedes_roles",
    "composition_rule", "external_rule", "roles",
}
if not required_v2.issubset(v2):
    errors.append("v2 required field drift")
if v2.get("schema") != "awa-hook-owner/v2" or v2.get("version") != 2:
    errors.append("v2 schema/version drift")
if v2.get("successor_of") != "awa-hook-owner/v1":
    errors.append("v2 successor drift")
if v2.get("v1_contract") != "contracts/awa-contract.v1.json#hook_ownership":
    errors.append("v2 compatibility pointer drift")
if v2.get("modes") != ["direct", "external"]:
    errors.append("v2 mode vocabulary/order drift")
if v2.get("default_mode") != "direct":
    errors.append("v2 direct default drift")
if v2.get("selection_env") != "AWA_HOOK_OWNER":
    errors.append("v2 selection env drift")
if v2.get("selection_schema") != "awa-hook-owner-selection/v1":
    errors.append("v2 selection schema drift")
if v2.get("external_real_hook_file_writes") is not False:
    errors.append("v2 external write boundary drift")
if v2.get("supersedes_roles") != ["worktree.shell-guard"]:
    errors.append("v2 supersession drift")
v2_roles = v2.get("roles")
if not isinstance(v2_roles, list) or len(v2_roles) != 3:
    errors.append("v2 role count drift")
    v2_roles = []
if [role.get("id") for role in v2_roles] != v2_ids:
    errors.append("v2 role identity/order drift")
if [role.get("event") for role in v2_roles] != v2_events:
    errors.append("v2 event order drift")
if [role.get("direct_command_role") for role in v2_roles] != v2_paths:
    errors.append("v2 direct path drift")
if any(
    role.get("external_command_path_class") != "host-policy-delegator"
    for role in v2_roles
):
    errors.append("v2 external path-class drift")
if v2_roles and v2_roles[-1].get("dormant_until_milestone") != "M2.4":
    errors.append("session-handoff historical activation metadata drift")

try:
    projection = json.load(open(os.environ["OWNER_DIRECT"], encoding="utf-8"))
except Exception:
    projection = {}
hooks = projection.get("hooks") if isinstance(projection, dict) else None
if projection.get("version") != 1 or not isinstance(hooks, dict):
    errors.append("direct hook projection shape drift")
    hooks = {}

home = pathlib.Path(os.environ["AWA_HOME"])
superseded = set(v2.get("supersedes_roles", []))
roles = [role for role in v1_roles if role.get("id") not in superseded]
roles.extend(v2_roles)
matched = 0
for role in roles:
    required_role = {
        "id", "event", "direct_command_role",
        "external_command_path_class", "entry",
    }
    allowed_role = required_role | {"dormant_until_milestone"}
    if not required_role.issubset(role) or not set(role).issubset(allowed_role):
        errors.append(f"role shape drift: {role.get('id')!r}")
        continue
    wanted = dict(role["entry"])
    wanted["command"] = str(
        (home / role["direct_command_role"]).resolve())
    rows = hooks.get(role["event"], [])
    count = rows.count(wanted) if isinstance(rows, list) else 0
    if count != 1:
        errors.append(f"direct projection count drift: {role['id']}={count}")
    matched += count
if sum(len(rows) for rows in hooks.values() if isinstance(rows, list)) != 7:
    errors.append("direct v2 projection does not contain exactly seven rows")
if matched != 7:
    errors.append("direct projection/contract parity incomplete")

if errors:
    print("; ".join(errors), file=sys.stderr)
    raise SystemExit(1)
PY
then
  pass "awa-hook-owner/v2 preferred; seven-role direct projection matches; v1 compatibility and external zero-access retained"
else
  bad "awa-hook-owner v2/v1 contract or reconciler parity drifted"
fi
rm -rf "$owner_tmp" 2>/dev/null || true

# 0a) M1-C hook mechanics: the composite delegates guard output through exec
# and both observers use the detached fast verifier. M2.4 handoff delegates to
# its single metadata-only authority with fail-open sessionStart behavior.
if has_executable_mode "$COMPOSITE_GUARD" "$INTEGRITY_OBSERVER" \
     "$SESSION_HANDOFF" "$INTEGRITY_DETACHER" && \
   grep -Fq '[[ -z "${AWA_INTEGRITY_GUARD:-}" ]]' \
     "$COMPOSITE_GUARD" && \
   grep -Fq 'exec bash "$GUARD"' "$COMPOSITE_GUARD" && \
   grep -Fq 'exec "$GUARD"' "$COMPOSITE_GUARD" && \
   grep -Fq -- '--trigger beforeShell' "$COMPOSITE_GUARD" && \
   grep -Fq -- '--trigger stop' "$INTEGRITY_OBSERVER" && \
   grep -Fq 'awa_handoff.py' "$SESSION_HANDOFF" && \
   grep -Fq 'consume' "$SESSION_HANDOFF" && \
   grep -Fq '|| true' "$SESSION_HANDOFF" && \
   grep -Fq 'awa-session-handoff/v1' "$HANDOFF_AUTHORITY" && \
   ! grep -Eq 'integrity[[:space:]]+verify|move_agent_to_root' "$SESSION_HANDOFF" && \
   INTEGRITY_DETACHER="$INTEGRITY_DETACHER" python3 - <<'PY'
import ast
import os
from pathlib import Path

source = Path(os.environ["INTEGRITY_DETACHER"]).read_text(encoding="utf-8")
tree = ast.parse(source)
popen_calls = [
    node for node in ast.walk(tree)
    if isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and node.func.attr == "Popen"
]
required = {"stdin", "stdout", "stderr", "start_new_session", "close_fds"}
if len(popen_calls) < 2:
    raise SystemExit(1)
for call in popen_calls:
    keywords = {keyword.arg: keyword.value for keyword in call.keywords}
    if not required.issubset(keywords):
        raise SystemExit(1)
    for name in ("stdin", "stdout", "stderr"):
        value = keywords[name]
        if not (
            isinstance(value, ast.Attribute)
            and value.attr == "DEVNULL"
        ):
            raise SystemExit(1)
    for name in ("start_new_session", "close_fds"):
        value = keywords[name]
        if not (isinstance(value, ast.Constant) and value.value is True):
            raise SystemExit(1)
PY
then
  pass "M1-C hooks valid; M2.4 metadata-only session-handoff is active and fail-open"
else
  bad "M1-C hook mechanics or M2.4 handoff semantics drifted"
fi

# 1) CLI surface: every frozen verb + flag must appear in dev-worktree.sh usage/dispatch.
if CONTRACT="$CONTRACT" DEV_SRC="$(cat "$DEV_WORKTREE" 2>/dev/null || true)" python3 - <<'PY'
import json, os, re, sys
c = json.load(open(os.environ["CONTRACT"]))
src = os.environ["DEV_SRC"]
missing = []
for verb in c["cli"]["verbs"]:
    if not re.search(rf'(^|\||\s){re.escape(verb)}\)\s', src):
        missing.append(f"verb:{verb}")
for verb, flags in c["cli"]["flags"].items():
    for fl in flags:
        if fl not in src:
            missing.append(f"flag:{verb}{fl}")
if missing:
    print("MISSING " + " ".join(missing), file=sys.stderr); sys.exit(1)
sys.exit(0)
PY
then
  pass "CLI verbs + flags match frozen contract"
else
  bad "CLI surface drifted from frozen contract (a removal/rename needs awa-contract.v2.json)"
fi

# 2) awa-worktree/v1 JSON shape: run the emitter on an empty tmp root, assert schema+top+summary
#    keys live and the emitter SOURCE declares each frozen repo/worktree/orphan key.
awa_tmp="$(mktemp -d)"
emit="$(bash "$DEV_WORKTREE" dashboard-data --root "$awa_tmp" 2>/dev/null || true)"
rmdir "$awa_tmp" 2>/dev/null || true
if CONTRACT="$CONTRACT" EMIT="$emit" EMITTER_SRC="$(cat "$EMITTER" 2>/dev/null || true)" python3 - <<'PY'
import json, os, sys
c = json.load(open(os.environ["CONTRACT"]))["dashboard_data"]
try:
    d = json.loads(os.environ["EMIT"])
except Exception as exc:
    print(f"emit not JSON: {exc}", file=sys.stderr); sys.exit(1)
src = os.environ["EMITTER_SRC"]
errs = []
if d.get("schema") != c["schema"]:
    errs.append(f'schema={d.get("schema")!r} != {c["schema"]!r}')
for k in c["top_keys"]:
    if k not in d:
        errs.append(f"top-key missing: {k}")
summ = d.get("summary", {})
for k in c["summary_keys"]:
    if k not in summ:
        errs.append(f"summary-key missing: {k}")
for level, keys in (("repo", c["repo_keys"]), ("worktree", c["worktree_keys"]), ("orphan_branch", c["orphan_branch_keys"])):
    for k in keys:
        if f'"{k}"' not in src:
            errs.append(f"{level}-key not authored in emitter: {k}")
if errs:
    print("SHAPE DRIFT: " + "; ".join(errs), file=sys.stderr); sys.exit(1)
sys.exit(0)
PY
then
  pass "awa-worktree/v1 JSON shape satisfies frozen floor (schema+summary live; repo/wt/orphan keys authored)"
else
  bad "awa-worktree/v1 JSON shape drifted from frozen contract"
fi

# 3) Guard permission schema: allow => {permission}; an included-primary MUTATION => an
#    ENFORCED deny {permission,user_message,agent_message} (Cursor honors deny; ask is
#    non-blocking — L4); afterFileEdit => allow (observation-only, X2).
#    STANDALONE UAT (no host dependency): a temp git repo under a temp governed root, with
#    AWA_GOVERNED_ROOT + a policy that classifies it include+primary.
guat="$(mktemp -d)"
repo="$guat/proj"
allow_json=""; deny_json=""; fileedit_json=""
if mkdir -p "$repo"; then
  ( unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES 2>/dev/null || true
    git init -q "$repo" && printf '#\n' > "$repo/f" && git -C "$repo" add f &&
    git -C "$repo" -c user.email="49759187+KleinPerkins@users.noreply.github.com" -c user.name="KleinPerkins" commit -qm init &&
    git -C "$repo" branch -M main &&
    git -C "$repo" remote add origin "git@github.com:KleinPerkins/awa-contract-temp.git" ) >/dev/null 2>&1
  # Non-mutating command -> fast-path allow (validates allow shape).
  allow_json="$(printf '{"cwd":"%s","command":"git status"}' "$repo" | \
    AWA_GOVERNED_ROOT="$guat" bash "$GUARD" 2>/dev/null || true)"
  # Mutating command on an included primary checkout -> enforced deny (validates deny shape).
  deny_json="$(printf '{"cwd":"%s","command":"git add f"}' "$repo" | \
    AWA_GOVERNED_ROOT="$guat" bash "$GUARD" 2>/dev/null || true)"
  # afterFileEdit (filePath, no command) -> observation-only allow (X2), never a no-op ask/deny.
  fileedit_json="$(printf '{"cwd":"%s","filePath":"%s"}' "$repo" "$repo/f" | \
    XDG_STATE_HOME="$guat/state" AWA_GOVERNED_ROOT="$guat" bash "$GUARD" 2>/dev/null || true)"
fi
rm -rf "$guat" 2>/dev/null || true
if CONTRACT="$CONTRACT" ALLOW="$allow_json" DENY="$deny_json" FILEEDIT="$fileedit_json" python3 - <<'PY'
import json, os, sys
c = json.load(open(os.environ["CONTRACT"]))["guard_permission"]
errs = []
# deny_shape must be DECLARED in the contract (frozen additive shape for the enforced block).
if "deny_shape" not in c:
    errs.append("contract guard_permission missing deny_shape")
# allow shape
try:
    a = json.loads(os.environ["ALLOW"])
except Exception:
    a = {}; errs.append("allow response not JSON")
if a.get("permission") not in c["permission_values"]:
    errs.append(f'allow.permission={a.get("permission")!r} not in {c["permission_values"]}')
if a.get("permission") == "allow" and set(a.keys()) - set(c["allow_shape"]):
    errs.append(f"allow shape has extra keys: {set(a.keys())}")
# deny shape (the load-bearing change): included-primary mutation must DENY with deny_shape.
try:
    k = json.loads(os.environ["DENY"])
except Exception:
    k = {}; errs.append("deny response not JSON")
if k.get("permission") != "deny":
    errs.append(f'expected deny on an included-primary mutation, got {k.get("permission")!r}')
else:
    for key in c.get("deny_shape", []):
        if key not in k:
            errs.append(f"deny shape missing: {key}")
# afterFileEdit is observation-only: MUST allow (never a no-op ask/deny) — X2.
try:
    fe = json.loads(os.environ["FILEEDIT"])
except Exception:
    fe = {}; errs.append("afterFileEdit response not JSON")
if fe.get("permission") != "allow":
    errs.append(f'afterFileEdit expected allow (observation-only), got {fe.get("permission")!r}')
if errs:
    print("GUARD SCHEMA DRIFT: " + "; ".join(errs), file=sys.stderr); sys.exit(1)
sys.exit(0)
PY
then
  pass "guard permission schema matches frozen contract (allow + enforced deny + deny_shape + afterFileEdit allow)"
else
  bad "guard permission schema drifted from frozen contract"
fi

# 3b) Git read-only family classifier UAT: deterministic read-only forms inside mutating
#     Git families must allow; mutating forms must still deny on an included primary.
guat_git="$(mktemp -d)"
repo_git="$guat_git/proj"
guard_git_cases=""
if mkdir -p "$repo_git"; then
  ( unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES 2>/dev/null || true
    git init -q "$repo_git" && printf '#\n' > "$repo_git/f" && git -C "$repo_git" add f &&
    git -C "$repo_git" -c user.email="49759187+KleinPerkins@users.noreply.github.com" -c user.name="KleinPerkins" commit -qm init &&
    git -C "$repo_git" branch -M main &&
    git -C "$repo_git" remote add origin "git@github.com:KleinPerkins/awa-contract-temp.git" ) >/dev/null 2>&1
  guard_git_cases="$(REPO="$repo_git" GUARD="$GUARD" ROOT="$guat_git" python3 - <<'PY'
import json, os, subprocess, sys
repo = os.environ["REPO"]
guard = os.environ["GUARD"]
root = os.environ["ROOT"]
cases = [
    ("git worktree list --porcelain", "allow"),
    ("git stash list", "allow"),
    ("git stash show --stat", "allow"),
    ("git clean --dry-run -d -x", "allow"),
    ("git clean -n .", "allow"),
    ("git branch --show-current", "allow"),
    ("git remote get-url origin", "allow"),
    ("git config --get remote.origin.url", "allow"),
    ("git submodule status", "allow"),
    ("git sparse-checkout list", "allow"),
    ("git worktree add ../awa-contract-wt", "deny"),
    ("git stash pop", "deny"),
    ("git clean -fdx", "deny"),
    ("git clean -f -- -n", "deny"),
    ("git fetch --dry-run", "deny"),
    ("git push --dry-run", "deny"),
    ("git push -n", "deny"),
    ("git branch -d topic", "deny"),
    ("git remote add upstream https://example.invalid/repo.git", "deny"),
    ("git config user.name changed", "deny"),
    ("git submodule update --init", "deny"),
    ("git sparse-checkout set src", "deny"),
    ("git sparse-checkout check-rules", "deny"),
]
out = []
for cmd, expected in cases:
    payload = json.dumps({"cwd": repo, "command": cmd})
    proc = subprocess.run(
        ["bash", guard],
        input=payload,
        capture_output=True,
        text=True,
        env={"AWA_GOVERNED_ROOT": root, **os.environ},
    )
    try:
        resp = json.loads(proc.stdout or "{}")
    except Exception:
        resp = {}
    out.append({"command": cmd, "expected": expected, "permission": resp.get("permission")})
print(json.dumps(out))
PY
)"
fi
rm -rf "$guat_git" 2>/dev/null || true
if GUARD_CASES="$guard_git_cases" python3 - <<'PY'
import json, os, sys
raw = os.environ.get("GUARD_CASES", "")
if not raw:
    print("git family guard UAT fixture missing", file=sys.stderr); sys.exit(1)
cases = json.loads(raw)
errs = []
for case in cases:
    got = case.get("permission")
    expected = case.get("expected")
    cmd = case.get("command")
    if got != expected:
        errs.append(f"{cmd!r}: expected {expected!r}, got {got!r}")
    if expected == "deny":
        if got == "deny":
            pass  # shape already covered in section 3
if errs:
    print("GIT FAMILY GUARD UAT: " + "; ".join(errs), file=sys.stderr); sys.exit(1)
sys.exit(0)
PY
then
  pass "git read-only family classifier allows read-only forms and denies mutating forms"
else
  bad "git read-only family classifier drifted from frozen contract expectations"
fi

# 3c) Protected-primary maintenance UAT: the role-resolved hook permits only the two
#     canonical operations in safe live state and keeps representative near misses denied.
maintenance_tmp="$(mktemp -d)"
maintenance_remote="$maintenance_tmp/remote.git"
maintenance_seed="$maintenance_tmp/seed"
maintenance_repo="$maintenance_tmp/proj"
maintenance_cases=""
if (
  export GIT_CONFIG_NOSYSTEM=1
  export GIT_CONFIG_SYSTEM=/dev/null
  export GIT_CONFIG_GLOBAL=/dev/null
  unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY \
    GIT_ALTERNATE_OBJECT_DIRECTORIES 2>/dev/null || true
  git init -q --bare "$maintenance_remote" &&
  git init -q "$maintenance_seed" &&
  printf 'one\n' > "$maintenance_seed/f" &&
  git -C "$maintenance_seed" add f &&
  git -C "$maintenance_seed" \
    -c user.email="49759187+KleinPerkins@users.noreply.github.com" \
    -c user.name="KleinPerkins" commit -qm initial &&
  git -C "$maintenance_seed" branch -M main &&
  git -C "$maintenance_seed" remote add origin "$maintenance_remote" &&
  git -C "$maintenance_seed" push -qu origin main &&
  git -C "$maintenance_remote" symbolic-ref HEAD refs/heads/main &&
  git clone -q "$maintenance_remote" "$maintenance_repo" &&
  printf 'two\n' >> "$maintenance_seed/f" &&
  git -C "$maintenance_seed" add f &&
  git -C "$maintenance_seed" \
    -c user.email="49759187+KleinPerkins@users.noreply.github.com" \
    -c user.name="KleinPerkins" commit -qm advance &&
  git -C "$maintenance_seed" push -q origin main &&
  git -C "$maintenance_repo" fetch -q origin
); then
  maintenance_cases="$(
    REPO="$maintenance_repo" GUARD="$GUARD" ROOT="$maintenance_tmp" \
      DEFAULT_POLICY="$AWA_HOME/kernel/policy/default-worktree-policy.yml" python3 - <<'PY'
import json
import os
import pathlib
import subprocess

repo = pathlib.Path(os.environ["REPO"])
guard = os.environ["GUARD"]
root = os.environ["ROOT"]
home = pathlib.Path(root) / "home"
for path in (home, home / ".config", home / ".local" / "state"):
    path.mkdir(parents=True, exist_ok=True)
drop = {
    "AWA_FORCE_CLOUD",
    "CURSOR_AGENT_IDENTITY_BROKER",
    "CURSOR_BACKGROUND_AGENT",
    "CURSOR_CLOUD_AGENT",
    "DEV_WORKTREE_GUARD_ALLOW_PRIMARY",
    "IS_BACKGROUND_AGENT",
    "cloud_agent_identity_broker",
    "is_background_agent",
}
guard_env = {
    key: value
    for key, value in os.environ.items()
    if not key.startswith("GIT_") and key not in drop
}
guard_env.update(
    {
        "AWA_GOVERNED_ROOT": root,
        "AWA_POLICY": os.environ["DEFAULT_POLICY"],
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_STATE_HOME": str(home / ".local" / "state"),
    }
)
cases = [
    ("canonical fetch", "git fetch", "allow", False),
    (
        "canonical fast-forward",
        "git merge --ff-only --no-overwrite-ignore",
        "allow",
        False,
    ),
    ("dirty state", "git fetch", "deny", True),
    (
        "wrong upstream ref",
        "git merge --ff-only --no-overwrite-ignore origin/wrong",
        "deny",
        False,
    ),
    ("environment laundering", "env GIT_DIR=.git git fetch", "deny", False),
    ("Git global option", "git -C . fetch", "deny", False),
    (
        "fetch refspec",
        "git fetch origin refs/heads/main:refs/remotes/origin/main",
        "deny",
        False,
    ),
    ("pull", "git pull --ff-only", "deny", False),
    ("push", "git push", "deny", False),
]
out = []
dirty_path = repo / "local-only"
for label, command, expected, dirty in cases:
    if dirty:
        dirty_path.write_text("local\n", encoding="utf-8")
    payload = json.dumps({"cwd": str(repo), "command": command})
    proc = subprocess.run(
        ["bash", guard],
        input=payload,
        capture_output=True,
        text=True,
        env=guard_env,
    )
    try:
        response = json.loads(proc.stdout or "{}")
    except Exception:
        response = {}
    out.append(
        {
            "label": label,
            "command": command,
            "expected": expected,
            "permission": response.get("permission"),
        }
    )
    if dirty:
        dirty_path.unlink()
print(json.dumps(out))
PY
  )"
fi
rm -rf "$maintenance_tmp" 2>/dev/null || true
if MAINTENANCE_CASES="$maintenance_cases" python3 - <<'PY'
import json
import os
import sys

raw = os.environ.get("MAINTENANCE_CASES", "")
if not raw:
    print("primary maintenance UAT fixture missing", file=sys.stderr)
    sys.exit(1)
try:
    cases = json.loads(raw)
except Exception as exc:
    print(f"primary maintenance UAT output not JSON: {exc}", file=sys.stderr)
    sys.exit(1)
errors = []
for case in cases:
    if case.get("permission") != case.get("expected"):
        errors.append(
            "{0}: {1!r} expected {2!r}, got {3!r}".format(
                case.get("label"),
                case.get("command"),
                case.get("expected"),
                case.get("permission"),
            )
        )
if errors:
    print("PRIMARY MAINTENANCE UAT: " + "; ".join(errors), file=sys.stderr)
    sys.exit(1)
PY
then
  pass "protected-primary maintenance allows canonical fetch/fast-forward and denies representative near misses"
else
  bad "protected-primary maintenance role-resolved hook behavior drifted"
fi

# 4) Lease shape: no component emits a lease yet, so assert the contract DECLARES the frozen shape.
if CONTRACT="$CONTRACT" python3 - <<'PY'
import json, os, sys
c = json.load(open(os.environ["CONTRACT"]))["lease"]
need = {"schema", "required_keys", "identity_rule", "collision_boundary", "wal_placement"}
missing = need - set(c.keys())
if missing:
    print(f"lease contract under-specified: missing {missing}", file=sys.stderr); sys.exit(1)
if c["schema"] != "awa-lease/v1":
    print(f'lease schema pinned wrong: {c["schema"]!r}', file=sys.stderr); sys.exit(1)
if "NEVER a bare pid" not in c["identity_rule"]:
    print("lease identity rule must forbid a bare pid", file=sys.stderr); sys.exit(1)
sys.exit(0)
PY
then
  pass "lease shape (awa-lease/v1) frozen as forward contract (identity != bare pid)"
else
  bad "lease shape contract is under-specified"
fi

# 5) Fail-safe classification: a legacy/typo per-repo mode VALUE and a legacy default_mode both
#    resolve to include (protected) — only `off` disables. STANDALONE fixture: a temp governed
#    root + a host policy pointing at a modes file with a removed legacy value.
mouat="$(mktemp -d)"
morepo="$mouat/proj"
cat > "$mouat/policy.yml" <<'YML'
version: 1
default: include
modes_file: modes.yml
YML
cat > "$mouat/modes.yml" <<'YML'
schema: awa-modes/v1
default_mode: on
modes:
  proj: legacy_removed_value
YML
failsafe_json=""
if mkdir -p "$morepo"; then
  ( unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES 2>/dev/null || true
    git init -q "$morepo" && printf '#\n' > "$morepo/f" && git -C "$morepo" add f &&
    git -C "$morepo" -c user.email="49759187+KleinPerkins@users.noreply.github.com" -c user.name="KleinPerkins" commit -qm init &&
    git -C "$morepo" branch -M main &&
    git -C "$morepo" remote add origin "git@github.com:KleinPerkins/awa-contract-temp.git" ) >/dev/null 2>&1
  # A mutating command on a repo whose explicit mode value is an unknown/legacy token must still
  # DENY (fail-safe: any non-`off` value -> include/protected).
  failsafe_json="$(printf '{"cwd":"%s","command":"git add f"}' "$morepo" | \
    AWA_GOVERNED_ROOT="$mouat" AWA_POLICY="$mouat/policy.yml" bash "$GUARD" 2>/dev/null || true)"
fi
rm -rf "$mouat" 2>/dev/null || true
if CONTRACT="$CONTRACT" FS="$failsafe_json" python3 - <<'PY'
import json, os, sys
errs = []
try:
    k = json.loads(os.environ["FS"])
except Exception:
    k = {}; errs.append("fail-safe guard response not JSON")
if k.get("permission") != "deny":
    errs.append(f'a legacy/unknown mode value must fail safe to deny, got {k.get("permission")!r}')
if errs:
    print("FAIL-SAFE DRIFT: " + "; ".join(errs), file=sys.stderr); sys.exit(1)
sys.exit(0)
PY
then
  pass "fail-safe: a legacy/unknown per-repo mode value resolves to include -> mutating primary denies"
else
  bad "fail-safe broken: a legacy/unknown mode value did not protect the repo (must deny)"
fi

ROOTS_LIB="$AWA_HOME/kernel/lib/awa_roots.py"

# 6) clean_receipt/v1 shape (additive-within-v1): the contract must DECLARE the receipt schema,
#    `clean --bundle` must stay v1-compatible, and a LIVE terminal clean (a refusal that needs no
#    git repo) must emit a schema-valid receipt. Exercised under a TEMP XDG_STATE_HOME so the
#    operator's real receipts dir is never touched.
crat="$(mktemp -d)"
receipt_ls=""
if [ -f "$ROOTS_LIB" ]; then
  # not_a_directory refusal -> a terminal clean path that emits a receipt with no git needed.
  XDG_STATE_HOME="$crat/state" bash "$DEV_WORKTREE" clean --path "$crat/nope" >/dev/null 2>&1 || true
  receipt_ls="$(XDG_STATE_HOME="$crat/state" python3 "$ROOTS_LIB" list-receipts --limit 5 2>/dev/null || true)"
fi
if CONTRACT="$CONTRACT" DEV_SRC="$(cat "$DEV_WORKTREE" 2>/dev/null || true)" RECEIPTS="$receipt_ls" \
   ROOTS_OK="$([ -f "$ROOTS_LIB" ] && echo 1 || echo 0)" python3 - <<'PY'
import json, os, sys
c = json.load(open(os.environ["CONTRACT"]))
errs = []
cr = c.get("clean_receipt")
if not isinstance(cr, dict):
    errs.append("contract missing clean_receipt block")
else:
    if cr.get("schema") != "clean_receipt/v1":
        errs.append(f'clean_receipt.schema={cr.get("schema")!r} != clean_receipt/v1')
    for k in ("required_keys", "disposition_values", "flags_keys"):
        if not isinstance(cr.get(k), list) or not cr.get(k):
            errs.append(f"clean_receipt.{k} missing/empty")
    if set(cr.get("disposition_values", [])) != {"removed", "refused", "error"}:
        errs.append(f'clean_receipt.disposition_values={cr.get("disposition_values")}')
    if "WITHIN v1" not in (cr.get("bundle_rule") or ""):
        errs.append("clean_receipt.bundle_rule must state --bundle stays WITHIN v1")
# --bundle honored: still a frozen `clean` flag (the v7 resolution, contract-compatible in v1).
if "bundle" not in [f.lstrip("-") for f in c["cli"]["flags"].get("clean", [])]:
    errs.append("--bundle missing from frozen clean flags (bundle-compat rule broken)")
# LIVE: the refusal terminal path emitted a schema-valid receipt (only when the kernel lib ships).
if os.environ.get("ROOTS_OK") == "1":
    try:
        receipts = json.loads(os.environ.get("RECEIPTS") or "[]")
    except Exception as exc:
        receipts = []; errs.append(f"live receipts not JSON: {exc}")
    if not receipts:
        errs.append("no clean_receipt emitted on a live terminal clean refusal path")
    else:
        r = receipts[0]
        for k in cr.get("required_keys", []):
            if k not in r:
                errs.append(f"live receipt missing required key: {k}")
        if r.get("schema") != "clean_receipt/v1":
            errs.append(f'live receipt schema={r.get("schema")!r}')
        if r.get("disposition") not in cr.get("disposition_values", []):
            errs.append(f'live receipt disposition={r.get("disposition")!r} not in vocabulary')
        if not isinstance(r.get("flags"), dict):
            errs.append("live receipt flags not an object")
if errs:
    print("CLEAN_RECEIPT DRIFT: " + "; ".join(errs), file=sys.stderr); sys.exit(1)
sys.exit(0)
PY
then
  pass "clean_receipt/v1 declared + --bundle v1-compatible + live terminal clean emits schema-valid receipt"
else
  bad "clean_receipt/v1 shape drifted (contract, --bundle compat, or live receipt emission)"
fi
rm -rf "$crat" 2>/dev/null || true

# 7) active_root/v1 shape (additive-within-v1): the contract must DECLARE the heartbeat schema +
#    the 5-state canonical disposition vocabulary, and a LIVE heartbeat/disposition round-trip
#    must classify a fresh root ACTIVE (blocks removal). TEMP XDG_STATE_HOME.
arat="$(mktemp -d)"
disp_json=""; rec_present="0"
if [ -f "$ROOTS_LIB" ]; then
  XDG_STATE_HOME="$arat/state" python3 "$ROOTS_LIB" heartbeat --root "$arat" >/dev/null 2>&1 || true
  disp_json="$(XDG_STATE_HOME="$arat/state" python3 "$ROOTS_LIB" disposition --root "$arat" 2>/dev/null || true)"
  rec_present=1
fi
if CONTRACT="$CONTRACT" DISP="$disp_json" ROOTS_OK="$rec_present" python3 - <<'PY'
import json, os, sys
c = json.load(open(os.environ["CONTRACT"]))
errs = []
ar = c.get("active_root")
if not isinstance(ar, dict):
    errs.append("contract missing active_root block")
else:
    if ar.get("schema") != "active_root/v1":
        errs.append(f'active_root.schema={ar.get("schema")!r} != active_root/v1')
    if not isinstance(ar.get("required_keys"), list) or not ar.get("required_keys"):
        errs.append("active_root.required_keys missing/empty")
    if set(ar.get("disposition_values", [])) != {"active", "stale", "dead", "untracked", "absent"}:
        errs.append(f'active_root.disposition_values={ar.get("disposition_values")}')
    if "source of truth" not in (ar.get("canonical_disposition") or "").lower():
        errs.append("active_root.canonical_disposition must name the single source of truth")
# LIVE: a fresh heartbeat -> disposition active + blocks_removal, record carries required keys.
if os.environ.get("ROOTS_OK") == "1":
    try:
        d = json.loads(os.environ.get("DISP") or "{}")
    except Exception as exc:
        d = {}; errs.append(f"live disposition not JSON: {exc}")
    if d.get("disposition") != "active":
        errs.append(f'fresh heartbeat disposition={d.get("disposition")!r} != active')
    if d.get("blocks_removal") is not True:
        errs.append("fresh active root must block removal")
    rec = d.get("record") or {}
    for k in ar.get("required_keys", []):
        if k not in rec:
            errs.append(f"live active_root record missing required key: {k}")
if errs:
    print("ACTIVE_ROOT DRIFT: " + "; ".join(errs), file=sys.stderr); sys.exit(1)
sys.exit(0)
PY
then
  pass "active_root/v1 declared + 5-state canonical disposition + live fresh heartbeat blocks removal"
else
  bad "active_root/v1 shape drifted (contract or live heartbeat/disposition round-trip)"
fi
rm -rf "$arat" 2>/dev/null || true

# 8) Finish additive schemas/keysets are exact-pinned to live constants and declared shapes.
if CONTRACT="$CONTRACT" AWA_HOME="$AWA_HOME" python3 - <<'PY'
import importlib.util, json, os, pathlib, sys
root = pathlib.Path(os.environ["AWA_HOME"])
contract = json.load(open(os.environ["CONTRACT"], encoding="utf-8"))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
ux = load("awa_finish_consumer_freeze", root / "consumer" / "finish_current.py")
fin = load("awa_finish_kernel_freeze", root / "kernel" / "lib" / "awa_finish.py")
roots = load("awa_roots_freeze", root / "kernel" / "lib" / "awa_roots.py")
durability = load("awa_durability_freeze", root / "kernel" / "lib" / "awa_durability.py")
fc = contract["finish_conversation"]
errors = []
checks = (
    (ux.DIALOGUE_SCHEMA, fc["dialogue"]["schema"], "dialogue schema"),
    (ux.CURRENT_INDEX_SCHEMA, fc["current_index"]["schema"], "index schema"),
    (ux.CHOICE_ENVELOPE_SCHEMA, fc["choice_envelope"]["schema"], "envelope schema"),
    (ux.HOOK_PUBLICATION_TICKET_SCHEMA,
     fc["hook"]["publication_ticket"]["schema"], "hook publication ticket schema"),
    (ux.RETAIN_SCHEMA, fc["protected_retain"]["schema"], "retain schema"),
    (ux.RETAIN_PUBLICATION_SCHEMA,
     fc["protected_retain"]["publication"]["schema"], "retain publication schema"),
    (fin.SCHEMA_RETAIN_PUBLICATION,
     fc["protected_retain"]["publication"]["schema"], "kernel retain publication schema"),
    (fin.SCHEMA_CHALLENGE, contract["awa_finish_challenge"]["schema"], "challenge schema"),
    (fin.SCHEMA_OPERATION_MANIFEST,
     contract["awa_git_operation_manifest"]["schema"], "operation manifest schema"),
    (fin.SCHEMA_GENERATION_STATE,
     contract["awa_finish_generation_state"]["schema"], "generation-state schema"),
    (fin.SCHEMA_REMOVAL_JOURNAL,
     contract["awa_finish_removal"]["schema"], "removal-journal schema"),
    (fin.SCHEMA_SELECTED_SNAPSHOT,
     fc["protected_retain"]["selected_snapshot"]["schema"], "snapshot schema"),
    (roots.SCHEMA_CURRENT_SESSION,
     contract["active_root"]["current_session_identity"]["schema"], "current-session schema"),
)
for live, declared, label in checks:
    if live != declared:
        errors.append(f"{label}: {live!r} != {declared!r}")
keyset_checks = (
    (ux.DIALOGUE_KEYS, fc["dialogue"]["declared_keys"], "dialogue keys"),
    (ux.CURRENT_INDEX_KEYS, fc["current_index"]["declared_keys"], "current-index keys"),
    (ux.CHOICE_ENVELOPE_KEYS, fc["choice_envelope"]["declared_keys"], "choice-envelope keys"),
    (ux.HOOK_PUBLICATION_TICKET_KEYS,
     fc["hook"]["publication_ticket"]["declared_keys"], "hook publication ticket keys"),
    (fin.CHALLENGE_KEYS, contract["awa_finish_challenge"]["declared_keys"], "challenge keys"),
    (fin.GENERATION_STATE_KEYS,
     contract["awa_finish_generation_state"]["declared_keys"], "generation-state keys"),
    (fin.REMOVAL_JOURNAL_KEYS,
     contract["awa_finish_removal"]["declared_keys"], "removal-journal keys"),
    (roots.ACTIVE_SESSION_KEYS,
     contract["active_root"]["sessions_field"]["member_declared_keys"],
     "active-root session-member keys"),
    (roots.CURRENT_SESSION_KEYS,
     contract["active_root"]["current_session_identity"]["declared_keys"],
     "current-session keys"),
)
for live, declared, label in keyset_checks:
    if set(live) != set(declared):
        errors.append(f"{label}: live/contract drift")
if set(fin.GENERATION_TRANSITIONS) != set(
        contract["awa_finish_generation_state"]["transition_values"]):
    errors.append("generation-state transition vocabulary drift")
if set(fin.REMOVAL_PHASES) != set(contract["awa_finish_removal"]["phase_values"]):
    errors.append("removal-journal phase vocabulary drift")
operation_contract = contract["awa_git_operation_manifest"]
if set(fin._OPERATION_GROUP_COPY) != set(operation_contract["groups"]):
    errors.append("operation group vocabulary drift")
if fin.OPERATION_CLASSIFICATION_VERSION != operation_contract["classification_version"]:
    errors.append("operation classification version drift")
if fin.INVENTORY_FINGERPRINT_VERSION != operation_contract["inventory_fingerprint_version"]:
    errors.append("inventory fingerprint version drift")
if fin.INVENTORY_STRUCTURE_VERSION != operation_contract["inventory_structure_version"]:
    errors.append("inventory structure version drift")
if fin.RETAIN_CLASSIFICATION_VERSION != operation_contract["retain_classification_version"]:
    errors.append("retain classification version drift")
for name in (
        "_sync_fd", "write_all", "atomic_private_replace", "create_private_exclusive",
        "durable_unlink", "durable_adopt", "adopt_visible",
        "ensure_private_directory", "sync_directory", "sync_regular"):
    if not callable(getattr(durability, name, None)):
        errors.append(f"shared durability primitive missing {name}")
if "operation_id" not in contract["clean_receipt"]["finish_fields"]["keys"]:
    errors.append("clean receipt operation_id not declared")
visibility_rule = contract["clean_receipt"]["finish_fields"].get(
    "finish_index_visibility_rule", "")
if fin.INDEX_VISIBILITY_REFUSAL != "index_visibility_flags":
    errors.append("finish index-visibility refusal token drift")
for required in (
        "assume-unchanged", "skip-worktree", "fsmonitor", "SHA-1", "SHA-256",
        "GIT_OPTIONAL_LOCKS=0", "GIT_NO_LAZY_FETCH=1", "ordinary `clean --path`",
):
    if required not in visibility_rule:
        errors.append(f"finish index-visibility contract missing {required}")
expected = {
    "dialogue": {"schema","recognizer_version","conversation_id","session_id","state",
                 "target","fingerprint","structure_fingerprint","nonce","generation",
                 "hook_mode","visible","rows","created_at_epoch","action_kind","action_commit_complete",
                 "action_retain_complete","action_artifact_id"},
    "current_index": {"schema","root","session_id","conversation_id","generation","nonce",
                      "fingerprint","created_at_epoch"},
    "choice_envelope": {"schema","root","session_id","conversation_id","generation","nonce",
                        "exact_text","canonical_choice","attachments_present","event_id",
                        "created_at_epoch"},
}
for name, keys in expected.items():
    if set(fc[name]["declared_keys"]) != keys:
        errors.append(f"{name}.declared_keys drift")
snapshot_keys = {"schema","selected_paths","status_hex","index_hex","entries"}
if set(fc["protected_retain"]["selected_snapshot"]["declared_keys"]) != snapshot_keys:
    errors.append("selected_snapshot.declared_keys drift")
if set(fc["protected_retain"]["publication"]["declared_keys"]) != set(
        ux.RETAIN_PUBLICATION_KEYS):
    errors.append("retain publication declared_keys drift")
if set(fc["protected_retain"]["manifest_declared_keys"]) != set(
        ux.RETAIN_MANIFEST_KEYS):
    errors.append("retain manifest declared_keys drift")
if set(fin.RETAIN_PUBLICATION_KEYS) != set(ux.RETAIN_PUBLICATION_KEYS):
    errors.append("kernel/consumer retain publication key drift")
if fc["protected_retain"]["publication"].get("protocol") != ux.RETAIN_PUBLICATION_PROTOCOL:
    errors.append("retain publication protocol drift")
public_projection = fc["dialogue"]["public_projection"]
if public_projection.get("outcomes") != [
        item.value for item in ux.PublicDispatchOutcome]:
    errors.append("public projection outcome vocabulary drift")
if public_projection.get("reasons") != [
        item.value for item in ux.PublicDispatchReason]:
    errors.append("public projection reason vocabulary drift")
if public_projection.get("branch_results") != [
        item.value for item in ux.PublicBranchResult]:
    errors.append("public projection branch vocabulary drift")
if public_projection.get("selection_states") != [
        item.value for item in ux.PublicSelectionState]:
    errors.append("public projection selection vocabulary drift")
if public_projection.get("action_states") != ["action_complete_refresh_pending"]:
    errors.append("public projection action-state vocabulary drift")
if public_projection.get("shell_machine_mode_env") != ux.FINISH_PUBLIC_PROJECTION_ENV:
    errors.append("public projection shell machine-mode environment drift")
shell_text = (root / "kernel" / "bin" / "dev-worktree.sh").read_text(encoding="utf-8")
if ux.FINISH_PUBLIC_PROJECTION_ENV not in shell_text:
    errors.append("public projection shell machine mode missing")
session_keys = {"schema","root","session_id","conversation_id","session_key","branch",
                "common_dir","boot_id","updated_at_epoch"}
if set(contract["active_root"]["current_session_identity"]["declared_keys"]) != session_keys:
    errors.append("current_session_identity.declared_keys drift")
hook_entry = fc["hook"].get("installed_entry")
if hook_entry != {"command_role": "kernel/hooks/before-submit-prompt.sh", "type": "command",
                  "matcher": "UserPromptSubmit", "timeout": 20, "failClosed": False}:
    errors.append("hook.installed_entry drift")
if fc["hook"].get("output_shape") != ["continue", "user_message"]:
    errors.append("hook.output_shape drift")
if fc["hook"].get("continue_shape") != ["continue"]:
    errors.append("hook.continue_shape drift")
if errors:
    print("PHASE2 CONTRACT DRIFT: " + "; ".join(errors), file=sys.stderr)
    sys.exit(1)
PY
then
  pass "Finish schemas, constants, and declared keysets exact-pinned"
else
  bad "Finish contract/code constants or keysets drifted"
fi

if [ "$fail" -eq 0 ]; then
  echo "awa-contract-freeze: OK"
else
  echo "awa-contract-freeze: FAILED"
fi
exit "$fail"
