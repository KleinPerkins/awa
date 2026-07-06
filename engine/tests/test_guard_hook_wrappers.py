"""Bash-hook parity for the option-aware wrapper-skip + brace-group fixes (#2, #7).

`engine/guard.py` and `kernel/hooks/worktree-guard.sh` ship TWO mirror implementations of the
mutating-command detector. `test_guard.py` proves the engine mirror; this drives the ACTUAL
bash hook (the load-bearing beforeShellExecution gate) end-to-end so a wrapper-obscured
mutation still returns the frozen `ask` on an included primary checkout — proving the kernel
mirror got the same fix. No host dependency: a temp git repo under a temp governed root.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_GUARD = _REPO / "kernel" / "hooks" / "worktree-guard.sh"

_IDENT = ("-c", "user.email=49759187+KleinPerkins@users.noreply.github.com",
          "-c", "user.name=KleinPerkins")

_POLICY = """\
version: 1
governed_roots:
  - {root}
default: include
include:
  - '*'
exclude:
  - .
detectors:
  governed_markers:
    - _ops/POLICY.md
  foreign_hook_frameworks:
    - husky
"""


class TestBashGuardWrapperParity(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-hook-wrap.")
        self.root = Path(self._tmp.name)
        self.repo = self.root / "proj"
        self.repo.mkdir()
        env = dict(os.environ)
        for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                  "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
            env.pop(k, None)
        self._git_env = env
        self._git("init", "-q", str(self.repo))
        (self.repo / "f").write_text("#\n", encoding="utf-8")
        self._git("-C", str(self.repo), "add", "f")
        self._git("-C", str(self.repo), *_IDENT, "commit", "-qm", "init")
        self._git("-C", str(self.repo), "branch", "-M", "main")
        self._git("-C", str(self.repo), "remote", "add", "origin",
                  "git@github.com:KleinPerkins/awa-hook-wrap.git")
        self.policy = self.root / "policy.yml"
        self.policy.write_text(_POLICY.format(root=self.root), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, *args):
        subprocess.run(["git", *args], check=True, capture_output=True,
                       text=True, env=self._git_env)

    def _guard(self, command: str) -> dict:
        payload = json.dumps({"cwd": str(self.repo), "command": command})
        env = dict(os.environ)
        env["AWA_GOVERNED_ROOT"] = str(self.root)
        env["AWA_POLICY"] = str(self.policy)
        proc = subprocess.run([str(_GUARD)], input=payload, capture_output=True,
                              text=True, env=env)
        return json.loads(proc.stdout)

    def test_wrapper_mutating_forms_ask(self):
        for cmd in ("nice -n 10 git commit -am x", "env -C /r git commit",
                    "env -i git commit", "sudo -u root git commit",
                    "xargs -I{} git commit", "xargs -I {} git commit",
                    "timeout 5 git commit", "timeout -s KILL 5 git commit",
                    "ionice -c 3 git commit", "chrt -b 0 git commit",
                    "stdbuf -oL git commit", "{ git commit; }",
                    "nice -n 10 rm -rf x"):
            resp = self._guard(cmd)
            self.assertEqual(resp.get("permission"), "ask", cmd)
            # frozen ask shape
            self.assertIn("user_message", resp)
            self.assertIn("agent_message", resp)

    def test_wrapper_readonly_forms_allow(self):
        for cmd in ("timeout 5 git status", "nice -n 10 ls -la",
                    "sudo -u root git status", "{ git status; }"):
            resp = self._guard(cmd)
            self.assertEqual(resp.get("permission"), "allow", cmd)


if __name__ == "__main__":
    unittest.main()
