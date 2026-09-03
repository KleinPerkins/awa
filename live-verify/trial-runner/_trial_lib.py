"""_trial_lib.py — core for the AWA Root-Bound Worktree Finish comprehensive UAT trial runner.

This is TEST INFRASTRUCTURE (Layer A). It provisions a fully DISPOSABLE sandbox OUTSIDE the real
worktree/state/runtime and drives EVERY finish/retention state transition (Phases 1-3) end-to-end
through the REAL production entrypoints:

  * kernel   -> ``kernel/lib/awa_finish.py`` CLI + ``kernel/bin/dev-worktree.sh`` + ``awa_roots.py``
  * consumer -> ``consumer/finish_current.py`` CLI + ``kernel/hooks/before-submit-prompt.sh``
  * engine   -> ``python -m engine recover|daemon`` + ``kernel/hooks/awa-recovery-maintenance.sh``
             -> in-process ``engine.retention`` (the SAME public API the oracle suites call)

Expected outcomes are the assertions already encoded in the finish/retention test suites; every row
cites the exact ``module::Class::test`` oracle it mirrors, so this harness re-checks the same
assertion at the real CLI/shell boundary against a freshly provisioned sandbox rather than
re-deriving semantics.

Isolation: each transition runs inside its own ``Sandbox`` — a temp dir with ``XDG_STATE_HOME`` /
``XDG_DATA_HOME`` / ``XDG_CONFIG_HOME`` redirected, throwaway git repos + linked worktrees, and a
disposable AWA state root. It never reads or writes the real state root (``~/.local/state/awa``),
the real worktree's git, or the released runtime (``~/.local/share/awa/current``). The harness
fingerprints the real state root + worktree git before and after the run and asserts they are
unchanged.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ---- repo layout (this file lives at live-verify/trial-runner/_trial_lib.py) ---------------------
REPO = Path(__file__).resolve().parents[2]
FINISH_PY = REPO / "kernel" / "lib" / "awa_finish.py"
ROOTS_PY = REPO / "kernel" / "lib" / "awa_roots.py"
DURABILITY_PY = REPO / "kernel" / "lib" / "awa_durability.py"
DEV_WORKTREE = REPO / "kernel" / "bin" / "dev-worktree.sh"
HOOK_BEFORE_SUBMIT = REPO / "kernel" / "hooks" / "before-submit-prompt.sh"
HOOK_SESSION = REPO / "kernel" / "hooks" / "worktree-session.sh"
HOOK_RECOVERY = REPO / "kernel" / "hooks" / "awa-recovery-maintenance.sh"
INSTALL_HOOKS = REPO / "kernel" / "hooks" / "install-hooks.sh"
INSTALL_SH = REPO / "install.sh"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# The consumer surface is the SAME module the oracle suite (`test_finish_conversation`) imports.
from consumer import finish_current as UX  # noqa: E402

_IDENT = ("-c", "user.email=49759187+KleinPerkins@users.noreply.github.com",
          "-c", "user.name=KleinPerkins")

# ---- results row ---------------------------------------------------------------------------------
PASS, FAIL, ERROR, SKIP = "PASS", "FAIL", "ERROR", "SKIP"


@dataclasses.dataclass
class Row:
    id: str
    phase: str
    title: str
    precondition: str
    inp: str
    expected: str
    oracle: str
    layer: str = "headless"          # headless | live-deferred
    observed: str = ""
    status: str = "PENDING"
    detail: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class TrialAssertion(AssertionError):
    """Raised by a transition drive when an observed outcome diverges from the oracle."""


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise TrialAssertion(msg)


def check_eq(got, want, label: str) -> None:
    if got != want:
        raise TrialAssertion(f"{label}: got {got!r}, want {want!r}")


def stat_mode(path) -> int:
    return Path(path).stat().st_mode & 0o777


# ---- sandbox -------------------------------------------------------------------------------------
class Sandbox:
    """A disposable, XDG-isolated sandbox. Mirrors engine/tests/helpers.py::EngineTestCase but as a
    context manager so the comprehensive harness can provision a fresh one per transition."""

    def __init__(self) -> None:
        self._saved: dict[str, str | None] = {}
        self.tmp = Path(tempfile.mkdtemp(prefix="awa-uat-p123."))
        self.state = self.tmp / "state"
        self.data = self.tmp / "data"
        self.cfg = self.tmp / "config"
        for d in (self.state, self.data, self.cfg):
            d.mkdir(parents=True, exist_ok=True)

    # -- env lifecycle --
    def __enter__(self) -> "Sandbox":
        setenv = {
            "XDG_STATE_HOME": str(self.state),
            "XDG_DATA_HOME": str(self.data),
            "XDG_CONFIG_HOME": str(self.cfg),
            "AWA_HOME": str(REPO),
            "AWA_ROOTS_LIB": str(ROOTS_PY),
            "AWA_FINISH_LIB": str(FINISH_PY),
            "AWA_DURABILITY_LIB": str(DURABILITY_PY),
        }
        clear = [
            "DEV_SESSION_ID", "AWA_FINISH_CONVERSATION_ID", "AWA_FINISH_AUTHORIZATION",
            "AWA_FINISH_CHALLENGE_TTL_SECONDS", "AWA_HEARTBEAT_TTL_SECONDS",
            "AWA_FINISH_SESSION_BIND_WAIT_SECONDS", "AWA_HOOKS_JSON",
            "AWA_FINISH_PUBLIC_PROJECTION", "AWA_FINISH_HOOK_PUBLICATION_INVOCATION",
        ]
        for k, v in setenv.items():
            self._saved[k] = os.environ.get(k)
            os.environ[k] = v
        for k in clear:
            self._saved[k] = os.environ.get(k)
            os.environ.pop(k, None)
        return self

    def __exit__(self, *exc) -> None:
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- subprocess envs --
    def kernel_env(self, *, path: str | None = None, engine_off: bool = True,
                   extra: dict | None = None) -> dict:
        """Env for a kernel (awa_finish.py / dev-worktree.sh / awa_roots.py) subprocess. By default
        the engine package is made UNIMPORTABLE (engine-OFF proof) exactly like FinishBase.env."""
        env = os.environ.copy()
        if engine_off:
            empty = self.data / "empty-pp"
            empty.mkdir(parents=True, exist_ok=True)
            env["PYTHONPATH"] = str(empty)
        if path is not None:
            env["PATH"] = path
        if extra:
            env.update(extra)
        return env

    def engine_env(self, *, extra: dict | None = None) -> dict:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO)
        if extra:
            env.update(extra)
        return env

    # -- git builders (system temp -> no governed hooks, cf. helpers.py) --
    @staticmethod
    def git(cwd: str, *args: str, check_rc: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True,
                              check=check_rc)

    def commit_all(self, cwd: str, message: str) -> None:
        self.git(cwd, "add", "-A")
        subprocess.run(["git", "-C", cwd, *_IDENT, "commit", "-qm", message],
                       capture_output=True, text=True, check=True)

    def make_repo(self, name: str = "repo", *, origin: bool = True) -> str:
        repo = str(self.tmp / name)
        os.makedirs(repo, exist_ok=True)
        self.git(repo, "init", "-q", ".")
        Path(repo, "README.md").write_text("# uat\n", encoding="utf-8")
        self.commit_all(repo, "init")
        self.git(repo, "branch", "-M", "main")
        if origin:
            self.git(repo, "remote", "add", "origin",
                     "git@github.com:KleinPerkins/awa-test.git")
        return repo

    def add_worktree(self, repo: str, branch: str, suffix: str = ".wt") -> str:
        wt = repo + suffix
        self.git(repo, "worktree", "add", "-q", "-b", branch, wt, "main")
        return wt

    def add_bare_remote(self, repo: str, name: str = "origin.git") -> str:
        bare = str(self.tmp / name)
        self.git(str(self.tmp), "init", "-q", "--bare", bare)
        r = subprocess.run(["git", "-C", repo, "remote", "set-url", "origin", bare],
                           capture_output=True, text=True)
        if r.returncode != 0:
            self.git(repo, "remote", "add", "origin", bare)
        return bare

    def linked(self, name: str = "finish") -> tuple[str, str]:
        repo = self.make_repo(name)
        wt = self.add_worktree(repo, f"cursor/worktree/{name}")
        return repo, wt

    def ephemeral_wt(self, name: str, files: dict | None = None, *,
                     branch: str | None = None) -> tuple[str, str, str]:
        repo = self.make_repo(name)
        br = branch or f"cursor/worktree/{name}"
        wt = repo + ".wt"
        self.git(repo, "worktree", "add", "-q", "-b", br, wt, "main")
        for rel, content in (files or {}).items():
            p = Path(wt, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return repo, wt, br

    def targets(self, wt: str) -> dict:
        gd = self.git(wt, "rev-parse", "--path-format=absolute", "--git-dir").stdout.strip()
        cd = self.git(wt, "rev-parse", "--path-format=absolute",
                      "--git-common-dir").stdout.strip()
        br = self.git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        hd = self.git(wt, "rev-parse", "HEAD").stdout.strip()
        return {"root": os.path.realpath(wt), "git_dir": gd, "common_dir": cd,
                "branch": br, "head": hd}

    # -- kernel CLI drivers (mirror FinishBase.preview / .execute) --
    def _common_target_args(self, wt: str, conv: str, session: str) -> list[str]:
        t = self.targets(wt)
        return ["--root", wt, "--git-dir", t["git_dir"], "--common-dir", t["common_dir"],
                "--branch", t["branch"], "--head", t["head"],
                "--session-id", session, "--conversation-id", conv]

    def run_kernel(self, *args: str, env: dict | None = None,
                   cwd: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["python3", str(FINISH_PY), *args],
                              env=env or self.kernel_env(), cwd=cwd or str(REPO),
                              capture_output=True, text=True)

    def kernel_preview(self, wt: str, conv: str = "conv", session: str = "sess") -> dict:
        r = self.run_kernel("preview", *self._common_target_args(wt, conv, session))
        check(r.returncode == 0, f"kernel preview rc={r.returncode}: {r.stdout}{r.stderr}")
        return json.loads(r.stdout)

    def kernel_execute(self, wt: str, answer: str, conv: str = "conv", session: str = "sess",
                       env: dict | None = None) -> dict:
        r = self.run_kernel("finish-execute", *self._common_target_args(wt, conv, session),
                            "--answer", answer, env=env)
        try:
            return json.loads(r.stdout)
        except (ValueError, json.JSONDecodeError) as exc:
            raise TrialAssertion(
                f"finish-execute produced non-JSON (rc={r.returncode}): "
                f"stdout={r.stdout!r} stderr={r.stderr!r}") from exc

    def run_dev_finish(self, *args: str, cwd: str,
                       env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(DEV_WORKTREE), "clean", "--finish-current", *args],
                              cwd=cwd, env=env or self.kernel_env(),
                              capture_output=True, text=True)

    def receipts(self) -> list[dict]:
        rd = self.state / "awa" / "receipts"
        if not rd.is_dir():
            return []
        files = sorted(rd.glob("clean-*.json"), key=lambda p: p.stat().st_mtime_ns)
        return [json.loads(p.read_text(encoding="utf-8")) for p in files]

    def last_receipt(self) -> dict:
        rs = self.receipts()
        check(bool(rs), "expected at least one clean receipt")
        return rs[-1]

    def roots_heartbeat(self, wt: str, session_id: str, branch: str, common: str) -> None:
        r = subprocess.run(
            ["python3", str(ROOTS_PY), "heartbeat", "--root", wt, "--branch", branch,
             "--common-dir", common, "--session-id", session_id],
            env=self.kernel_env(), capture_output=True, text=True)
        check(r.returncode == 0, f"heartbeat rc={r.returncode}: {r.stderr}")

    # -- consumer in-process helpers (mirror test_finish_conversation.Phase2Base.payload) --
    @staticmethod
    def finish_payload(wt: str, prompt: str = "I'm done", conv: str = "conv") -> dict:
        try:
            target = UX.resolve_linked_root({"cwd": wt})
        except UX.FinishUXError:
            target = None
        if target is not None:
            UX._load_finish()._roots_module().write_current_session(
                wt, session_id=conv, conversation_id=conv,
                branch=target["branch"], common_dir=target["common_dir"])
        return {"hook_event_name": "beforeSubmitPrompt", "prompt": prompt,
                "conversation_id": conv, "session_id": conv, "cwd": wt,
                "workspace_roots": [wt]}

    def preview_payload(self, wt: str, conv: str = "conv", prompt: str = "I'm done") -> dict:
        return UX.preview_payload(self.finish_payload(wt, prompt=prompt, conv=conv))

    # -- consumer CLI --
    def run_consumer(self, *args: str, stdin: str | None = None,
                     env: dict | None = None, cwd: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["python3", str(UX.__file__), *args],
                              input=stdin, env=env or os.environ.copy(),
                              cwd=cwd or str(REPO), capture_output=True, text=True)

    # -- engine CLI --
    def run_engine(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["python3", "-m", "engine", *args],
                              env=env or self.engine_env(), cwd=str(REPO),
                              capture_output=True, text=True)

    # -- shell hook + arbitrary subprocess (sandbox env by default) --
    def run_hook(self, script, stdin: str,
                 env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([str(script)], input=stdin, env=env or os.environ.copy(),
                              capture_output=True, text=True)

    @staticmethod
    def run_raw(cmd: list[str], env: dict | None = None,
                cwd: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True)


# ---- real-environment guard ----------------------------------------------------------------------
def _real_state_root() -> Path:
    return Path.home() / ".local" / "state" / "awa"


# Top-level state-root subtrees OWNED BY THE LIVE RUNTIME that mutate on their own clock (heartbeat
# rotation, receipts appended by ANY session, transient locks, per-prompt hook metadata). They change
# independently of this harness — the harness redirects XDG_STATE_HOME per sandbox, so nothing it does
# lands here. Changes under these prefixes are reported as informational live-churn, NOT failures. The
# finish AUTHORIZATION + recovery/retain subtrees (where a real harness leak WOULD show) stay STRICT.
_VOLATILE_STATE_PREFIXES = frozenset({
    "roots", "receipts", "locks", "detections", "hook-probe", "current-session",
    "finish-hook-observations", "finish-hook-publications",
})


def _is_volatile(rel: str) -> bool:
    return rel.split("/", 1)[0] in _VOLATILE_STATE_PREFIXES


def fingerprint_real_env() -> dict:
    """A defensible snapshot proving the harness left the real environment untouched.

    * worktree git status + HEAD (STRICT: the harness must never dirty the real worktree), and
    * the real state-root file SET + sizes, split into the live-runtime-owned VOLATILE subtrees
      (``roots``/``receipts``/``locks``/hook metadata — the operator's live runtime rotates these on
      its own clock, so they are reported but NOT asserted) and everything else, INCLUDING the finish
      authorization + recovery/retain subtrees, which are STRICT: a real harness leak would show there
      and is never tolerated.
    """
    real = _real_state_root()
    files: list[tuple[str, int, int]] = []
    if real.exists():
        for p in sorted(real.rglob("*")):
            try:
                st = p.lstat()
            except OSError:
                continue
            files.append((str(p.relative_to(real)), int(st.st_size), stat.S_IFMT(st.st_mode)))
    strict = [f for f in files if not _is_volatile(f[0])]
    setsig = hashlib.sha256(repr(strict).encode()).hexdigest()
    wt_status = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain=v1"],
                               capture_output=True, text=True).stdout
    wt_head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
    return {"state_setsig": setsig, "state_count": len(files),
            "strict_count": len(strict), "wt_status": wt_status, "wt_head": wt_head,
            "state_files": files}


def diff_real_env(before: dict, after: dict) -> list[str]:
    """Return HARD problems only. Live-runtime volatile churn is excluded (see _is_volatile)."""
    problems: list[str] = []
    if before["wt_head"] != after["wt_head"]:
        problems.append(f"worktree HEAD changed {before['wt_head']} -> {after['wt_head']}")
    if before["wt_status"] != after["wt_status"]:
        problems.append("worktree git status changed during the run (harness dirtied the worktree)")
    if before["state_setsig"] != after["state_setsig"]:
        b = {f[0] for f in before["state_files"] if not _is_volatile(f[0])}
        a = {f[0] for f in after["state_files"] if not _is_volatile(f[0])}
        added = sorted(a - b)
        removed = sorted(b - a)
        bsz = {f[0]: f[1] for f in before["state_files"] if not _is_volatile(f[0])}
        asz = {f[0]: f[1] for f in after["state_files"] if not _is_volatile(f[0])}
        resized = sorted(p for p in (a & b) if bsz.get(p) != asz.get(p))
        problems.append(
            f"real state root (finish/recovery/non-volatile) changed: added={added} "
            f"removed={removed} resized={resized}")
    return problems


def live_churn(before: dict, after: dict) -> int:
    """Count live-runtime volatile-subtree file-set changes (informational; not a failure)."""
    b = {f[0] for f in before["state_files"] if _is_volatile(f[0])}
    a = {f[0] for f in after["state_files"] if _is_volatile(f[0])}
    return len(a ^ b)


# ---- registry ------------------------------------------------------------------------------------
_REGISTRY: list[tuple[Row, object]] = []


def transition(row: Row):
    """Decorator: register a drive callable ``fn(sb: Sandbox) -> str`` (returns an observed
    summary; raises TrialAssertion on divergence)."""
    def deco(fn):
        _REGISTRY.append((row, fn))
        return fn
    return deco


def registry() -> list[tuple[Row, object]]:
    return _REGISTRY


@contextlib.contextmanager
def monkeypatch(obj, name, value):
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)
