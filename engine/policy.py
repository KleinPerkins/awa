"""policy.py — generic, zero-link repo classifier (kernel policy resolver).

Reads a machine-local policy file (worktree-policy.yml) that supplies the
governed roots, include/exclude globs, and detectors. Classification is decided
GENERICALLY here — this module carries ZERO org-specific literals (§D3):

  * governed-marker detector: a repo that carries its OWN governance marker
    (e.g. `_ops/POLICY.md`) is self-governed -> `exclude`. This captures a
    self-governed sibling repo WITHOUT naming it.
  * foreign-hook detector: a repo whose `core.hooksPath` points at a foreign hook
    framework (husky/lefthook/pre-commit) -> `exclude`.
  * include/exclude globs + read-only paths come from the policy file (which MAY
    name org/vendor literals, because it is machine-local and never vendored).

Only a tiny YAML subset is parsed (stdlib only): scalars, `- ` lists, and one level
of nested maps under a top-level key. That is all worktree-policy.yml needs.
"""

from __future__ import annotations

import fnmatch
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

INCLUDE = "include"
EXCLUDE = "exclude"
ADVISORY = "advisory"
NOT_GIT = "not-git"

# Explicit per-repo mode values (awa-modes/v1). Kept as a tuple so callers can
# distinguish a present-but-invalid mode value from a valid one. ONE fail-safe rule
# governs every read/write path: only `off` disables protection; ANY other value
# (a typo, a removed legacy value, an unknown) resolves to ON/include.
MODE_VALUES = ("on", "off")


def _parse_mini_yaml(text: str) -> dict:
    """Parse the small YAML subset worktree-policy.yml uses. Returns nested dict/list.

    Supported: `key: scalar`, inline `key: []`/`key: {}`, `key:` then an indented
    `- item` list, and `key:` then an indented `subkey:` map (one or more levels).
    Comments (#) and blank lines are ignored. Indentation-driven (any consistent step).

    A `key:` with an empty value creates a placeholder that becomes a LIST on the first
    `- item` child or stays a MAP on the first `subkey:` child.
    """
    root: dict = {}
    # frames: {"indent", "container", "parent", "key"}; container is a dict or a list.
    stack: list[dict] = [{"indent": -1, "container": root, "parent": None, "key": None}]

    for raw in text.splitlines():
        line = raw.split(" #", 1)[0] if " #" in raw else raw
        line = line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))

        while len(stack) > 1 and indent <= stack[-1]["indent"]:
            stack.pop()
        top = stack[-1]
        container = top["container"]

        if stripped.startswith("- "):
            item = stripped[2:].strip().strip("'\"")
            if isinstance(container, dict) and container == {} and top["parent"] is not None:
                new_list: list = []
                top["parent"][top["key"]] = new_list
                top["container"] = new_list
                container = new_list
            if isinstance(container, list):
                container.append(item)
            continue

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip("'\"")
            if not isinstance(container, dict):
                continue
            if val in ("[]", "{}"):
                container[key] = [] if val == "[]" else {}
            elif val:
                container[key] = val
            else:
                child: dict = {}
                container[key] = child
                stack.append({"indent": indent, "container": child,
                              "parent": container, "key": key})
    return root


def _modes_from_data(data: dict) -> tuple[dict, str | None]:
    """Extract (modes, default_mode) from one parsed policy/modes document.

    `modes` values are case-normalized; `default_mode` is None when absent so callers
    can distinguish "not specified" from an explicit value during merge.
    """
    modes: dict = {}
    raw = data.get("modes")
    if isinstance(raw, dict):
        for k, v in raw.items():
            modes[str(k)] = str(v).strip().lower()
    dm = data.get("default_mode")
    default_mode = str(dm).strip().lower() if dm is not None else None
    return modes, default_mode


def _read_regular_text(path: str | Path) -> str:
    """Read one regular file without blocking on FIFOs or following symlinks."""
    flags = os.O_RDONLY
    flags |= getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(f"not a regular file: {path}")
        with os.fdopen(fd, "r", encoding="utf-8") as fh:
            fd = -1
            return fh.read()
    finally:
        if fd >= 0:
            os.close(fd)


def _resolve_modes(data: dict, policy_path: str | Path) -> tuple[dict, str]:
    """Resolve the explicit modes map + default_mode from inline policy values and an
    optional `modes_file:` pointer.

    The pointer is resolved relative to the policy file's directory (~ and absolute paths
    honored). A readable regular referenced file (schema awa-modes/v1) is MERGED over the
    inline values, the referenced file winning on key collision. A missing file leaves the
    inline settings in effect. A present but unreadable/non-regular file forces every inline
    mode and the default to protected ``on``: its unknown contents must never make a primary
    checkout less protected.
    """
    modes, inline_default = _modes_from_data(data)
    default_mode = inline_default or "on"

    modes_file = data.get("modes_file")
    if modes_file:
        mf = os.path.expanduser(str(modes_file))
        if not os.path.isabs(mf):
            base = Path(policy_path).resolve().parent
            mf = str(base / mf)
        try:
            text = _read_regular_text(mf)
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError):
            # The referenced file may contain protective overrides for inline `off` values.
            # When its contents are unknowable, fail closed instead of trusting lower-priority
            # inline settings that could weaken protection.
            return ({key: "on" for key in modes}, "on")
        else:
            fdata = _parse_mini_yaml(text)
            fmodes, fdefault = _modes_from_data(fdata)
            modes.update(fmodes)  # referenced file wins on key collision
            if fdefault:
                default_mode = fdefault
    return modes, default_mode


@dataclass
class PolicyConfig:
    version: int = 1
    governed_roots: list[str] = field(default_factory=list)
    managed_location: str = "~/.cursor/worktrees"
    default: str = INCLUDE
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    governed_markers: list[str] = field(default_factory=list)
    foreign_hook_frameworks: list[str] = field(default_factory=list)
    read_only_paths: list[str] = field(default_factory=list)
    overrides_include: list[str] = field(default_factory=list)
    overrides_exclude: list[str] = field(default_factory=list)
    # Explicit per-repo modes (rel-glob -> on|off). Empty by default so a host
    # that configures nothing behaves byte-for-byte as before.
    modes: dict = field(default_factory=dict)
    # Governs eligible repos with no explicit mode. Default "on" reproduces today's
    # derived classification byte-for-byte.
    default_mode: str = "on"

    @classmethod
    def load(cls, path: str | Path) -> "PolicyConfig":
        # Missing policy -> safe defaults (mirror kernel/lib/awa_policy.py). This keeps
        # `awa guard shell` / MCP `awa_guard_shell` from crashing on an absent policy path;
        # the derived posture (default include + default_mode on) still protects a repo.
        p = Path(path)
        if not p.exists():
            return cls()
        data = _parse_mini_yaml(p.read_text(encoding="utf-8"))
        detectors = data.get("detectors", {}) if isinstance(data.get("detectors"), dict) else {}
        overrides = data.get("overrides", {}) if isinstance(data.get("overrides"), dict) else {}
        modes, default_mode = _resolve_modes(data, path)
        return cls(
            version=int(str(data.get("version", 1)) or 1),
            governed_roots=list(data.get("governed_roots", []) or []),
            managed_location=str(data.get("managed_location", "~/.cursor/worktrees")),
            default=str(data.get("default", INCLUDE)),
            include=list(data.get("include", []) or []),
            exclude=list(data.get("exclude", []) or []),
            governed_markers=list(detectors.get("governed_markers", []) or []),
            foreign_hook_frameworks=list(detectors.get("foreign_hook_frameworks", []) or []),
            read_only_paths=list(detectors.get("read_only_paths", []) or []),
            overrides_include=list(overrides.get("include", []) or []),
            overrides_exclude=list(overrides.get("exclude", []) or []),
            modes=modes,
            default_mode=default_mode,
        )


@dataclass
class Classification:
    classification: str
    reason: str


def _match_any(rel: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if rel == pat or fnmatch.fnmatch(rel, pat):
            return True
    return False


def has_governed_marker(toplevel: str, markers: list[str]) -> bool:
    """A repo that carries its OWN governance marker is self-governed (generic exclude)."""
    for marker in markers:
        if (Path(toplevel) / marker).exists():
            return True
    return False


def _is_glob(pat: str) -> bool:
    """A key is a glob if it carries an fnmatch metacharacter (`*`, `?`, `[`)."""
    return any(c in pat for c in "*?[")


def mode_for(rel: str, cfg: PolicyConfig) -> str:
    """Return the matching inline/file mode for `rel`, preferring EXACT keys over globs.

    Exact (non-glob) keys are matched first (by equality), then glob keys in insertion
    order — so an exact key wins even when a matching glob precedes it in the file. The
    returned value is case-normalized and MAY be invalid (present-but-not-in MODE_VALUES);
    callers validate. Returns "" when no entry matches.
    """
    for pat, val in cfg.modes.items():
        if not _is_glob(pat) and rel == pat:
            return str(val).strip().lower()
    for pat, val in cfg.modes.items():
        if _is_glob(pat) and fnmatch.fnmatch(rel, pat):
            return str(val).strip().lower()
    return ""


def _eligible(reason_on: str, cfg: PolicyConfig) -> Classification:
    """Map an eligible (would-be-include) repo through default_mode.

    One fail-safe rule: only an exact `off` default excludes; ANY other default_mode
    (`on`, a typo, a removed legacy value) protects the repo -> INCLUDE. `policy-check`
    WARNs on a non-canonical default_mode; it never silently disables protection.
    """
    if cfg.default_mode == "off":
        return Classification(EXCLUDE, "policy default_mode: off")
    return Classification(INCLUDE, reason_on)


def classify(
    rel: str,
    toplevel: str | None,
    cfg: PolicyConfig,
    *,
    hooks_path: str = "",
    has_origin: bool = True,
    is_root: bool = False,
    is_standalone: bool = False,
) -> Classification:
    """Generic classification. `rel` is the repo path relative to the governed root.

    Order (first match wins): not-git -> explicit OFF -> legacy overrides -> SAFETY
    excludes (umbrella / governed-marker / foreign-hook / read-only) -> any explicit
    non-off mode (ON / typo / legacy) -> exclude globs -> no-origin advisory ->
    explicit include-glob eligibility -> standalone advisory (outside every governed
    root) -> policy-default eligibility, mapped through default_mode. One fail-safe
    rule: only `off` disables; ANY other explicit value -> INCLUDE. Safety-excludes
    beat an explicit ON; explicit OFF beats everything; an explicit include-glob match
    beats standalone.
    """
    if toplevel is None:
        return Classification(NOT_GIT, "not a git repository")

    m = mode_for(rel, cfg)

    if m == "off":
        return Classification(EXCLUDE, "explicit mode: off")

    if _match_any(rel, cfg.overrides_exclude):
        return Classification(EXCLUDE, "operator override: exclude")
    if _match_any(rel, cfg.overrides_include):
        return Classification(INCLUDE, "operator override: include")

    if is_root or rel == ".":
        return Classification(EXCLUDE, "umbrella root: worktree omits nested repos")

    if has_governed_marker(toplevel, cfg.governed_markers):
        return Classification(EXCLUDE, "self-governed repo (own governance marker; generic exclude)")

    if hooks_path:
        for fw in cfg.foreign_hook_frameworks:
            if fw in hooks_path:
                return Classification(EXCLUDE, f"foreign hook framework: {fw}")

    if _match_any(rel, cfg.read_only_paths):
        return Classification(EXCLUDE, "read-only/reference path")

    # Fail-safe: any explicit mode value that survived the early `off` check protects the
    # repo. `on`, a typo, and a removed legacy value all resolve to INCLUDE here.
    if m:
        return Classification(INCLUDE, "explicit mode: on")

    if _match_any(rel, cfg.exclude):
        return Classification(EXCLUDE, "excluded by workspace policy")

    if not has_origin:
        return Classification(ADVISORY, "no origin remote")

    if _match_any(rel, cfg.include):
        return _eligible("included by workspace policy", cfg)

    if is_standalone:
        return Classification(ADVISORY, "standalone repo (outside every governed root)")

    if cfg.default == INCLUDE:
        return _eligible("policy default: include", cfg)
    return Classification(ADVISORY, "outside governed include patterns")
