"""S5 redaction scaffold tests (engine/redact.py).

The audit/command-log writer pipes every persisted string through ``redact.redact``
so no secret/PII lands in a record (plan §H4 row S5). These tests assert the pass
redacts common secret shapes AND that the raw secret never survives the pass.

Secret-shaped fixtures are BUILT at runtime (never a literal in this file) so the
data-guard pre-commit gate stays honest.
"""

from __future__ import annotations

import unittest

from engine import redact


class TestRedact(unittest.TestCase):
    def test_github_token_redacted(self):
        tok = "ghp_" + ("A" * 36)
        out = redact.redact(f"run --flag --token {tok} now")
        self.assertIn("redacted", out)
        self.assertNotIn(tok, out)

    def test_secret_assignment_redacted(self):
        secret = "s" + ("9" * 24)
        out = redact.redact(f"deploy --password={secret}")
        self.assertIn("<redacted:", out)
        self.assertNotIn(secret, out)

    def test_env_secret_redacted(self):
        secret = "z" + ("7" * 30)
        out = redact.redact(f"API_KEY={secret}")
        self.assertIn("<redacted:", out)
        self.assertNotIn(secret, out)

    def test_url_credentials_redacted(self):
        pw = "p" + ("4" * 20)
        out = redact.redact(f"clone https://user:{pw}@example.invalid/repo.git")
        self.assertIn("<redacted:url-credentials>", out)
        self.assertNotIn(pw, out)

    def test_empty_and_clean_passthrough(self):
        self.assertEqual(redact.redact(""), "")
        self.assertEqual(redact.redact("git status --porcelain"), "git status --porcelain")


if __name__ == "__main__":
    unittest.main()
