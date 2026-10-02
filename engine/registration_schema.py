"""Frozen ADR 0025 SQL v1 and ADR 0026 canonical SQL v2.

The checked-in SQL file remains the accepted v1 input.  V2 is derived only by
the exact, hash-pinned ADR 0026 transformation.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import sqlite3
import stat
import uuid
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Callable


SCHEMA_V1_SHA256 = "221aaf6680b50ca8f6c8c2cf024acbedbf5273b90c8c5625bcc4100c448d5ede"
SCHEMA_SHA256 = "b97f02ef67d48886f917368fa420fda0c5dd5942441b23a190732e3cc45106c8"
SCHEMA_V2_BYTES = 130_952
SCHEMA_V2_LINES = 1_285
TABLE_NAMES = frozenset(
    {
        "registration_protocol_epoch",
        "registration_member",
        "registration_episode",
        "registration_effect",
        "registration_effect_action",
        "registration_runtime_status",
        "registration_operation_audit",
    }
)
TRIGGER_NAMES = frozenset(
    {
        "trg_protocol_epoch_insert",
        "trg_operation_audit_insert",
        "trg_member_update_state_machine",
        "trg_episode_insert",
        "trg_effect_insert",
        "trg_effect_close",
        "trg_effect_action_append",
        "trg_runtime_status_insert",
        "trg_runtime_status_update",
    }
)

_LEAF_MANIFEST = """\
trg_protocol_epoch_insert=bootstrap@BOOTSTRAP@BOOTSTRAP@BOOTSTRAP@-;activate@ACTIVATE@ACTIVATE@ACTIVATE@-;first_effect@OPEN_EFFECT@FIRST_EFFECT@FIRST_EFFECT@-;begin_drain@BEGIN_DRAIN@BEGIN_DRAIN@BEGIN_DRAIN@-;stage_next@STAGE_NEXT@STAGE_NEXT@STAGE_NEXT@-;cancel_drain@CANCEL_DRAIN@CANCEL_DRAIN@CANCEL_DRAIN@-;advance_generation@ADVANCE_GENERATION@ADVANCE_GENERATION@ADVANCE_GENERATION@-;pre_effect_dormant@PRE_EFFECT_DORMANT@PRE_EFFECT_DORMANT@PRE_EFFECT_DORMANT@-;contain_boot@ENTER_CONTAINMENT@ENTER_CONTAINMENT@DRAIN_BOOT_CHANGED@-;contain_timeout@ENTER_CONTAINMENT@ENTER_CONTAINMENT@DRAIN_TIMEOUT@-;contain_adoption@ENTER_CONTAINMENT@ENTER_CONTAINMENT@ADOPTION_FAILED@-;contain_store@ENTER_CONTAINMENT@ENTER_CONTAINMENT@STORE_FAILURE@-;begin_repair@BEGIN_REPAIR@BEGIN_REPAIR@BEGIN_REPAIR@-
trg_operation_audit_insert=bootstrap@BOOTSTRAP@-@-@-;install_member@INSTALL_MEMBER@-@-@-;bind_episode@BIND_EPISODE@-@-@-;reacquire@REACQUIRE_EFFECT@-@-@-;open@OPEN_EFFECT@-@-@-;append@APPEND_ACTION@-@-@-;close_success@CLOSE_SUCCESS@-@-@SUCCESS;close_conflict@CLOSE_CONFLICT@-@-@LOGICAL_CONFLICT;invalidate@INVALIDATE_REQUESTED@-@BASIS_CHANGED@SUPERSEDED;set_pending@SET_PENDING@-@-@-;replace_pending@REPLACE_PENDING@-@PENDING_REPLACED@SUPERSEDED;handoff@HANDOFF_RESOLVED@-@-@-;mark_unavailable@MARK_UNAVAILABLE@-@-@-;reboot@REBOOT_STATUS@-@-@-;schedule@SCHEDULE_STATUS@-@-@-;activate@ACTIVATE@-@-@-;begin_drain@BEGIN_DRAIN@-@-@-;stage_next@STAGE_NEXT@-@-@-;cancel_drain@CANCEL_DRAIN@-@-@-;adopt@ADOPT_EFFECT@-@-@-;advance@ADVANCE_GENERATION@-@-@-;pre_effect_dormant@PRE_EFFECT_DORMANT@-@-@-;contain@ENTER_CONTAINMENT@-@-@-;begin_repair@BEGIN_REPAIR@-@-@-
trg_member_update_state_machine=invalidate@INVALIDATE_REQUESTED@REQUESTED_TO_REQUESTED@BASIS_CHANGED@SUPERSEDED;open@OPEN_EFFECT@REQUESTED_TO_IN_FLIGHT@-@-;set_pending@SET_PENDING@IN_FLIGHT_TO_IN_FLIGHT@-@-;replace_pending@REPLACE_PENDING@IN_FLIGHT_TO_IN_FLIGHT@PENDING_REPLACED@SUPERSEDED;adopt_preserve@ADOPT_EFFECT@IN_FLIGHT_TO_IN_FLIGHT@-@-;adopt_replace@ADOPT_EFFECT@IN_FLIGHT_TO_IN_FLIGHT@STAGED_CAPABILITY_INCOMPATIBLE@SUPERSEDED;close_success@CLOSE_SUCCESS@IN_FLIGHT_TO_RESOLVED@-@SUCCESS;close_conflict@CLOSE_CONFLICT@IN_FLIGHT_TO_RESOLVED@-@LOGICAL_CONFLICT;handoff_pending@HANDOFF_RESOLVED@RESOLVED_TO_REQUESTED@BASIS_CHANGED@-;handoff_basis@HANDOFF_RESOLVED@RESOLVED_TO_REQUESTED@BASIS_CHANGED@-;handoff_closure@HANDOFF_RESOLVED@RESOLVED_TO_REQUESTED@CURRENT_CLOSURE_CHANGED@-;handoff_conflict_retry@HANDOFF_RESOLVED@RESOLVED_TO_REQUESTED@EXPLICIT_CONFLICT_RETRY@-
trg_episode_insert=bind@BIND_EPISODE@-@-@-
trg_effect_insert=install@INSTALL_MEMBER@-@-@-;invalidate@INVALIDATE_REQUESTED@-@BASIS_CHANGED@-;set_pending@SET_PENDING@-@-@-;replace_pending@REPLACE_PENDING@-@PENDING_REPLACED@-;handoff_basis@HANDOFF_RESOLVED@-@BASIS_CHANGED@-;handoff_closure@HANDOFF_RESOLVED@-@CURRENT_CLOSURE_CHANGED@-;handoff_conflict_retry@HANDOFF_RESOLVED@-@EXPLICIT_CONFLICT_RETRY@-;adopt_replace@ADOPT_EFFECT@-@STAGED_CAPABILITY_INCOMPATIBLE@-
trg_effect_close=success@CLOSE_SUCCESS@-@-@SUCCESS;conflict@CLOSE_CONFLICT@-@-@LOGICAL_CONFLICT;supersede_requested@INVALIDATE_REQUESTED@-@BASIS_CHANGED@SUPERSEDED;supersede_pending@REPLACE_PENDING@-@PENDING_REPLACED@SUPERSEDED;supersede_adopted@ADOPT_EFFECT@-@STAGED_CAPABILITY_INCOMPATIBLE@SUPERSEDED
trg_effect_action_append=observed_exact@APPEND_ACTION@-@-@OBSERVED_EXACT;applied_verified@APPEND_ACTION@-@-@APPLIED_VERIFIED;logical_conflict@APPEND_ACTION@-@-@LOGICAL_CONFLICT
trg_runtime_status_insert=clean@INSTALL_MEMBER@-@CLEAN_ELIGIBLE@-;dirty@INSTALL_MEMBER@-@BLOCKED_DIRTY@-;operation_blocked@INSTALL_MEMBER@-@BLOCKED_OPERATION@-
trg_runtime_status_update=reacquire_native@REACQUIRE_EFFECT@-@NATIVE_GENERATION@-;reacquire_adopted@REACQUIRE_EFFECT@-@ADOPTED_LINEAGE@-;open@OPEN_EFFECT@-@-@-;close_success_idle@CLOSE_SUCCESS@-@NO_PENDING@SUCCESS;close_success_pending@CLOSE_SUCCESS@-@PENDING@SUCCESS;close_conflict_idle@CLOSE_CONFLICT@-@NO_PENDING@LOGICAL_CONFLICT;close_conflict_pending@CLOSE_CONFLICT@-@PENDING@LOGICAL_CONFLICT;invalidate_clean@INVALIDATE_REQUESTED@-@CLEAN_ELIGIBLE@-;invalidate_dirty@INVALIDATE_REQUESTED@-@BLOCKED_DIRTY@-;invalidate_operation@INVALIDATE_REQUESTED@-@BLOCKED_OPERATION@-;handoff_basis_clean@HANDOFF_RESOLVED@-@BASIS_CHANGED_CLEAN@-;handoff_basis_dirty@HANDOFF_RESOLVED@-@BASIS_CHANGED_DIRTY@-;handoff_basis_operation@HANDOFF_RESOLVED@-@BASIS_CHANGED_OPERATION@-;handoff_closure_clean@HANDOFF_RESOLVED@-@CURRENT_CLOSURE_CHANGED_CLEAN@-;handoff_closure_dirty@HANDOFF_RESOLVED@-@CURRENT_CLOSURE_CHANGED_DIRTY@-;handoff_closure_operation@HANDOFF_RESOLVED@-@CURRENT_CLOSURE_CHANGED_OPERATION@-;handoff_conflict_retry@HANDOFF_RESOLVED@-@EXPLICIT_CONFLICT_RETRY@-;adopt_preserve@ADOPT_EFFECT@-@PRESERVE_EXECUTOR@-;adopt_install@ADOPT_EFFECT@-@INSTALL_EXECUTOR@-;mark_unavailable@MARK_UNAVAILABLE@-@-@-;reboot_requested_clean@REBOOT_STATUS@-@REQUESTED_CLEAN@-;reboot_requested_dirty@REBOOT_STATUS@-@REQUESTED_DIRTY@-;reboot_requested_operation@REBOOT_STATUS@-@REQUESTED_OPERATION@-;reboot_in_flight@REBOOT_STATUS@-@IN_FLIGHT@-;reboot_resolved_success@REBOOT_STATUS@-@RESOLVED_SUCCESS@-;reboot_resolved_conflict@REBOOT_STATUS@-@RESOLVED_CONFLICT@-;reboot_resolved_pending@REBOOT_STATUS@-@RESOLVED_PENDING@-;schedule@SCHEDULE_STATUS@-@-@-
"""


def _parse_leaf_groups() -> dict[str, tuple[str, ...]]:
    groups: dict[str, tuple[str, ...]] = {}
    for line in _LEAF_MANIFEST.splitlines():
        trigger, leaves = line.split("=", 1)
        groups[trigger] = tuple(leaves.split(";"))
    if set(groups) != TRIGGER_NAMES:
        raise RuntimeError("registration leaf trigger inventory drift")
    return groups


LEAF_GROUPS = _parse_leaf_groups()
LEAF_IDS = frozenset(
    f"{trigger}|{leaf.replace('@', '|')}"
    for trigger, leaves in LEAF_GROUPS.items()
    for leaf in leaves
)
if len(LEAF_IDS) != 97:
    raise RuntimeError("registration leaf count drift")

ACCEPTANCE_IDS = tuple([f"A{i:02d}" for i in range(1, 30)] + ["A32"])


@dataclass(frozen=True)
class _SqlEdit:
    name: str
    start: int
    end: int
    old_sha256: str
    replacement: bytes
    replacement_sha256: str


_SQL_V2_EDITS = (
    _SqlEdit(
        "E01a",
        19_368,
        19_415,
        "96e71175309f9cb8e81d8645552958b247e516b09afb8a312a69573d472ac1c8",
        b"outcome_reservation_bytes BETWEEN 98304 AND 1048576",
        "632ae0d0283c2526a26575048d8fb4ffdabb8f277824db67f64d29422c407fc2",
    ),
    _SqlEdit(
        "E01b",
        19_470,
        19_519,
        "ea22cc17e3d50362245655a8f23a3f7528dd87e800475ec73a3f43b30f67c66b",
        b"successor_reservation_bytes BETWEEN 32768 AND 1048576",
        "5c80dd03cec1802e8df22a2bf65e9a7101ba4bc0787a692fcdf18f814a63ed3d",
    ),
    _SqlEdit(
        "E02",
        64_962,
        65_340,
        "84cddbd8ec36e58438459f5dd136eefb350ed50cf472e5fedacdebd33097c27f",
        b"""    AND NEW.runtime_capability_hash=CASE WHEN NEW.operation_kind IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT') AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' THEN (SELECT staged_runtime_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) ELSE (SELECT runtime_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) END
    AND NEW.writer_binary_hash=CASE WHEN NEW.operation_kind IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT') AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' THEN (SELECT staged_writer_binary_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) ELSE (SELECT writer_binary_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) END
    AND NEW.profile_hash=CASE WHEN NEW.operation_kind IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT') AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' THEN (SELECT staged_profile_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) ELSE (SELECT profile_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) END""",
        "cd79dae4ee624ff43a1daa2fbb5c6c7068bd37f5bac07378ca33b1282c208a86",
    ),
    _SqlEdit(
        "E03",
        65_358,
        65_638,
        "da39334f0388167ae907ff23c6f026e0e3fa43444e63814ed4c47142143b7e92",
        b"""      NEW.operation_class='DATA'
      AND (
       (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='WRITABLE'
       OR (
        NEW.operation_kind IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT')
        AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING'
        AND NEW.target_staged_epoch_hash=(SELECT staged_epoch_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
        AND EXISTS(
         SELECT 1 FROM registration_member m JOIN registration_runtime_status s ON s.member_id=m.member_id JOIN registration_effect e ON e.effect_id=m.current_effect_id JOIN registration_protocol_epoch p ON p.protocol_seq=(SELECT MAX(protocol_seq) FROM registration_protocol_epoch)
         WHERE m.member_id=NEW.target_member_id AND m.phase='EFFECT_IN_FLIGHT' AND m.current_effect_id=NEW.target_effect_id AND m.helper_generation=p.staged_generation AND e.outcome_kind IS NULL
           AND ((NEW.operation_kind='MARK_UNAVAILABLE' AND s.executor_token_hash=NEW.target_executor_token_hash AND s.executor_generation=p.staged_generation) OR (NEW.operation_kind='REACQUIRE_EFFECT' AND s.executor_token_hash IS NULL AND s.help_due=1))
           AND EXISTS(SELECT 1 FROM registration_operation_audit adopt WHERE adopt.operation_kind='ADOPT_EFFECT' AND adopt.target_member_id=m.member_id AND adopt.lineage_effect_id=e.effect_id AND adopt.target_staged_epoch_hash=p.staged_epoch_hash AND adopt.target_member_tuple_hash=m.member_tuple_hash)
        )
       )
      )
      AND NEW.writer_capability_receipt_hash=CASE WHEN (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' THEN (SELECT staged_writer_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) ELSE (SELECT writer_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) END""",
        "2276598eb92ff87f78820f4b464034aac97e7a1d9045278182437a5a9beda9df",
    ),
    _SqlEdit(
        "E04.1",
        68_017,
        68_145,
        "fe890932f5ca8e9623c604effeb935d840ab49c8b6df48784d32ffffca87b2fc",
        b"18874368 ELSE 1048576",
        "59e2f68c9c44a9aa81d8ecd6920fad16bb7397668e5a8142f4014cf5c9eb7042",
    ),
    _SqlEdit(
        "E05",
        68_431,
        68_431,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        b"""    AND (NEW.operation_kind NOT IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT') OR (NEW.projected_db_growth_bytes=8192 AND (SELECT COUNT(*) FROM registration_operation_audit WHERE operation_kind IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT') AND target_effect_id=NEW.target_effect_id)<6 AND (SELECT COALESCE(SUM(projected_db_growth_bytes),0) FROM registration_operation_audit WHERE operation_kind IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT') AND target_effect_id=NEW.target_effect_id)+NEW.projected_db_growth_bytes<=49152))
""",
        "7215af995833c039a006298500002c8967fe618835faa8b1fa89ed2a8115c967",
    ),
    _SqlEdit(
        "E04.2",
        68_766,
        68_894,
        "fe890932f5ca8e9623c604effeb935d840ab49c8b6df48784d32ffffca87b2fc",
        b"18874368 ELSE 1048576",
        "59e2f68c9c44a9aa81d8ecd6920fad16bb7397668e5a8142f4014cf5c9eb7042",
    ),
    _SqlEdit(
        "E06a",
        69_245,
        69_812,
        "3c3f7bfb45702b70e83db0a9529bbda1f994c9bb460577c2d9e78ce161d1c47b",
        b"WHEN NEW.operation_kind='APPEND_ACTION' THEN 18874368",
        "39bcd4b912d7821397b9a704e94e0a2ae1fab025ccbc5225286307c3aa56ab17",
    ),
    _SqlEdit(
        "E06b",
        69_820,
        69_996,
        "9b15d84b730b111e756f344a88653271918552f1c6d0b428ba02d6561ef774aa",
        b"WHEN NEW.operation_kind IN('CLOSE_SUCCESS','CLOSE_CONFLICT') THEN 1048576",
        "803a1f9e78bc33ae3897ad0889240033e64d71fad3005ac3dbaa9a4fc415513d",
    ),
    _SqlEdit(
        "E06.1",
        70_353,
        70_412,
        "56d1fae8267774c0571c7dca46e463150bd72b37035dead3093c653de4b941ae",
        b"+NEW.projected_db_growth_bytes<=e.outcome_reservation_bytes-49152",
        "2a898dd125979d80033753eb1319e23ed8621b74048f3968eceb9de6264445e0",
    ),
    _SqlEdit(
        "E06.2",
        70_950,
        71_009,
        "56d1fae8267774c0571c7dca46e463150bd72b37035dead3093c653de4b941ae",
        b"+NEW.projected_db_growth_bytes<=e.outcome_reservation_bytes-49152",
        "2a898dd125979d80033753eb1319e23ed8621b74048f3968eceb9de6264445e0",
    ),
    _SqlEdit(
        "E04.3",
        72_038,
        72_166,
        "fe890932f5ca8e9623c604effeb935d840ab49c8b6df48784d32ffffca87b2fc",
        b"18874368 ELSE 1048576",
        "59e2f68c9c44a9aa81d8ecd6920fad16bb7397668e5a8142f4014cf5c9eb7042",
    ),
    _SqlEdit(
        "E07",
        112_722,
        113_934,
        "bbf8700f5788f573a917c10aa7b61595e1fc6e5a9110281d92f93b94e4634119",
        b"""         AND (
          (p.mode='WRITABLE' AND p.protocol_generation=m.helper_generation AND ((e.required_protocol_generation=m.helper_generation AND e.required_runtime_capability_hash=p.runtime_capability_hash) OR (e.required_protocol_generation<>m.helper_generation AND EXISTS(SELECT 1 FROM registration_operation_audit adopt JOIN registration_protocol_epoch staged ON staged.protocol_seq=adopt.protocol_seq WHERE adopt.operation_kind='ADOPT_EFFECT' AND adopt.target_member_id=m.member_id AND adopt.lineage_effect_id=e.effect_id AND adopt.expected_generation=e.required_protocol_generation AND adopt.target_action_plan_hash=e.action_plan_hash AND adopt.target_staged_epoch_hash=staged.staged_epoch_hash AND staged.protocol_generation=e.required_protocol_generation AND staged.runtime_capability_hash=e.required_runtime_capability_hash AND staged.staged_generation=m.helper_generation AND staged.staged_runtime_capability_hash=p.runtime_capability_hash))))
          OR
          (p.mode='DRAINING' AND p.staged_generation=m.helper_generation AND EXISTS(SELECT 1 FROM registration_operation_audit adopt WHERE adopt.operation_kind='ADOPT_EFFECT' AND adopt.target_member_id=m.member_id AND adopt.lineage_effect_id=e.effect_id AND adopt.target_staged_epoch_hash=p.staged_epoch_hash AND adopt.target_member_tuple_hash=m.member_tuple_hash))
         )""",
        "86203c31d570c634d689be5ecb5a995c12ab7d906e824a75be7b153fc65c7f5c",
    ),
    _SqlEdit(
        "E08",
        114_273,
        114_619,
        "e2d31cc77febe39db28c86a7cf8a72f097ab64c2bd80dd6173083c4078e9889e",
        b"""      AND NEW.executor_token_hash IS NOT NULL
      AND NEW.executor_boot_id=(SELECT sample_boot_id FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id)
      AND NEW.executor_generation=CASE WHEN (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' THEN (SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) ELSE (SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) END
      AND NEW.schedule_boot_id IS NULL""",
        "20c6a2efb66c69043bfca653f4a64383548d8eef209f512ee29085c0e9b42153",
    ),
    _SqlEdit(
        "E09",
        121_861,
        121_861,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        b"""      AND (((SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='WRITABLE' AND OLD.executor_generation=(SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)) OR ((SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' AND OLD.executor_generation=(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) AND EXISTS(SELECT 1 FROM registration_member m JOIN registration_effect e ON e.effect_id=m.current_effect_id JOIN registration_protocol_epoch p ON p.protocol_seq=(SELECT MAX(protocol_seq) FROM registration_protocol_epoch) WHERE m.member_id=NEW.member_id AND m.helper_generation=p.staged_generation AND EXISTS(SELECT 1 FROM registration_operation_audit adopt WHERE adopt.operation_kind='ADOPT_EFFECT' AND adopt.target_member_id=m.member_id AND adopt.lineage_effect_id=e.effect_id AND adopt.target_staged_epoch_hash=p.staged_epoch_hash AND adopt.target_member_tuple_hash=m.member_tuple_hash))))
""",
        "b988180a6236bb7b04b9f54182d19831ad4a6da9f3d29877242a10f0380cc731",
    ),
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@lru_cache(maxsize=1)
def _canonical_sql_v2_bytes() -> bytes:
    source = Path(__file__).with_name("registration_schema.sql").read_bytes()
    if b"\r" in source or not source.endswith(b";\n"):
        raise RuntimeError("canonical registration SQL v1 framing mismatch")
    try:
        source.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise RuntimeError("canonical registration SQL v1 is not UTF-8") from error
    if _sha256(source) != SCHEMA_V1_SHA256:
        raise RuntimeError("canonical registration SQL v1 hash mismatch")
    transformed = source
    for edit in reversed(_SQL_V2_EDITS):
        old = source[edit.start : edit.end]
        if _sha256(old) != edit.old_sha256:
            raise RuntimeError(f"canonical SQL v2 {edit.name} source span mismatch")
        if _sha256(edit.replacement) != edit.replacement_sha256:
            raise RuntimeError(f"canonical SQL v2 {edit.name} replacement mismatch")
        transformed = (
            transformed[: edit.start] + edit.replacement + transformed[edit.end :]
        )
    if (
        len(transformed) != SCHEMA_V2_BYTES
        or transformed.count(b"\n") != SCHEMA_V2_LINES
        or not transformed.endswith(b";\n")
        or _sha256(transformed) != SCHEMA_SHA256
    ):
        raise RuntimeError("canonical registration SQL v2 output mismatch")
    return transformed


def canonical_sql_bytes() -> bytes:
    return _canonical_sql_v2_bytes()


def canonical_sql_text() -> str:
    return canonical_sql_bytes().decode("utf-8", "strict")


def _inventory(
    connection: sqlite3.Connection,
) -> list[tuple[str, str, str, str | None]]:
    return [
        tuple(row)
        for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
    ]


def verify_canonical_schema(
    connection: sqlite3.Connection, *, require_empty_genesis: bool = False
) -> None:
    actual = _inventory(connection)
    reference = sqlite3.connect(":memory:")
    try:
        reference.executescript(canonical_sql_text())
        expected = _inventory(reference)
    finally:
        reference.close()
    if actual != expected:
        raise RuntimeError("registration schema inventory/SQL drift")
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("registration schema integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("registration schema foreign-key drift")
    if require_empty_genesis:
        for table in TABLE_NAMES:
            if connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]:
                raise RuntimeError("registration schema genesis is not empty")


class FreshSchemaState(str, Enum):
    ABSENT = "ABSENT"
    COMPLETE = "COMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


class FreshSchemaPublicationError(RuntimeError):
    def __init__(self, state: FreshSchemaState, detail: str):
        super().__init__(f"{state.value}: {detail}")
        self.state = state


def has_fresh_schema_residue(path: Path) -> bool:
    path = Path(path)
    prefix = f".{path.name}.awa-schema-"
    try:
        with os.scandir(path.parent) as entries:
            return any(entry.name.startswith(prefix) for entry in entries)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise FreshSchemaPublicationError(
            FreshSchemaState.UNAVAILABLE,
            "schema residue classification is unavailable",
        ) from error


def _classify_fresh_schema(
    path: Path, *, ignored_candidate: Path | None = None
) -> FreshSchemaState:
    path = Path(path)
    for suffix in ("-journal", "-wal", "-shm"):
        try:
            Path(f"{path}{suffix}").lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return FreshSchemaState.UNAVAILABLE
        return FreshSchemaState.UNAVAILABLE
    try:
        with os.scandir(path.parent) as entries:
            prefix = f".{path.name}.awa-schema-"
            for entry in entries:
                if entry.name.startswith(prefix) and (
                    ignored_candidate is None
                    or entry.name != ignored_candidate.name
                ):
                    return FreshSchemaState.UNAVAILABLE
    except FileNotFoundError:
        pass
    except OSError:
        return FreshSchemaState.UNAVAILABLE
    try:
        info = path.lstat()
    except FileNotFoundError:
        return FreshSchemaState.ABSENT
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        return FreshSchemaState.UNAVAILABLE
    descriptor = -1
    result = FreshSchemaState.UNAVAILABLE
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if _stat_identity(before) == _stat_identity(info):
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                verify_canonical_schema(connection)
            finally:
                connection.close()
            after = os.fstat(descriptor)
            named = path.lstat()
            if (
                _stat_identity(before) == _stat_identity(after)
                and _stat_identity(after) == _stat_identity(named)
            ):
                result = FreshSchemaState.COMPLETE
    except (OSError, RuntimeError, sqlite3.Error):
        result = FreshSchemaState.UNAVAILABLE
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                result = FreshSchemaState.UNAVAILABLE
    return result


def classify_fresh_schema(path: Path) -> FreshSchemaState:
    return _classify_fresh_schema(Path(path))


def _canonical_statements() -> tuple[str, ...]:
    statements: list[str] = []
    pending = ""
    for line in canonical_sql_text().splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            statements.append(pending)
            pending = ""
    if pending or not statements:
        raise RuntimeError("canonical registration SQL statement framing mismatch")
    return tuple(statements)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_no_replace(source: Path, target: Path) -> None:
    if hasattr(ctypes.CDLL(None), "renameatx_np"):
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renameatx_np
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        if rename(
            -2,
            os.fsencode(source),
            -2,
            os.fsencode(target),
            0x00000004,
        ):
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(target))
        return
    os.link(source, target, follow_symlinks=False)
    source.unlink()


def _stat_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _verify_publisher_binding(descriptor: int, path: Path) -> None:
    try:
        held = os.fstat(descriptor)
        named = path.lstat()
    except OSError as error:
        raise FreshSchemaPublicationError(
            FreshSchemaState.UNAVAILABLE,
            "schema candidate binding is unavailable",
        ) from error
    if (
        _stat_identity(held) != _stat_identity(named)
        or not stat.S_ISREG(held.st_mode)
        or held.st_uid != os.geteuid()
        or stat.S_IMODE(held.st_mode) != 0o600
        or held.st_nlink != 1
    ):
        raise FreshSchemaPublicationError(
            FreshSchemaState.UNAVAILABLE,
            "schema candidate binding changed",
        )


def _retire_held_candidate(
    descriptor: int,
    candidate: Path,
    *,
    fault: Callable[[str], None],
) -> None:
    try:
        candidate.lstat()
    except FileNotFoundError:
        return
    _verify_publisher_binding(descriptor, candidate)
    fault("before_schema_candidate_unlink")
    candidate.unlink()
    fault("after_schema_candidate_unlink")
    fault("before_schema_cleanup_parent_fsync")
    _fsync_directory(candidate.parent)
    fault("after_schema_cleanup_parent_fsync")
    held = os.fstat(descriptor)
    if held.st_nlink != 0:
        raise FreshSchemaPublicationError(
            FreshSchemaState.UNAVAILABLE,
            "schema candidate inode remains linked",
        )
    try:
        candidate.lstat()
    except FileNotFoundError:
        return
    raise FreshSchemaPublicationError(
        FreshSchemaState.UNAVAILABLE,
        "schema candidate name was rebound during retirement",
    )


def _annotate_fresh_schema_state(
    error: BaseException,
    path: Path,
    candidate: Path,
    *,
    phase: str,
) -> FreshSchemaState | None:
    try:
        state = _classify_fresh_schema(
            path, ignored_candidate=candidate
        )
    except BaseException as classification:
        error.add_note(
            f"fresh-schema {phase} classification failed secondarily: "
            f"{type(classification).__name__}"
        )
        return None
    error.add_note(f"fresh-schema {phase} classified {state.value}")
    return state


def publish_fresh_schema(
    path: Path,
    *,
    fault: Callable[[str], None] | None = None,
    operation_id: str | None = None,
) -> FreshSchemaState:
    path = Path(path)
    fault = fault or (lambda _point: None)
    initial = classify_fresh_schema(path)
    if initial is not FreshSchemaState.ABSENT:
        raise FreshSchemaPublicationError(
            FreshSchemaState.UNAVAILABLE,
            "canonical database must be proven absent",
        )
    operation_id = operation_id or uuid.uuid4().hex + uuid.uuid4().hex
    if (
        len(operation_id) != 64
        or any(character not in "0123456789abcdef" for character in operation_id)
    ):
        raise FreshSchemaPublicationError(
            FreshSchemaState.UNAVAILABLE,
            "schema publication operation id is invalid",
        )
    candidate = path.with_name(
        f".{path.name}.awa-schema-{operation_id}.tmp"
    )
    descriptor = os.open(
        candidate,
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    primary: BaseException | None = None
    try:
        connection = sqlite3.connect(str(candidate), isolation_level=None)
        connection_primary: BaseException | None = None
        try:
            connection.execute("BEGIN EXCLUSIVE")
            for ordinal, statement in enumerate(_canonical_statements(), 1):
                fault(f"before_schema_statement:{ordinal}")
                connection.execute(statement)
                fault(f"after_schema_statement:{ordinal}")
            fault("before_schema_commit")
            connection.execute("COMMIT")
            fault("after_schema_commit")
            verify_canonical_schema(connection, require_empty_genesis=True)
        except BaseException as error:
            connection_primary = error
            if connection.in_transaction:
                try:
                    connection.execute("ROLLBACK")
                except BaseException as cleanup:
                    error.add_note(
                        "fresh-schema rollback failed secondarily: "
                        f"{type(cleanup).__name__}"
                    )
            raise
        finally:
            try:
                connection.close()
            except BaseException as cleanup:
                if connection_primary is not None:
                    connection_primary.add_note(
                        "fresh-schema connection close failed secondarily: "
                        f"{type(cleanup).__name__}"
                    )
                else:
                    raise
        os.fchmod(descriptor, 0o600)
        _verify_publisher_binding(descriptor, candidate)
        fault("before_schema_file_fsync")
        os.fsync(descriptor)
        fault("after_schema_file_fsync")
        if (
            _classify_fresh_schema(path, ignored_candidate=candidate)
            is not FreshSchemaState.ABSENT
        ):
            raise FreshSchemaPublicationError(
                FreshSchemaState.UNAVAILABLE,
                "canonical database appeared before publication",
            )
        fault("before_schema_publish")
        _verify_publisher_binding(descriptor, candidate)
        try:
            _publish_no_replace(candidate, path)
        except BaseException as error:
            state = _annotate_fresh_schema_state(
                error, path, candidate, phase="publication"
            )
            if isinstance(error, OSError) and error.errno in {
                errno.EEXIST,
                errno.EISDIR,
                errno.ENOTEMPTY,
            }:
                classified = FreshSchemaPublicationError(
                    FreshSchemaState.UNAVAILABLE,
                    "no-replace publication conflict",
                )
                if state is not None:
                    classified.add_note(
                        "fresh-schema publication classified "
                        f"{state.value}"
                    )
                raise classified from error
            raise
        published = _classify_fresh_schema(
            path, ignored_candidate=candidate
        )
        if published is not FreshSchemaState.COMPLETE:
            raise FreshSchemaPublicationError(
                published,
                "published database is not a complete canonical schema",
            )
        fault("after_schema_publish")
        _verify_publisher_binding(descriptor, path)
        fault("before_schema_parent_fsync")
        _fsync_directory(path.parent)
        fault("after_schema_parent_fsync")
        _verify_publisher_binding(descriptor, path)
        fault("before_schema_reopen")
        final = classify_fresh_schema(path)
        fault("after_schema_reopen")
        if final is not FreshSchemaState.COMPLETE:
            raise FreshSchemaPublicationError(
                FreshSchemaState.UNAVAILABLE,
                "published database did not classify COMPLETE",
            )
        _verify_publisher_binding(descriptor, path)
        return final
    except BaseException as error:
        primary = error
        _annotate_fresh_schema_state(
            error, path, candidate, phase="failure"
        )
        raise
    finally:
        cleanup_failure: BaseException | None = None
        try:
            _retire_held_candidate(
                descriptor,
                candidate,
                fault=fault,
            )
            for suffix in ("-journal", "-wal", "-shm"):
                residue = Path(f"{candidate}{suffix}")
                try:
                    residue.lstat()
                except FileNotFoundError:
                    continue
                raise FreshSchemaPublicationError(
                    FreshSchemaState.UNAVAILABLE,
                    f"unclassified schema residue remains: {residue.name}",
                )
        except BaseException as cleanup:
            if primary is not None:
                primary.add_note(
                    "fresh-schema residue cleanup failed secondarily: "
                    f"{type(cleanup).__name__}"
                )
            else:
                cleanup_failure = cleanup
        try:
            os.close(descriptor)
        except BaseException as cleanup:
            if primary is not None:
                primary.add_note(
                    "fresh-schema descriptor cleanup failed secondarily: "
                    f"{type(cleanup).__name__}"
                )
            elif cleanup_failure is not None:
                cleanup_failure.add_note(
                    "fresh-schema descriptor cleanup failed secondarily: "
                    f"{type(cleanup).__name__}"
                )
            else:
                cleanup_failure = cleanup
        if cleanup_failure is not None:
            raise cleanup_failure
