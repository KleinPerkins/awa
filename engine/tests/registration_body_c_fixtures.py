"""Body C-owned immutable scenario catalog supplied to A25/A27/A28/A32."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SerializerFixture:
    event: str
    reason: str
    expected_permission: str


@dataclass(frozen=True)
class ControlSequenceFixture:
    cut: str
    protocol_mode: str
    staged: bool
    old_entry_enabled: bool
    expected_action: str


@dataclass(frozen=True)
class ResolverFixture:
    resolver: str
    fault: str
    expected: str


@dataclass(frozen=True)
class StorageFixture:
    call_site: str
    fault: str
    expected: str
    durable_claim: bool


A25_SERIALIZERS = (
    SerializerFixture("preToolUse", "READY", "allow"),
    SerializerFixture(
        "preToolUse", "TASK_SUBAGENT_DENIED", "deny"
    ),
    SerializerFixture(
        "beforeShellExecution", "HOOK_UNSUPPORTED", "deny"
    ),
    SerializerFixture("beforeReadFile", "PARSER_REJECT", "deny"),
    SerializerFixture(
        "beforeMCPExecution", "UNKNOWN_DISCRIMINATOR", "deny"
    ),
    SerializerFixture(
        "subagentStart", "TASK_SUBAGENT_DENIED", "deny"
    ),
)

A27_CONTROL_SEQUENCE = (
    ControlSequenceFixture("C0", "WRITABLE", False, True, "R0_PREFLIGHT"),
    ControlSequenceFixture("C1", "WRITABLE", False, True, "PROJECT_NEW"),
    ControlSequenceFixture("C2", "WRITABLE", False, True, "DISABLE_OLD"),
    ControlSequenceFixture("C3", "WRITABLE", False, False, "BEGIN_DRAIN"),
    ControlSequenceFixture("C4", "DRAINING", False, False, "STAGE_ADOPT"),
    ControlSequenceFixture("C5", "DRAINING", True, False, "ADVANCE"),
    ControlSequenceFixture("C6", "WRITABLE", False, False, "CLEAN_OLD"),
    ControlSequenceFixture("C7", "WRITABLE", False, False, "VERIFY"),
)

A28_RESOLVERS = tuple(
    ResolverFixture(resolver, fault, expected)
    for resolver, outcomes in (
        (
            "close",
            {
                "committed_success": "COMMITTED_SUCCESS",
                "committed_conflict": "COMMITTED_LOGICAL_CONFLICT",
                "absent": "ABSENT",
                "busy": "UNAVAILABLE",
                "ioerr": "UNAVAILABLE",
                "enospc": "UNAVAILABLE",
                "lock": "UNAVAILABLE",
                "reboot": "UNAVAILABLE",
                "concurrency": "UNAVAILABLE",
            },
        ),
        (
            "successor",
            {
                "applied": "APPLIED",
                "absent": "ABSENT",
                "obsolete": "OBSOLETE",
                "busy": "UNAVAILABLE",
                "ioerr": "UNAVAILABLE",
                "enospc": "UNAVAILABLE",
                "lock": "UNAVAILABLE",
                "reboot": "UNAVAILABLE",
                "concurrency": "UNAVAILABLE",
            },
        ),
        (
            "reacquire",
            {
                "committed": "COMMITTED",
                "absent": "ABSENT",
                "partial": "PARTIAL",
                "busy": "UNAVAILABLE",
                "ioerr": "UNAVAILABLE",
                "enospc": "UNAVAILABLE",
                "lock": "UNAVAILABLE",
                "reboot": "UNAVAILABLE",
                "concurrency": "UNAVAILABLE",
            },
        ),
    )
    for fault, expected in outcomes.items()
)

A32_STORAGE_CALL_SITES = (
    StorageFixture("install", "low_free", "ZERO_WRITE", False),
    StorageFixture("begin_drain", "low_free", "ZERO_WRITE", False),
    StorageFixture("stage_next", "SQLITE_FULL", "ABSENT", False),
    StorageFixture("adopt_effect", "SQLITE_IOERR", "RESOLVE_EXACT", False),
    StorageFixture(
        "advance_generation", "containment_commit_failed",
        "CONTAINMENT_UNAVAILABLE", False
    ),
    StorageFixture(
        "advance_generation", "containment_committed", "CONTAINMENT", True
    ),
)
