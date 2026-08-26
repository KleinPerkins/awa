"""Bounded, redacted native alert dispatch for AWA integrity transitions."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from collections.abc import Callable


NATIVE_TIMEOUT_SECONDS = 5.0
_SEVERITY_RANK = {"green": 0, "degraded": 1, "red": 2}


def _worsened(previous: dict | None, current: dict) -> bool:
    current_rank = _SEVERITY_RANK.get(current.get("overall"))
    if current_rank is None:
        return False
    previous_rank = (
        _SEVERITY_RANK.get(previous.get("overall"))
        if isinstance(previous, dict)
        else None
    )
    if previous_rank is None:
        return current_rank > 0
    return current_rank > previous_rank


def _attempted(alert: object, transition_id: str) -> bool:
    if not isinstance(alert, dict):
        return False
    if (
        alert.get("last_transition") == transition_id
        and isinstance(alert.get("delivered"), dict)
    ):
        delivered = alert["delivered"]
        if delivered.get("native") in {"accepted", "failed"}:
            return True
    values = alert.get("attempted")
    if not isinstance(values, list):
        return False
    return any(
        value == transition_id
        or (
            isinstance(value, dict)
            and value.get("transition_id") == transition_id
        )
        for value in values
    )


def _accepted(alert: object, transition_id: str) -> bool:
    if not isinstance(alert, dict):
        return False
    delivered = alert.get("delivered")
    return bool(
        alert.get("last_transition") == transition_id
        and isinstance(delivered, dict)
        and any(
            delivered.get(channel) == "accepted"
            for channel in ("native", "slack")
        )
    )


def _record_attempt(
    current: dict,
    transition_id: str,
    outcomes: dict[str, str],
) -> None:
    alert = current.setdefault("alert", {})
    if not isinstance(alert, dict):
        alert = {}
        current["alert"] = alert
    attempted = alert.setdefault("attempted", [])
    if not isinstance(attempted, list):
        attempted = []
        alert["attempted"] = attempted
    attempted.append(
        {
            "transition_id": transition_id,
            "channels": [
                channel
                for channel, outcome in outcomes.items()
                if outcome != "opted_out"
            ],
        }
    )


def _force_alert_failure_red(current: dict) -> None:
    if current.get("overall") == "green":
        return
    current["overall"] = "red"
    invariants = current.get("invariants")
    if not isinstance(invariants, list):
        invariants = []
        current["invariants"] = invariants
    for item in invariants:
        if isinstance(item, dict) and item.get("id") == "alert_delivery":
            item["severity"] = "red"
            item["evidence"] = "all configured alert paths failed"
            break
    else:
        invariants.append(
            {
                "id": "alert_delivery",
                "severity": "red",
                "evidence": "all configured alert paths failed",
                "profile": current.get("profile", "deep"),
                "checked_at": current.get("generated_at"),
            }
        )


def _slack_payload(before: object, after: object) -> dict:
    previous_overall = (
        before
        if before in {"green", "degraded", "red"}
        else "unknown"
    )
    overall = after if after in {"degraded", "red"} else "red"
    return {
        "schema": "awa-integrity-slack-alert/v1",
        "previous_overall": previous_overall,
        "overall": overall,
    }


def _attempt_slack(slack, payload: dict) -> str:
    try:
        if slack is None:
            from . import integrity_slack

            result = integrity_slack.send_configured(payload)
        elif callable(slack):
            result = slack(payload)
        else:
            result = "failed"
    except Exception:
        result = "failed"
    return (
        result
        if result in {"accepted", "failed", "opted_out"}
        else "failed"
    )


def _fallback_if_all_failed(current: dict, outcomes: dict[str, str]) -> None:
    configured = [
        outcome
        for outcome in outcomes.values()
        if outcome != "opted_out"
    ]
    if (
        current.get("overall") == "green"
        or not configured
        or not all(outcome == "failed" for outcome in configured)
    ):
        return
    _force_alert_failure_red(current)
    if current.get("trigger") == "cli":
        try:
            sys.stderr.write(
                "awa: integrity alert delivery failed on all configured paths\n"
            )
            sys.stderr.flush()
        except Exception:
            pass


def _bounded_native(
    native: Callable[[str, str], bool],
    title: str,
    body: str,
) -> bool:
    result: queue.Queue[bool] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            accepted = native(title, body) is True
        except BaseException:  # Alert delivery faults never crash the evaluator.
            accepted = False
        try:
            result.put_nowait(accepted)
        except queue.Full:
            pass

    worker = threading.Thread(
        target=invoke,
        name="awa-integrity-native-alert",
        daemon=True,
    )
    worker.start()
    worker.join(max(0.0, float(NATIVE_TIMEOUT_SECONDS)))
    if worker.is_alive():
        return False
    try:
        return result.get_nowait()
    except queue.Empty:
        return False


def _native(title: str, body: str) -> bool:
    """Ask macOS to accept a notification; success never implies it was seen."""
    if os.environ.get("AWA_ENGINE_TEST_ACTIVE") == "1":
        return True
    script = (
        "on run argv\n"
        "display notification (item 2 of argv) with title (item 1 of argv)\n"
        "end run"
    )
    try:
        completed = subprocess.run(
            ["osascript", "-e", script, "--", title, body],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=NATIVE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def dispatch(
    previous: dict | None,
    current: dict,
    *,
    native: Callable[[str, str], bool],
    slack=None,
    pending: bool = False,
) -> dict[str, str] | None:
    """Attempt a new worsening or retry its current immutable pending outbox."""
    if not isinstance(current, dict):
        return None
    if not pending and not _worsened(previous, current):
        return None
    transition_id = current.get("transition_id")
    if not isinstance(transition_id, str) or not transition_id:
        return None
    alert = current.get("alert")
    if _accepted(alert, transition_id):
        return None
    if not pending and _attempted(alert, transition_id):
        return None

    before = (
        previous.get("overall")
        if isinstance(previous, dict)
        else "unknown"
    )
    after = current.get("overall")
    title = f"AWA integrity {str(after).upper()}"
    body = f"Integrity changed from {before} to {after}."
    native_result = (
        "accepted"
        if _bounded_native(native, title, body)
        else "failed"
    )
    slack_result = _attempt_slack(
        slack,
        _slack_payload(before, after),
    )
    outcomes = {"native": native_result, "slack": slack_result}
    _record_attempt(current, transition_id, outcomes)
    _fallback_if_all_failed(current, outcomes)
    return outcomes
