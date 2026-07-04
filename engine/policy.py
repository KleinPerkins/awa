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
from dataclasses import dataclass, field
from pathlib import Path

INCLUDE = "include"
EXCLUDE = "exclude"
ADVISORY = "advisory"
NOT_GIT = "not-git"


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

    @classmethod
    def load(cls, path: str | Path) -> "PolicyConfig":
        data = _parse_mini_yaml(Path(path).read_text(encoding="utf-8"))
        detectors = data.get("detectors", {}) if isinstance(data.get("detectors"), dict) else {}
        overrides = data.get("overrides", {}) if isinstance(data.get("overrides"), dict) else {}
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


def classify(
    rel: str,
    toplevel: str | None,
    cfg: PolicyConfig,
    *,
    hooks_path: str = "",
    has_origin: bool = True,
    is_root: bool = False,
) -> Classification:
    """Generic classification. `rel` is the repo path relative to the governed root.

    Order (first match wins): explicit overrides -> umbrella root -> governed-marker
    (self-governed sibling) -> foreign-hook -> read-only -> exclude globs -> no-origin
    advisory -> include globs -> policy default.
    """
    if toplevel is None:
        return Classification(NOT_GIT, "not a git repository")

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

    if _match_any(rel, cfg.exclude):
        return Classification(EXCLUDE, "excluded by workspace policy")

    if not has_origin:
        return Classification(ADVISORY, "no origin remote")

    if _match_any(rel, cfg.include):
        return Classification(INCLUDE, "included by workspace policy")

    if cfg.default == INCLUDE:
        return Classification(INCLUDE, "policy default: include")
    return Classification(ADVISORY, "outside governed include patterns")
