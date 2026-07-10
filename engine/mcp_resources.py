"""Pure, fixed MCP resource registry and guidance renderer.

This module intentionally has no access to environment, filesystem, policy, contracts,
database, or live AWA state.  The caller supplies the advertised in-memory tool descriptions,
which are reused verbatim in the operator guide and inline instructions.
"""

from __future__ import annotations

from typing import Any, Mapping


OPERATOR_GUIDE_URI = "awa://assistant/operator-guide/v1"
OPERATOR_GUIDE_MIME_TYPE = "text/markdown"
_OPERATOR_GUIDE = {
    "uri": OPERATOR_GUIDE_URI,
    "name": "awa-operator-guide-v1",
    "description": "Fixed advisory routing and safety guidance for AWA operators.",
    "mimeType": OPERATOR_GUIDE_MIME_TYPE,
}


def list_resources() -> list[dict[str, str]]:
    """Return the single fixed resource descriptor."""
    return [dict(_OPERATOR_GUIDE)]


def render_guidance(tools: Mapping[str, Mapping[str, Any]]) -> str:
    """Render shared inline/resource guidance from the one tool catalog."""
    lines = [
        (
            "AWA guidance is advisory; kernel protection and cleanup remain authoritative when "
            "the engine is off."
        ),
        (
            "Descriptions/instructions are primary; the guide is host-driven secondary context, "
            "never a routing or safety control."
        ),
        "",
        "## Tool routing",
    ]
    for name, spec in tools.items():
        description = spec.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"tool {name!r} is missing description guidance")
        lines.append(f"- `{name}` — {description.strip()}")
    lines.extend([
        "",
        "## CLI boundary",
        (
            "`dev-worktree.sh`: `status` reports current-repo classification/root/worktree state; "
            "`ensure` creates/selects a Safe Workspace; `doctor` checks policy/worktree health; "
            "`clean` performs bundle-or-refuse removal. Use `awa-engine` for adopt, attest, "
            "apply-back, publish, retire, or recovery. MCP performs none of these actions."
        ),
        "",
        "## Safety interpretation",
        (
            "Guard output is diagnostic, not authorization to run a command or bypass the live "
            "hook. Lease reads check contract fields/hash only; cleanup uses the active-root "
            "heartbeat plus git/content checks. Runtime merges inline policy and referenced-file "
            "modes, then prefers an exact combined key and the first matching glob. `default_mode` "
            "applies only at the final eligibility step when neither matches. Only exact `off` "
            "disables; `on` cannot override safety exclusions. Unreadable/non-regular files force "
            "`on`. Repair/sync coerce invalid values to "
            "`on`; sync can seed `off` only for a missing or invalid file default."
        ),
    ])
    return "\n".join(lines) + "\n"


def render_operator_guide(tools: Mapping[str, Mapping[str, Any]]) -> str:
    """Render the deterministic, bounded operator guide."""
    text = "# AWA operator guide (v1)\n\n" + render_guidance(tools)
    if len(text.split()) > 500:
        raise ValueError("operator guide exceeds 500 words")
    return text


def read_resource(
    uri: str, tools: Mapping[str, Mapping[str, Any]]
) -> dict[str, str] | None:
    """Return the exact fixed resource, or None for an unknown URI."""
    if uri != OPERATOR_GUIDE_URI:
        return None
    return {
        "uri": OPERATOR_GUIDE_URI,
        "mimeType": OPERATOR_GUIDE_MIME_TYPE,
        "text": render_operator_guide(tools),
    }
