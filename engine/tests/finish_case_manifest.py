"""Closed pure/physical partition for finish choice matrices and safety canaries."""

from __future__ import annotations

import builtins
import contextlib
import fcntl
import os
import socket
import subprocess
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from unittest import mock

from consumer import finish_current as UX


PURE_CHOICE_ORACLE = "consumer.finish_current.canonicalize_choice"
PHYSICAL_CHOICE_ORACLE = (
    "engine.tests.test_finish_hardening.CurrentEnvelopeAdversarialTest."
    "test_non_destructive_casing_matrix_through_hook_envelope_and_current"
)


@dataclass(frozen=True)
class FinishCase:
    case_id: str
    layer: str
    input: Mapping[str, object]
    expected: Mapping[str, object]
    oracle: str


def _closed(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(values))


def _choice_case(
        case_id: str, answer: object, canonical_choice: str | None, reason: str, *,
        layer: str = "pure", state: str | None = None,
        attachments: object = None) -> FinishCase:
    input_values = {"answer": answer}
    if attachments is not None:
        input_values["attachments"] = attachments
    expected = {
        "canonical_choice": canonical_choice,
        "reason": reason,
        "accepted": canonical_choice is not None,
    }
    oracle = PURE_CHOICE_ORACLE
    if layer == "physical":
        expected["state"] = state
        oracle = PHYSICAL_CHOICE_ORACLE
    return FinishCase(
        case_id=case_id,
        layer=layer,
        input=_closed(input_values),
        expected=_closed(expected),
        oracle=oracle,
    )


ALL_FINISH_CASES = (
    _choice_case("choice.commit.exact", "Commit", "Commit", "ok"),
    _choice_case("choice.commit.lower", "commit", "Commit", "ok"),
    _choice_case("choice.commit.upper", "COMMIT", "Commit", "ok"),
    _choice_case(
        "choice.commit.mixed", "CoMmIt", "Commit", "ok",
        layer="physical", state="awaiting_commit_selection"),
    _choice_case("choice.commit.trimmed", " \tcommit\n", "Commit", "ok"),
    _choice_case("choice.retain.exact", "Retain", "Retain", "ok"),
    _choice_case("choice.retain.lower", "retain", "Retain", "ok"),
    _choice_case("choice.retain.upper", "RETAIN", "Retain", "ok"),
    _choice_case(
        "choice.retain.mixed", "ReTaIn", "Retain", "ok",
        layer="physical", state="awaiting_retain_selection"),
    _choice_case("choice.retain.trimmed", "\nretain ", "Retain", "ok"),
    _choice_case("choice.mixed.exact", "Mixed", "Mixed", "ok"),
    _choice_case("choice.mixed.lower", "mixed", "Mixed", "ok"),
    _choice_case("choice.mixed.upper", "MIXED", "Mixed", "ok"),
    _choice_case(
        "choice.mixed.mixed", "MiXeD", "Mixed", "ok",
        layer="physical", state="awaiting_mixed_selection"),
    _choice_case("choice.mixed.trimmed", " mixed\t", "Mixed", "ok"),
    _choice_case("choice.cancel.exact", "Cancel", "Cancel", "ok"),
    _choice_case("choice.cancel.lower", "cancel", "Cancel", "ok"),
    _choice_case("choice.cancel.upper", "CANCEL", "Cancel", "ok"),
    _choice_case(
        "choice.cancel.mixed", "CaNcEl", "Cancel", "ok",
        layer="physical", state="cancelled"),
    _choice_case("choice.cancel.trimmed", "\tcancel ", "Cancel", "ok"),
    _choice_case("choice.close.exact", "Close", "Close", "ok"),
    _choice_case(
        "choice.close.lower", "close", None, "close_must_be_exact"),
    _choice_case(
        "choice.close.upper", "CLOSE", None, "close_must_be_exact"),
    _choice_case(
        "choice.close.mixed", "cLoSe", None, "close_must_be_exact"),
    _choice_case(
        "choice.close.padded", " Close ", None, "close_must_be_exact"),
    _choice_case(
        "choice.close.tabbed", "\tClose\n", None, "close_must_be_exact"),
    _choice_case(
        "choice.reject.extra_words", "Close please", None, "choice_not_standalone"),
    _choice_case(
        "choice.reject.yes", "yes", None, "choice_not_standalone"),
    _choice_case("choice.reject.empty", "", None, "choice_empty"),
    _choice_case(
        "choice.reject.true", True, None, "boolean_not_allowed"),
    _choice_case(
        "choice.reject.false", False, None, "boolean_not_allowed"),
    _choice_case(
        "choice.reject.integer", 1, None, "choice_not_string"),
    _choice_case(
        "choice.reject.none", None, None, "choice_not_string"),
    _choice_case(
        "choice.reject.attachment", "Cancel", None, "attachments_present",
        attachments=(("name", "x"),)),
)


PHYSICAL_CANARIES = MappingProxyType({
    "crash_cut": _closed({
        "positive": (
            "engine.tests.test_finish_kernel.OrdinaryCleanUnchangedTest."
            "test_ordinary_clean_path_still_removes_merged_worktree"
        ),
        "negative": (
            "engine.tests.test_finish_publication_projection.RetainTrustLatchTest."
            "test_crash_immediately_before_and_after_commit_marker_is_truthful"
        ),
    }),
    "fsync": _closed({
        "positive": (
            "engine.tests.test_finish_durability.DestructiveDurabilityOrderingTest."
            "test_namespace_sync_precedes_branch_update_and_journal_receipt"
        ),
        "negative": (
            "engine.tests.test_finish_durability.DurabilityPrimitiveTest."
            "test_nested_private_creation_replace_visibility_adoption_and_unlink"
        ),
    }),
    "f_fullfsync": _closed({
        "positive": (
            "engine.tests.test_finish_durability.DurabilityPrimitiveTest."
            "test_darwin_requires_fsync_then_fullfsync_and_retries_eintr"
        ),
        "negative": (
            "engine.tests.test_finish_durability.DurabilityPrimitiveTest."
            "test_darwin_missing_or_failed_fullfsync_never_downgrades"
        ),
    }),
    "retention": _closed({
        "positive": (
            "engine.tests.test_finish_conversation.RetainArtifactTest."
            "test_typed_artifact_restore_proof_permissions_lifecycle_and_secret"
        ),
        "negative": (
            "engine.tests.test_finish_conversation.RetainArtifactTest."
            "test_retain_lock_contention_refuses_and_preserves_source"
        ),
    }),
    "publication": _closed({
        "positive": (
            "engine.tests.test_finish_publication_projection.RetainTrustLatchTest."
            "test_committed_marker_binds_exact_true_manifest_and_suppression"
        ),
        "negative": (
            "engine.tests.test_finish_publication_projection.RetainTrustLatchTest."
            "test_post_manifest_replace_pre_parent_sync_is_never_published"
        ),
    }),
    "stable_snapshot_recapture": _closed({
        "positive": (
            "engine.tests.test_finish_kernel.DeterminismGateTest."
            "test_fingerprint_stable_across_repeated_runs"
        ),
        "negative": (
            "engine.tests.test_finish_operations.GitOperationInventoryTest."
            "test_operation_admin_links_specials_mounts_and_drift_refuse"
        ),
    }),
    "no_follow": _closed({
        "positive": (
            "engine.tests.test_finish_kernel.InventoryTest."
            "test_directory_traversal_scans_open_nofollow_descriptors"
        ),
        "negative": (
            "engine.tests.test_finish_kernel.InventoryTest."
            "test_symlink_escape_refuses"
        ),
    }),
    "shared_lock": _closed({
        "positive": (
            "engine.tests.test_finish_kernel.EngineOffAndLockAbiTest."
            "test_finish_execute_removes_with_engine_unimportable"
        ),
        "negative": (
            "engine.tests.test_finish_kernel.FoldedHardeningTest."
            "test_finish_refuses_when_common_dir_lock_held"
        ),
    }),
    "removal_journal": _closed({
        "positive": (
            "engine.tests.test_finish_kernel.RemovalJournalTest."
            "test_shell_reconciles_valid_removed_result_before_deferred_receipt"
        ),
        "negative": (
            "engine.tests.test_finish_kernel.RemovalJournalTest."
            "test_prepared_state_write_failure_preserves_root_and_reports_no_removal"
        ),
    }),
})


_FORBIDDEN_PHYSICAL_CALLS = (
    (builtins, "open"),
    (os, "open"),
    (os, "stat"),
    (os, "lstat"),
    (os, "replace"),
    (os, "rename"),
    (os, "unlink"),
    (os, "mkdir"),
    (os, "makedirs"),
    (os, "chmod"),
    (os, "fchmod"),
    (os, "fsync"),
    (subprocess, "run"),
    (subprocess, "Popen"),
    (fcntl, "flock"),
    (time, "time"),
    (time, "monotonic"),
    (socket, "socket"),
)


@contextlib.contextmanager
def deny_physical_access() -> Iterator[None]:
    with contextlib.ExitStack() as stack:
        for owner, name in _FORBIDDEN_PHYSICAL_CALLS:
            stack.enter_context(mock.patch.object(
                owner, name,
                side_effect=AssertionError("physical access from pure case"),
            ))
        yield


def finish_cases(*, layer: str | None = None) -> tuple[FinishCase, ...]:
    if layer is None:
        return ALL_FINISH_CASES
    if layer not in {"pure", "physical"}:
        raise ValueError("unknown finish case layer")
    return tuple(case for case in ALL_FINISH_CASES if case.layer == layer)


def production_decision_adapter(case_input: Mapping[str, object]) -> Mapping[str, object]:
    answer = case_input.get("answer")
    attachments = case_input.get("attachments")
    canonical_choice, reason = UX.canonicalize_choice(answer, attachments)
    return _closed({
        "canonical_choice": canonical_choice,
        "reason": reason,
        "accepted": UX.is_exact_choice(answer, attachments),
    })


def run_pure_case(
        case: FinishCase,
        adapter: Callable[[Mapping[str, object]], Mapping[str, object]] =
        production_decision_adapter) -> Mapping[str, object]:
    if case.layer != "pure":
        raise AssertionError("physical case cannot use pure runner")
    if case.oracle != PURE_CHOICE_ORACLE:
        raise AssertionError("unknown pure finish oracle")
    with deny_physical_access():
        actual = adapter(case.input)
    if dict(actual) != dict(case.expected):
        raise AssertionError(
            f"{case.case_id}: {dict(actual)!r} != {dict(case.expected)!r}")
    return actual
