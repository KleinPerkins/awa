#!/usr/bin/env python3
"""redact.py — S5 secret/PII redaction pass for AWA audit + command logs (scaffold).

Plan v2.1 §H4 row S5 (v1:862-864) requires that NO prompt/transcript/file-content and NO
secret/PII lands in an audit or command-log record. The AWA engine's audit writer is unbuilt
(Phases 4/6), so this module is the FORWARD scaffold the writer must use: every command string
or log line MUST be piped through ``redact()`` before it is persisted.

Usage:
  import redact; safe = redact.redact(cmd)          # library
  echo '<line>' | redact.py                          # stdin->stdout filter

It is deliberately conservative (over-redacts rather than leaks). It never emits the original
secret; matched spans become ``<redacted:KIND>``.
"""

from __future__ import annotations

import re
import sys

# (name, compiled pattern). Order matters — most specific first.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    # GitHub tokens (classic + fine-grained + oauth/app/server/refresh).
    ("github-token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,255}|github_pat_[A-Za-z0-9_]{20,255})\b")),
    # AWS access key id + secret access key.
    ("aws-akid", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("aws-secret", re.compile(r"(?i)\baws_secret_access_key\b\s*[=:]\s*\S+")),
    # Slack / Google / generic bearer + private keys.
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    # URL embedded credentials: scheme://user:pass@host
    ("url-credentials", re.compile(r"\b([a-zA-Z][a-zA-Z0-9+.\-]*://[^\s:/@]+):[^\s:/@]+@")),
    # Flag/env style: --password=..., TOKEN=..., api_key: ...
    ("secret-assignment", re.compile(
        r"(?i)(--?(?:password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key|auth)\b\s*[=:\s]\s*)(\S+)")),
    ("env-secret", re.compile(
        r"(?im)^\s*([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY)[A-Z0-9_]*)\s*=\s*(\S+)")),
]


def redact(text: str) -> str:
    """Return ``text`` with secret-looking spans replaced by ``<redacted:KIND>``."""
    if not text:
        return text
    out = text
    for name, pat in _PATTERNS:
        if name == "url-credentials":
            out = pat.sub(lambda m: f"{m.group(1)}:<redacted:url-credentials>@", out)
        elif name in ("secret-assignment", "env-secret"):
            out = pat.sub(lambda m: f"{m.group(1)}<redacted:{name}>", out)
        else:
            out = pat.sub(f"<redacted:{name}>", out)
    return out


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    sys.stdout.write(redact(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
