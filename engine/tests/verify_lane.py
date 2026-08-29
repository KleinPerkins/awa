"""Fail-closed verification-lane classification for AWA source changes."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import stat
import subprocess
import sys
import urllib.parse
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional, Sequence, TextIO, Tuple


_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_HEX_OID = re.compile(r"[0-9a-f]{40,64}\Z")
_ADR_PATH = re.compile(r"docs/adr/[0-9]{4}-[^/]+\.md\Z")
_CURSOR_CHAT_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z",
    re.IGNORECASE,
)
_INLINE_LINK = re.compile(
    r"!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^\s)\n]+)"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"
)
_REFERENCE_LINK = re.compile(
    r"(?m)^[ \t]{0,3}\[[^\]\n]+\]:[ \t]*(<[^>\n]+>|[^\s\n]+)"
)
_INDEX_CODE_PATH = re.compile(r"`([^`\n]+\.md)`")
_INLINE_CODE = re.compile(r"(`+)(.+?)\1")
_REGULAR_MODES = frozenset((0o100644, 0o100755))
_SOURCES = ("committed", "staged", "unstaged", "untracked")


class LaneError(RuntimeError):
    """Verification input could not be proven safe for the docs lane."""


@dataclasses.dataclass(frozen=True)
class ChangeRecord:
    status: str
    old_path: Optional[str]
    new_path: Optional[str]
    old_mode: Optional[int]
    new_mode: Optional[int]
    source: str


def _run_git(root: Path, args: Sequence[str]) -> subprocess.CompletedProcess:
    process = subprocess.run(
        ("git", *args),
        cwd=str(root),
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", "replace").strip()
        raise LaneError(
            "git {0} failed{1}".format(
                " ".join(args[:2]),
                ": " + detail if detail else "",
            )
        )
    return process


def _validated_base(root: Path, base: str) -> str:
    if not isinstance(base, str) or not base.strip():
        raise LaneError("verification base must be a non-empty Git ref")
    process = _run_git(
        root,
        ("rev-parse", "--verify", "--end-of-options", base + "^{commit}"),
    )
    oid = process.stdout.decode("ascii", "strict").strip()
    if not _HEX_OID.fullmatch(oid):
        raise LaneError("verification base did not resolve to a commit")
    return oid


def _mode(value: bytes) -> Optional[int]:
    try:
        parsed = int(value, 8)
    except ValueError as exc:
        raise LaneError("Git returned an invalid file mode") from exc
    return parsed or None


def _path(value: bytes) -> str:
    if not value:
        raise LaneError("Git returned an empty path")
    return value.decode("utf-8", "surrogateescape")


def _parse_raw(output: bytes, source: str) -> Tuple[ChangeRecord, ...]:
    tokens = output.split(b"\0")
    records = []
    index = 0
    while index < len(tokens) and tokens[index]:
        header = tokens[index]
        index += 1
        if not header.startswith(b":"):
            raise LaneError("Git raw diff record is malformed")
        fields = header[1:].split()
        if len(fields) != 5:
            raise LaneError("Git raw diff header is malformed")
        old_mode, new_mode, _old_oid, _new_oid, status_bytes = fields
        try:
            status = status_bytes.decode("ascii", "strict")
        except UnicodeDecodeError as exc:
            raise LaneError("Git raw diff status is malformed") from exc
        if index >= len(tokens) or not tokens[index]:
            raise LaneError("Git raw diff path is missing")
        first_path = _path(tokens[index])
        index += 1
        kind = status[:1]
        if kind in ("R", "C"):
            if index >= len(tokens) or not tokens[index]:
                raise LaneError("Git rename/copy destination is missing")
            second_path = _path(tokens[index])
            index += 1
            old_path, new_path = first_path, second_path
        elif kind == "A":
            old_path, new_path = None, first_path
        elif kind == "D":
            old_path, new_path = first_path, None
        else:
            old_path, new_path = first_path, first_path
        records.append(
            ChangeRecord(
                status=status,
                old_path=old_path,
                new_path=new_path,
                old_mode=_mode(old_mode),
                new_mode=_mode(new_mode),
                source=source,
            )
        )
    if any(tokens[index:]):
        raise LaneError("Git raw diff has trailing data")
    return tuple(records)


def _raw_diff(root: Path, args: Sequence[str], source: str) -> Tuple[ChangeRecord, ...]:
    common = (
        "--raw",
        "-z",
        "--no-abbrev",
        "--find-renames",
        "--find-copies",
    )
    return _parse_raw(_run_git(root, ("diff", *common, *args)).stdout, source)


def _filesystem_mode(path: Path) -> int:
    try:
        value = path.lstat().st_mode
    except OSError as exc:
        raise LaneError("unable to inspect untracked path") from exc
    if stat.S_ISREG(value):
        return 0o100755 if value & 0o111 else 0o100644
    if stat.S_ISLNK(value):
        return 0o120000
    return stat.S_IFMT(value)


def _untracked_records(root: Path) -> Tuple[ChangeRecord, ...]:
    output = _run_git(
        root,
        ("ls-files", "--others", "--exclude-standard", "-z", "--"),
    ).stdout
    records = []
    for raw_path in output.split(b"\0"):
        if not raw_path:
            continue
        relative = _path(raw_path)
        records.append(
            ChangeRecord(
                status="A",
                old_path=None,
                new_path=relative,
                old_mode=None,
                new_mode=_filesystem_mode(root / relative),
                source="untracked",
            )
        )
    return tuple(records)


def _duplicate_sentinel(
    records: Sequence[ChangeRecord],
) -> Optional[ChangeRecord]:
    seen = {}
    for record in records:
        for path in sorted(
            {value for value in (record.old_path, record.new_path) if value is not None}
        ):
            previous = seen.get(path)
            if previous is not None:
                return ChangeRecord(
                    status="X",
                    old_path=path,
                    new_path=path,
                    old_mode=previous.old_mode,
                    new_mode=record.new_mode,
                    source="conflict:{0}+{1}".format(
                        previous.source,
                        record.source,
                    ),
                )
            seen[path] = record
    return None


def changed_records(root: Path, base: str) -> Tuple[ChangeRecord, ...]:
    root = Path(root).resolve()
    base_oid = _validated_base(root, base)
    records = []
    records.extend(
        _raw_diff(root, (base_oid + "...HEAD", "--"), "committed")
    )
    records.extend(
        _raw_diff(root, ("--cached", "HEAD", "--"), "staged")
    )
    records.extend(_raw_diff(root, ("--",), "unstaged"))
    records.extend(_untracked_records(root))
    duplicate = _duplicate_sentinel(records)
    if duplicate is not None:
        records.append(duplicate)
    source_order = {name: index for index, name in enumerate(_SOURCES)}
    records.sort(
        key=lambda record: (
            source_order.get(record.source, len(source_order)),
            record.old_path or "",
            record.new_path or "",
            record.status,
        )
    )
    return tuple(records)


def _eligible_doc_side(path: Optional[str], mode: Optional[int]) -> bool:
    if path is None:
        return mode is None
    if not isinstance(path, str) or mode not in _REGULAR_MODES:
        return False
    if not path or "\\" in path or any(ord(char) < 32 for char in path):
        return False
    if any(0xD800 <= ord(char) <= 0xDFFF for char in path):
        return False
    pure = PurePosixPath(path)
    if (
        pure.is_absolute()
        or pure.as_posix() != path
        or ".." in pure.parts
        or ".git" in pure.parts
    ):
        return False
    return pure.name not in ("", ".", "..") and path.endswith(".md")


def _valid_status(status: str) -> bool:
    if status in ("A", "M", "D"):
        return True
    if status[:1] not in ("R", "C") or not status[1:].isdigit():
        return False
    score = int(status[1:])
    return 0 <= score <= 100


def classify_changes(records: Sequence[ChangeRecord]) -> str:
    records = tuple(records)
    if not records:
        return "pre-pr"
    for record in records:
        if not isinstance(record, ChangeRecord) or not _valid_status(record.status):
            return "pre-pr"
        kind = record.status[:1]
        shape = (record.old_path is not None, record.new_path is not None)
        if (
            (kind == "A" and shape != (False, True))
            or (kind == "D" and shape != (True, False))
            or (kind in ("M", "R", "C") and shape != (True, True))
        ):
            return "pre-pr"
        if kind == "M" and record.old_path != record.new_path:
            return "pre-pr"
        if not _eligible_doc_side(record.old_path, record.old_mode):
            return "pre-pr"
        if not _eligible_doc_side(record.new_path, record.new_mode):
            return "pre-pr"
    return "docs"


def _diff_checks(root: Path, base_oid: str) -> None:
    commands = (
        ("diff", "--check", base_oid + "...HEAD", "--"),
        ("diff", "--cached", "--check", "HEAD", "--"),
        ("diff", "--check", "--"),
    )
    for command in commands:
        process = _run_git(root, command)
        if process.stdout.strip():
            raise LaneError(
                process.stdout.decode("utf-8", "replace").strip()
                or "Git diff check failed"
            )


def _check_untracked_markdown(root: Path, records: Sequence[ChangeRecord]) -> None:
    for record in records:
        if record.source != "untracked" or record.new_path is None:
            continue
        path = root / record.new_path
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise LaneError(
                "unable to read untracked Markdown: " + record.new_path
            ) from exc
        for number, line in enumerate(lines, 1):
            if line.endswith((" ", "\t")):
                raise LaneError(
                    "{0}:{1}: trailing whitespace".format(
                        record.new_path,
                        number,
                    )
                )
            if line.startswith(("<<<<<<<", "=======", ">>>>>>>")):
                raise LaneError(
                    "{0}:{1}: conflict marker".format(
                        record.new_path,
                        number,
                    )
                )


def _tracked_paths(root: Path) -> Tuple[str, ...]:
    output = _run_git(root, ("ls-files", "-z", "--")).stdout
    return tuple(
        sorted(_path(item) for item in output.split(b"\0") if item)
    )


def _markdown_paths(
    root: Path, records: Sequence[ChangeRecord]
) -> Tuple[str, ...]:
    values = {path for path in _tracked_paths(root) if path.endswith(".md")}
    values.update(
        record.new_path
        for record in records
        if record.source == "untracked"
        and record.new_path is not None
        and _eligible_doc_side(record.new_path, record.new_mode)
    )
    current = []
    for relative in sorted(values):
        path = root / relative
        try:
            mode = _filesystem_mode(path)
        except LaneError:
            if not path.exists() and not path.is_symlink():
                continue
            raise
        if mode not in _REGULAR_MODES:
            raise LaneError("Markdown path is not a regular file: " + relative)
        current.append(relative)
    return tuple(current)


def _without_code_blocks(text: str) -> str:
    output = []
    fence = None
    for line in text.splitlines():
        stripped = line.lstrip()
        marker = stripped[:1]
        run = len(stripped) - len(stripped.lstrip(marker)) if marker else 0
        if marker in ("`", "~") and run >= 3:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            output.append("")
            continue
        if fence is None:
            output.append(_INLINE_CODE.sub("", line))
        else:
            output.append("")
    return "\n".join(output)


def _link_targets(text: str) -> Tuple[str, ...]:
    scrubbed = _without_code_blocks(text)
    values = []
    for pattern in (_INLINE_LINK, _REFERENCE_LINK):
        for match in pattern.finditer(scrubbed):
            value = match.group(1)
            if value.startswith("<") and value.endswith(">"):
                value = value[1:-1]
            values.append(value)
    return tuple(values)


def _relative_target(root: Path, source: Path, target: str) -> Optional[Path]:
    lowered = target.lower()
    if (
        lowered.startswith("http:")
        or lowered.startswith("https:")
        or lowered.startswith("mailto:")
        or target.startswith("#")
        or _CURSOR_CHAT_ID.fullmatch(target)
    ):
        return None
    parsed = urllib.parse.urlsplit(target)
    if parsed.scheme or parsed.netloc:
        raise LaneError("unsupported Markdown link target: " + target)
    decoded = urllib.parse.unquote(parsed.path)
    if not decoded:
        return None
    pure = PurePosixPath(decoded)
    if pure.is_absolute():
        raise LaneError("absolute Markdown link target: " + target)
    candidate = (source.parent / Path(*pure.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise LaneError("Markdown link escapes repository: " + target) from exc
    return candidate


def _read_markdown(path: Path, relative: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise LaneError("unable to read Markdown: " + relative) from exc


def _validate_relative_links(root: Path, markdown: Sequence[str]) -> None:
    for relative in markdown:
        source = root / relative
        text = _read_markdown(source, relative)
        for target in _link_targets(text):
            destination = _relative_target(root, source, target)
            if destination is not None and not destination.exists():
                raise LaneError(
                    "{0}: missing relative link target: {1}".format(
                        relative,
                        target,
                    )
                )


def _index_targets(root: Path, relative: str) -> Tuple[str, ...]:
    index = root / relative
    text = _read_markdown(index, relative)
    table_text = "\n".join(
        line for line in text.splitlines() if line.lstrip().startswith("|")
    )
    targets = []
    raw_targets = list(_link_targets(table_text))
    raw_targets.extend(_INDEX_CODE_PATH.findall(table_text))
    for target in raw_targets:
        destination = _relative_target(root, index, target)
        if destination is None:
            continue
        try:
            targets.append(destination.relative_to(root).as_posix())
        except ValueError as exc:
            raise LaneError("index link escapes repository") from exc
    return tuple(targets)


def _validate_governed_indexes(root: Path, markdown: Sequence[str]) -> None:
    adr_targets = _index_targets(root, "docs/adr/README.md")
    plan_targets = _index_targets(root, "docs/plans/README.md")
    for relative in markdown:
        if _ADR_PATH.fullmatch(relative):
            count = adr_targets.count(relative)
            if count != 1:
                raise LaneError(
                    "{0} has {1} ADR index links; expected 1".format(
                        relative,
                        count,
                    )
                )
        path = PurePosixPath(relative)
        if (
            path.parent == PurePosixPath("docs/plans")
            and path.name != "README.md"
        ):
            count = plan_targets.count(relative)
            if count != 1:
                raise LaneError(
                    "{0} has {1} plan index links; expected 1".format(
                        relative,
                        count,
                    )
                )


def _record_payload(record: ChangeRecord) -> dict:
    return {
        "status": record.status,
        "old_path": record.old_path,
        "new_path": record.new_path,
        "old_mode": record.old_mode,
        "new_mode": record.new_mode,
        "source": record.source,
    }


def require_docs(
    root: Path,
    base: str,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    root = Path(root).resolve()
    try:
        base_oid = _validated_base(root, base)
        records = changed_records(root, base_oid)
        classification = classify_changes(records)
        stdout.write(
            json.dumps(
                {
                    "classification": classification,
                    "records": [_record_payload(record) for record in records],
                },
                sort_keys=True,
            )
            + "\n"
        )
        if classification != "docs":
            stderr.write("verify-docs: changes require the pre-pr lane\n")
            return 2
        _diff_checks(root, base_oid)
        _check_untracked_markdown(root, records)
        markdown = _markdown_paths(root, records)
        _validate_relative_links(root, markdown)
        _validate_governed_indexes(root, markdown)
    except (LaneError, OSError, UnicodeError, ValueError) as exc:
        stderr.write("verify-docs: {0}\n".format(exc))
        return 2
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m engine.tests.verify_lane")
    subparsers = parser.add_subparsers(dest="command", required=True)
    docs = subparsers.add_parser("require-docs")
    source = docs.add_mutually_exclusive_group(required=True)
    source.add_argument("--base")
    source.add_argument("--base-env")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command != "require-docs":
        return 2
    base = arguments.base
    if arguments.base_env is not None:
        if not _ENV_NAME.fullmatch(arguments.base_env):
            sys.stderr.write(
                "verify-docs: --base-env requires an environment variable name\n"
            )
            return 2
        base = os.environ.get(arguments.base_env)
        if base is None:
            sys.stderr.write(
                "verify-docs: {0} is not set\n".format(arguments.base_env)
            )
            return 2
    return require_docs(Path.cwd(), base)


if __name__ == "__main__":
    raise SystemExit(main())
