#!/usr/bin/env python3
"""awa_policy.py — generic, ZERO-LINK kernel policy resolver.

The kernel scripts (dev-worktree.sh, the guard hook, the dashboard emitter) are
host-agnostic: they carry NO org/vendor literals. Every include/exclude glob,
governed root, and detector comes from a machine-local policy file (worktree-policy.yml)
resolved BY ROLE (AWA_POLICY, else the installed kernel default template). This module
is the single kernel-layer implementation of:

  * a tiny stdlib-only YAML subset parser (scalars, `- ` lists, one-deep nested maps),
  * generic repo classification (self-governed-marker + foreign-hook detectors decide
    exclusions GENERICALLY, so a self-governed sibling repo is left alone WITHOUT naming
    it), and
  * governed-root resolution + include-root enumeration for the read-only dashboard.

It deliberately mirrors the engine-layer `engine/policy.py` classifier so the kernel
delivers the safety guarantee with the engine OFF. `engine/tests/test_kernel_policy_parity.py`
asserts the two never drift.

CLI (consumed by the shell kernel):
  awa_policy.py dump --policy P [--governed-root R]
      emit shell-eval-safe assignments (POL_DEFAULT, POL_MANAGED, POL_GOVERNED_ROOTS=(...), ...)
  awa_policy.py classify --policy P [--governed-root R] --toplevel T [--hooks-path H] [--has-origin 0|1]
      print: <class>\t<reason>\t<rel>\t<governed_root>
  awa_policy.py governed-roots --policy P [--governed-root R]
      print resolved governed roots, one per line
"""

from __future__ import annotations

import fnmatch
import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

INCLUDE = "include"
EXCLUDE = "exclude"
ADVISORY = "advisory"
NOT_GIT = "not-git"


def parse_mini_yaml(text: str) -> dict:
    """Parse the small YAML subset worktree-policy.yml uses. Returns nested dict/list.

    Supported: `key: scalar`, inline `key: []`/`key: {}`, `key:` then an indented
    `- item` list, and `key:` then an indented `subkey:` map. Comments (#) and blank
    lines are ignored. (Mirror of engine/policy.py:_parse_mini_yaml — keep in sync.)
    """
    root: dict = {}
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
        p = Path(path)
        if not p.exists():
            return cls()
        data = parse_mini_yaml(p.read_text(encoding="utf-8"))
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


def _match_any(rel: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if rel == pat or fnmatch.fnmatch(rel, pat):
            return True
    return False


def has_governed_marker(toplevel: str, markers: list[str]) -> bool:
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
) -> tuple[str, str]:
    """Generic classification. Order (first match wins) mirrors engine/policy.py."""
    if toplevel is None:
        return (NOT_GIT, "not a git repository")

    if _match_any(rel, cfg.overrides_exclude):
        return (EXCLUDE, "operator override: exclude")
    if _match_any(rel, cfg.overrides_include):
        return (INCLUDE, "operator override: include")

    if is_root or rel == ".":
        return (EXCLUDE, "umbrella root: worktree omits nested repos")

    if has_governed_marker(toplevel, cfg.governed_markers):
        return (EXCLUDE, "self-governed repo (own governance marker; generic exclude)")

    if hooks_path:
        for fw in cfg.foreign_hook_frameworks:
            if fw in hooks_path:
                return (EXCLUDE, f"foreign hook framework: {fw}")

    if _match_any(rel, cfg.read_only_paths):
        return (EXCLUDE, "read-only/reference path")

    if _match_any(rel, cfg.exclude):
        return (EXCLUDE, "excluded by workspace policy")

    if not has_origin:
        return (ADVISORY, "no origin remote")

    if _match_any(rel, cfg.include):
        return (INCLUDE, "included by workspace policy")

    if cfg.default == INCLUDE:
        return (INCLUDE, "policy default: include")
    return (ADVISORY, "outside governed include patterns")


def _norm(path: str) -> str:
    return os.path.realpath(os.path.expanduser(path))


def resolve_governed_root(toplevel: str, env_root: str, cfg: PolicyConfig) -> str:
    """Pick the governed root that contains `toplevel`: env override first, then policy.

    Returns "" when no governed root contains the repo — the STANDALONE case, where the
    repo is its own context (never an umbrella), so a freshly cloned repo is eligible.
    """
    top = _norm(toplevel)
    candidates: list[str] = []
    if env_root:
        candidates.append(env_root)
    candidates.extend(cfg.governed_roots)
    for cand in candidates:
        gr = _norm(cand)
        if top == gr or top.startswith(gr + os.sep):
            return gr
    return ""


def rel_to_root(toplevel: str, governed_root: str) -> str:
    top = _norm(toplevel)
    if not governed_root:
        return os.path.basename(top.rstrip(os.sep)) or top
    gr = _norm(governed_root)
    if top == gr:
        return "."
    if top.startswith(gr + os.sep):
        return top[len(gr) + 1:]
    return top


def include_roots(cfg: PolicyConfig) -> list[str]:
    """First path segment of each include glob (enumeration hints for the dashboard).

    e.g. include ['personal/*', 'a/b/*'] -> ['personal', 'a/b']. Absent include globs,
    the dashboard falls back to a shallow scan of the governed root itself.
    """
    roots: list[str] = []
    for pat in cfg.include:
        seg = pat.split("*", 1)[0].rstrip("/")
        if seg and seg not in roots:
            roots.append(seg)
    return roots


# --------------------------------------------------------------------------- CLI

def _cli_dump(cfg: PolicyConfig) -> int:
    def arr(name: str, items: list[str]) -> None:
        print("%s=(%s)" % (name, " ".join(shlex.quote(str(x)) for x in items)))

    print("POL_DEFAULT=%s" % shlex.quote(str(cfg.default)))
    print("POL_MANAGED=%s" % shlex.quote(os.path.expanduser(str(cfg.managed_location))))
    arr("POL_GOVERNED_ROOTS", [os.path.expanduser(x) for x in cfg.governed_roots])
    arr("POL_INCLUDE", cfg.include)
    arr("POL_EXCLUDE", cfg.exclude)
    arr("POL_GOV_MARKERS", cfg.governed_markers)
    arr("POL_FOREIGN", cfg.foreign_hook_frameworks)
    arr("POL_READONLY", cfg.read_only_paths)
    arr("POL_OVR_INC", cfg.overrides_include)
    arr("POL_OVR_EXC", cfg.overrides_exclude)
    return 0


def _opt(argv: list[str], name: str, default: str = "") -> str:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: awa_policy.py {dump|classify|governed-roots} --policy P [...]", file=sys.stderr)
        return 2
    cmd = argv[0]
    rest = argv[1:]
    policy = _opt(rest, "--policy")
    env_root = _opt(rest, "--governed-root")
    cfg = PolicyConfig.load(policy) if policy else PolicyConfig()

    if cmd == "dump":
        return _cli_dump(cfg)

    if cmd == "governed-roots":
        roots = ([_norm(env_root)] if env_root else []) + [_norm(r) for r in cfg.governed_roots]
        seen: set[str] = set()
        for r in roots:
            if r and r not in seen:
                seen.add(r)
                print(r)
        return 0

    if cmd == "classify":
        toplevel = _opt(rest, "--toplevel")
        if not toplevel:
            print("classify requires --toplevel", file=sys.stderr)
            return 2
        hooks_path = _opt(rest, "--hooks-path")
        has_origin = _opt(rest, "--has-origin", "1") != "0"
        gr = resolve_governed_root(toplevel, env_root, cfg)
        rel = rel_to_root(toplevel, gr)
        cls, reason = classify(
            rel, toplevel, cfg,
            hooks_path=hooks_path, has_origin=has_origin, is_root=(rel == "."),
        )
        print("\t".join([cls, reason, rel, gr]))
        return 0

    print(f"awa_policy.py: unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
