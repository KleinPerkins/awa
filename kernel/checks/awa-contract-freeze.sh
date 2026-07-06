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
DEV_WORKTREE="$AWA_HOME/kernel/bin/dev-worktree.sh"
GUARD="$AWA_HOME/kernel/hooks/worktree-guard.sh"
EMITTER="$AWA_HOME/dashboard/emitter.py"

fail=0
pass() { printf '  PASS  %s\n' "$1"; }
bad()  { printf '  FAIL  %s\n' "$1"; fail=1; }

echo "== AWA kernel contract freeze (v1, behavior-only, role-resolved) =="
echo "   AWA_HOME=$AWA_HOME"

if [ ! -f "$CONTRACT" ]; then
  bad "frozen contract missing: $CONTRACT"; echo "awa-contract-freeze: FAILED"; exit 1
fi
if ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$CONTRACT" 2>/dev/null; then
  bad "frozen contract is not valid JSON: $CONTRACT"; echo "awa-contract-freeze: FAILED"; exit 1
fi
pass "frozen contract present + valid JSON"
for f in "$DEV_WORKTREE" "$GUARD" "$EMITTER"; do
  [ -f "$f" ] || bad "role-resolved shim missing: $f"
done

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
emit="$("$DEV_WORKTREE" dashboard-data --root "$awa_tmp" 2>/dev/null || true)"
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

# 3) Guard permission schema: allow => {permission}; ask => {permission,user_message,agent_message}.
#    STANDALONE UAT (no host dependency): a temp git repo under a temp governed root, with
#    AWA_GOVERNED_ROOT + a policy that classifies it include+primary, so the guard returns `ask`.
guat="$(mktemp -d)"
repo="$guat/proj"
allow_json=""; ask_json=""
if mkdir -p "$repo"; then
  ( unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES 2>/dev/null || true
    git init -q "$repo" && printf '#\n' > "$repo/f" && git -C "$repo" add f &&
    git -C "$repo" -c user.email="49759187+KleinPerkins@users.noreply.github.com" -c user.name="KleinPerkins" commit -qm init &&
    git -C "$repo" branch -M main &&
    git -C "$repo" remote add origin "git@github.com:KleinPerkins/awa-contract-temp.git" ) >/dev/null 2>&1
  # Non-mutating command -> fast-path allow (validates allow shape).
  allow_json="$(printf '{"cwd":"%s","command":"git status"}' "$repo" | \
    AWA_GOVERNED_ROOT="$guat" "$GUARD" 2>/dev/null || true)"
  # Mutating command on an included primary checkout -> ask (validates ask shape).
  ask_json="$(printf '{"cwd":"%s","command":"git add f"}' "$repo" | \
    AWA_GOVERNED_ROOT="$guat" "$GUARD" 2>/dev/null || true)"
fi
rm -rf "$guat" 2>/dev/null || true
if CONTRACT="$CONTRACT" ALLOW="$allow_json" ASK="$ask_json" python3 - <<'PY'
import json, os, sys
c = json.load(open(os.environ["CONTRACT"]))["guard_permission"]
errs = []
try:
    a = json.loads(os.environ["ALLOW"])
except Exception:
    a = {}; errs.append("allow response not JSON")
if a.get("permission") not in c["permission_values"]:
    errs.append(f'allow.permission={a.get("permission")!r} not in {c["permission_values"]}')
if a.get("permission") == "allow" and set(a.keys()) - set(c["allow_shape"]):
    errs.append(f"allow shape has extra keys: {set(a.keys())}")
try:
    k = json.loads(os.environ["ASK"])
except Exception:
    k = {}; errs.append("ask response not JSON")
if k.get("permission") != "ask":
    errs.append(f'expected ask, got {k.get("permission")!r}')
else:
    for key in c["ask_shape"]:
        if key not in k:
            errs.append(f"ask shape missing: {key}")
if errs:
    print("GUARD SCHEMA DRIFT: " + "; ".join(errs), file=sys.stderr); sys.exit(1)
sys.exit(0)
PY
then
  pass "guard permission schema matches frozen contract (allow + ask shapes)"
else
  bad "guard permission schema drifted from frozen contract"
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

if [ "$fail" -eq 0 ]; then
  echo "awa-contract-freeze: OK"
else
  echo "awa-contract-freeze: FAILED"
fi
exit "$fail"
