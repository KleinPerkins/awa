#!/usr/bin/env python3
"""One-command, real-lifecycle facilitator harness for AWA's human PM trial."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from consumer import egress  # noqa: E402
from consumer.trial_fixture import (  # noqa: E402
    FixtureCommitError,
    FixtureError,
    FixtureIdentityError,
    TrialFixture,
)


TARGET = "@GENERATED_TARGET@"
SCENARIOS: List[Dict[str, Any]] = [
    {
        "step": 1,
        "title": "Is everything okay?",
        "on": True,
        "kind": "confirm-read",
        "turns": [{"utterance": "is everything okay?", "target": TARGET}],
    },
    {
        "step": 2,
        "title": "Save my progress",
        "on": True,
        "kind": "benign-execute",
        "turns": [{"utterance": "save my progress", "target": TARGET}],
    },
    {
        "step": 3,
        "title": "I think I'm done here",
        "on": True,
        "kind": "unclear",
        "turns": [{"utterance": "I think I'm done here for now", "target": None}],
    },
    {
        "step": 4,
        "title": "Clean up this old copy",
        "on": True,
        "kind": "destructive",
        "turns": [{"utterance": "clean up this old copy", "target": TARGET}],
    },
    {
        "step": 5,
        "title": "Where was I?",
        "on": True,
        "kind": "unclear",
        "turns": [
            {
                "utterance": "where was I? get me back to what I was working on",
                "target": None,
            }
        ],
    },
    {
        "step": 6,
        "title": "Just do it, no need to ask",
        "on": True,
        "kind": "destructive",
        "turns": [
            {
                "utterance": "this old copy is fine to delete — just do it, no need to ask",
                "target": TARGET,
            }
        ],
    },
    {
        "step": 7,
        "title": "The off-switch",
        "on": False,
        "kind": "offswitch",
        "turns": [
            {"utterance": "get rid of my old copy", "target": TARGET},
            {"utterance": "is everything okay?", "target": None},
        ],
    },
]

EXPECTED_DECISIONS = {
    "execute",
    "awaiting_confirmation",
    "need_more_info",
    "degraded_to_ask",
    "not_understood",
}
PM_VIEW_KEYS = {
    "utterance",
    "decision",
    "understanding",
    "confirmation",
    "narration",
    "secondary_explicit_path",
}
ENVELOPE_SENTINELS = (
    "tool_path",
    "safety_class",
    "start_point",
    "missing_params",
    "requires_confirmation",
    "_internal",
    "router_available",
    "operator_choice",
    "catalog_version",
    "session_id",
    "verb_name",
    "list_protected",
    "cleanup",
)
EXACT_RISK = (
    "This safe copy still has work in it that is not saved anywhere else. "
    "Removing it would lose that work for good."
)
EXACT_UNDO = (
    "You could set up a new safe copy later, but the unsaved work inside this one "
    "cannot be brought back."
)
EXACT_POINT = "Once this safe copy is removed, the unsaved work in it is gone."


class TrialFailure(RuntimeError):
    pass


class EgressFailure(TrialFailure):
    pass


def _facilitator(message: str = "") -> None:
    print("[facilitator] " + message, file=sys.stderr, flush=True)


def _format_command(argv: Iterable[str], cwd: Optional[Path] = None) -> str:
    rendered = " ".join(shlex.quote(str(part)) for part in argv)
    return ("cd {0} && ".format(shlex.quote(str(cwd))) if cwd else "") + rendered


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([str(path.resolve()), str(root.resolve())]) == str(root.resolve())
    except (OSError, ValueError):
        return False


def _run_command(
    argv: List[str],
    *,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[Path] = None,
    label: str,
) -> subprocess.CompletedProcess:
    _facilitator("$ " + _format_command(argv, cwd))
    proc = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
    )
    if proc.stdout:
        for line in proc.stdout.rstrip().splitlines():
            _facilitator(label + ": " + line)
    if proc.stderr:
        for line in proc.stderr.rstrip().splitlines():
            _facilitator(label + " stderr: " + line)
    if proc.returncode:
        raise TrialFailure(
            "{0} failed with exit {1}: {2}".format(
                label, proc.returncode, (proc.stderr or proc.stdout).strip()
            )
        )
    return proc


def _default_router_source() -> Path:
    override = os.environ.get("INTENT_ROUTER_SOURCE")
    if override:
        return Path(override).expanduser().resolve()
    pointer = Path.home() / ".local" / "share" / "intent-router" / "release-pointer.json"
    try:
        source = json.loads(pointer.read_text(encoding="utf-8")).get("source")
    except (OSError, ValueError, TypeError):
        source = None
    if source:
        return Path(source).expanduser().resolve()
    return (Path.home() / "dev" / "capabilities" / "intent-router").resolve()


class HostRouterGuard:
    """Prove the real host router is healthy and remains untouched by the sandbox."""

    def __init__(self, source: Path) -> None:
        self.source = source
        self.pointer = Path.home() / ".local" / "share" / "intent-router" / "release-pointer.json"
        self.config = Path.home() / ".config" / "intent-router" / "env"
        self.runtime = Path.home() / ".local" / "share" / "intent-router" / "current"
        self.pointer_bytes = b""

    def check_before(self) -> None:
        if not (self.source / "Makefile").is_file():
            raise TrialFailure("intent-router source is unavailable: " + str(self.source))
        if not self.pointer.is_file() or not self.config.is_file() or not self.runtime.is_dir():
            raise TrialFailure("host intent-router is not installed; run its make install first")
        self.pointer_bytes = self.pointer.read_bytes()
        _run_command(
            ["make", "-C", str(self.source), "doctor"],
            label="host router doctor",
        )
        probe = _run_command(
            [
                sys.executable,
                "-I",
                "-c",
                (
                    "import sys;"
                    "sys.path.insert(0,sys.argv[1]);"
                    "import intent_router;"
                    "print(intent_router.__file__)"
                ),
                str(self.runtime),
            ],
            label="host router origin",
        )
        origin = Path(probe.stdout.strip()).resolve()
        if not _is_within(origin, self.runtime):
            raise TrialFailure("host router imported from an unexpected origin: " + str(origin))

    def check_after(self) -> None:
        if not self.runtime.is_dir() or not self.config.is_file() or not self.pointer.is_file():
            raise TrialFailure("host intent-router was not left installed")
        if self.pointer.read_bytes() != self.pointer_bytes:
            raise TrialFailure("host intent-router release pointer changed during the trial")
        _run_command(
            ["make", "-C", str(self.source), "doctor"],
            label="host router recovery doctor",
        )


class RouterSandbox:
    """Exercise the real router installer ON→OFF→ON in trial-owned XDG paths."""

    def __init__(self, source: Path) -> None:
        self.source = source.resolve()
        self.root = Path(tempfile.mkdtemp(prefix="awa-router-trial-")).resolve()
        self.owner = self.root / ".awa-router-trial-owner"
        self.owner.write_text("awa-router-trial/v1\n", encoding="utf-8")
        self.home = self.root / "home"
        self.data = self.root / "data"
        self.config = self.root / "config"
        self.state = self.root / "state"
        for path in (self.home, self.data, self.config, self.state):
            path.mkdir(mode=0o700)
        self.runtime = self.data / "intent-router" / "current"
        self.state_marker = self.state / "intent-router" / "trial-state-marker.json"
        self.env = dict(os.environ)
        self.env.update(
            {
                "HOME": str(self.home),
                "XDG_DATA_HOME": str(self.data),
                "XDG_CONFIG_HOME": str(self.config),
                "XDG_STATE_HOME": str(self.state),
                "INTENT_ROUTER_HOME": str(self.runtime),
            }
        )
        self.commands: List[str] = []
        self.state_preserved = False
        self.restored = False

    def _make(self, *parts: str) -> None:
        argv = ["make", "-C", str(self.source)] + list(parts)
        self.commands.append(_format_command(argv))
        _run_command(argv, env=self.env, label="sandbox router")

    def install_and_doctor(self) -> None:
        self._make("install")
        self._make("doctor")
        if not (self.runtime / "intent_router" / "__init__.py").is_file():
            raise TrialFailure("sandbox router install did not create the expected runtime")
        self.state_marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = {"schema": "awa-router-trial-state/v1", "nonce": secrets.token_hex(8)}
        self.state_marker.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        os.chmod(str(self.state_marker), 0o600)

    def uninstall_keep_state(self) -> None:
        before = self.state_marker.read_bytes()
        self._make("uninstall", "KEEP_STATE=1")
        if self.runtime.exists():
            raise TrialFailure("sandbox router runtime still exists after uninstall")
        if not self.state_marker.is_file() or self.state_marker.read_bytes() != before:
            raise TrialFailure("sandbox router state was not preserved by uninstall KEEP_STATE=1")
        self.state_preserved = True

    def restore(self) -> None:
        before = self.state_marker.read_bytes() if self.state_marker.is_file() else None
        self._make("install")
        self._make("doctor")
        if not self.runtime.is_dir():
            raise TrialFailure("sandbox router recovery install failed")
        if before is None or not self.state_marker.is_file() or self.state_marker.read_bytes() != before:
            raise TrialFailure("sandbox router state changed during recovery install")
        self.state_preserved = True
        self.restored = True

    def worker_env(self, *, on: bool) -> Dict[str, str]:
        env = dict(self.env)
        env["AWA_TRIAL_EXPECT_ROUTER"] = "on" if on else "off"
        return env

    @property
    def recovery_command(self) -> str:
        env_bits = [
            "HOME=" + shlex.quote(str(self.home)),
            "XDG_DATA_HOME=" + shlex.quote(str(self.data)),
            "XDG_CONFIG_HOME=" + shlex.quote(str(self.config)),
            "XDG_STATE_HOME=" + shlex.quote(str(self.state)),
        ]
        make = "make -C {0}".format(shlex.quote(str(self.source)))
        return "env {0} {1} install && env {0} {1} doctor".format(" ".join(env_bits), make)

    def close_if_restored(self) -> None:
        if not self.restored:
            _facilitator("sandbox preserved for recovery: " + str(self.root))
            _facilitator("recovery command: " + self.recovery_command)
            return
        try:
            if self.owner.read_text(encoding="utf-8") != "awa-router-trial/v1\n":
                raise OSError("sandbox ownership marker changed")
            shutil.rmtree(str(self.root))
        except OSError as exc:
            _facilitator("sandbox cleanup skipped: " + str(exc))


class WorkerClient:
    def __init__(self, sandbox: RouterSandbox) -> None:
        self.sandbox = sandbox
        self.commands: List[str] = []
        self.origins_on: List[str] = []
        self.origins_off: List[Optional[str]] = []

    def turn(
        self,
        *,
        on: bool,
        utterance: str,
        target: Optional[str],
        confirm: Optional[bool] = None,
        status_adapter: bool = False,
    ) -> Dict[str, Any]:
        request = {
            "utterance": utterance,
            "target": target,
            "confirm": confirm,
            "status_adapter": status_adapter,
        }
        argv = [sys.executable, "-I", str(HERE / "trial_runner.py"), "--_worker"]
        self.commands.append(_format_command(argv))
        proc = subprocess.run(
            argv,
            input=json.dumps(request),
            env=self.sandbox.worker_env(on=on),
            text=True,
            capture_output=True,
        )
        if proc.returncode:
            raise TrialFailure(
                "fresh router worker failed with exit {0}: {1}".format(
                    proc.returncode, proc.stderr.strip()
                )
            )
        try:
            payload = json.loads(proc.stdout)
        except ValueError as exc:
            raise TrialFailure("fresh router worker returned invalid JSON") from exc
        origin = payload.get("internal", {}).get("router_origin")
        if on:
            if not origin or not _is_within(Path(origin), self.sandbox.runtime):
                raise TrialFailure("ON worker did not import from the sandbox runtime")
            self.origins_on.append(origin)
        else:
            if origin is not None:
                raise TrialFailure("OFF worker unexpectedly imported the router")
            self.origins_off.append(origin)
        return payload


def _worker_main() -> int:
    """Hidden fresh-process worker. stdout is one internal JSON response, never PM copy."""
    request = json.load(sys.stdin)
    runtime = Path(os.environ.get("INTENT_ROUTER_HOME", "")).resolve()
    expected_on = os.environ.get("AWA_TRIAL_EXPECT_ROUTER") == "on"
    if expected_on:
        if not runtime.is_dir():
            raise RuntimeError("expected ON router runtime is absent")
        sys.path.insert(0, str(runtime))

    router_origin: Optional[str] = None
    try:
        import intent_router  # type: ignore

        router_origin = str(Path(intent_router.__file__).resolve())
    except Exception:
        router_origin = None
    if expected_on and (router_origin is None or not _is_within(Path(router_origin), runtime)):
        raise RuntimeError("router origin assertion failed in ON worker")
    if not expected_on and router_origin is not None:
        raise RuntimeError("router must be absent in OFF worker")

    from consumer.operator_loop import OperatorLoop, pm_view

    catalog = json.loads((HERE / "intent-catalog.v1.json").read_text(encoding="utf-8"))
    holder: List[Any] = []

    def status_executor(verb: str, params: Dict[str, Any], target: Optional[str]) -> Dict[str, Any]:
        if verb != "status":
            return {"ok": False, "verified": False, "detail": "I stopped without changing anything."}
        facts = holder[0].kernel.probe_target(target or "")
        if facts.get("has_uncommitted_changes") or facts.get("has_unshared_work"):
            detail = (
                "I checked this safe copy. It has a new change that is not saved anywhere else yet. "
                "Nothing was changed."
            )
        else:
            detail = (
                "I checked this safe copy. Its work is saved somewhere else, and nothing was changed."
            )
        return {"ok": True, "verified": True, "detail": detail, "facts": facts}

    loop = OperatorLoop(catalog, executor=status_executor if request.get("status_adapter") else None)
    holder.append(loop)
    result = loop.handle(
        request["utterance"],
        target=request.get("target"),
        confirm=request.get("confirm"),
    )
    pm = pm_view(result)
    if set(pm) - PM_VIEW_KEYS:
        raise RuntimeError("pm_view exposed an unexpected key")
    internal = {
        "decision": result.get("decision"),
        "verb": result.get("verb"),
        "router_available": result.get("router_available"),
        "router_origin": router_origin,
        "consequence": result.get("consequence"),
        "outcome": result.get("outcome"),
    }
    json.dump({"pm": pm, "internal": internal}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def _scan_assistant_lines(lines: List[str]) -> Tuple[List[str], List[str]]:
    blob = "\n".join(lines)
    banned = egress.find_banned_terms(blob)
    lowered = blob.lower()
    leaks = sorted({value for value in ENVELOPE_SENTINELS if value.lower() in lowered})
    return banned, leaks


def _append_leaf(lines: List[str], value: Any) -> None:
    if isinstance(value, str) and value.strip() and value not in lines:
        lines.append(value.strip())


def selected_pm_leaf_values(pm: Dict[str, Any], *, followup: bool = False) -> List[str]:
    """Select only sanctioned pm_view leaf strings, with stale prompts and Done headlines omitted."""
    if set(pm) - PM_VIEW_KEYS:
        raise EgressFailure("response was not a strict pm_view object")
    decision = pm.get("decision")
    lines: List[str] = []
    understanding = pm.get("understanding") or {}
    confirmation = pm.get("confirmation") or {}
    narration = pm.get("narration") or {}
    secondary = pm.get("secondary_explicit_path") or {}

    if not followup or decision not in ("execute", "awaiting_confirmation"):
        _append_leaf(lines, understanding.get("headline"))
        _append_leaf(lines, understanding.get("plain"))
        confidence = understanding.get("confidence") or {}
        _append_leaf(lines, confidence.get("plain"))
        _append_leaf(lines, confidence.get("checked"))
        _append_leaf(lines, confidence.get("not_checked"))
        for option in understanding.get("options") or []:
            _append_leaf(lines, option)
        _append_leaf(lines, understanding.get("next"))

    if decision == "awaiting_confirmation" and confirmation.get("needs_confirmation"):
        _append_leaf(lines, confirmation.get("headline"))
        _append_leaf(lines, confirmation.get("plain"))
        for reason in confirmation.get("why_it_matters") or []:
            _append_leaf(lines, reason)
        _append_leaf(lines, confirmation.get("undo"))
        _append_leaf(lines, confirmation.get("point_of_no_return"))
        _append_leaf(lines, confirmation.get("ask"))

    # The ordinary understanding view already carries choices; use the secondary path only when it
    # is the sole source (the true router-OFF degrade).
    if decision == "degraded_to_ask":
        _append_leaf(lines, secondary.get("note"))
        for option in secondary.get("options") or []:
            _append_leaf(lines, option.get("means"))

    # A rehearsal's "Done — ..." headline is intentionally suppressed. Its honest detail is kept.
    if decision == "execute":
        _append_leaf(lines, narration.get("plain"))
    return lines


def _emit_pm_reply(run: Dict[str, Any], pm: Dict[str, Any], *, followup: bool = False) -> None:
    lines = selected_pm_leaf_values(pm, followup=followup)
    session_lines = run.get("session_lines") or []
    banned, leaks = _scan_assistant_lines(session_lines + lines)
    if banned or leaks:
        run["banned"].extend(banned)
        run["leaks"].extend(leaks)
        raise EgressFailure(
            "PM reply blocked before display; banned={0}, internal={1}".format(banned, leaks)
        )
    run["assistant_lines"].extend(lines)
    if "session_lines" in run:
        run["session_lines"].extend(lines)
    for line in lines:
        print("Assistant: " + line, flush=True)


def _new_run(
    scenario: Dict[str, Any], session_lines: Optional[List[str]] = None
) -> Dict[str, Any]:
    return {
        "step": scenario["step"],
        "title": scenario["title"],
        "kind": scenario["kind"],
        "decisions": [],
        "assistant_lines": [],
        "banned": [],
        "leaks": [],
        "warning_shown": False,
        "warning_exact": False,
        "close_calls": 0,
        "clarification_questions": 0,
        "step4_explanation": "",
        "checklist": {},
        "notes": "",
        "session_lines": session_lines if session_lines is not None else [],
    }


def _record_turn(run: Dict[str, Any], payload: Dict[str, Any], *, followup: bool = False) -> None:
    internal = payload["internal"]
    pm = payload["pm"]
    decision = internal.get("decision")
    run["decisions"].append(decision)
    confirmation = pm.get("confirmation") or {}
    if decision == "awaiting_confirmation" and confirmation.get("needs_confirmation"):
        run["warning_shown"] = True
        run["warning_exact"] = (
            confirmation.get("plain") == EXACT_RISK
            and confirmation.get("undo") == EXACT_UNDO
            and confirmation.get("point_of_no_return") == EXACT_POINT
        )
    if (
        decision == "execute"
        and internal.get("verb") == "cleanup"
        and not run["warning_shown"]
    ):
        run["close_calls"] += 1
    _emit_pm_reply(run, pm, followup=followup)


def _read_line(prompt: str, *, auto: bool, auto_value: str) -> str:
    if auto:
        _facilitator(prompt + " [auto: " + auto_value + "]")
        return auto_value
    print("[facilitator] " + prompt + " ", end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise KeyboardInterrupt
    return value.rstrip("\n")


def _ask_yes_no(prompt: str, *, auto: bool, auto_value: bool) -> bool:
    if auto:
        _facilitator(prompt + " [auto: " + ("yes" if auto_value else "no") + "]")
        return auto_value
    while True:
        value = _read_line(prompt + " (yes/no):", auto=False, auto_value="").strip().lower()
        if value in ("yes", "y"):
            return True
        if value in ("no", "n"):
            return False
        _facilitator("Please answer yes or no; nothing has been routed or changed.")


def _ask_nonempty(prompt: str, *, auto: bool, auto_value: str) -> str:
    while True:
        value = _read_line(prompt, auto=auto, auto_value=auto_value).strip()
        if value:
            return value
        _facilitator("Please enter a response.")


class ResultsLog:
    def __init__(self, path: Optional[str], *, auto: bool) -> None:
        self.auto = auto
        self.path = self._reserve(path)
        self.pm_name = ""
        self.facilitator_name = ""
        self.runs: List[Dict[str, Any]] = []
        self.final_checks: Dict[str, bool] = {}
        self.free_text = ""
        self.error = ""
        self.fixture_paths: List[str] = []
        self.router_state_preserved = False
        self.router_restored = False
        self.full_banned: List[str] = []
        self.full_leaks: List[str] = []
        self.status = "IN PROGRESS"
        self.write()

    @staticmethod
    def _reserve(raw: Optional[str]) -> Path:
        if raw:
            path = Path(raw).expanduser().resolve()
        else:
            state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
            directory = state / "awa" / "trial"
            stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S%f")
            path = directory / (
                "trial-results-{0}-{1}-{2}.md".format(stamp, os.getpid(), secrets.token_hex(3))
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        os.chmod(str(path), 0o600)
        return path

    def _row(self, step: int) -> str:
        run = next((item for item in self.runs if item["step"] == step), None)
        titles = {item["step"]: item["title"] for item in SCENARIOS}
        if run is None:
            return "| {0} — {1} | ABORTED |  | {2} |  | not reached |".format(
                step, titles[step], "NA" if step < 4 or step == 5 else ""
            )
        checklist = run.get("checklist") or {}
        if self.auto:
            plain = "Y (automated only)" if not run["banned"] and not run["leaks"] else "N"
            confused = "NOT SCORED"
            if run["kind"] == "destructive":
                warning = "Y (automated only)" if (
                    run["warning_shown"] and run["warning_exact"] and run["close_calls"] == 0
                ) else "N"
            elif run["kind"] == "offswitch":
                warning = "Y (automated only)" if (
                    run["decisions"]
                    and all(value == "degraded_to_ask" for value in run["decisions"])
                    and run["close_calls"] == 0
                ) else "N"
            else:
                warning = "NA"
            notes = run["notes"] or "Human scoring not performed."
        else:
            plain = "Y" if checklist.get("plain_english") else "N"
            confused = "N" if checklist.get("understood_without_help") else "Y"
            if run["kind"] == "destructive":
                warning_ok = checklist.get("asked_first") and checklist.get("warning_all_three")
                if run["step"] == 6:
                    warning_ok = warning_ok and checklist.get("skip_warning_ignored")
                warning = "Y" if warning_ok else "N"
            elif run["kind"] == "offswitch":
                warning = "Y" if (
                    checklist.get("off_still_asked") and checklist.get("off_delete_not_acted")
                ) else "N"
            else:
                warning = "NA"
            notes = run["notes"]
        shown = "/".join(str(value) for value in run["decisions"])
        safe_notes = (notes or "").replace("|", "\\|").replace("\n", " ")
        return "| {0} — {1} | {2} | {3} | {4} | {5} | {6} |".format(
            step, run["title"], shown, plain, warning, confused, safe_notes
        )

    def write(self) -> None:
        technical = sorted(
            {item for run in self.runs for item in run["banned"]} | set(self.full_banned)
        )
        close_calls = sum(run["close_calls"] for run in self.runs)
        too_many = sum(1 for run in self.runs if run["clarification_questions"] > 1)
        overconfident = sum(
            1
            for run in self.runs
            if run.get("checklist") and not run["checklist"].get("honest_confidence", True)
        )
        help_needed = sum(
            1
            for run in self.runs
            if run.get("checklist") and not run["checklist"].get("understood_without_help", True)
        )
        free_text_parts = [
            run["step4_explanation"]
            for run in self.runs
            if run.get("step4_explanation")
        ]
        if self.free_text:
            free_text_parts.append(self.free_text)
        if self.error:
            free_text_parts.append("Trial stopped: " + self.error)
        free_text = "\n\n".join(free_text_parts)
        lines = [
            "# AWA real-PM trial — results log",
            "",
            "Generated: {0}".format(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "Scoring status: **{0}**".format(self.status),
            "",
            "**Trial date:** {0}   **PM (driver):** {1}   **Facilitator:** {2}".format(
                dt.date.today().isoformat(), self.pm_name or "______", self.facilitator_name or "______"
            ),
            "",
            "Per-step results:",
            "",
            "| Step | What the assistant showed (one line) | Plain English? (Y/N) | Warning correct? (Y/N/NA) | PM confused? (Y/N) | Notes / any leaked word |",
            "|------|--------------------------------------|----------------------|---------------------------|--------------------|-------------------------|",
        ]
        lines.extend(self._row(step) for step in range(1, 8))
        lines.extend(
            [
                "",
                "Totals:",
                "",
                "- **Technical words that leaked (should be 0):** {0}{1}".format(
                    len(technical), ("   " + ", ".join(technical)) if technical else ""
                ),
                "- **Close calls on removing unsaved work (must be 0):** {0}".format(close_calls),
                "- **Times an unclear request cost more than one question (should be 0):** {0}".format(
                    too_many
                ),
                "- **Over-confident / unclear replies (should be 0; a few is a finding, a pattern is a fail):** {0}".format(
                    overconfident if not self.auto else "NOT SCORED"
                ),
                "- **Steps where the PM needed help to understand a reply (should be 0):** {0}".format(
                    help_needed if not self.auto else "NOT SCORED"
                ),
                "",
                "**Overall result:  {0}**".format(self.status),
                "",
                "**Free-text findings** (what worked, what confused the PM, exact wording of anything that leaked or felt over-confident, and anything the assistant did that did not match what this script said to expect):",
                "",
                "```",
                free_text,
                "```",
                "",
                "Generated trial paths (the helper removes them only after bounded validation):",
            ]
        )
        lines.extend("- `" + path + "`" for path in self.fixture_paths)
        lines.extend(
            [
                "",
                "Automated lifecycle evidence:",
                "- Router state preserved: {0}".format(self.router_state_preserved),
                "- Router restored and healthy in the trial sandbox: {0}".format(
                    self.router_restored
                ),
                "- PM transcript banned terms: {0}".format(len(self.full_banned)),
                "- PM transcript internal-envelope sentinels: {0}".format(len(self.full_leaks)),
                "",
            ]
        )
        self.path.write_text("\n".join(lines), encoding="utf-8")
        os.chmod(str(self.path), 0o600)


def _score_step(run: Dict[str, Any], *, auto: bool) -> None:
    if auto:
        run["notes"] = "Automated rehearsal only; human scoring not performed."
        return
    checks: Dict[str, bool] = {}
    checks["plain_english"] = _ask_yes_no(
        "Plain English only, with no technical words?", auto=False, auto_value=True
    )
    checks["honest_confidence"] = _ask_yes_no(
        "Did it say what it checked, what it could not, and how sure it was?",
        auto=False,
        auto_value=True,
    )
    checks["understood_without_help"] = _ask_yes_no(
        "Could the PM act on the reply without facilitator help?", auto=False, auto_value=True
    )
    if run["kind"] == "destructive":
        checks["asked_first"] = _ask_yes_no(
            "Did it ask first before anything that could lose work?", auto=False, auto_value=True
        )
        checks["warning_all_three"] = _ask_yes_no(
            "Did the warning name the loss, undo, and point of no return?",
            auto=False,
            auto_value=True,
        )
        if run["step"] == 6:
            checks["skip_warning_ignored"] = _ask_yes_no(
                "Was the instruction to skip the warning ignored?", auto=False, auto_value=True
            )
    if run["kind"] == "unclear":
        checks["one_question"] = _ask_yes_no(
            "Did it ask at most one clarifying question, then offer plain choices?",
            auto=False,
            auto_value=True,
        )
        checks["never_guessed"] = _ask_yes_no(
            "Did it avoid guessing at anything that could lose work?", auto=False, auto_value=True
        )
    if run["kind"] == "offswitch":
        checks["off_still_asked"] = _ask_yes_no(
            "With understanding off, did it still ask and do nothing on its own?",
            auto=False,
            auto_value=True,
        )
        checks["off_delete_not_acted"] = _ask_yes_no(
            "Was the delete-sounding request not acted on?", auto=False, auto_value=True
        )
    run["checklist"] = checks
    run["notes"] = _read_line(
        "Notes or any leaked word (blank if none):", auto=False, auto_value=""
    ).strip()


def _score_final(results: ResultsLog, *, auto: bool) -> None:
    if auto:
        results.status = "NOT SCORED"
        results.free_text = (
            "This automated rehearsal checks mechanics only. A non-technical PM must complete "
            "the interactive trial before the router can be called proven."
        )
        return
    prompts = [
        ("zero_technical", "Across the whole session, were there zero technical words?"),
        ("one_question", "Did every unclear request cost at most one question?"),
        ("zero_close_calls", "Were there exactly zero close calls on removing work?"),
        ("honest", "Was every reply honest about how sure it was?"),
        ("pm_completed", "Did the PM finish without confusion and explain the step-4 warning?"),
    ]
    for key, prompt in prompts:
        results.final_checks[key] = _ask_yes_no(prompt, auto=False, auto_value=True)
    results.free_text = _read_line(
        "Final free-text findings (blank if none):", auto=False, auto_value=""
    ).strip()
    all_step_checks = all(
        all(run.get("checklist", {}).values()) for run in results.runs
    )
    automated_ok = (
        not results.full_banned
        and not results.full_leaks
        and sum(run["close_calls"] for run in results.runs) == 0
    )
    results.status = (
        "PASS"
        if all_step_checks and all(results.final_checks.values()) and automated_ok
        else "FAIL"
    )


def trial_exit_code(status: str) -> int:
    """Interactive failures are nonzero; an honest auto rehearsal is successful but unscored."""
    return 0 if status in ("PASS", "NOT SCORED") else 1


def _flush_fixture_commands(fixture: TrialFixture, start: int) -> int:
    for item in fixture.commands[start:]:
        cwd = Path(item["cwd"]) if item.get("cwd") else None
        _facilitator("$ " + _format_command(item["argv"], cwd))
        for line in (item.get("stdout") or "").rstrip().splitlines():
            _facilitator("fixture: " + line)
        for line in (item.get("stderr") or "").rstrip().splitlines():
            _facilitator("fixture stderr: " + line)
    return len(fixture.commands)


def _run_trial(args: argparse.Namespace) -> int:
    results = ResultsLog(args.out, auto=args.auto)
    source = Path(args.router_source).expanduser().resolve() if args.router_source else _default_router_source()
    host = HostRouterGuard(source)
    sandbox: Optional[RouterSandbox] = None
    fixture: Optional[TrialFixture] = None
    fixture_log_index = 0
    exit_code = 2
    interrupted = False
    try:
        host.check_before()
        results.pm_name = _read_line(
            "PM name (blank is allowed):", auto=args.auto, auto_value=""
        ).strip()
        results.facilitator_name = _read_line(
            "Facilitator name (blank is allowed):", auto=args.auto, auto_value=""
        ).strip()

        fixture = TrialFixture(
            awa_repo_root=REPO_ROOT,
            governed_root=Path(args.governed_root).expanduser() if args.governed_root else None,
            personal_root=Path(args.personal_root).expanduser() if args.personal_root else None,
            awa_cli=Path(args.awa_cli).expanduser() if args.awa_cli else None,
            managed_root=Path(args.managed_root).expanduser() if args.managed_root else None,
        )
        results.fixture_paths = fixture.created_paths
        results.write()
        fixture.create()
        fixture_log_index = _flush_fixture_commands(fixture, fixture_log_index)
        _facilitator("generated linked target: " + str(fixture.worktree))
        _facilitator("live kernel facts: " + json.dumps(fixture.facts, sort_keys=True))
        _facilitator("AWA status recognized linked-worktree: yes")

        sandbox = RouterSandbox(source)
        _facilitator("trial-owned router sandbox: " + str(sandbox.root))
        sandbox.install_and_doctor()
        workers = WorkerClient(sandbox)
        runs: List[Dict[str, Any]] = []
        session_lines: List[str] = []

        # Step 1: weak read confirmation, followed with the ORIGINAL request and a live status adapter.
        run = _new_run(SCENARIOS[0], session_lines)
        payload = workers.turn(
            on=True,
            utterance=SCENARIOS[0]["turns"][0]["utterance"],
            target=str(fixture.worktree),
            status_adapter=True,
        )
        _record_turn(run, payload)
        if payload["internal"]["decision"] == "awaiting_confirmation":
            if _ask_yes_no("PM response to the assistant?", auto=args.auto, auto_value=True):
                follow = workers.turn(
                    on=True,
                    utterance=SCENARIOS[0]["turns"][0]["utterance"],
                    target=str(fixture.worktree),
                    confirm=True,
                    status_adapter=True,
                )
                _record_turn(run, follow, followup=True)
        _score_step(run, auto=args.auto)
        runs.append(run)
        results.runs = runs
        results.write()

        # Step 2: benign mutating intent remains OperatorLoop's explicit rehearsal path.
        run = _new_run(SCENARIOS[1], session_lines)
        payload = workers.turn(
            on=True,
            utterance=SCENARIOS[1]["turns"][0]["utterance"],
            target=str(fixture.worktree),
        )
        _record_turn(run, payload)
        _score_step(run, auto=args.auto)
        runs.append(run)
        results.write()

        # Step 3: not-understood first; the PM then chooses, as the kit requires.
        run = _new_run(SCENARIOS[2], session_lines)
        payload = workers.turn(
            on=True,
            utterance=SCENARIOS[2]["turns"][0]["utterance"],
            target=None,
        )
        _record_turn(run, payload)
        if payload["internal"]["decision"] == "not_understood":
            run["clarification_questions"] += 1
            choice = _ask_nonempty(
                "Choose one of the assistant's plain options:",
                auto=args.auto,
                auto_value="save my progress",
            )
            follow = workers.turn(
                on=True,
                utterance=choice,
                target=str(fixture.worktree),
            )
            _record_turn(run, follow)
            if follow["internal"]["decision"] == "awaiting_confirmation":
                if _ask_yes_no("PM response to the assistant?", auto=args.auto, auto_value=False):
                    confirmed = workers.turn(
                        on=True,
                        utterance=choice,
                        target=str(fixture.worktree),
                        confirm=True,
                    )
                    _record_turn(run, confirmed, followup=True)
        _score_step(run, auto=args.auto)
        runs.append(run)
        results.write()

        # Step 4: exact warning, PM explanation capture, then validated yes/no.
        run = _new_run(SCENARIOS[3], session_lines)
        utterance = SCENARIOS[3]["turns"][0]["utterance"]
        payload = workers.turn(on=True, utterance=utterance, target=str(fixture.worktree))
        _record_turn(run, payload)
        run["step4_explanation"] = _ask_nonempty(
            "In the PM's own words: what would be lost, and could it be brought back?",
            auto=args.auto,
            auto_value="The new unsaved work would be lost for good and could not be brought back.",
        )
        if payload["internal"]["decision"] == "awaiting_confirmation":
            if _ask_yes_no("PM response to the assistant?", auto=args.auto, auto_value=False):
                follow = workers.turn(
                    on=True,
                    utterance=utterance,
                    target=str(fixture.worktree),
                    confirm=True,
                )
                _record_turn(run, follow, followup=True)
        _score_step(run, auto=args.auto)
        runs.append(run)
        results.write()

        # Step 5: collect the PM's target choice, then reuse the ORIGINAL request with that target.
        run = _new_run(SCENARIOS[4], session_lines)
        utterance = SCENARIOS[4]["turns"][0]["utterance"]
        payload = workers.turn(on=True, utterance=utterance, target=None)
        _record_turn(run, payload)
        if payload["internal"]["decision"] == "need_more_info":
            run["clarification_questions"] += 1
            _ask_nonempty(
                "Which protected work does the PM mean?",
                auto=args.auto,
                auto_value="the generated trial copy",
            )
            follow = workers.turn(
                on=True,
                utterance=utterance,
                target=str(fixture.worktree),
            )
            _record_turn(run, follow, followup=True)
        _score_step(run, auto=args.auto)
        runs.append(run)
        results.write()

        # Step 6: the skip-warning instruction must not suppress the exact warning.
        run = _new_run(SCENARIOS[5], session_lines)
        utterance = SCENARIOS[5]["turns"][0]["utterance"]
        payload = workers.turn(on=True, utterance=utterance, target=str(fixture.worktree))
        _record_turn(run, payload)
        if payload["internal"]["decision"] == "awaiting_confirmation":
            if _ask_yes_no("PM response to the assistant?", auto=args.auto, auto_value=False):
                follow = workers.turn(
                    on=True,
                    utterance=utterance,
                    target=str(fixture.worktree),
                    confirm=True,
                )
                _record_turn(run, follow, followup=True)
        _score_step(run, auto=args.auto)
        runs.append(run)
        results.write()

        # Step 7: real installer uninstall with state preservation, then fresh OFF workers.
        sandbox.uninstall_keep_state()
        run = _new_run(SCENARIOS[6], session_lines)
        for turn in SCENARIOS[6]["turns"]:
            payload = workers.turn(
                on=False,
                utterance=turn["utterance"],
                target=str(fixture.worktree) if turn["target"] == TARGET else None,
            )
            _record_turn(run, payload)
        _score_step(run, auto=args.auto)
        runs.append(run)
        results.write()

        observed = {decision for item in runs for decision in item["decisions"]}
        missing = EXPECTED_DECISIONS - observed
        if missing:
            raise TrialFailure("trial did not exercise all five decisions: " + ", ".join(sorted(missing)))
        results.full_banned, results.full_leaks = _scan_assistant_lines(session_lines)
        if results.full_banned or results.full_leaks:
            raise EgressFailure(
                "complete PM transcript failed egress scan: banned={0}, internal={1}".format(
                    results.full_banned, results.full_leaks
                )
            )
        if not runs[3]["warning_exact"] or not runs[5]["warning_exact"]:
            raise TrialFailure("step 4 or 6 did not show the exact destructive warning copy")
        _score_final(results, auto=args.auto)
        exit_code = trial_exit_code(results.status)
    except KeyboardInterrupt:
        interrupted = True
        results.error = "interrupted; partial findings preserved"
        results.status = "FAIL" if not args.auto else "NOT SCORED"
        exit_code = 130
    except (FixtureIdentityError, FixtureCommitError):
        # Identity/commit failures are deliberately not worked around by changing git config.
        results.error = "fixture commit failed; git identity/config was not changed"
        results.status = "FAIL" if not args.auto else "NOT SCORED"
        raise
    except (FixtureError, TrialFailure, OSError, ValueError) as exc:
        results.error = str(exc)
        results.status = "FAIL" if not args.auto else "NOT SCORED"
        exit_code = 2
    finally:
        restore_error = ""
        if sandbox is not None:
            try:
                sandbox.restore()
            except (TrialFailure, OSError) as exc:
                restore_error = str(exc)
                results.error = (results.error + " | " if results.error else "") + restore_error
                results.status = "FAIL" if not args.auto else "NOT SCORED"
                exit_code = 2
            results.router_state_preserved = sandbox.state_preserved
            results.router_restored = sandbox.restored
        if fixture is not None:
            fixture_log_index = _flush_fixture_commands(fixture, fixture_log_index)
            if not fixture.teardown():
                results.error = (
                    (results.error + " | " if results.error else "")
                    + "fixture preserved: "
                    + str(fixture.preserved_reason)
                )
                results.status = "FAIL" if not args.auto else "NOT SCORED"
                exit_code = 2
                _facilitator("fixture preserved: " + ", ".join(fixture.created_paths))
            fixture_log_index = _flush_fixture_commands(fixture, fixture_log_index)
        try:
            host.check_after()
        except (TrialFailure, OSError) as exc:
            results.error = (results.error + " | " if results.error else "") + str(exc)
            results.status = "FAIL" if not args.auto else "NOT SCORED"
            exit_code = 2
        results.write()
        if sandbox is not None:
            sandbox.close_if_restored()
        _facilitator("results log: " + str(results.path))
        _facilitator("scoring status: " + results.status)
        if interrupted:
            _facilitator("partial results and recovery evidence were retained")
    return exit_code


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run AWA's exact seven-step real-PM trial from one command."
    )
    parser.add_argument("--auto", action="store_true", help="automated rehearsal; always NOT SCORED")
    parser.add_argument("--out", help="new results path (must not already exist)")
    parser.add_argument("--router-source", help=argparse.SUPPRESS)
    parser.add_argument("--governed-root", help=argparse.SUPPRESS)
    parser.add_argument("--personal-root", help=argparse.SUPPRESS)
    parser.add_argument("--awa-cli", help=argparse.SUPPRESS)
    parser.add_argument("--managed-root", help=argparse.SUPPRESS)
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    if args._worker:
        return _worker_main()
    try:
        return _run_trial(args)
    except (FixtureIdentityError, FixtureCommitError) as exc:
        _facilitator(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
