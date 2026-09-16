"""retention.py — the canonical recovery-retention evaluator + crash-resumable deletion
transaction (Phase 3).

This is the SINGLE implementation of retention policy for AWA. Artifact creation
(`recovery.create_*`), the sessionStart maintenance hook, `daemon run-once`, and manual
`recover prune --maintenance` all call ONE evaluator (`run_maintenance`) and ONE deletion
transaction (`_delete_one` / `_resume`). The hook contains NO retention logic and never unlinks a
file itself.

Policy (authoritative plan §"Recovery retention lifecycle"):
  * Age starts when the SOURCE work is deleted, not when the archive is created. Ordinary bundles
    and patches expire at a seven-day TTL.
  * A 1-GiB soft watermark prunes the OLDEST ordinary artifacts after a 24-hour minimum age;
    young or protected artifacts may honestly leave storage above the watermark.
  * Protected Retain / whole-worktree artifacts are NEVER automatically removed (TTL or pressure).
  * Every deletion is contained beneath the physical recovery root, symlink/escape-rejecting, and
    crash-resumable via an on-disk tombstone journal plus reconcile; a missing/failed unlink is an
    ERROR, never a reported success (fail-safe: uncertainty preserves the artifact).

Kernel-first: this runs in the ENGINE, under the shared state-root lock ABI, and NEVER on the
finish authorization/removal path. Worktree cleanup stays correct with the engine absent.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import lock as lock_mod, paths, state as state_mod

# Reuse the ONE shared kernel durability helper (Darwin F_FULLFSYNC; atomic private replace;
# durable unlink with parent sync). Import it by role like dashboard/emitter.py imports the policy
# resolver. Kernel-first: if the kernel libs are somehow absent, degrade to a stdlib fallback so the
# engine still functions (durability is best-effort bookkeeping here, never a safety gate).
_AWA_HOME = Path(__file__).resolve().parent.parent
if str(_AWA_HOME / "kernel" / "lib") not in sys.path:
    sys.path.insert(0, str(_AWA_HOME / "kernel" / "lib"))
try:  # pragma: no cover - exercised implicitly by every maintenance pass
    import awa_durability as _dur  # noqa: E402
except Exception:  # noqa: BLE001 - degrade to stdlib fallback (engine stays usable)
    _dur = None  # type: ignore

# ---- canonical constants (behavior-only; pinned by the recovery_retention contract block) -------
SCHEMA_ARTIFACT = "awa_recovery_artifact/v1"      # the ONE unified recovery manifest shape
SCHEMA_DELETION_JOURNAL = "awa_recovery_deletion/v1"  # transient crash-resume tombstone journal
SCHEMA_TOMBSTONE = "awa_recovery_tombstone/v1"    # durable prune tombstone (DB)

TTL_SECONDS = 7 * 24 * 3600                        # ordinary artifacts expire seven days after
#                                                    the SOURCE work is deleted.
PRESSURE_WATERMARK_BYTES = 1024 * 1024 * 1024      # 1-GiB soft watermark over ORDINARY artifacts.
PRESSURE_MIN_AGE_SECONDS = 24 * 3600               # a 24-hour minimum age before pressure pruning.
MAINTENANCE_THROTTLE_SECONDS = 24 * 3600           # opportunistic triggers run at most once/24h.

MAX_DELETE_ATTEMPTS = 3                             # bounded retry/backoff on a transient unlink.
_BACKOFF_BASE_SECONDS = 0.02

REASON_TTL = "ttl"
REASON_PRESSURE = "pressure"
REASON_MANUAL = "manual"
TOMBSTONE_REASONS = frozenset({REASON_TTL, REASON_PRESSURE, REASON_MANUAL})

# The unified manifest key floor emitted by BOTH the kernel bundler (dev-worktree.sh) and the
# engine writers (recovery.py). Additive kind-specific keys (included/skipped_secrets/…) may follow.
MANIFEST_KEYS = (
    "schema", "artifact_id", "kind", "protected", "source",
    "archive", "archive_name", "size", "sha256", "created_at", "created_at_epoch",
)

# maintenance meta keys (stored in the state db `meta` table).
META_LAST_RUN = "retention_last_run_epoch"
META_LAST_STATUS = "retention_last_status"
META_LAST_ERROR = "retention_last_error"
META_PROTECTED_BYTES = "retention_protected_bytes"
META_ORDINARY_BYTES = "retention_ordinary_bytes"
META_OVERAGE_BYTES = "retention_watermark_overage_bytes"
META_NEEDS_REPAIR = "retention_needs_repair_count"

_DIR_MODE = 0o700
_FILE_MODE = 0o600
_PROTECTED_FILE_MODE = 0o400
_TRASH_DIRNAME = ".trash"
_QUARANTINE_DIRNAME = "quarantine"


# ---- durability shims (shared helper preferred; stdlib fallback) --------------------------------
def _durable_write(path: Path, data: bytes) -> None:
    if _dur is not None:
        _dur.atomic_private_replace(str(path), data)
        return
    paths.ensure_dir(path.parent)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _durable_unlink(path: Path) -> bool:
    """Unlink + persist the parent namespace. Returns True if a file was removed, False if it was
    already absent. Raises OSError on a real failure (caller treats that as an ERROR, never
    success)."""
    if _dur is not None:
        return _dur.durable_unlink(str(path), missing_ok=True)
    try:
        os.unlink(str(path))
        return True
    except FileNotFoundError:
        return False


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def new_artifact_id(kind: str) -> str:
    """A collision-resistant artifact id: `<kind>-<128-bit hex>` (mirrors the Retain artifact id
    convention so kernel + engine share one identity vocabulary)."""
    return f"{kind}-{os.urandom(16).hex()}"


def _legacy_artifact_id(name: str) -> str:
    """A DETERMINISTIC id for a legacy artifact that predates the unified manifest (stable across
    runs so its tombstone/age clock is consistent)."""
    return "legacy-" + hashlib.sha256(name.encode("utf-8", "replace")).hexdigest()[:32]


def build_manifest(kind: str, source: str, archive: str | Path, *, protected: bool = False,
                   extra: dict | None = None, recovery_root: str | Path | None = None) -> dict:
    """Build ONE unified recovery manifest (the shape kernel + engine both emit). `archive` must
    already exist so size + SHA-256 are computed over the real bytes."""
    archive = Path(archive)
    size = archive.stat().st_size if archive.exists() else 0
    digest = _sha256_file(archive) if archive.exists() else ""
    epoch = int(time.time())
    doc = {
        "schema": SCHEMA_ARTIFACT,
        "artifact_id": new_artifact_id(kind),
        "kind": kind,
        "protected": bool(protected),
        "source": source,
        "archive": str(archive),
        "archive_name": archive.name,   # archive-relative location (resolvable under the root)
        "size": size,
        "sha256": digest,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch)),
        "created_at_epoch": epoch,
    }
    if extra:
        doc.update(extra)
    return doc


# ---- artifact descriptors (unified + legacy normalization) --------------------------------------
@dataclass
class ArtifactDescriptor:
    artifact_id: str
    kind: str
    protected: bool
    source: str
    archive: Path | None
    manifest: Path | None
    size: int
    created_at_epoch: int
    sha256: str = ""
    legacy: bool = False
    manifest_doc: dict = field(default_factory=dict)


def _parse_epoch(doc: dict, fallback_path: Path | None) -> int:
    v = doc.get("created_at_epoch")
    if isinstance(v, int) and v > 0:
        return v
    iso = doc.get("created_at")
    if isinstance(iso, str) and iso:
        try:
            return int(time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")))
        except (ValueError, TypeError):
            pass
    if fallback_path is not None and fallback_path.exists():
        try:
            return int(fallback_path.stat().st_mtime)
        except OSError:
            pass
    return int(time.time())


def _infer_kind_from_manifest_name(name: str) -> str:
    if name.endswith(".worktree.manifest.json"):
        return "worktree-archive"
    if name.endswith(".patch.manifest.json"):
        return "patch"
    return "bundle"


def _descriptor_from_manifest(mpath: Path, recovery_root: Path) -> ArtifactDescriptor | None:
    try:
        doc = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    kind = str(doc.get("kind") or _infer_kind_from_manifest_name(mpath.name))
    legacy = doc.get("schema") != SCHEMA_ARTIFACT
    # Resolve the archive: prefer an explicit archive path, else archive_name under the root, else
    # derive from the manifest name (strip `.manifest.json`).
    archive: Path | None = None
    if doc.get("archive"):
        archive = Path(str(doc["archive"]))
    elif doc.get("archive_name"):
        archive = recovery_root / str(doc["archive_name"])
    else:
        base = mpath.name[: -len(".manifest.json")] if mpath.name.endswith(".manifest.json") else ""
        if base:
            cand = recovery_root / (base + ".tar.gz")
            archive = cand
    # Retention accounting is about ACTUAL disk usage: trust the ON-DISK size (an absent archive
    # contributes 0 and self-heals via needs_repair) rather than a manifest's claimed `size`, so a
    # stale/lying manifest can never inflate watermark pressure.
    size = archive.stat().st_size if (archive and archive.exists()) else 0
    aid = str(doc.get("artifact_id") or _legacy_artifact_id(archive.name if archive else mpath.name))
    return ArtifactDescriptor(
        artifact_id=aid,
        kind=kind,
        protected=bool(doc.get("protected")),
        source=str(doc.get("source") or ""),
        archive=archive,
        manifest=mpath,
        size=int(size),
        created_at_epoch=_parse_epoch(doc, archive or mpath),
        sha256=str(doc.get("sha256") or ""),
        legacy=legacy,
        manifest_doc=doc,
    )


@dataclass
class ScanResult:
    descriptors: list[ArtifactDescriptor] = field(default_factory=list)
    needs_repair: list[str] = field(default_factory=list)  # orphan/partial artifacts (surfaced)


def scan(recovery_dir: Path) -> ScanResult:
    """Enumerate recovery artifacts as normalized descriptors (new + legacy), surfacing
    orphan/partial artifacts (a manifest with no archive, or a bare archive with no manifest) for
    repair rather than silently trusting them."""
    res = ScanResult()
    if not recovery_dir.exists():
        return res
    referenced: set[str] = set()
    manifest_paths = sorted(p for p in recovery_dir.iterdir()
                            if p.is_file() and p.name.endswith(".manifest.json"))
    for mpath in manifest_paths:
        desc = _descriptor_from_manifest(mpath, recovery_dir)
        if desc is None:
            res.needs_repair.append(str(mpath))   # unreadable/malformed manifest
            continue
        if desc.archive is not None:
            referenced.add(desc.archive.name)
            if not desc.archive.exists():
                res.needs_repair.append(str(desc.archive))  # manifest without its archive
        res.descriptors.append(desc)
    # Bare patches (legacy, no sidecar manifest) participate as ordinary patch artifacts.
    for p in sorted(recovery_dir.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.suffix == ".patch" and (p.name + ".manifest.json") not in {m.name for m in manifest_paths}:
            res.descriptors.append(ArtifactDescriptor(
                artifact_id=_legacy_artifact_id(p.name),
                kind="patch", protected=False, source="",
                archive=p, manifest=None, size=p.stat().st_size,
                created_at_epoch=int(p.stat().st_mtime), legacy=True,
            ))
        elif (p.name.endswith(".tar.gz") and p.name not in referenced):
            res.needs_repair.append(str(p))  # bare archive with no manifest -> repair, never trust
    return res


def repair_permissions(recovery_dir: Path, scan_res: ScanResult) -> None:
    """S4/legacy permission repair BEFORE policy evaluation: recovery dir + trash are 0700; every
    artifact archive/manifest is owner-only (0600, or 0400 for a protected artifact)."""
    try:
        os.chmod(recovery_dir, _DIR_MODE)
    except OSError:
        pass
    trash = recovery_dir / _TRASH_DIRNAME
    if trash.exists():
        try:
            os.chmod(trash, _DIR_MODE)
        except OSError:
            pass
    for desc in scan_res.descriptors:
        want = _PROTECTED_FILE_MODE if desc.protected else _FILE_MODE
        for f in (desc.archive, desc.manifest):
            if f is None or not f.exists() or f.is_symlink():
                continue
            try:
                cur = f.stat().st_mode & 0o777
                if cur & 0o077 or (desc.protected and cur != _PROTECTED_FILE_MODE):
                    os.chmod(f, want)
            except OSError:
                pass


# ---- source-deletion age clock ------------------------------------------------------------------
def _effective_age(desc: ArtifactDescriptor, state: state_mod.State | None, now: float) -> float:
    """Seconds since the SOURCE work was deleted (0 while the source still exists). Protected
    artifacts never age. Without a state db we cannot persist first-observation, so we fail SAFE
    (age 0 -> never TTL/pressure eligible)."""
    if desc.protected:
        return 0.0
    if desc.source and os.path.exists(desc.source):
        if state is not None:
            state.clear_source_deleted(desc.artifact_id)
        return 0.0
    if state is None:
        return 0.0
    recorded = state.get_source_deleted_epoch(desc.artifact_id)
    if recorded is None:
        state.set_source_deleted_epoch(desc.artifact_id, int(now))
        return 0.0
    return max(0.0, now - recorded)


# ---- containment + crash-resumable deletion transaction -----------------------------------------
def _safe_target(p: Path, recovery_root: Path) -> bool:
    """True only when `p` is a NON-symlink file resolving to somewhere beneath the physical
    recovery root (rejects symlink/path escapes and ambiguous targets)."""
    try:
        if p.is_symlink():
            return False
        rp = p.resolve(strict=False)
        rr = recovery_root.resolve(strict=False)
    except OSError:
        return False
    return rp == rr or str(rp).startswith(str(rr) + os.sep)


def _is_quarantine_target(p: Path, recovery_root: Path) -> bool:
    """Quarantine is a separate preservation namespace, never a deletion target."""
    try:
        target = p.resolve(strict=False)
        quarantine = (recovery_root / _QUARANTINE_DIRNAME).resolve(strict=False)
        target.relative_to(quarantine)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _unlink_retry(p: Path) -> tuple[bool, str]:
    """Bounded retry/backoff unlink. Returns (ok, error). ok=True means the file is GONE
    (removed or already absent); ok=False means a real failure after retries (an ERROR)."""
    last = ""
    for attempt in range(MAX_DELETE_ATTEMPTS):
        try:
            _durable_unlink(p)
            return True, ""
        except OSError as exc:
            last = str(exc)
            time.sleep(_BACKOFF_BASE_SECONDS * (2 ** attempt))
    return False, last


def _trash_dir(recovery_root: Path) -> Path:
    return recovery_root / _TRASH_DIRNAME


_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _journal_path(trash: Path, artifact_id: str, recovery_root: Path) -> Path | None:
    """A deletion-journal path whose FILENAME is derived from a SANITIZED id (+ a hash of the raw
    id for uniqueness), so a tampered manifest `artifact_id` (e.g. one containing path separators)
    can never make the journal escape the trash dir. The real id always lives in the journal BODY,
    so resume/tombstoning are unaffected. Returns None if the resolved path would still escape the
    recovery root (defense-in-depth: uncertainty preserves — the caller reports an error)."""
    stem = _UNSAFE_NAME.sub("_", artifact_id).strip("._")[:80] or "artifact"
    suffix = hashlib.sha256(artifact_id.encode("utf-8", "replace")).hexdigest()[:8]
    journal = trash / f"{stem}-{suffix}.deletion.json"
    return journal if _safe_target(journal, recovery_root) else None


def _delete_one(recovery_root: Path, desc: ArtifactDescriptor, reason: str,
                state: state_mod.State | None) -> dict:
    """Delete ONE artifact (archive + manifest) as a crash-resumable, tombstoned transaction.

    Order: write the deletion journal (durable intent) -> unlink the archive -> unlink the manifest
    -> record the durable tombstone + reconcile the recovery row -> remove the journal. A crash at
    any point is completed idempotently by `_resume`. A failed ARCHIVE unlink is an ERROR (the
    artifact is still restorable, so no tombstone is written and it is not counted deleted)."""
    if desc.archive is None:
        return {"outcome": "error", "artifact_id": desc.artifact_id, "detail": "no archive path"}
    if (
        not _safe_target(desc.archive, recovery_root)
        or _is_quarantine_target(desc.archive, recovery_root)
    ):
        return {"outcome": "refused_containment", "artifact_id": desc.artifact_id,
                "detail": str(desc.archive)}
    if desc.manifest is not None and desc.manifest.exists() \
            and (
                not _safe_target(desc.manifest, recovery_root)
                or _is_quarantine_target(desc.manifest, recovery_root)
            ):
        return {"outcome": "refused_containment", "artifact_id": desc.artifact_id,
                "detail": str(desc.manifest)}

    trash = _trash_dir(recovery_root)
    journal = _journal_path(trash, desc.artifact_id, recovery_root)
    if journal is None:  # unsanitizable/escaping id -> refuse (never write outside the root)
        return {"outcome": "error", "artifact_id": desc.artifact_id,
                "detail": "unsafe deletion-journal path"}
    jdoc = {
        "schema": SCHEMA_DELETION_JOURNAL,
        "artifact_id": desc.artifact_id,
        "kind": desc.kind,
        "reason": reason,
        "bytes": desc.size,
        "archive": str(desc.archive),
        "manifest": str(desc.manifest) if desc.manifest else "",
        "source": desc.source,
        "phase": "prepared",
        "created_at_epoch": int(time.time()),
    }
    _durable_write(journal, (json.dumps(jdoc) + "\n").encode("utf-8"))

    ok, err = _unlink_retry(desc.archive)
    if not ok:
        # Archive still present -> honest ERROR, leave the journal for the next resume pass.
        return {"outcome": "error", "artifact_id": desc.artifact_id, "detail": err}

    jdoc["phase"] = "archive_removed"
    _durable_write(journal, (json.dumps(jdoc) + "\n").encode("utf-8"))

    residual = ""
    if desc.manifest is not None:
        man_ok, man_err = _unlink_retry(desc.manifest)
        if not man_ok:
            residual = str(desc.manifest)   # archive gone (not restorable) but manifest lingers

    if state is not None:
        state.record_recovery_tombstone(
            desc.artifact_id, reason=reason, bytes=desc.size, kind=desc.kind,
            archive=str(desc.archive), manifest=(str(desc.manifest) if desc.manifest else None),
            source=desc.source)
        state.mark_recovery_pruned(desc.artifact_id, str(desc.archive))
        state.clear_source_deleted(desc.artifact_id)

    _durable_unlink(journal)
    out = {"outcome": "deleted", "artifact_id": desc.artifact_id, "reason": reason,
           "bytes": desc.size}
    if residual:
        out["residual_manifest"] = residual
    return out


def _resume(recovery_root: Path, state: state_mod.State | None) -> dict:
    """Complete any interrupted deletion transactions (crash recovery). Idempotent: re-unlinks
    already-absent paths safely, records the tombstone once, then removes the journal."""
    trash = _trash_dir(recovery_root)
    result = {"resumed": [], "needs_repair": []}
    if not trash.exists():
        return result
    for journal in sorted(trash.glob("*.deletion.json")):
        try:
            jdoc = json.loads(journal.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            result["needs_repair"].append(str(journal))     # malformed journal -> surface
            continue
        aid = str(jdoc.get("artifact_id") or "")
        archive = jdoc.get("archive") or ""
        manifest = jdoc.get("manifest") or ""
        reason = str(jdoc.get("reason") or "resume")
        # Never resume through a symlink/escape (a tampered journal must not delete outside root).
        if archive and (
            not _safe_target(Path(archive), recovery_root)
            or _is_quarantine_target(Path(archive), recovery_root)
        ):
            result["needs_repair"].append(str(journal))
            continue
        if manifest and (
            not _safe_target(Path(manifest), recovery_root)
            or _is_quarantine_target(Path(manifest), recovery_root)
        ):
            result["needs_repair"].append(str(journal))
            continue
        ok = True
        if archive:
            ok, _ = _unlink_retry(Path(archive))
        if not ok:
            continue   # leave the journal; the next pass retries (honest, never false success)
        if manifest:
            _unlink_retry(Path(manifest))
        if state is not None and aid:
            state.record_recovery_tombstone(
                aid, reason=reason, bytes=int(jdoc.get("bytes") or 0), kind=jdoc.get("kind"),
                archive=archive or None, manifest=manifest or None, source=jdoc.get("source"))
            state.mark_recovery_pruned(aid, archive or "")
            state.clear_source_deleted(aid)
        _durable_unlink(journal)
        result["resumed"].append(aid or journal.name)
    return result


# ---- the canonical evaluator --------------------------------------------------------------------
def evaluate(descriptors: list[ArtifactDescriptor], *, state: state_mod.State | None, now: float,
             ttl_seconds: float, watermark_bytes: int, min_age_seconds: float) -> dict:
    """Decide which ordinary artifacts to prune. Returns a plan: {"ttl": [...], "pressure": [...],
    "protected_bytes": int, "ordinary_bytes": int}. Protected artifacts are never selected."""
    ordinary = [d for d in descriptors if not d.protected]
    protected_bytes = sum(d.size for d in descriptors if d.protected)

    ages = {d.artifact_id: _effective_age(d, state, now) for d in ordinary}

    ttl_prune = [d for d in ordinary if ages[d.artifact_id] >= ttl_seconds]
    ttl_ids = {d.artifact_id for d in ttl_prune}
    survivors = [d for d in ordinary if d.artifact_id not in ttl_ids]

    ordinary_bytes = sum(d.size for d in survivors)
    pressure_prune: list[ArtifactDescriptor] = []
    if ordinary_bytes > watermark_bytes:
        # oldest-first (largest effective age), then by creation time, then id (deterministic).
        candidates = sorted(
            (d for d in survivors if ages[d.artifact_id] >= min_age_seconds),
            key=lambda d: (-ages[d.artifact_id], d.created_at_epoch, d.artifact_id))
        running = ordinary_bytes
        for d in candidates:
            if running <= watermark_bytes:
                break
            pressure_prune.append(d)
            running -= d.size
    # `ordinary_bytes` reports the post-TTL SURVIVOR bytes pressure evaluated against (authoritative
    # figures for the operator come from `_summarize`; this keeps the evaluator's own return honest).
    return {"ttl": ttl_prune, "pressure": pressure_prune,
            "protected_bytes": protected_bytes,
            "ordinary_bytes": ordinary_bytes}


def _summarize(recovery_dir: Path, state: state_mod.State | None, now: float) -> dict:
    scan_res = scan(recovery_dir)
    protected_bytes = sum(d.size for d in scan_res.descriptors if d.protected)
    ordinary_bytes = sum(d.size for d in scan_res.descriptors if not d.protected)
    overage = max(0, ordinary_bytes - PRESSURE_WATERMARK_BYTES)
    return {
        "protected_bytes": protected_bytes,
        "ordinary_bytes": ordinary_bytes,
        "watermark_bytes": PRESSURE_WATERMARK_BYTES,
        "watermark_overage_bytes": overage,
        "needs_repair": scan_res.needs_repair,
    }


def _record_meta(state: state_mod.State | None, summary: dict, status: str,
                 error: str = "") -> None:
    if state is None:
        return
    state._set_meta(META_LAST_STATUS, status)
    state._set_meta(META_LAST_ERROR, error)
    state._set_meta(META_PROTECTED_BYTES, str(summary.get("protected_bytes", 0)))
    state._set_meta(META_ORDINARY_BYTES, str(summary.get("ordinary_bytes", 0)))
    state._set_meta(META_OVERAGE_BYTES, str(summary.get("watermark_overage_bytes", 0)))
    state._set_meta(META_NEEDS_REPAIR, str(len(summary.get("needs_repair", []))))


def run_maintenance(state: state_mod.State | None = None, *,
                    recovery_dir: str | Path | None = None,
                    trigger: str = REASON_MANUAL,
                    now: float | None = None,
                    ttl_seconds: float | None = None,
                    watermark_bytes: int | None = None,
                    min_age_seconds: float | None = None,
                    blocking: bool | None = None,
                    timeout: float = 30.0) -> dict:
    """Run ONE bounded maintenance pass under the single state-root lock: resume interrupted
    deletions, permission-repair, evaluate TTL + pressure, execute the crash-resumable deletion
    transaction, then reconcile tombstones + maintenance meta.

    `trigger`: "create" (prune-on-creation), "opportunistic" (sessionStart hook / daemon run-once —
    throttled to once per 24h, non-blocking so a concurrent pass simply skips), or "manual"
    (explicit `recover prune --maintenance`). Fail-safe: any error preserves artifacts and is
    reported honestly (never a false-successful deletion)."""
    rec = Path(recovery_dir) if recovery_dir else paths.recovery_dir()
    now = time.time() if now is None else now
    ttl = TTL_SECONDS if ttl_seconds is None else ttl_seconds
    watermark = PRESSURE_WATERMARK_BYTES if watermark_bytes is None else watermark_bytes
    min_age = PRESSURE_MIN_AGE_SECONDS if min_age_seconds is None else min_age_seconds
    if blocking is None:
        blocking = trigger != "opportunistic"

    base = {"trigger": trigger, "ran": False, "deleted": [], "errors": [],
            "refused_containment": [], "resumed": [], "needs_repair": []}
    try:
        with lock_mod.state_root_lock(blocking=blocking, timeout=timeout):
            if trigger == "opportunistic" and state is not None:
                last = state.get_meta(META_LAST_RUN)
                if last:
                    try:
                        if now - float(last) < MAINTENANCE_THROTTLE_SECONDS:
                            base["skipped"] = "throttled"
                            return base
                    except (TypeError, ValueError):
                        pass
            try:
                resumed = _resume(rec, state)
                base["resumed"] = resumed["resumed"]
                base["needs_repair"].extend(resumed["needs_repair"])

                scan_res = scan(rec)
                repair_permissions(rec, scan_res)
                base["needs_repair"].extend(scan_res.needs_repair)

                plan = evaluate(scan_res.descriptors, state=state, now=now, ttl_seconds=ttl,
                                watermark_bytes=watermark, min_age_seconds=min_age)
                for desc in plan["ttl"] + plan["pressure"]:
                    reason = REASON_TTL if desc in plan["ttl"] else REASON_PRESSURE
                    out = _delete_one(rec, desc, reason, state)
                    if out["outcome"] == "deleted":
                        base["deleted"].append(out)
                        if out.get("residual_manifest"):  # archive gone but manifest lingered
                            base["needs_repair"].append(out["residual_manifest"])
                    elif out["outcome"] == "refused_containment":
                        base["refused_containment"].append(out)
                    else:
                        base["errors"].append(out)

                summary = _summarize(rec, state, now)
                base.update({k: summary[k] for k in
                             ("protected_bytes", "ordinary_bytes", "watermark_bytes",
                              "watermark_overage_bytes")})
                status_val = "errors" if (base["errors"] or base["needs_repair"]) else "ok"
                if state is not None:
                    state._set_meta(META_LAST_RUN, str(int(now)))
                    _record_meta(state, summary, status_val)
                base["ran"] = True
                base["status"] = status_val
            except Exception as exc:  # noqa: BLE001 - fail-safe: never crash the caller
                base["errors"].append({"outcome": "error", "detail": f"maintenance: {exc}"})
                base["status"] = "errors"
                if state is not None:
                    state._set_meta(META_LAST_RUN, str(int(now)))
                    state._set_meta(META_LAST_STATUS, "errors")
                    state._set_meta(META_LAST_ERROR, str(exc))
    except lock_mod.LockBusy:
        base["skipped"] = "lock_busy"
    return base


def status(state: state_mod.State | None = None, *,
           recovery_dir: str | Path | None = None, now: float | None = None) -> dict:
    """Read-only retention status (for `recover status` + the dashboard): storage totals, watermark
    overage, artifacts needing repair, recent tombstones, and the last maintenance outcome."""
    rec = Path(recovery_dir) if recovery_dir else paths.recovery_dir()
    now = time.time() if now is None else now
    scan_res = scan(rec)
    summary = _summarize(rec, state, now)
    out = {
        "recovery_dir": str(rec),
        "artifact_count": len(scan_res.descriptors),
        "protected_count": sum(1 for d in scan_res.descriptors if d.protected),
        "ordinary_count": sum(1 for d in scan_res.descriptors if not d.protected),
        "ttl_days": TTL_SECONDS / 86400,
        "min_age_hours": PRESSURE_MIN_AGE_SECONDS / 3600,
        "throttle_hours": MAINTENANCE_THROTTLE_SECONDS / 3600,
        **summary,
    }
    if state is not None:
        out["last_run_epoch"] = state.get_meta(META_LAST_RUN)
        out["last_status"] = state.get_meta(META_LAST_STATUS)
        out["last_error"] = state.get_meta(META_LAST_ERROR)
        out["tombstone_count"] = len(state.recovery_tombstones(limit=1000))
    return out
