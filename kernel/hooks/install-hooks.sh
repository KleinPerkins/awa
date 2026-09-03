#!/usr/bin/env bash
# install-hooks.sh — reconcile or verify AWA-owned Cursor user-hook rows.
set -euo pipefail

MODE="install"
case "${1:-}" in
  --check) MODE="check" ;;
  "") ;;
  *) printf 'usage: %s [--check]\n' "$0" >&2; exit 2 ;;
esac

HOOK_OWNER="${AWA_HOOK_OWNER-direct}"
case "$HOOK_OWNER" in
  direct) ;;
  external)
    printf '%s\n' "install-hooks: hook owner external; selected hook file not inspected by AWA"
    exit 0
    ;;
  *)
    printf '%s\n' "install-hooks: hook-owner selection is invalid" >&2
    exit 2
    ;;
esac

# The selected destination is not resolved until after the external-owner return.
# External mode performs zero selected-hook-file reads, stats, directory creation,
# chmod, backups, writes, or row rendering.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd -P)"
AWA_HOME="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
HOOKS_JSON="${AWA_HOOKS_JSON:-$HOME/.cursor/hooks.json}"
V1_CONTRACT="$AWA_HOME/contracts/awa-contract.v1.json"
V2_CONTRACT="$AWA_HOME/contracts/awa-hook-owner.v2.json"

MODE="$MODE" HOOKS_JSON="$HOOKS_JSON" AWA_HOME="$AWA_HOME" \
V1_CONTRACT="$V1_CONTRACT" V2_CONTRACT="$V2_CONTRACT" python3 - <<'PY'
from __future__ import annotations

import json
import os
import pathlib
import shutil
import stat
import sys
import tempfile
import time


def refuse(message: str, *, check: bool = False) -> None:
    prefix = "install-hooks --check" if check else "install-hooks"
    print(f"{prefix}: {message}", file=sys.stderr)
    raise SystemExit(1)


mode = os.environ["MODE"]
checking = mode == "check"
root = pathlib.Path(os.environ["AWA_HOME"]).resolve()
source_checkout = (root / ".git").exists()
destination = pathlib.Path(os.environ["HOOKS_JSON"]).expanduser()
v1_path = pathlib.Path(os.environ["V1_CONTRACT"])
v2_path = pathlib.Path(os.environ["V2_CONTRACT"])


def load_json(path: pathlib.Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        refuse(f"{label} is missing or invalid JSON: {exc}", check=checking)
    if not isinstance(value, dict):
        refuse(f"{label} must be a JSON object", check=checking)
    return value


def valid_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("type") != "command":
        return False
    if type(entry.get("timeout")) is not int or entry["timeout"] <= 0:
        return False
    if "failClosed" in entry and type(entry["failClosed"]) is not bool:
        return False
    return "command" not in entry


def valid_role(role: object, *, allow_dormant: bool) -> bool:
    if not isinstance(role, dict):
        return False
    required = {
        "id",
        "event",
        "direct_command_role",
        "external_command_path_class",
        "entry",
    }
    allowed = required | ({"dormant_until_milestone"} if allow_dormant else set())
    if set(role) - allowed or not required.issubset(role):
        return False
    if not all(
        isinstance(role[key], str) and role[key]
        for key in (
            "id",
            "event",
            "direct_command_role",
            "external_command_path_class",
        )
    ):
        return False
    if role["external_command_path_class"] not in {
        "host-policy-delegator",
        "installed-awa",
    }:
        return False
    relative = pathlib.PurePosixPath(role["direct_command_role"])
    if relative.is_absolute() or ".." in relative.parts:
        return False
    command = (root / relative).resolve()
    try:
        command.relative_to(root)
    except ValueError:
        return False
    try:
        command_mode = command.lstat().st_mode
    except OSError:
        return False
    if (
        not stat.S_ISREG(command_mode)
        or command_mode & 0o111 == 0
    ):
        return False
    if source_checkout:
        if not os.access(command, os.R_OK):
            return False
    elif not os.access(command, os.X_OK):
        return False
    return valid_entry(role["entry"])


v1_doc = load_json(v1_path, "awa-contract.v1.json")
v1 = v1_doc.get("hook_ownership")
v1_ids = [
    "worktree.session-context",
    "worktree.shell-guard",
    "worktree.file-observer",
    "recovery.maintenance",
    "finish.prompt-recall",
]
if (
    not isinstance(v1, dict)
    or v1.get("schema") != "awa-hook-owner/v1"
    or v1.get("modes") != ["direct", "external"]
    or v1.get("default_mode") != "direct"
    or v1.get("selection_env") != "AWA_HOOK_OWNER"
    or v1.get("selection_schema") != "awa-hook-owner-selection/v1"
    or v1.get("external_real_hook_file_writes") is not False
    or not isinstance(v1.get("roles"), list)
    or [role.get("id") for role in v1["roles"] if isinstance(role, dict)]
    != v1_ids
    or not all(valid_role(role, allow_dormant=False) for role in v1["roles"])
):
    refuse("awa-hook-owner/v1 contract validation failed", check=checking)

contract_name = "awa-hook-owner/v1"
effective = list(v1["roles"])
all_roles = list(v1["roles"])
if v2_path.is_file():
    v2 = load_json(v2_path, "awa-hook-owner.v2.json")
    expected_v2 = [
        (
            "worktree.shell-guard-composite",
            "beforeShellExecution",
            "kernel/hooks/worktree-guard-with-integrity.sh",
            "host-policy-delegator",
            {"type": "command", "timeout": 20, "failClosed": False},
            None,
        ),
        (
            "worktree.stop-observer",
            "stop",
            "kernel/hooks/awa-integrity-observer.sh",
            "host-policy-delegator",
            {"type": "command", "timeout": 5, "failClosed": False},
            None,
        ),
        (
            "worktree.session-handoff",
            "sessionStart",
            "kernel/hooks/awa-session-handoff.sh",
            "host-policy-delegator",
            {"type": "command", "timeout": 5, "failClosed": False},
            "M2.4",
        ),
    ]
    v2_roles = v2.get("roles")
    actual_v2 = [
        (
            role.get("id"),
            role.get("event"),
            role.get("direct_command_role"),
            role.get("external_command_path_class"),
            role.get("entry"),
            role.get("dormant_until_milestone"),
        )
        for role in v2_roles
        if isinstance(role, dict)
    ] if isinstance(v2_roles, list) else []
    if (
        v2.get("schema") != "awa-hook-owner/v2"
        or v2.get("version") != 2
        or v2.get("successor_of") != "awa-hook-owner/v1"
        or v2.get("v1_contract")
        != "contracts/awa-contract.v1.json#hook_ownership"
        or v2.get("modes") != ["direct", "external"]
        or v2.get("default_mode") != "direct"
        or v2.get("selection_env") != "AWA_HOOK_OWNER"
        or v2.get("selection_schema") != "awa-hook-owner-selection/v1"
        or v2.get("external_real_hook_file_writes") is not False
        or v2.get("supersedes_roles") != ["worktree.shell-guard"]
        or not isinstance(v2.get("composition_rule"), str)
        or not v2["composition_rule"]
        or not isinstance(v2.get("external_rule"), str)
        or not v2["external_rule"]
        or actual_v2 != expected_v2
        or not all(valid_role(role, allow_dormant=True) for role in v2_roles or [])
        or v2_roles[-1].get("dormant_until_milestone") != "M2.4"
        or any(
            role.get("external_command_path_class") != "host-policy-delegator"
            or role["entry"].get("failClosed") is not False
            for role in v2_roles or []
        )
    ):
        refuse("awa-hook-owner/v2 contract validation failed", check=checking)
    superseded = set(v2["supersedes_roles"])
    effective = [role for role in v1["roles"] if role["id"] not in superseded]
    effective.extend(v2_roles)
    all_roles.extend(v2_roles)
    contract_name = "awa-hook-owner/v2"


def resolved_command(role: dict) -> pathlib.Path:
    return (root / role["direct_command_role"]).resolve()


def row_for(role: dict) -> dict:
    row = dict(role["entry"])
    row["command"] = str(resolved_command(role))
    return row


def awa_owned(entry: dict) -> bool:
    command = entry.get("command")
    if not isinstance(command, str) or not command:
        return False
    resolved = pathlib.Path(command).expanduser().resolve()
    for role in all_roles:
        wanted = resolved_command(role)
        if resolved == wanted:
            return True
        parts = resolved.parts
        if len(parts) >= 5 and parts[-5:] == (
            "awa",
            "current",
            "kernel",
            "hooks",
            wanted.name,
        ):
            return True
    return False


def load_destination() -> dict:
    if destination.is_symlink():
        refuse(f"refusing symlink destination {destination}", check=checking)
    if not destination.exists():
        if checking:
            refuse(f"missing required {destination}", check=True)
        return {"version": 1, "hooks": {}}
    if not destination.is_file():
        refuse(f"refusing non-regular destination {destination}", check=checking)
    try:
        data = json.loads(destination.read_text(encoding="utf-8"))
    except Exception as exc:
        refuse(
            f"{destination} is not valid JSON: {exc}",
            check=checking,
        )
    if (
        not isinstance(data, dict)
        or data.get("version") != 1
        or not isinstance(data.get("hooks"), dict)
    ):
        refuse(
            "refusing invalid object/version/hooks shape without writing",
            check=checking,
        )
    for event, rows in data["hooks"].items():
        if (
            not isinstance(event, str)
            or not isinstance(rows, list)
            or not all(isinstance(row, dict) for row in rows)
        ):
            refuse("refusing malformed hooks shape without writing", check=checking)
    return data


data = load_destination()
hooks = data["hooks"]
wanted_by_event: dict[str, list[dict]] = {}
for role in effective:
    wanted_by_event.setdefault(role["event"], []).append(row_for(role))

if checking:
    errors: list[str] = []
    for event, wanted_rows in wanted_by_event.items():
        actual = hooks.get(event)
        if not isinstance(actual, list):
            errors.append(f"{event}: missing/non-list")
            continue
        for wanted in wanted_rows:
            count = actual.count(wanted)
            if count != 1:
                errors.append(
                    f"{event}[{pathlib.Path(wanted['command']).name}]: "
                    f"expected one exact AWA row, found {count}"
                )
    for event, rows in hooks.items():
        wanted_rows = wanted_by_event.get(event, [])
        for row in rows:
            if awa_owned(row) and row not in wanted_rows:
                errors.append(f"{event}: stale or drifted AWA-owned row")
    if errors:
        refuse("; ".join(errors), check=True)
    print(f"install-hooks --check: exact {contract_name} AWA entries OK")
    raise SystemExit(0)

for event in list(hooks):
    hooks[event] = [row for row in hooks[event] if not awa_owned(row)]
    if not hooks[event]:
        hooks.pop(event)
for role in effective:
    hooks.setdefault(role["event"], []).append(row_for(role))

new = json.dumps(data, indent=2, sort_keys=False) + "\n"
old = destination.read_text(encoding="utf-8") if destination.exists() else None
if old == new:
    print(f"install-hooks: already current {destination} ({contract_name})")
    raise SystemExit(0)

destination.parent.mkdir(parents=True, exist_ok=True)
if destination.is_symlink():
    refuse(f"refusing symlink destination {destination}")
prior_mode = stat.S_IMODE(destination.stat().st_mode) if destination.exists() else 0o600
if destination.exists():
    backup = destination.with_name(
        destination.name + f".bak-{time.time_ns()}"
    )
    shutil.copy2(destination, backup, follow_symlinks=False)

temporary: pathlib.Path | None = None
try:
    fd, name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.awa-",
    )
    temporary = pathlib.Path(name)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(new)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, prior_mode)
    os.replace(temporary, destination)
    temporary = None
    try:
        parent_fd = os.open(
            destination.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
    except OSError:
        parent_fd = None
    if parent_fd is not None:
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
finally:
    if temporary is not None:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass

print(f"install-hooks: updated {destination} ({contract_name})")
PY
