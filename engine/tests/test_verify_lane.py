"""M1-B verification-lane classification and graph tests."""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from engine.tests import verify_lane


ROOT = Path(__file__).resolve().parents[2]
REGULAR = 0o100644
SYMLINK = 0o120000


def change(
    status: str,
    old_path: Optional[str],
    new_path: Optional[str],
    old_mode: Optional[int],
    new_mode: Optional[int],
    source: str = "test",
) -> verify_lane.ChangeRecord:
    return verify_lane.ChangeRecord(
        status=status,
        old_path=old_path,
        new_path=new_path,
        old_mode=old_mode,
        new_mode=new_mode,
        source=source,
    )


class VerifyLaneTest(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ("git", "-C", str(root), *args),
            text=True,
            capture_output=True,
            check=True,
        )

    def _repo(self) -> tuple:
        temporary = tempfile.TemporaryDirectory(prefix="awa-verify-lane.")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self._git(root, "init", "-q")
        self._git(root, "config", "user.name", "Fixture")
        self._git(root, "config", "user.email", "fixture@example.invalid")
        (root / "docs" / "adr").mkdir(parents=True)
        (root / "docs" / "plans").mkdir(parents=True)
        (root / "README.md").write_text(
            "# Fixture\n\n[Guide](docs/guide.md)\n", encoding="utf-8"
        )
        (root / "docs" / "guide.md").write_text(
            "# Guide\n\n[Home](../README.md)\n", encoding="utf-8"
        )
        (root / "docs" / "adr" / "0001-base.md").write_text(
            "# ADR 0001\n", encoding="utf-8"
        )
        (root / "docs" / "adr" / "README.md").write_text(
            "# ADRs\n\n| ADR |\n|---|\n| [0001](0001-base.md) |\n",
            encoding="utf-8",
        )
        (root / "docs" / "plans" / "base-v1.md").write_text(
            "# Base plan\n", encoding="utf-8"
        )
        (root / "docs" / "plans" / "README.md").write_text(
            "# Plans\n\n| Plan |\n|---|\n| `base-v1.md` |\n",
            encoding="utf-8",
        )
        self._git(root, "add", ".")
        self._git(root, "commit", "-qm", "base")
        base = self._git(root, "rev-parse", "HEAD").stdout.strip()
        return root, base

    def test_markdown_add_modify_delete_rename_and_copy_are_docs(self) -> None:
        records = (
            change("A", None, "docs/new.md", None, REGULAR),
            change("M", "docs/a.md", "docs/a.md", REGULAR, REGULAR),
            change("D", "docs/old.md", None, REGULAR, None),
            change(
                "R100",
                "docs/old.md",
                "docs/new.md",
                REGULAR,
                REGULAR,
            ),
            change(
                "C100",
                "docs/source.md",
                "docs/copy.md",
                REGULAR,
                REGULAR,
            ),
        )
        for record in records:
            with self.subTest(record=record):
                self.assertEqual(
                    verify_lane.classify_changes((record,)),
                    "docs",
                )

    def test_empty_mixed_escape_symlink_and_unknown_fail_broad(self) -> None:
        cases = (
            (),
            (
                change("M", "docs/x.md", "docs/x.md", REGULAR, REGULAR),
                change("M", "engine/x.py", "engine/x.py", REGULAR, REGULAR),
            ),
            (
                change(
                    "R100",
                    "engine/x.py",
                    "docs/x.md",
                    REGULAR,
                    REGULAR,
                ),
            ),
            (change("A", None, "../outside.md", None, REGULAR),),
            (change("A", None, "/absolute.md", None, REGULAR),),
            (change("A", None, "docs/dangling.md", None, SYMLINK),),
            (change("X", "docs/x.md", "docs/x.md", REGULAR, REGULAR),),
            (change("A", None, None, None, None),),
        )
        for records in cases:
            with self.subTest(records=records):
                self.assertEqual(
                    verify_lane.classify_changes(records),
                    "pre-pr",
                )

    def test_changed_records_cover_all_git_layers(self) -> None:
        root, base = self._repo()
        guide = root / "docs" / "guide.md"
        guide.write_text("# Guide changed\n", encoding="utf-8")
        self._git(root, "add", "docs/guide.md")
        self._git(root, "commit", "-qm", "committed docs")
        (root / "docs" / "staged.md").write_text("# Staged\n", encoding="utf-8")
        self._git(root, "add", "docs/staged.md")
        (root / "README.md").write_text("# Working tree\n", encoding="utf-8")
        (root / "docs" / "untracked.md").write_text(
            "# Untracked\n", encoding="utf-8"
        )

        records = verify_lane.changed_records(root, base)

        self.assertEqual(
            {record.source for record in records},
            {"committed", "staged", "unstaged", "untracked"},
        )
        self.assertEqual(verify_lane.classify_changes(records), "docs")

    def test_duplicate_path_across_layers_fails_broad(self) -> None:
        root, base = self._repo()
        guide = root / "docs" / "guide.md"
        guide.write_text("# Committed\n", encoding="utf-8")
        self._git(root, "add", "docs/guide.md")
        self._git(root, "commit", "-qm", "committed")
        guide.write_text("# Changed again\n", encoding="utf-8")

        records = verify_lane.changed_records(root, base)

        self.assertTrue(any(record.status == "X" for record in records))
        self.assertEqual(verify_lane.classify_changes(records), "pre-pr")

    def test_require_docs_checks_links_indexes_and_untracked_whitespace(self) -> None:
        root, base = self._repo()
        (root / "docs" / "guide.md").write_text(
            "# Guide updated\n\n"
            "[Home](../README.md)\n"
            "[Cursor chat](e1559421-e3c6-4673-bb4e-a79b0a8aef92)\n",
            encoding="utf-8",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        self.assertEqual(
            verify_lane.require_docs(root, base, stdout, stderr),
            0,
            stderr.getvalue(),
        )
        self.assertIn('"classification": "docs"', stdout.getvalue())

        (root / "docs" / "broken.md").write_text(
            "# Broken  \n\n[Missing](missing.md)\n", encoding="utf-8"
        )
        self.assertEqual(
            verify_lane.require_docs(root, base, io.StringIO(), io.StringIO()),
            2,
        )

    def test_unindexed_governed_document_fails_docs_lane(self) -> None:
        root, base = self._repo()
        (root / "docs" / "adr" / "0002-new.md").write_text(
            "# ADR 0002\n", encoding="utf-8"
        )
        self.assertEqual(
            verify_lane.require_docs(root, base, io.StringIO(), io.StringIO()),
            2,
        )

    def test_make_inputs_are_exported_not_interpolated_as_shell(self) -> None:
        with tempfile.TemporaryDirectory(prefix="awa-make-lane.") as tmp:
            marker = Path(tmp) / "must-not-exist"
            payload = "$(shell touch {0})".format(marker)
            for assignment, target in (
                ("TESTS=" + payload, "verify-focused"),
                ("VERIFY_BASE=" + payload, "verify-docs"),
            ):
                with self.subTest(target=target):
                    subprocess.run(
                        ("make", target, assignment),
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                        timeout=20,
                    )
                    self.assertFalse(marker.exists())

    def test_makefile_has_named_lanes_and_only_two_freeze_paths(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        for target in (
            "verify-docs:",
            "verify-focused:",
            "verify-pre-pr:",
            "verify-release:",
        ):
            self.assertIn(target, makefile)
        self.assertNotIn(
            "@AWA_HOME=$(CURDIR) bash kernel/checks/awa-contract-freeze.sh",
            makefile,
        )
        self.assertIn("@./install.sh --check", makefile)
        self.assertIn(
            "awa-contract-freeze.sh",
            (ROOT / "install.sh").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "test_freeze_checker_passes",
            (ROOT / "engine" / "tests" / "test_contract_schemas.py").read_text(
                encoding="utf-8"
            ),
        )


if __name__ == "__main__":
    unittest.main()
