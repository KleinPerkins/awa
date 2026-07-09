"""recovery.py — recovery manager: bundles / patches / quarantine / restore (Phase 3).

Built BEFORE any new destructive cleanup. Two artifact kinds:

  * PATCH  — a git diff (tracked working-tree + staged changes) that round-trips:
             create -> restore reproduces the uncommitted work exactly. This is what
             makes "uncommitted work is preserved" true (§H1 recovery-manager gate).
  * BUNDLE — a tar.gz of git-IGNORED files (`.env`, local `*.db`, build output) that
             `git worktree remove` would otherwise delete with no recovery.
  * WORKTREE-ARCHIVE — a tar.gz of the WHOLE worktree tree (tracked + untracked + ignored,
             minus `.git`) captured as a protected, archive-only safety net. It is written
             read-only (file mode 0o400 — NO OS immutable flag / lock) and `prune_artifacts`
             REFUSES to destroy it, so a later cleanup can never silently discard it.

S1: secret-pattern files are EXCLUDED from a bundle (recorded as skipped) unless the
operator explicitly opts in. S5: the manifest + audit are metadata-only (never file
content). S2: a symlink whose real target escapes the worktree root is never archived.
Recovery archives live on durable LOCAL disk under the state root, never a repo, and
their names never start with a dot (operators list them with a plain `ls`).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import gitutil, paths, state as state_mod

# S1 secret denylist (basename patterns), mirroring .gitignore secret classes.
_SECRET = re.compile(
    r"(\.env$|\.env\.|\.(pem|key|p12|pfx|keystore|jks)$|(^|/)(id_rsa|id_ed25519)"
    r"|credential|secret|token|\.netrc$|\.npmrc$)",
    re.I,
)

# Manifest `kind` for the protected whole-worktree archive (D2). `prune_artifacts` treats any
# artifact whose manifest marks `protected: true` as never-deletable.
WORKTREE_ARCHIVE_KIND = "worktree-archive"


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    s = re.sub(r"^\.+", "", s)  # never a hidden (leading-dot) archive name.
    return s or "worktree"


def _stamp() -> str:
    return time.strftime("%Y%m%d%H%M%S", time.gmtime())


@dataclass
class BundleResult:
    archive: str
    manifest: str
    included: list[str] = field(default_factory=list)
    skipped_secrets: list[str] = field(default_factory=list)
    skipped_symlink_escape: list[str] = field(default_factory=list)


@dataclass
class ArchiveResult:
    archive: str
    manifest: str
    included: list[str] = field(default_factory=list)
    skipped_secrets: list[str] = field(default_factory=list)
    skipped_symlink_escape: list[str] = field(default_factory=list)
    protected: bool = True


def create_bundle(worktree_path: str, *, allow_secrets: bool = False,
                  recovery_dir: Path | None = None,
                  state: state_mod.State | None = None,
                  lease_id: str | None = None) -> BundleResult:
    """Archive git-ignored files under `worktree_path` (S1/S2/S5-safe)."""
    src = os.path.abspath(worktree_path)
    src_real = os.path.realpath(src)
    rec = Path(recovery_dir) if recovery_dir else paths.recovery_dir()
    paths.ensure_dir(rec)

    entries = gitutil.ignored_files(src)
    included: list[str] = []
    skipped_secrets: list[str] = []
    skipped_symlink: list[str] = []
    for e in entries:
        real = os.path.realpath(os.path.join(src, e))
        if real != src_real and not real.startswith(src_real + os.sep):
            skipped_symlink.append(e)  # S2: escapes the worktree root.
            continue
        if _SECRET.search(e) and not allow_secrets:
            skipped_secrets.append(e)  # S1.
        else:
            included.append(e)

    slug = _slug(os.path.basename(src))
    stamp = _stamp()
    archive = rec / f"{slug}-{stamp}.tar.gz"
    manifest = rec / f"{slug}-{stamp}.manifest.json"

    if included:
        listfile = str(archive) + ".list"
        Path(listfile).write_text("\n".join(included) + "\n", encoding="utf-8")
        try:
            rc = subprocess.run(
                ["tar", "-czf", str(archive), "-C", src, "-T", listfile],
            ).returncode
        finally:
            try:
                os.remove(listfile)
            except OSError:
                pass
        if rc != 0:
            raise RuntimeError(f"tar failed ({rc}) creating {archive}")
    else:
        archive.write_bytes(b"")  # nothing safe to archive; still write the manifest.
    try:
        os.chmod(archive, paths.FILE_MODE)
    except OSError:
        pass

    manifest_doc = {
        "kind": "bundle",
        "source": src,
        "archive": str(archive),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "included": included,
        "skipped_secrets": skipped_secrets,
        "skipped_symlink_escape": skipped_symlink,
        "allow_secrets": allow_secrets,
    }
    paths.write_private(manifest, json.dumps(manifest_doc, indent=2) + "\n")

    if state is not None:
        state.record_recovery("bundle", src, str(archive), str(manifest), lease_id)
        state.record_event("recovery_bundle",
                           f"bundle {archive.name}: {len(included)} incl, "
                           f"{len(skipped_secrets)} secret-skipped", lease_id)
    return BundleResult(str(archive), str(manifest), included, skipped_secrets, skipped_symlink)


def create_worktree_archive(worktree_path: str, *, allow_secrets: bool = False,
                            recovery_dir: Path | None = None,
                            state: state_mod.State | None = None,
                            lease_id: str | None = None) -> ArchiveResult:
    """Archive the WHOLE worktree tree (tracked + untracked + ignored, minus `.git`) as a
    PROTECTED, archive-only safety net (D2).

    S1/S2/S5-safe, exactly like `create_bundle`: secret-pattern files are excluded (unless
    `allow_secrets`), symlinks whose real target escapes the worktree root are dropped, and the
    manifest is metadata-only. The archive + manifest are then made READ-ONLY (file mode 0o400)
    so the protected copy cannot be edited/truncated in place — deliberately PERMS-ONLY, with NO
    macOS immutable flag / OS lock (a locked K0/K1 non-goal, enforced product-wide by the
    kernel-off matrix). `prune_artifacts` refuses to delete it.
    """
    src = os.path.abspath(worktree_path)
    src_real = os.path.realpath(src)
    rec = Path(recovery_dir) if recovery_dir else paths.recovery_dir()
    paths.ensure_dir(rec)

    included: list[str] = []
    skipped_secrets: list[str] = []
    skipped_symlink: list[str] = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != ".git"]  # never descend git metadata.
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, src)
            if rel == ".git" or rel.startswith(".git" + os.sep):
                continue  # a linked worktree's `.git` is a pointer FILE — skip it.
            real = os.path.realpath(full)
            if real != src_real and not real.startswith(src_real + os.sep):
                skipped_symlink.append(rel)  # S2: escapes the worktree root.
                continue
            if _SECRET.search(rel) and not allow_secrets:
                skipped_secrets.append(rel)  # S1.
            else:
                included.append(rel)
    included.sort()
    skipped_secrets.sort()
    skipped_symlink.sort()

    slug = _slug(os.path.basename(src))
    stamp = _stamp()
    archive = rec / f"{slug}-{stamp}.worktree.tar.gz"
    manifest = rec / f"{slug}-{stamp}.worktree.manifest.json"

    if included:
        listfile = str(archive) + ".list"
        Path(listfile).write_text("\n".join(included) + "\n", encoding="utf-8")
        try:
            rc = subprocess.run(
                ["tar", "-czf", str(archive), "-C", src, "-T", listfile],
            ).returncode
        finally:
            try:
                os.remove(listfile)
            except OSError:
                pass
        if rc != 0:
            raise RuntimeError(f"tar failed ({rc}) creating {archive}")
    else:
        archive.write_bytes(b"")  # nothing safe to archive; still write the manifest.

    manifest_doc = {
        "kind": WORKTREE_ARCHIVE_KIND,
        "protected": True,
        "source": src,
        "archive": str(archive),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "included": included,
        "skipped_secrets": skipped_secrets,
        "skipped_symlink_escape": skipped_symlink,
        "allow_secrets": allow_secrets,
        "hardening": "archive-only (read-only file mode 0o400); no OS immutable flag / lock",
    }
    paths.write_private(manifest, json.dumps(manifest_doc, indent=2) + "\n")
    # Archive-only hardening (perms-only, no OS lock): make the archive + manifest READ-ONLY.
    for p in (archive, manifest):
        try:
            os.chmod(p, 0o400)
        except OSError:
            pass

    if state is not None:
        state.record_recovery(WORKTREE_ARCHIVE_KIND, src, str(archive), str(manifest), lease_id)
        state.record_event("recovery_worktree_archive",
                           f"protected whole-worktree archive {archive.name}: "
                           f"{len(included)} file(s), {len(skipped_secrets)} secret-skipped",
                           lease_id)
    return ArchiveResult(str(archive), str(manifest), included, skipped_secrets, skipped_symlink, True)


def restore_bundle(archive: str, dest: str) -> list[str]:
    """Extract a bundle into `dest`. Returns the list of restored paths."""
    dest_p = Path(dest)
    dest_p.mkdir(parents=True, exist_ok=True)
    if os.path.getsize(archive) == 0:
        return []
    rc = subprocess.run(["tar", "-xzf", archive, "-C", str(dest_p)]).returncode
    if rc != 0:
        raise RuntimeError(f"tar extract failed ({rc}) for {archive}")
    rc, out, _ = _tar_list(archive)
    return [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []


def _tar_list(archive: str) -> tuple[int, str, str]:
    proc = subprocess.run(["tar", "-tzf", archive], capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


@dataclass
class PatchResult:
    patch: str
    has_changes: bool
    included_staged: bool


def create_patch(worktree_path: str, *, recovery_dir: Path | None = None,
                 state: state_mod.State | None = None,
                 lease_id: str | None = None) -> PatchResult:
    """Capture uncommitted tracked changes (working tree + staged) as a git patch.

    Round-trips with `restore_patch`. Uses `git diff HEAD --binary` so staged AND
    unstaged changes to tracked files are captured in one applyable patch.
    """
    src = os.path.abspath(worktree_path)
    rec = Path(recovery_dir) if recovery_dir else paths.recovery_dir()
    paths.ensure_dir(rec)
    slug = _slug(os.path.basename(src))
    stamp = _stamp()
    patch = rec / f"{slug}-{stamp}.patch"

    rc, out, err = gitutil.git(src, "diff", "HEAD", "--binary", timeout=60)
    if rc != 0:
        raise RuntimeError(f"git diff failed: {err.strip()}")
    paths.write_private(patch, out)
    has_changes = bool(out.strip())
    # were there staged changes? (informational)
    rc2, staged, _ = gitutil.git(src, "diff", "--cached", "--name-only", timeout=30)
    included_staged = rc2 == 0 and bool(staged.strip())

    if state is not None:
        state.record_recovery("patch", src, str(patch), None, lease_id)
        state.record_event("recovery_patch",
                           f"patch {patch.name} ({'changes' if has_changes else 'empty'})",
                           lease_id)
    return PatchResult(str(patch), has_changes, included_staged)


def restore_patch(patch: str, dest_worktree: str, *, index: bool = False) -> None:
    """Apply a patch created by `create_patch` back into `dest_worktree`.

    `index=True` also stages the changes (git apply --index). Raises on conflict.
    """
    if os.path.getsize(patch) == 0:
        return  # empty patch: nothing to restore.
    args = ["apply", "--whitespace=nowarn"]
    if index:
        args.append("--index")
    args.append(patch)
    rc, _, err = gitutil.git(dest_worktree, *args, timeout=60)
    if rc != 0:
        raise RuntimeError(f"git apply failed: {err.strip()}")


def list_artifacts(recovery_dir: Path | None = None) -> list[dict]:
    """Enumerate recovery artifacts on disk (manifests + patches)."""
    rec = Path(recovery_dir) if recovery_dir else paths.recovery_dir()
    if not rec.exists():
        return []
    out: list[dict] = []
    for p in sorted(rec.iterdir()):
        if p.name.endswith(".manifest.json"):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass
        elif p.suffix == ".patch":
            out.append({"kind": "patch", "archive": str(p),
                        "size": p.stat().st_size})
    return out


def prune_artifacts(recovery_dir: Path | None = None, *,
                    older_than_seconds: float | None = None,
                    force: bool = False) -> dict:
    """Cleanup pass over recovery artifacts that REFUSES to destroy a protected archive (D2).

    A protected whole-worktree archive (manifest ``protected: true``) is NEVER deleted — not
    even with ``force`` — so a later cleanup cannot silently discard the safety net. Other
    (non-protected) artifacts are eligible only when explicitly requested: ``force`` deletes
    them, or ``older_than_seconds`` deletes those whose manifest/patch mtime is at least that
    old. With neither, nothing is deleted (the pass just reports what it would keep/refuse).

    Returns ``{"deleted": [...], "refused_protected": [...], "kept": [...]}`` (archive paths).
    """
    rec = Path(recovery_dir) if recovery_dir else paths.recovery_dir()
    result: dict[str, list[str]] = {"deleted": [], "refused_protected": [], "kept": []}
    if not rec.exists():
        return result
    now = time.time()

    def _eligible(p: Path) -> bool:
        if force:
            return True
        if older_than_seconds is None:
            return False
        try:
            return (now - p.stat().st_mtime) >= older_than_seconds
        except OSError:
            return False

    def _rm(p: Path) -> None:
        try:
            os.chmod(p, 0o600)  # loosen only what we are deleting (bundles are already 0o600).
        except OSError:
            pass
        try:
            p.unlink()
        except OSError:
            pass

    for p in sorted(rec.iterdir()):
        if p.name.endswith(".manifest.json"):
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                doc = {}
            label = doc.get("archive") or str(p)
            if doc.get("protected"):
                result["refused_protected"].append(label)  # cleanup MUST refuse to destroy it.
                continue
            if _eligible(p):
                archive = doc.get("archive")
                if archive and Path(archive).exists():
                    _rm(Path(archive))
                _rm(p)
                result["deleted"].append(label)
            else:
                result["kept"].append(label)
        elif p.suffix == ".patch":
            if _eligible(p):
                _rm(p)
                result["deleted"].append(str(p))
            else:
                result["kept"].append(str(p))
        # A `.tar.gz` is reached via its manifest; a protected archive is thus never unlinked here.
    return result
