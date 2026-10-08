"""Body C permission-hook receiver and closed fail-open serializers."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Protocol

from . import registration_admission


MAX_PAYLOAD_BYTES = 65_536
_COMMON_KEYS = {
    "conversation_id",
    "generation_id",
    "session_id",
    "model",
    "model_id",
    "model_params",
    "hook_event_name",
    "cursor_version",
    "workspace_roots",
    "user_email",
    "transcript_path",
    "event",
    "conversationId",
    "generationId",
    "sessionId",
    "workspaceRoot",
    "workspace_path",
    "root",
    "projectRoot",
}
_EVENT_KEYS = {
    "preToolUse": {
        "tool_name",
        "tool_input",
        "tool_use_id",
        "cwd",
        "agent_message",
    },
    "subagentStart": {
        "subagent_id",
        "subagent_type",
        "task",
        "parent_conversation_id",
        "tool_call_id",
        "subagent_model",
        "is_parallel_worker",
        "git_branch",
    },
    "beforeShellExecution": {"command", "cwd", "sandbox"},
    "beforeReadFile": {"file_path", "content", "attachments"},
    "beforeMCPExecution": {
        "tool_name",
        "tool_input",
        "mcp_server_name",
        "url",
        "mcp_server_url",
        "command",
    },
    # Older documented builds used this spelling. It is an explicit
    # compatibility ingress, never an inferred alias in persisted evidence.
    "beforeMCP": {
        "tool_name",
        "tool_input",
        "mcp_server_name",
        "url",
        "mcp_server_url",
        "command",
    },
}


class HookUnavailable(RuntimeError):
    """No seam-valid deny may be claimed for this invocation."""


class SerializerUnavailable(HookUnavailable):
    """The event has no exact permission response schema."""


class Service(Protocol):
    def handle(
        self, payload: object, invocation: "ObservableInvocation"
    ) -> registration_admission.AdmissionDecision: ...


@dataclass(frozen=True)
class ObservableInvocation:
    event: str
    server_or_empty: str
    discriminator: str
    serializer_schema: str


@dataclass(frozen=True)
class DispatchResult:
    event: str
    discriminator: str
    decision: registration_admission.AdmissionDecision
    output: bytes


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _decode(raw: bytes) -> dict:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_PAYLOAD_BYTES:
        raise ValueError("payload size unsupported")
    try:
        registration_admission._scan_json_shape(raw)
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(value)
            ),
        )
    except (
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        RecursionError,
        MemoryError,
        registration_admission.EventRefused,
    ) as exc:
        raise ValueError("payload is not strict JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    return value


def _event_and_discriminator(value: dict) -> tuple[str, str]:
    event = value.get("hook_event_name")
    if not isinstance(event, str) or event not in _EVENT_KEYS:
        raise ValueError("unsupported event")
    if set(value) - (_COMMON_KEYS | _EVENT_KEYS[event]):
        raise ValueError("unknown event field")
    if event == "subagentStart":
        discriminator = "Task"
    elif event == "beforeShellExecution":
        discriminator = "Shell"
    elif event == "beforeReadFile":
        discriminator = "Read"
    elif event in {"beforeMCPExecution", "beforeMCP"}:
        tool = value.get("tool_name")
        if not isinstance(tool, str) or not tool:
            raise ValueError("MCP tool name unavailable")
        discriminator = f"MCP:{tool}"
    else:
        discriminator = value.get("tool_name")
        if not isinstance(discriminator, str) or not discriminator:
            raise ValueError("tool discriminator unavailable")
    if (
        not isinstance(discriminator, str)
        or discriminator != discriminator.strip()
        or len(discriminator.encode("utf-8")) > 256
        or "\0" in discriminator
    ):
        raise ValueError("invalid tool discriminator")
    return event, discriminator


def _observable_invocation(
    value: dict, event: str, discriminator: str
) -> ObservableInvocation:
    server = (
        value.get("mcp_server_name", "")
        if event in {"beforeMCPExecution", "beforeMCP"}
        else ""
    )
    if (
        not isinstance(server, str)
        or "\0" in server
        or (
            event in {"beforeMCPExecution", "beforeMCP"}
            and not server
        )
    ):
        raise ValueError("MCP server identity is invalid")
    serializer = (
        "cursor-subagent/v1"
        if event == "subagentStart"
        else "cursor-permission/v1"
    )
    return ObservableInvocation(
        event=event,
        server_or_empty=server,
        discriminator=discriminator,
        serializer_schema=serializer,
    )


def parse_observable_invocation(payload: object) -> ObservableInvocation:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    event, discriminator = _event_and_discriminator(payload)
    return _observable_invocation(payload, event, discriminator)


def _normalized_event(value: dict, event: str) -> dict:
    normalized = {
        key: value[key]
        for key in (
            "hook_event_name",
            "event",
            "workspace_roots",
            "conversation_id",
            "conversationId",
            "generation_id",
            "generationId",
            "session_id",
            "sessionId",
            "cwd",
            "workspaceRoot",
            "workspace_path",
            "root",
            "projectRoot",
        )
        if key in value
    }
    normalized["hook_event_name"] = event
    nested = value.get("tool_input")
    if isinstance(nested, str):
        if event not in {"beforeMCPExecution", "beforeMCP"}:
            raise ValueError("string tool_input is unsupported")
        if len(nested.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError("nested tool input exceeds bound")
        try:
            nested_raw = nested.encode("utf-8", "strict")
            registration_admission._scan_json_shape(nested_raw)
            nested = json.loads(
                nested_raw.decode("utf-8", "strict"),
                object_pairs_hook=_pairs,
                parse_constant=lambda item: (_ for _ in ()).throw(
                    ValueError(item)
                ),
            )
        except (
            UnicodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            RecursionError,
            MemoryError,
            registration_admission.EventRefused,
        ) as exc:
            raise ValueError("nested tool input is not strict JSON") from exc
    if nested is not None:
        if not isinstance(nested, dict):
            raise ValueError("tool_input must be an object")
        normalized["tool_input"] = nested
    return normalized


def _preidentity(
    event: str = "preToolUse",
) -> registration_admission.AdmissionDecision:
    del event
    return registration_admission.AdmissionDecision(
        False,
        "PARSER_REJECT",
        registration_admission.PREIDENTITY_RESPONSE,
        0,
    )


def serialize_decision(
    event: str, decision: registration_admission.AdmissionDecision
) -> bytes:
    if event not in _EVENT_KEYS:
        raise SerializerUnavailable("unsupported hook serializer")
    permission = "allow" if decision.allowed else "deny"
    if event == "subagentStart":
        value = {
            "permission": permission,
            "user_message": decision.response,
        }
    else:
        value = {
            "permission": permission,
            "user_message": decision.response,
            "agent_message": decision.response,
        }
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")


def dispatch_bytes(raw: bytes, service: Service) -> DispatchResult:
    try:
        value = _decode(raw)
        invocation = parse_observable_invocation(value)
        event = invocation.event
        discriminator = invocation.discriminator
        normalized = _normalized_event(value, event)
        # Preserve accepted discriminator ordering: preidentity/root parsing
        # happens before launch/unknown/ordinary policy.
        registration_admission.parse_registration_event(normalized)
    except (
        ValueError,
        registration_admission.EventRefused,
    ):
        event = (
            value.get("hook_event_name", "preToolUse")
            if "value" in locals() and isinstance(value, dict)
            else "preToolUse"
        )
        if event not in _EVENT_KEYS:
            event = "preToolUse"
        decision = _preidentity(event)
        return DispatchResult(
            event,
            "",
            decision,
            serialize_decision(event, decision),
        )
    decision = service.handle(normalized, invocation)
    if decision.reason in {
        "STORE_UNAVAILABLE",
        "CONTAINMENT_UNAVAILABLE",
    }:
        raise HookUnavailable(
            "authority unavailable; no denial claim is valid"
        )
    return DispatchResult(
        event,
        discriminator,
        decision,
        serialize_decision(event, decision),
    )


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES + 1)
        from . import registration_host

        with registration_host.open_service() as service:
            result = dispatch_bytes(raw, service)
        sys.stdout.buffer.write(result.output)
        sys.stdout.buffer.flush()
        return 0
    except BaseException:
        # This global wrapper is deliberately quiet and fail-open. Only an
        # already serialized response or intentional exit 2 may claim denial.
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
