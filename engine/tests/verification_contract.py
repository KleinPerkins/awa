"""Closed machine validators for AWA verification evidence.

These records are descriptive evidence only.  They never authorize a skipped
verification step or any AWA safety/lifecycle decision.
"""

from __future__ import annotations

import datetime as _datetime
import re
from collections.abc import Mapping


RECEIPT_SCHEMA = "awa-test-receipt/v1"
OUTCOMES = (
    "passed",
    "failure",
    "error",
    "skipped",
    "expected_failure",
    "unexpected_success",
)
RUN_OUTCOMES = ("passed", "failure", "error")
LANES = ("docs", "focused", "pre-pr", "install", "release")

RECEIPT_KEYS = frozenset(
    {
        "schema",
        "head_before",
        "head_after",
        "source_clean_before",
        "source_clean_after",
        "source_state",
        "reusable",
        "authorizes_skip",
        "lane",
        "jobs",
        "python",
        "git",
        "runner_sha256",
        "inventory_sha256",
        "test_count",
        "records",
        "run",
        "context",
    }
)
RECORD_KEYS = frozenset(
    {"test_id", "module", "outcome", "skip_reason", "elapsed_ms"}
)
RUN_KEYS = frozenset({"outcome", "elapsed_ms", "counts"})
CONTEXT_KEYS = frozenset(
    {
        "command",
        "selectors",
        "platform",
        "architecture",
        "logical_cpu_count",
        "load_note",
        "generated_at_utc",
        "resource",
    }
)
RESOURCE_KEYS = frozenset({"user_ms", "system_ms", "max_rss_kb"})

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_OID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


class ContractError(ValueError):
    """A verification evidence document violated its closed contract."""


def _require_mapping(value: object, label: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    return value


def _require_exact_keys(value: object, expected: frozenset, label: str) -> Mapping:
    mapping = _require_mapping(value, label)
    actual = frozenset(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ContractError(
            f"{label} keys mismatch: missing={missing!r} unknown={unknown!r}"
        )
    return mapping


def _require_literal(value: object, expected: object, label: str) -> None:
    if value != expected or type(value) is not type(expected):
        raise ContractError(f"{label} must be {expected!r}")


def _require_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise ContractError(f"{label} must be a boolean")
    return value


def _require_nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ContractError(f"{label} must be a non-negative integer")
    return value


def _require_positive_int(value: object, label: str) -> int:
    result = _require_nonnegative_int(value, label)
    if result == 0:
        raise ContractError(f"{label} must be positive")
    return result


def _require_string(value: object, label: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{label} must be a string")
    if nonempty and not value:
        raise ContractError(f"{label} must not be empty")
    return value


def _require_string_list(value: object, label: str) -> list:
    if not isinstance(value, list):
        raise ContractError(f"{label} must be an array")
    for index, item in enumerate(value):
        _require_string(item, f"{label}[{index}]")
    return value


def _require_sha256(value: object, label: str) -> str:
    text = _require_string(value, label)
    if not _SHA256.fullmatch(text):
        raise ContractError(f"{label} must be a lowercase SHA-256")
    return text


def _require_git_oid(value: object, label: str) -> str:
    text = _require_string(value, label)
    if not _GIT_OID.fullmatch(text):
        raise ContractError(f"{label} must be a 40- or 64-character Git object id")
    return text


def _validate_record(value: object, index: int) -> Mapping:
    label = f"records[{index}]"
    record = _require_exact_keys(value, RECORD_KEYS, label)
    _require_string(record["test_id"], f"{label}.test_id")
    _require_string(record["module"], f"{label}.module")
    outcome = _require_string(record["outcome"], f"{label}.outcome")
    if outcome not in OUTCOMES:
        raise ContractError(f"{label}.outcome is not recognized")
    reason = record["skip_reason"]
    if outcome == "skipped":
        _require_string(reason, f"{label}.skip_reason", nonempty=False)
    elif reason is not None:
        raise ContractError(f"{label}.skip_reason must be null unless skipped")
    _require_nonnegative_int(record["elapsed_ms"], f"{label}.elapsed_ms")
    return record


def _validate_run(value: object) -> Mapping:
    run = _require_exact_keys(value, RUN_KEYS, "run")
    outcome = _require_string(run["outcome"], "run.outcome")
    if outcome not in RUN_OUTCOMES:
        raise ContractError("run.outcome is not recognized")
    _require_nonnegative_int(run["elapsed_ms"], "run.elapsed_ms")
    counts = _require_exact_keys(run["counts"], frozenset(OUTCOMES), "run.counts")
    for name in OUTCOMES:
        _require_nonnegative_int(counts[name], f"run.counts.{name}")
    expected = "passed"
    if counts["error"]:
        expected = "error"
    elif counts["failure"] or counts["unexpected_success"]:
        expected = "failure"
    if outcome != expected:
        raise ContractError(
            f"run.outcome {outcome!r} is inconsistent with counts ({expected!r})"
        )
    return run


def _validate_context(value: object) -> Mapping:
    context = _require_exact_keys(value, CONTEXT_KEYS, "context")
    _require_string_list(context["command"], "context.command")
    _require_string_list(context["selectors"], "context.selectors")
    _require_string(context["platform"], "context.platform")
    _require_string(context["architecture"], "context.architecture")
    _require_positive_int(
        context["logical_cpu_count"], "context.logical_cpu_count"
    )
    _require_string(context["load_note"], "context.load_note")
    generated = _require_string(
        context["generated_at_utc"], "context.generated_at_utc"
    )
    try:
        parsed = _datetime.datetime.fromisoformat(generated)
    except ValueError as exc:
        raise ContractError("context.generated_at_utc must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ContractError("context.generated_at_utc must include a timezone")
    resource = _require_exact_keys(
        context["resource"], RESOURCE_KEYS, "context.resource"
    )
    for name in RESOURCE_KEYS:
        _require_nonnegative_int(resource[name], f"context.resource.{name}")
    return context


def validate_receipt(value: object) -> None:
    """Validate one ``awa-test-receipt/v1`` document or raise ContractError."""

    receipt = _require_exact_keys(value, RECEIPT_KEYS, "receipt")
    _require_literal(receipt["schema"], RECEIPT_SCHEMA, "receipt.schema")
    _require_git_oid(receipt["head_before"], "receipt.head_before")
    _require_git_oid(receipt["head_after"], "receipt.head_after")
    clean_before = _require_bool(
        receipt["source_clean_before"], "receipt.source_clean_before"
    )
    clean_after = _require_bool(
        receipt["source_clean_after"], "receipt.source_clean_after"
    )
    source_state = _require_string(receipt["source_state"], "receipt.source_state")
    if source_state not in ("stable", "unstable"):
        raise ContractError("receipt.source_state is not recognized")
    reusable = _require_bool(receipt["reusable"], "receipt.reusable")
    _require_literal(
        receipt["authorizes_skip"], False, "receipt.authorizes_skip"
    )
    lane = _require_string(receipt["lane"], "receipt.lane")
    if lane not in LANES:
        raise ContractError("receipt.lane is not recognized")
    jobs = _require_positive_int(receipt["jobs"], "receipt.jobs")
    if jobs not in (1, 2, 4):
        raise ContractError("receipt.jobs must be one of 1, 2, or 4")
    _require_string(receipt["python"], "receipt.python")
    _require_string(receipt["git"], "receipt.git")
    _require_sha256(receipt["runner_sha256"], "receipt.runner_sha256")
    _require_sha256(receipt["inventory_sha256"], "receipt.inventory_sha256")
    test_count = _require_nonnegative_int(
        receipt["test_count"], "receipt.test_count"
    )
    records = receipt["records"]
    if not isinstance(records, list):
        raise ContractError("receipt.records must be an array")
    for index, record in enumerate(records):
        _validate_record(record, index)
    ids = [record["test_id"] for record in records]
    if ids != sorted(ids):
        raise ContractError("records must be sorted by test_id")
    if len(ids) != len(set(ids)):
        raise ContractError("records contain a duplicate test_id")
    run = _validate_run(receipt["run"])
    if sum(run["counts"].values()) != len(records):
        raise ContractError("run counts must equal the number of records")
    if run["outcome"] == "passed" and len(records) != test_count:
        raise ContractError("a passed run must record every discovered test")
    _validate_context(receipt["context"])

    stable = (
        receipt["head_before"] == receipt["head_after"]
        and clean_before
        and clean_after
    )
    expected_state = "stable" if stable else "unstable"
    if source_state != expected_state:
        raise ContractError(
            "receipt.source_state is inconsistent with source identity"
        )
    expected_reusable = stable and run["outcome"] == "passed"
    if reusable != expected_reusable:
        raise ContractError("receipt.reusable is inconsistent with source/run state")
