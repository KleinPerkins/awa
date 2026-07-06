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

# 5+6) Per-repo MODE ask_on is a FIRST-CLASS behavior, ADDITIVE WITHIN v1 (no v2). One shared
#      STANDALONE fixture: a temp governed root + a host policy pointing at a modes file that
#      classifies the repo `proj` as ask_on. From it we assert BOTH the guard ask outcome and
#      the dashboard surfacing. No host dependency; the modes_file is resolved relative to the
#      temp policy's own directory.
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
  proj: ask_on
YML
askon_guard_json=""; askon_emit=""
if mkdir -p "$morepo"; then
  ( unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES 2>/dev/null || true
    git init -q "$morepo" && printf '#\n' > "$morepo/f" && git -C "$morepo" add f &&
    git -C "$morepo" -c user.email="49759187+KleinPerkins@users.noreply.github.com" -c user.name="KleinPerkins" commit -qm init &&
    git -C "$morepo" branch -M main &&
    git -C "$morepo" remote add origin "git@github.com:KleinPerkins/awa-contract-temp.git" ) >/dev/null 2>&1
  # (a) GUARD: a mutating command on an ask_on primary checkout -> frozen `ask` shape.
  askon_guard_json="$(printf '{"cwd":"%s","command":"git add f"}' "$morepo" | \
    AWA_GOVERNED_ROOT="$mouat" AWA_POLICY="$mouat/policy.yml" "$GUARD" 2>/dev/null || true)"
  # (b) DASHBOARD: the emitter tolerates + surfaces ask_on without a summary-map KeyError.
  askon_emit="$(AWA_GOVERNED_ROOT="$mouat" AWA_POLICY="$mouat/policy.yml" \
    "$DEV_WORKTREE" dashboard-data --root "$mouat" 2>/dev/null || true)"
fi
rm -rf "$mouat" 2>/dev/null || true

# 5) Guard: ask_on asks on a mutating primary exactly like include/on (frozen ask shape).
if CONTRACT="$CONTRACT" ASKON="$askon_guard_json" python3 - <<'PY'
import json, os, sys
c = json.load(open(os.environ["CONTRACT"]))["guard_permission"]
errs = []
try:
    k = json.loads(os.environ["ASKON"])
except Exception:
    k = {}; errs.append("ask_on guard response not JSON")
if k.get("permission") != "ask":
    errs.append(f'ask_on mutating primary expected ask, got {k.get("permission")!r}')
else:
    for key in c["ask_shape"]:
        if key not in k:
            errs.append(f"ask shape missing: {key}")
    if k.get("permission") not in c["permission_values"]:
        errs.append(f'permission {k.get("permission")!r} not in {c["permission_values"]}')
if errs:
    print("ASK_ON GUARD DRIFT: " + "; ".join(errs), file=sys.stderr); sys.exit(1)
sys.exit(0)
PY
then
  pass "ask_on classification yields the frozen ask shape on a mutating primary (additive within v1)"
else
  bad "ask_on guard behavior missing/broken (a mutating primary must ASK for an ask_on repo)"
fi

# 6) Dashboard: the emitter tolerates ask_on (no KeyError) and surfaces the OPTIONAL summary.ask_on
#    key + an ask_on repo row, while the frozen required floor (schema + summary_keys) stays intact.
if CONTRACT="$CONTRACT" EMIT="$askon_emit" python3 - <<'PY'
import json, os, sys
c = json.load(open(os.environ["CONTRACT"]))["dashboard_data"]
errs = []
try:
    d = json.loads(os.environ["EMIT"])
except Exception as exc:
    print(f"ask_on emit not JSON (summary-map KeyError/crash on ask_on?): {exc}", file=sys.stderr); sys.exit(1)
# Frozen required floor must remain intact (the additive ask_on path must not drop it).
if d.get("schema") != c["schema"]:
    errs.append(f'schema={d.get("schema")!r} != {c["schema"]!r}')
summ = d.get("summary", {})
for k in c["summary_keys"]:
    if k not in summ:
        errs.append(f"required summary-key dropped: {k}")
# Additive: ask_on must be surfaced (optional key present + counted) and appear as a repo row.
if "ask_on" not in summ:
    errs.append("optional summary.ask_on not surfaced when modes configure ask_on")
elif not isinstance(summ.get("ask_on"), int) or summ.get("ask_on", 0) < 1:
    errs.append(f'summary.ask_on={summ.get("ask_on")!r} did not count the ask_on repo')
if not any(r.get("classification") == "ask_on" for r in d.get("repos", [])):
    errs.append("no repo surfaced with classification ask_on")
if errs:
    print("ASK_ON DASHBOARD DRIFT: " + "; ".join(errs), file=sys.stderr); sys.exit(1)
sys.exit(0)
PY
then
  pass "dashboard emitter surfaces ask_on additively (summary.ask_on present + counted; required floor intact; no KeyError)"
else
  bad "dashboard emitter does not tolerate/surface ask_on (summary.ask_on / count / KeyError / floor)"
fi

if [ "$fail" -eq 0 ]; then
  echo "awa-contract-freeze: OK"
else
  echo "awa-contract-freeze: FAILED"
fi
exit "$fail"
