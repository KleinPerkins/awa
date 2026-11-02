#!/usr/bin/env python3
"""awa_policy.py — generic, ZERO-LINK kernel policy resolver.

The kernel scripts (dev-worktree.sh, the guard hook, the dashboard emitter) are
host-agnostic: they carry NO org/vendor literals. Every include/exclude glob,
governed root, and detector comes from a machine-local policy file (worktree-policy.yml)
resolved BY ROLE (AWA_POLICY, else the installed kernel default template). This module
is the single kernel-layer implementation of:

  * a tiny stdlib-only YAML subset parser (scalars, `- ` lists, one-deep nested maps),
  * generic repo classification (self-governed-marker + foreign-hook detectors decide
    exclusions GENERICALLY, so a self-governed sibling repo is left alone WITHOUT naming
    it), and
  * governed-root resolution + include-root enumeration for the read-only dashboard.

It deliberately mirrors the engine-layer `engine/policy.py` classifier so the kernel
delivers the safety guarantee with the engine OFF. `engine/tests/test_kernel_policy_parity.py`
asserts the two never drift.

CLI (consumed by the shell kernel):
  awa_policy.py dump --policy P [--governed-root R]
      emit shell-eval-safe assignments (POL_DEFAULT, POL_MANAGED, POL_GOVERNED_ROOTS=(...), ...)
  awa_policy.py classify --policy P [--governed-root R] --toplevel T [--hooks-path H] [--has-origin 0|1]
      print: <class>\t<reason>\t<rel>\t<governed_root>
  awa_policy.py mode-for --policy P --toplevel T [--governed-root R]
      print the resolved matching exact/glob mode for the repo: on|off|"" (no match) |
      "invalid" (a matching entry has a bad value). Additive; does NOT change classify.
  awa_policy.py governed-roots --policy P [--governed-root R]
      print resolved governed roots, one per line
"""

from __future__ import annotations

import fnmatch
import os
import shlex
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path

INCLUDE = "include"
EXCLUDE = "exclude"
ADVISORY = "advisory"
NOT_GIT = "not-git"

# Explicit per-repo mode values (awa-modes/v1). Kept as a tuple so callers can
# distinguish a present-but-invalid mode value from a valid one. ONE fail-safe rule
# governs every read/write path: only `off` disables protection; ANY other value
# (a typo, a removed legacy value, an unknown) resolves to ON/include.
MODE_VALUES = ("on", "off")
HARD_NO_TOUCH_SCHEMA = "awa-hard-no-touch/v1"
HARD_NO_TOUCH_FIELD = "hard_no_touch_paths"
HARD_NO_TOUCH_EXACT_ROOTS = "exact_roots"
HARD_NO_TOUCH_MANAGED_PREFIXES = "managed_namespace_prefixes"
HARD_NO_TOUCH_KINDS = (
    "exact_root",
    "managed_namespace",
    "none",
    "invalid_policy",
    "invalid_candidate",
)
_HARD_NO_TOUCH_KEYS = frozenset(
    {HARD_NO_TOUCH_EXACT_ROOTS, HARD_NO_TOUCH_MANAGED_PREFIXES}
)
_HARD_NO_TOUCH_GLOB_CHARS = frozenset("*?[]")
_HARD_NO_TOUCH_ABSENT = object()


class _HardNoTouchSyntaxError(ValueError):
    pass


def parse_mini_yaml(text: str) -> dict:
    """Parse the small YAML subset worktree-policy.yml uses. Returns nested dict/list.

    Supported: `key: scalar`, inline `key: []`/`key: {}`, `key:` then an indented
    `- item` list, and `key:` then an indented `subkey:` map. Comments (#) and blank
    lines are ignored. (Mirror of engine/policy.py:_parse_mini_yaml — keep in sync.)
    """
    root: dict = {}
    stack: list[dict] = [{"indent": -1, "container": root, "parent": None, "key": None}]

    for raw in text.splitlines():
        line = raw.split(" #", 1)[0] if " #" in raw else raw
        line = line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))

        while len(stack) > 1 and indent <= stack[-1]["indent"]:
            stack.pop()
        top = stack[-1]
        container = top["container"]

        if stripped.startswith("- "):
            item = stripped[2:].strip().strip("'\"")
            if isinstance(container, dict) and container == {} and top["parent"] is not None:
                new_list: list = []
                top["parent"][top["key"]] = new_list
                top["container"] = new_list
                container = new_list
            if isinstance(container, list):
                container.append(item)
            continue

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip("'\"")
            if not isinstance(container, dict):
                continue
            if val in ("[]", "{}"):
                container[key] = [] if val == "[]" else {}
            elif val:
                container[key] = val
            else:
                child: dict = {}
                container[key] = child
                stack.append({"indent": indent, "container": child,
                              "parent": container, "key": key})
    return root


def _modes_from_data(data: dict) -> tuple[dict, str | None]:
    """Extract (modes, default_mode) from one parsed policy/modes document.

    `modes` values are case-normalized; `default_mode` is None when absent so callers
    can distinguish "not specified" from an explicit value during merge.
    """
    modes: dict = {}
    raw = data.get("modes")
    if isinstance(raw, dict):
        for k, v in raw.items():
            modes[str(k)] = str(v).strip().lower()
    dm = data.get("default_mode")
    default_mode = str(dm).strip().lower() if dm is not None else None
    return modes, default_mode


def _read_regular_text(path: str | Path) -> str:
    """Read one regular file without blocking on FIFOs or following symlinks."""
    flags = os.O_RDONLY
    flags |= getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(f"not a regular file: {path}")
        with os.fdopen(fd, "r", encoding="utf-8") as fh:
            fd = -1
            return fh.read()
    finally:
        if fd >= 0:
            os.close(fd)


def _hard_no_touch_yaml_line(raw: str) -> str:
    """Strip a mini-YAML comment while respecting simple quoted path scalars."""
    content_start = len(raw) - len(raw.lstrip())
    quote_starts = {content_start}
    if raw[content_start:].startswith("-"):
        scalar_start = content_start + 1
    else:
        colon = raw.find(":", content_start)
        scalar_start = colon + 1 if colon >= 0 else len(raw)
    while scalar_start < len(raw) and raw[scalar_start].isspace():
        scalar_start += 1
    quote_starts.add(scalar_start)

    quote = None
    escaped = False
    index = 0
    while index < len(raw):
        character = raw[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif quote == "'":
            if character == quote:
                if index + 1 < len(raw) and raw[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif character in ("'", '"') and index in quote_starts:
            quote = character
        elif character == "#" and (index == 0 or raw[index - 1].isspace()):
            return raw[:index].rstrip()
        index += 1
    if quote is not None or escaped:
        raise _HardNoTouchSyntaxError("unbalanced_quote")
    return raw.rstrip()


def _hard_no_touch_scalar(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if value[0] in ("'", '"'):
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            raise _HardNoTouchSyntaxError("unbalanced_quote")
        inner = value[1:-1]
        if quote in inner or (quote == '"' and "\\" in inner):
            raise _HardNoTouchSyntaxError("unsupported_quote_escape")
        return inner
    return value


def _hard_no_touch_reserved_key(raw: str) -> tuple[str, bool]:
    """Return a reserved key plus whether a non-canonical spelling was used."""
    value = raw.strip()
    reserved = (
        HARD_NO_TOUCH_FIELD,
        HARD_NO_TOUCH_EXACT_ROOTS,
        HARD_NO_TOUCH_MANAGED_PREFIXES,
        "version",
    )
    if value in reserved:
        return value, False
    for name in reserved:
        start = 0
        while True:
            index = value.find(name, start)
            if index < 0:
                break
            before = value[index - 1] if index else ""
            after_index = index + len(name)
            after = value[after_index] if after_index < len(value) else ""
            if (
                (not before or not (before.isalnum() or before in "_.-"))
                and (not after or not (after.isalnum() or after in "_.-"))
            ):
                return name, True
            start = index + 1
    return value, False


def _hard_no_touch_value_from_text(text: str) -> tuple[object, object]:
    """Strictly extract only the additive field without changing legacy parsing."""
    if not isinstance(text, str):
        raise _HardNoTouchSyntaxError("policy_not_text")

    lines = text.splitlines()
    found = False
    orphan_child = False
    version: object = _HARD_NO_TOUCH_ABSENT
    version_error = False
    result: object = _HARD_NO_TOUCH_ABSENT
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        candidate = raw.lstrip(" ")
        leading = raw[: len(raw) - len(raw.lstrip())]
        if not leading and candidate.startswith(
            ("'", '"', "?", "!", "&", "*", "{", "[", "%", "\ufeff", "- ")
        ):
            raise _HardNoTouchSyntaxError("unsupported_top_level_syntax")
        key, separator, _ = candidate.partition(":")
        key_name, unsupported_key = _hard_no_touch_reserved_key(key)
        if key_name == "version" and not leading:
            if unsupported_key or not separator or version is not _HARD_NO_TOUCH_ABSENT:
                version_error = True
                index += 1
                continue
            try:
                version_line = _hard_no_touch_yaml_line(raw)
                _, _, version_inline = version_line.partition(":")
                version_inline = version_inline.strip()
                if not version_inline:
                    raise _HardNoTouchSyntaxError("version_missing_value")
                version = _hard_no_touch_scalar(version_inline)
            except _HardNoTouchSyntaxError:
                version_error = True
            index += 1
            continue

        if key_name != HARD_NO_TOUCH_FIELD:
            if candidate.strip() == HARD_NO_TOUCH_FIELD:
                raise _HardNoTouchSyntaxError("field_missing_colon")
            if key_name in _HARD_NO_TOUCH_KEYS and not leading:
                if found:
                    raise _HardNoTouchSyntaxError("orphan_child")
                orphan_child = True
            index += 1
            continue
        if unsupported_key or not separator:
            raise _HardNoTouchSyntaxError("field_missing_colon")
        if leading:
            raise _HardNoTouchSyntaxError("field_not_top_level")
        if found:
            raise _HardNoTouchSyntaxError("duplicate_field")
        if orphan_child or version_error:
            raise _HardNoTouchSyntaxError("orphan_child")
        found = True

        line = _hard_no_touch_yaml_line(raw)
        _, _, inline = line.partition(":")
        inline = inline.strip()
        if inline == "{}":
            result = {}
            index += 1
            lookahead = index
            while lookahead < len(lines):
                following = lines[lookahead]
                following_stripped = following.strip()
                if not following_stripped or following_stripped.startswith("#"):
                    lookahead += 1
                    continue
                if following[:1].isspace():
                    raise _HardNoTouchSyntaxError("inline_map_has_children")
                break
            continue
        if inline:
            result = _hard_no_touch_scalar(inline)
            index += 1
            continue

        value: dict[str, object] = {}
        child_indent = None
        active_list = None
        list_indent = None
        index += 1
        while index < len(lines):
            child_raw = lines[index]
            child_stripped = child_raw.strip()
            if not child_stripped or child_stripped.startswith("#"):
                index += 1
                continue
            leading = child_raw[: len(child_raw) - len(child_raw.lstrip())]
            if "\t" in leading:
                raise _HardNoTouchSyntaxError("tab_indentation")
            indent = len(child_raw) - len(child_raw.lstrip(" "))
            if indent == 0:
                break

            child_line = _hard_no_touch_yaml_line(child_raw)
            child_content = child_line.strip()
            if child_indent is None:
                child_indent = indent
            if indent == child_indent:
                if child_content.startswith("-"):
                    raise _HardNoTouchSyntaxError("list_without_key")
                child_key, child_separator, child_inline = child_content.partition(":")
                child_key = child_key.strip()
                if not child_separator or not child_key:
                    raise _HardNoTouchSyntaxError("malformed_child")
                if child_key in value:
                    raise _HardNoTouchSyntaxError("duplicate_child")
                child_inline = child_inline.strip()
                if child_inline == "[]":
                    value[child_key] = []
                    active_list = None
                    list_indent = None
                elif not child_inline:
                    value[child_key] = []
                    active_list = child_key
                    list_indent = None
                else:
                    value[child_key] = _hard_no_touch_scalar(child_inline)
                    active_list = None
                    list_indent = None
            elif indent > child_indent:
                if active_list is None:
                    raise _HardNoTouchSyntaxError("unexpected_nested_value")
                if list_indent is None:
                    list_indent = indent
                if indent != list_indent or not child_content.startswith("-"):
                    raise _HardNoTouchSyntaxError("malformed_list")
                item = child_content[1:]
                if item and not item.startswith(" "):
                    raise _HardNoTouchSyntaxError("malformed_list")
                assert isinstance(value[active_list], list)
                value[active_list].append(_hard_no_touch_scalar(item))
            else:
                raise _HardNoTouchSyntaxError("inconsistent_indentation")
            index += 1
        result = value
    if found and version_error:
        raise _HardNoTouchSyntaxError("malformed_version")
    return result, version


def _collapse_leading_separators(value: str) -> str:
    """Keep one POSIX root separator so lexical equality is implementation-stable."""
    return os.sep + value.lstrip(os.sep) if value.startswith(os.sep) else value


def _trusted_home(home: str | Path | None = None) -> str | None:
    """Return one lexical absolute HOME without user-database or filesystem access."""
    raw = os.environ.get("HOME", "") if home is None else os.fspath(home)
    if (
        not isinstance(raw, str)
        or not raw
        or "\0" in raw
        or "\n" in raw
        or "\r" in raw
        or raw.startswith("~")
        or not os.path.isabs(raw)
    ):
        return None
    normalized = _collapse_leading_separators(os.path.normpath(raw))
    return normalized if os.path.isabs(normalized) else None


def _lexical_hard_no_touch_path(
    value: object,
    *,
    home: str | None,
    policy_entry: bool,
) -> str | None:
    """Normalize one path using strings only; never inspect the target."""
    if (
        not isinstance(value, str)
        or not value
        or "\0" in value
        or "\n" in value
        or "\r" in value
        or (policy_entry and any(character in value for character in _HARD_NO_TOUCH_GLOB_CHARS))
    ):
        return None
    if value == "~":
        if home is None:
            return None
        expanded = home
    elif value.startswith("~/"):
        if home is None:
            return None
        expanded = home + os.sep + value[2:]
    elif value.startswith("~"):
        return None
    else:
        expanded = value
    if not os.path.isabs(expanded):
        return None
    normalized = _collapse_leading_separators(os.path.normpath(expanded))
    if not normalized or normalized == "." or not os.path.isabs(normalized):
        return None
    return normalized


def _component_root_matches(root: str, candidate: str) -> bool:
    if root == os.sep:
        return candidate.startswith(os.sep)
    return candidate == root or candidate.startswith(root + os.sep)


@dataclass(frozen=True)
class HardNoTouchDecision:
    """Closed pre-access classification; configured roots are never returned."""

    matched: bool
    kind: str
    policy_valid: bool

    def __post_init__(self) -> None:
        if self.kind not in HARD_NO_TOUCH_KINDS:
            raise ValueError("invalid hard-no-touch decision kind")
        expected = {
            "exact_root": (True, True),
            "managed_namespace": (True, True),
            "none": (False, True),
            "invalid_policy": (True, False),
            "invalid_candidate": (True, True),
        }
        if (
            type(self.matched) is not bool
            or type(self.policy_valid) is not bool
            or (self.matched, self.policy_valid) != expected[self.kind]
        ):
            raise ValueError("inconsistent hard-no-touch decision")


@dataclass(frozen=True)
class HardNoTouchMatcher:
    """Immutable lexical matcher safe to call before target/repository access."""

    exact_roots: tuple[str, ...] = ()
    managed_namespace_prefixes: tuple[str, ...] = ()
    home: str | None = None
    valid: bool = True
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.valid) is not bool:
            raise ValueError("hard-no-touch validity must be boolean")
        normalized_home = None if self.home is None else _trusted_home(self.home)
        if self.home is not None and normalized_home is None:
            raise ValueError("hard-no-touch home must be lexical and absolute")
        if isinstance(self.errors, (str, bytes)):
            raise ValueError("hard-no-touch errors must be an immutable sequence")
        try:
            errors = tuple(self.errors)
        except TypeError as exc:
            raise ValueError("hard-no-touch errors must be an immutable sequence") from exc
        if any(not isinstance(error, str) or not error for error in errors):
            raise ValueError("hard-no-touch errors must be non-empty strings")

        normalized_fields = []
        for raw_values in (self.exact_roots, self.managed_namespace_prefixes):
            if isinstance(raw_values, (str, bytes)):
                raise ValueError("hard-no-touch roots must be path sequences")
            try:
                values = tuple(raw_values)
            except TypeError as exc:
                raise ValueError("hard-no-touch roots must be path sequences") from exc
            normalized_values = []
            for value in values:
                normalized = _lexical_hard_no_touch_path(
                    value,
                    home=normalized_home,
                    policy_entry=True,
                )
                if normalized is None or normalized != value:
                    raise ValueError("hard-no-touch matcher roots must be normalized")
                if normalized not in normalized_values:
                    normalized_values.append(normalized)
            normalized_fields.append(tuple(normalized_values))

        if not self.valid and any(normalized_fields):
            raise ValueError("invalid hard-no-touch matcher cannot carry roots")
        if self.valid and errors:
            raise ValueError("valid hard-no-touch matcher cannot carry errors")
        if not self.valid and not errors:
            errors = ("invalid_policy",)
        object.__setattr__(self, "home", normalized_home)
        object.__setattr__(self, "exact_roots", normalized_fields[0])
        object.__setattr__(self, "managed_namespace_prefixes", normalized_fields[1])
        object.__setattr__(self, "errors", tuple(sorted(set(errors))))

    @classmethod
    def empty(cls, *, home: str | Path | None = None) -> "HardNoTouchMatcher":
        return cls(home=_trusted_home(home))

    @classmethod
    def invalid(
        cls,
        *errors: str,
        home: str | Path | None = None,
    ) -> "HardNoTouchMatcher":
        normalized_errors = tuple(sorted(set(errors or ("invalid_policy",))))
        return cls(home=_trusted_home(home), valid=False, errors=normalized_errors)

    def classify(self, candidate: object) -> HardNoTouchDecision:
        if not self.valid:
            return HardNoTouchDecision(True, "invalid_policy", False)
        normalized = _lexical_hard_no_touch_path(
            candidate,
            home=self.home,
            policy_entry=False,
        )
        if normalized is None:
            return HardNoTouchDecision(True, "invalid_candidate", True)
        for root in self.exact_roots:
            if _component_root_matches(root, normalized):
                return HardNoTouchDecision(True, "exact_root", True)
        for root in self.managed_namespace_prefixes:
            if _component_root_matches(root, normalized):
                return HardNoTouchDecision(True, "managed_namespace", True)
        return HardNoTouchDecision(False, "none", True)

    def matches(self, candidate: object) -> bool:
        return self.classify(candidate).matched

    def to_policy_value(self) -> dict[str, list[str]]:
        """Closed normalized projection used for parity and semantic round trips."""
        if not self.valid:
            raise ValueError("invalid hard-no-touch matcher has no policy projection")
        return {
            HARD_NO_TOUCH_EXACT_ROOTS: list(self.exact_roots),
            HARD_NO_TOUCH_MANAGED_PREFIXES: list(self.managed_namespace_prefixes),
        }


def hard_no_touch_matcher_from_data(
    data: object,
    *,
    home: str | Path | None = None,
) -> HardNoTouchMatcher:
    """Validate the optional v1 field; any malformed value produces a deny-all matcher."""
    normalized_home = _trusted_home(home)
    if not isinstance(data, dict):
        return HardNoTouchMatcher.invalid("policy_not_map", home=home)
    if HARD_NO_TOUCH_FIELD not in data:
        return HardNoTouchMatcher(home=normalized_home)
    if str(data.get("version", 1)).strip() != "1":
        return HardNoTouchMatcher.invalid("unsupported_version", home=home)
    raw = data.get(HARD_NO_TOUCH_FIELD)
    if not isinstance(raw, dict):
        return HardNoTouchMatcher.invalid("field_not_map", home=home)
    if set(raw) - _HARD_NO_TOUCH_KEYS:
        return HardNoTouchMatcher.invalid("unknown_key", home=home)

    errors: list[str] = []
    normalized: dict[str, list[str]] = {
        HARD_NO_TOUCH_EXACT_ROOTS: [],
        HARD_NO_TOUCH_MANAGED_PREFIXES: [],
    }
    for key in (HARD_NO_TOUCH_EXACT_ROOTS, HARD_NO_TOUCH_MANAGED_PREFIXES):
        values = raw.get(key, [])
        if not isinstance(values, list):
            errors.append(f"{key}_not_list")
            continue
        for item in values:
            path = _lexical_hard_no_touch_path(
                item,
                home=normalized_home,
                policy_entry=True,
            )
            if path is None:
                errors.append(f"{key}_invalid_entry")
            elif path not in normalized[key]:
                normalized[key].append(path)
    if errors:
        return HardNoTouchMatcher.invalid(*errors, home=home)
    return HardNoTouchMatcher(
        exact_roots=tuple(normalized[HARD_NO_TOUCH_EXACT_ROOTS]),
        managed_namespace_prefixes=tuple(
            normalized[HARD_NO_TOUCH_MANAGED_PREFIXES]
        ),
        home=normalized_home,
    )


def hard_no_touch_matcher_from_text(
    text: str,
    *,
    home: str | Path | None = None,
) -> HardNoTouchMatcher:
    """Strictly ingest the new field while legacy policy keys keep their parser."""
    try:
        value, version = _hard_no_touch_value_from_text(text)
    except (TypeError, ValueError):
        return HardNoTouchMatcher.invalid("field_syntax", home=home)
    strict_data: dict[str, object] = {
        "version": 1 if version is _HARD_NO_TOUCH_ABSENT else version
    }
    if value is not _HARD_NO_TOUCH_ABSENT:
        strict_data[HARD_NO_TOUCH_FIELD] = value
    return hard_no_touch_matcher_from_data(strict_data, home=home)


def load_hard_no_touch_matcher(
    path: str | Path,
    *,
    home: str | Path | None = None,
) -> HardNoTouchMatcher:
    """Read only the trusted policy file; unreadable/malformed policy fails closed."""
    try:
        return hard_no_touch_matcher_from_text(
            _read_regular_text(path),
            home=home,
        )
    except (OSError, UnicodeError, ValueError, TypeError):
        return HardNoTouchMatcher.invalid("policy_unreadable", home=home)


def _resolve_modes(data: dict, policy_path: str | Path) -> tuple[dict, str]:
    """Resolve the explicit modes map + default_mode from inline policy values and an
    optional `modes_file:` pointer.

    The pointer is resolved relative to the policy file's directory (~ and absolute paths
    honored). A readable regular referenced file (schema awa-modes/v1) is MERGED over the
    inline values, the referenced file winning on key collision. A missing file leaves the
    inline settings in effect. A present but unreadable/non-regular file forces every inline
    mode and the default to protected ``on``: its unknown contents must never make a primary
    checkout less protected.
    """
    modes, inline_default = _modes_from_data(data)
    default_mode = inline_default or "on"

    modes_file = data.get("modes_file")
    if modes_file:
        mf = os.path.expanduser(str(modes_file))
        if not os.path.isabs(mf):
            base = Path(policy_path).resolve().parent
            mf = str(base / mf)
        try:
            text = _read_regular_text(mf)
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError):
            # The referenced file may contain protective overrides for inline `off` values.
            # When its contents are unknowable, fail closed instead of trusting lower-priority
            # inline settings that could weaken protection.
            return ({key: "on" for key in modes}, "on")
        else:
            fdata = parse_mini_yaml(text)
            fmodes, fdefault = _modes_from_data(fdata)
            modes.update(fmodes)  # referenced file wins on key collision
            if fdefault:
                default_mode = fdefault
    return modes, default_mode


@dataclass
class PolicyConfig:
    version: int = 1
    governed_roots: list[str] = field(default_factory=list)
    managed_location: str = "~/.cursor/worktrees"
    default: str = INCLUDE
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    governed_markers: list[str] = field(default_factory=list)
    foreign_hook_frameworks: list[str] = field(default_factory=list)
    read_only_paths: list[str] = field(default_factory=list)
    overrides_include: list[str] = field(default_factory=list)
    overrides_exclude: list[str] = field(default_factory=list)
    hard_no_touch_paths: HardNoTouchMatcher = field(
        default_factory=HardNoTouchMatcher.empty
    )
    # Explicit per-repo modes (rel-glob -> on|off). Empty by default so a host
    # that configures nothing behaves byte-for-byte as before.
    modes: dict = field(default_factory=dict)
    # Governs eligible repos with no explicit mode. Default "on" reproduces today's
    # derived classification byte-for-byte.
    default_mode: str = "on"

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        home: str | Path | None = None,
    ) -> "PolicyConfig":
        p = Path(path)
        if not p.exists():
            return cls(
                hard_no_touch_paths=HardNoTouchMatcher.invalid(
                    "policy_unreadable",
                    home=home,
                )
            )
        text = p.read_text(encoding="utf-8")
        data = parse_mini_yaml(text)
        return cls._from_data(
            data,
            path,
            home=home,
            hard_no_touch_paths=hard_no_touch_matcher_from_text(text, home=home),
        )

    @classmethod
    def _from_data(
        cls,
        data: dict,
        path: str | Path,
        *,
        home: str | Path | None = None,
        hard_no_touch_paths: HardNoTouchMatcher | None = None,
    ) -> "PolicyConfig":
        detectors = data.get("detectors", {}) if isinstance(data.get("detectors"), dict) else {}
        overrides = data.get("overrides", {}) if isinstance(data.get("overrides"), dict) else {}
        modes, default_mode = _resolve_modes(data, path)
        return cls(
            version=int(str(data.get("version", 1)) or 1),
            governed_roots=list(data.get("governed_roots", []) or []),
            managed_location=str(data.get("managed_location", "~/.cursor/worktrees")),
            default=str(data.get("default", INCLUDE)),
            include=list(data.get("include", []) or []),
            exclude=list(data.get("exclude", []) or []),
            governed_markers=list(detectors.get("governed_markers", []) or []),
            foreign_hook_frameworks=list(detectors.get("foreign_hook_frameworks", []) or []),
            read_only_paths=list(detectors.get("read_only_paths", []) or []),
            overrides_include=list(overrides.get("include", []) or []),
            overrides_exclude=list(overrides.get("exclude", []) or []),
            hard_no_touch_paths=(
                hard_no_touch_paths
                if hard_no_touch_paths is not None
                else hard_no_touch_matcher_from_data(data, home=home)
            ),
            modes=modes,
            default_mode=default_mode,
        )


def hard_no_touch_decision(
    path: object,
    cfg: PolicyConfig,
) -> HardNoTouchDecision:
    """Classify before repository access; an invalid config object fails closed."""
    if not isinstance(cfg, PolicyConfig):
        return HardNoTouchDecision(True, "invalid_policy", False)
    return cfg.hard_no_touch_paths.classify(path)


def is_hard_no_touch(path: object, cfg: PolicyConfig) -> bool:
    return hard_no_touch_decision(path, cfg).matched


def _match_any(rel: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if rel == pat or fnmatch.fnmatch(rel, pat):
            return True
    return False


def _is_glob(pat: str) -> bool:
    """A key is a glob if it carries an fnmatch metacharacter (`*`, `?`, `[`)."""
    return any(c in pat for c in "*?[")


def mode_for(rel: str, cfg: PolicyConfig) -> str:
    """Return the matching inline/file mode for `rel`, preferring EXACT keys over globs.

    Exact (non-glob) keys are matched first (by equality), then glob keys in insertion
    order — so an exact key wins even when a matching glob precedes it in the file. The
    returned value is case-normalized and MAY be invalid (present-but-not-in MODE_VALUES);
    callers validate. Returns "" when no entry matches.
    """
    for pat, val in cfg.modes.items():
        if not _is_glob(pat) and rel == pat:
            return str(val).strip().lower()
    for pat, val in cfg.modes.items():
        if _is_glob(pat) and fnmatch.fnmatch(rel, pat):
            return str(val).strip().lower()
    return ""


def has_governed_marker(toplevel: str, markers: list[str]) -> bool:
    for marker in markers:
        if (Path(toplevel) / marker).exists():
            return True
    return False


def _eligible(reason_on: str, cfg: PolicyConfig) -> tuple[str, str]:
    """Map an eligible (would-be-include) repo through default_mode.

    One fail-safe rule: only an exact `off` default excludes; ANY other default_mode
    (`on`, a typo, a removed legacy value) protects the repo -> INCLUDE. `policy-check`
    WARNs on a non-canonical default_mode; it never silently disables protection.
    """
    if cfg.default_mode == "off":
        return (EXCLUDE, "policy default_mode: off")
    return (INCLUDE, reason_on)


def classify(
    rel: str,
    toplevel: str | None,
    cfg: PolicyConfig,
    *,
    hooks_path: str = "",
    has_origin: bool = True,
    is_root: bool = False,
    is_standalone: bool = False,
) -> tuple[str, str]:
    """Generic classification. Order (first match wins) mirrors engine/policy.py.

    not-git -> explicit OFF -> legacy overrides -> SAFETY excludes (umbrella /
    governed-marker / foreign-hook / read-only) -> any explicit non-off mode (ON / typo /
    legacy) -> exclude globs -> no-origin advisory -> explicit include-glob eligibility ->
    standalone advisory (outside every governed root) -> policy-default eligibility. One
    fail-safe rule: only `off` disables; ANY other explicit value -> INCLUDE. Safety-excludes
    beat explicit ON; OFF beats all; an explicit include-glob match beats standalone.
    """
    if toplevel is None:
        return (NOT_GIT, "not a git repository")

    m = mode_for(rel, cfg)

    if m == "off":
        return (EXCLUDE, "explicit mode: off")

    if _match_any(rel, cfg.overrides_exclude):
        return (EXCLUDE, "operator override: exclude")
    if _match_any(rel, cfg.overrides_include):
        return (INCLUDE, "operator override: include")

    if is_root or rel == ".":
        return (EXCLUDE, "umbrella root: worktree omits nested repos")

    if has_governed_marker(toplevel, cfg.governed_markers):
        return (EXCLUDE, "self-governed repo (own governance marker; generic exclude)")

    if hooks_path:
        for fw in cfg.foreign_hook_frameworks:
            if fw in hooks_path:
                return (EXCLUDE, f"foreign hook framework: {fw}")

    if _match_any(rel, cfg.read_only_paths):
        return (EXCLUDE, "read-only/reference path")

    # Fail-safe: any explicit mode value that survived the early `off` check protects the
    # repo. `on`, a typo, and a removed legacy value all resolve to INCLUDE here.
    if m:
        return (INCLUDE, "explicit mode: on")

    if _match_any(rel, cfg.exclude):
        return (EXCLUDE, "excluded by workspace policy")

    if not has_origin:
        return (ADVISORY, "no origin remote")

    if _match_any(rel, cfg.include):
        return _eligible("included by workspace policy", cfg)

    if is_standalone:
        return (ADVISORY, "standalone repo (outside every governed root)")

    if cfg.default == INCLUDE:
        return _eligible("policy default: include", cfg)
    return (ADVISORY, "outside governed include patterns")


def _norm(path: str) -> str:
    return os.path.realpath(os.path.expanduser(path))


def resolve_governed_root(toplevel: str, env_root: str, cfg: PolicyConfig) -> str:
    """Pick the governed root that contains `toplevel`: env override first, then policy.

    Returns "" when no governed root contains the repo — the STANDALONE case, where the
    repo is its own context (never an umbrella), so a freshly cloned repo is eligible.
    """
    top = _norm(toplevel)
    candidates: list[str] = []
    if env_root:
        candidates.append(env_root)
    candidates.extend(cfg.governed_roots)
    for cand in candidates:
        gr = _norm(cand)
        if top == gr or top.startswith(gr + os.sep):
            return gr
    return ""


def rel_to_root(toplevel: str, governed_root: str) -> str:
    top = _norm(toplevel)
    if not governed_root:
        return os.path.basename(top.rstrip(os.sep)) or top
    gr = _norm(governed_root)
    if top == gr:
        return "."
    if top.startswith(gr + os.sep):
        return top[len(gr) + 1:]
    return top


def include_roots(cfg: PolicyConfig) -> list[str]:
    """First path segment of each include glob (enumeration hints for the dashboard).

    e.g. include ['personal/*', 'a/b/*'] -> ['personal', 'a/b']. Absent include globs,
    the dashboard falls back to a shallow scan of the governed root itself.
    """
    roots: list[str] = []
    for pat in cfg.include:
        seg = pat.split("*", 1)[0].rstrip("/")
        if seg and seg not in roots:
            roots.append(seg)
    return roots


# --------------------------------------------------------------------------- CLI

def _cli_dump(cfg: PolicyConfig) -> int:
    def arr(name: str, items: list[str]) -> None:
        print("%s=(%s)" % (name, " ".join(shlex.quote(str(x)) for x in items)))

    print("POL_DEFAULT=%s" % shlex.quote(str(cfg.default)))
    print("POL_MANAGED=%s" % shlex.quote(os.path.expanduser(str(cfg.managed_location))))
    arr("POL_GOVERNED_ROOTS", [os.path.expanduser(x) for x in cfg.governed_roots])
    arr("POL_INCLUDE", cfg.include)
    arr("POL_EXCLUDE", cfg.exclude)
    arr("POL_GOV_MARKERS", cfg.governed_markers)
    arr("POL_FOREIGN", cfg.foreign_hook_frameworks)
    arr("POL_READONLY", cfg.read_only_paths)
    arr("POL_OVR_INC", cfg.overrides_include)
    arr("POL_OVR_EXC", cfg.overrides_exclude)
    return 0


def _opt(argv: list[str], name: str, default: str = "") -> str:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: awa_policy.py {dump|classify|mode-for|governed-roots} --policy P [...]", file=sys.stderr)
        return 2
    cmd = argv[0]
    rest = argv[1:]
    policy = _opt(rest, "--policy")
    env_root = _opt(rest, "--governed-root")
    cfg = PolicyConfig.load(policy) if policy else PolicyConfig()

    if cmd == "dump":
        return _cli_dump(cfg)

    if cmd == "governed-roots":
        roots = ([_norm(env_root)] if env_root else []) + [_norm(r) for r in cfg.governed_roots]
        seen: set[str] = set()
        for r in roots:
            if r and r not in seen:
                seen.add(r)
                print(r)
        return 0

    if cmd == "classify":
        toplevel = _opt(rest, "--toplevel")
        if not toplevel:
            print("classify requires --toplevel", file=sys.stderr)
            return 2
        hooks_path = _opt(rest, "--hooks-path")
        has_origin = _opt(rest, "--has-origin", "1") != "0"
        gr = resolve_governed_root(toplevel, env_root, cfg)
        rel = rel_to_root(toplevel, gr)
        cls, reason = classify(
            rel, toplevel, cfg,
            hooks_path=hooks_path, has_origin=has_origin, is_root=(rel == "."),
            is_standalone=(gr == ""),
        )
        print("\t".join([cls, reason, rel, gr]))
        return 0

    if cmd == "mode-for":
        toplevel = _opt(rest, "--toplevel")
        if not toplevel:
            print("mode-for requires --toplevel", file=sys.stderr)
            return 2
        gr = resolve_governed_root(toplevel, env_root, cfg)
        rel = rel_to_root(toplevel, gr)
        m = mode_for(rel, cfg)
        if m == "":
            print("")
        elif m in MODE_VALUES:
            print(m)
        else:
            print("invalid")
        return 0

    print(f"awa_policy.py: unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
