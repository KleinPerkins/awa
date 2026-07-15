#!/usr/bin/env python3
"""Render the generic AWA dashboard into Cursor's machine-local Canvas directory.

The emitter remains read-only with respect to governed repositories. This renderer writes only the
derived Canvas snapshot and one narrowly named sidecar alias used by the optional local-jobs Canvas
bridge; it never writes inside a governed repository.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import emitter

CANVAS_NAME = "awa-worktree-dashboard.canvas.tsx"
BRIDGE_ALIAS_NAME = "local-jobs-dashboard-awa.canvas.data.json"
_START = re.compile(r"^.*AWA_DATA_START.*$", re.MULTILINE)
_END = re.compile(r"^.*AWA_DATA_END.*$", re.MULTILINE)


class RenderError(RuntimeError):
    """A dashboard publication boundary was unsafe or malformed."""


def workspace_canvas_dir(root: Path, projects_dir: Path | None = None) -> Path:
    projects = projects_dir or (Path.home() / ".cursor" / "projects")
    path_slug = str(root).lstrip("/").replace("/", "-")
    hyphen_slug = path_slug.replace(".", "-")
    if (projects / hyphen_slug).is_dir():
        slug = hyphen_slug
    elif (projects / path_slug).is_dir():
        slug = path_slug
    else:
        slug = hyphen_slug
    return projects / slug / "canvases"


def inject(seed: str, payload: dict[str, Any]) -> str:
    start = _START.search(seed)
    end = _END.search(seed)
    if start is None or end is None or start.end() >= end.start():
        raise RenderError("dashboard seed is missing ordered AWA_DATA markers")
    block = (
        "\nconst INITIAL_RAW = "
        + json.dumps(payload, indent=2, sort_keys=True)
        + " as unknown as DashboardData;\n"
    )
    return seed[: start.end()] + block + seed[end.start() :]


def write_atomic(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def ensure_bridge_alias(target: Path) -> Path:
    """Expose this Canvas sidecar to the existing bridge's narrow discovery rule.

    Refuse a non-symlink or a symlink with any other target. The renderer owns exactly this one
    alias and never replaces an uncertain path.
    """

    sidecar = target.with_suffix(".data.json")
    alias = target.parent / BRIDGE_ALIAS_NAME
    wanted = sidecar.name
    if alias.is_symlink():
        if os.readlink(alias) != wanted:
            raise RenderError("dashboard bridge alias points somewhere unexpected")
        return alias
    if os.path.lexists(alias):
        raise RenderError("dashboard bridge alias exists and is not an owned symlink")
    try:
        alias.symlink_to(wanted)
    except FileExistsError as exc:
        raise RenderError("dashboard bridge alias appeared concurrently") from exc
    return alias


def publish(
    root: Path,
    *,
    policy: Path | None = None,
    timeout: float = 4.0,
    canvas_dir: Path | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise RenderError(f"governed root is not a directory: {root}")

    previous_policy = os.environ.get("AWA_POLICY")
    if policy is not None:
        os.environ["AWA_POLICY"] = str(policy.expanduser().resolve())
    try:
        payload = emitter.build(root, timeout)
    finally:
        if previous_policy is None:
            os.environ.pop("AWA_POLICY", None)
        else:
            os.environ["AWA_POLICY"] = previous_policy

    if payload.get("schema") != emitter.SCHEMA:
        raise RenderError(f"unexpected dashboard schema: {payload.get('schema')!r}")
    seed_path = Path(__file__).with_name("seed.canvas.tsx")
    rendered = inject(seed_path.read_text(encoding="utf-8"), payload)
    target = (canvas_dir or workspace_canvas_dir(root)) / CANVAS_NAME
    write_atomic(target, rendered)
    alias = ensure_bridge_alias(target)
    return {
        "schema": "awa-dashboard-render/v1",
        "generated_at": payload.get("generated_at"),
        "canvas": str(target),
        "bridge_alias": str(alias),
        "repos": payload.get("summary", {}).get("repos", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--timeout", type=float, default=4.0)
    parser.add_argument("--canvas-dir", type=Path)
    args = parser.parse_args()
    result = publish(
        args.root,
        policy=args.policy,
        timeout=args.timeout,
        canvas_dir=args.canvas_dir,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
