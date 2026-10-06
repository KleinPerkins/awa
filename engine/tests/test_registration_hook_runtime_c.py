"""Body C A21/A23/A25 hook-ingress and serializer fixtures."""

from __future__ import annotations

import json
import unittest

from engine import (
    registration_admission,
    registration_hook_runtime,
    registration_host,
)


def _payload(event: str, **extra: object) -> bytes:
    value = {
        "hook_event_name": event,
        "workspace_roots": ["/fixture/root"],
        "conversation_id": "conversation-1",
        "generation_id": "generation-1",
        **extra,
    }
    return json.dumps(value, separators=(",", ":")).encode()


class FakeService:
    def __init__(self, decisions: dict[str, str] | None = None) -> None:
        self.decisions = decisions or {}
        self.calls: list[registration_hook_runtime.ObservableInvocation] = []

    def handle(
        self,
        payload: object,
        invocation: registration_hook_runtime.ObservableInvocation,
    ):
        self.calls.append(invocation)
        reason = self.decisions.get(
            invocation.discriminator, "READY"
        )
        return registration_admission.AdmissionDecision(
            allowed=reason == "READY",
            reason=reason,
            response=registration_admission.render_reason(reason),
            attempts=1,
        )


class HookIngressTest(unittest.TestCase):
    def test_mcp_and_subagent_identity_propagates_all_four_fields(self) -> None:
        service = FakeService()
        for raw, expected in (
            (
                _payload(
                    "beforeMCPExecution",
                    mcp_server_name="server-a",
                    tool_name="lookup",
                ),
                registration_hook_runtime.ObservableInvocation(
                    "beforeMCPExecution",
                    "server-a",
                    "MCP:lookup",
                    "cursor-permission/v1",
                ),
            ),
            (
                _payload(
                    "beforeMCPExecution",
                    mcp_server_name="server-b",
                    tool_name="lookup",
                ),
                registration_hook_runtime.ObservableInvocation(
                    "beforeMCPExecution",
                    "server-b",
                    "MCP:lookup",
                    "cursor-permission/v1",
                ),
            ),
            (
                _payload("subagentStart", subagent_type="generalPurpose"),
                registration_hook_runtime.ObservableInvocation(
                    "subagentStart",
                    "",
                    "Task",
                    "cursor-subagent/v1",
                ),
            ),
        ):
            with self.subTest(expected=expected):
                registration_hook_runtime.dispatch_bytes(raw, service)
                self.assertEqual(service.calls[-1], expected)
        self.assertNotEqual(service.calls[0], service.calls[1])

    def test_catch_all_receives_ordinary_unknown_renamed_mcp_and_task(self) -> None:
        service = FakeService(
            {
                "RenamedTool": "UNKNOWN_DISCRIMINATOR",
                "Mystery": "UNKNOWN_DISCRIMINATOR",
                "Task": "TASK_SUBAGENT_DENIED",
            }
        )
        cases = (
            ("preToolUse", {"tool_name": "Shell"}, "Shell", True),
            ("preToolUse", {"tool_name": "Read"}, "Read", True),
            ("preToolUse", {"tool_name": "RenamedTool"}, "RenamedTool", False),
            ("preToolUse", {"tool_name": "Mystery"}, "Mystery", False),
            (
                "preToolUse",
                {"tool_name": "MCP:awa_status", "tool_input": {}},
                "MCP:awa_status",
                True,
            ),
            ("preToolUse", {"tool_name": "Task"}, "Task", False),
            (
                "subagentStart",
                {"subagent_type": "generalPurpose"},
                "Task",
                False,
            ),
            ("beforeShellExecution", {"command": "git status"}, "Shell", True),
            ("beforeReadFile", {"file_path": "/fixture/root/a"}, "Read", True),
            (
                "beforeMCPExecution",
                {"mcp_server_name": "awa", "tool_name": "awa_status"},
                "MCP:awa_status",
                True,
            ),
        )
        for event, extra, discriminator, allowed in cases:
            with self.subTest(event=event, discriminator=discriminator):
                result = registration_hook_runtime.dispatch_bytes(
                    _payload(event, **extra), service
                )
                self.assertEqual(result.decision.allowed, allowed)
                self.assertEqual(result.discriminator, discriminator)
                output = json.loads(result.output)
                self.assertEqual(
                    output["permission"], "allow" if allowed else "deny"
                )
        self.assertEqual(
            [call.discriminator for call in service.calls],
            [case[2] for case in cases],
        )

    def test_task_launch_deny_uses_body_b_policy_oracle(self) -> None:
        service = FakeService({"Task": "TASK_SUBAGENT_DENIED"})
        result = registration_hook_runtime.dispatch_bytes(
            _payload("preToolUse", tool_name="Task"), service
        )
        self.assertEqual(result.decision.reason, "TASK_SUBAGENT_DENIED")
        self.assertEqual(
            [call.discriminator for call in service.calls], ["Task"]
        )

    def test_real_host_denies_task_before_basis_or_persistence(self) -> None:
        class RefusingCollector:
            def collect_observation(self, _event):
                raise AssertionError("Task reached basis collection")

        service = object.__new__(registration_host.HostService)
        service.inventory = registration_admission.ToolInventory(
            ordinary=frozenset({"Shell"}),
            task_launch=frozenset({"Task"}),
        )
        service.inventory_entries = (
            registration_host.registration_projection.InventoryEntry(
                "preToolUse",
                "",
                "Task",
                "task_launch",
                "cursor-permission/v1",
            ),
        )
        service.collector = RefusingCollector()
        service.admission = registration_admission.AdmissionController
        decision = service.handle(
            {
                "hook_event_name": "preToolUse",
                "workspace_roots": ["/fixture/root"],
                "conversation_id": "conversation-1",
                "generation_id": "generation-1",
            },
            registration_hook_runtime.ObservableInvocation(
                "preToolUse",
                "",
                "Task",
                "cursor-permission/v1",
            ),
        )
        self.assertEqual(decision.reason, "TASK_SUBAGENT_DENIED")

    def test_real_host_serializes_body_b_basis_policy_failures(self) -> None:
        for reason in (
            "ROOT_UNSUPPORTED",
            "DEVICE_MISMATCH",
            "BASIS_TIMEOUT",
            "DIRTY_UNSUPPORTED",
            "GIT_OPERATION_UNSUPPORTED",
        ):
            class RefusingCollector:
                def collect_observation(self, _event, reason=reason):
                    raise registration_admission.BasisUnavailable(reason)

            service = object.__new__(registration_host.HostService)
            service.inventory = registration_admission.ToolInventory(
                ordinary=frozenset({"Shell"}),
                task_launch=frozenset({"Task"}),
            )
            service.inventory_entries = (
                registration_host.registration_projection.InventoryEntry(
                    "preToolUse",
                    "",
                    "Shell",
                    "ordinary",
                    "cursor-permission/v1",
                ),
            )
            service.inventory_tokens = {
                (
                    "preToolUse",
                    "",
                    "Shell",
                    "cursor-permission/v1",
                ): "Shell"
            }
            service.collector = RefusingCollector()
            service.admission = registration_admission.AdmissionController
            with self.subTest(reason=reason):
                decision = service.handle(
                    {
                        "hook_event_name": "preToolUse",
                        "workspace_roots": ["/fixture/root"],
                        "conversation_id": "conversation-1",
                        "generation_id": "generation-1",
                    },
                    registration_hook_runtime.ObservableInvocation(
                        "preToolUse",
                        "",
                        "Shell",
                        "cursor-permission/v1",
                    ),
                )
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, reason)

    def test_preidentity_failure_is_fixed_stateless_deny(self) -> None:
        service = FakeService()
        raw = json.dumps(
            {
                "hook_event_name": "preToolUse",
                "workspace_roots": [],
                "conversation_id": "conversation-1",
                "generation_id": "generation-1",
                "tool_name": "Shell",
            }
        ).encode()
        result = registration_hook_runtime.dispatch_bytes(raw, service)
        self.assertFalse(result.decision.allowed)
        self.assertEqual(result.decision.reason, "PARSER_REJECT")
        self.assertEqual(
            result.decision.response,
            registration_admission.PREIDENTITY_RESPONSE,
        )
        self.assertEqual(service.calls, [])

    def test_nested_tool_input_root_and_identity_must_agree(self) -> None:
        service = FakeService()
        mismatched = registration_hook_runtime.dispatch_bytes(
            _payload(
                "preToolUse",
                tool_name="Shell",
                tool_input={
                    "command": "git status",
                    "workspace_roots": ["/other/root"],
                },
            ),
            service,
        )
        self.assertEqual(mismatched.decision.reason, "PARSER_REJECT")
        self.assertEqual(service.calls, [])
        matching = registration_hook_runtime.dispatch_bytes(
            _payload(
                "preToolUse",
                tool_name="Shell",
                tool_input={
                    "command": "git status",
                    "workspace_roots": ["/fixture/root"],
                    "conversation_id": "conversation-1",
                    "generation_id": "generation-1",
                },
            ),
            service,
        )
        self.assertTrue(matching.decision.allowed)
        self.assertEqual(
            [call.discriminator for call in service.calls], ["Shell"]
        )

    def test_event_specific_serializers_are_closed_and_deterministic(self) -> None:
        deny = registration_admission.AdmissionDecision(
            False,
            "TASK_SUBAGENT_DENIED",
            registration_admission.render_reason("TASK_SUBAGENT_DENIED"),
            0,
        )
        for event, expected_keys in (
            (
                "preToolUse",
                {"permission", "user_message", "agent_message"},
            ),
            (
                "beforeShellExecution",
                {"permission", "user_message", "agent_message"},
            ),
            (
                "beforeReadFile",
                {"permission", "user_message", "agent_message"},
            ),
            (
                "beforeMCPExecution",
                {"permission", "user_message", "agent_message"},
            ),
            ("subagentStart", {"permission", "user_message"}),
        ):
            with self.subTest(event=event):
                first = registration_hook_runtime.serialize_decision(
                    event, deny
                )
                second = registration_hook_runtime.serialize_decision(
                    event, deny
                )
                self.assertEqual(first, second)
                self.assertTrue(first.endswith(b"\n"))
                self.assertEqual(set(json.loads(first)), expected_keys)
        with self.assertRaises(
            registration_hook_runtime.SerializerUnavailable
        ):
            registration_hook_runtime.serialize_decision("renamedEvent", deny)

    def test_store_and_containment_unavailable_never_claim_denial(self) -> None:
        for reason in ("STORE_UNAVAILABLE", "CONTAINMENT_UNAVAILABLE"):
            with self.subTest(reason=reason):
                service = FakeService({"Shell": reason})
                with self.assertRaises(
                    registration_hook_runtime.HookUnavailable
                ):
                    registration_hook_runtime.dispatch_bytes(
                        _payload("preToolUse", tool_name="Shell"),
                        service,
                    )

    def test_duplicate_oversize_and_invalid_utf8_are_bounded_preidentity_denies(
        self,
    ) -> None:
        duplicate = (
            b'{"hook_event_name":"preToolUse",'
            b'"tool_name":"Shell","tool_name":"Read",'
            b'"workspace_roots":["/fixture/root"],'
            b'"conversation_id":"conversation-1",'
            b'"generation_id":"generation-1"}'
        )
        service = FakeService()
        for raw in (duplicate, b"\xff", b"x" * 65_537):
            with self.subTest(raw=raw[:20]):
                result = registration_hook_runtime.dispatch_bytes(raw, service)
                self.assertEqual(result.decision.reason, "PARSER_REJECT")
        self.assertEqual(service.calls, [])


if __name__ == "__main__":
    unittest.main()
