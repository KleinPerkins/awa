# AWA MCP guidance live evidence — 2026-07-09

## Verdict

**RETAIN `awa://assistant/operator-guide/v1`.** The resource added no routing coverage beyond the
inline instructions, but a real Cursor Desktop explicit on-demand resource fetch returned the
bounded `text/markdown` guide. That read alone is the proven utility satisfying the plan's
alternative retention criterion; descriptor discovery is supporting evidence, not model routing.

The strict live-metadata coverage score improved from baseline **0/8** to inline-only **8/8**;
inline-plus-resource remained **8/8**. This is a route-plus-safety-caveat metadata score, not a
model-output score.

## Installed baseline

- Cursor Desktop MCP server: `user-awa`, ready, nine AWA tools plus Cursor's `mcp_auth` helper.
- Installed pointer: version `1.0.0`, commit
  `a2b677325d8349368a150c16548ee4e01c772c87`, installed
  `2026-07-09T21:36:20Z`.
- Runtime/config: `~/.local/share/awa/current`, `~/.config/awa/env`, and `~/.cursor/mcp.json`.
- Baseline `FetchMcpResource(user-awa, awa://assistant/operator-guide/v1)` returned
  `MCP resource not found`.
- Baseline exposed no `initialize.instructions`; its tool descriptions had the previously recorded
  health, diagnostic-authority, cleanup-authority, fallback, and fail-safe normalization gaps.

## Controlled real-Cursor states

Candidate installs were created under one throwaway `/tmp/awa-mcp-live.*` root with isolated
`HOME`/XDG state. The inline-only installed copy removed only the resource capability and
list/read/template dispatch; it retained the candidate tool descriptions and
`initialize.instructions`. The candidate worktree was not changed for this state.

Representative setup:

```sh
TMP="$(mktemp -d /tmp/awa-mcp-live.XXXXXX)"
env HOME="$TMP/inline-home" XDG_DATA_HOME="$TMP/inline-home/.local/share" \
  XDG_CONFIG_HOME="$TMP/inline-home/.config" \
  XDG_STATE_HOME="$TMP/inline-home/.local/state" ./install.sh
env HOME="$TMP/resource-home" XDG_DATA_HOME="$TMP/resource-home/.local/share" \
  XDG_CONFIG_HOME="$TMP/resource-home/.config" \
  XDG_STATE_HOME="$TMP/resource-home/.local/state" ./install.sh
```

Three temporary, uniquely named entries were added to the real Cursor MCP config, pointing to the
installed baseline, isolated inline-only runtime, and isolated resource runtime. Cursor Desktop
then started three fresh processes and reported all three ready:

```text
GetMcpTools(pattern="awa-live")
user-awa-live-baseline  ready; no server instructions; baseline descriptions
user-awa-live-inline    ready; candidate instructions + candidate descriptions
user-awa-live-resource  ready; candidate instructions + candidate descriptions
```

Cursor's generated MCP catalog contained
`user-awa-live-resource/resources/awa-operator-guide-v1.json` with the exact URI, name,
description, and `text/markdown` MIME type. Neither baseline nor inline-only had a resource entry.

Exact on-demand reads:

```text
FetchMcpResource(user-awa-live-baseline, awa://assistant/operator-guide/v1)
  -> MCP resource not found
FetchMcpResource(user-awa-live-inline, awa://assistant/operator-guide/v1)
  -> MCP resource not found
FetchMcpResource(user-awa-live-resource, awa://assistant/operator-guide/v1)
  -> Resource: awa://assistant/operator-guide/v1 (text/markdown)
```

The successful body was the fixed `# AWA operator guide (v1)` document and included every
candidate tool description, the CLI boundary, diagnostic/cleanup caveats, exact/glob/default mode
resolution, and fail-safe repair/sync behavior. No live state, host path, contract, or secret was
present.

## Named-scenario results

The rubric required both the correct route and its safety interpretation in the metadata Cursor
actually discovered.

- Health: baseline implied `awa_status`; inline/resource route full health to CLI `doctor` and
  reserve `awa_status` for engine bookkeeping.
- Command diagnosis: baseline described an authoritative decision; inline/resource route to
  `awa_guard_shell` and state that the result is diagnostic and the live hook governs.
- Lease/cleanup: baseline exposed lease validation without a cleanup boundary; inline/resource use
  `awa_lease_read` only as evidence and route cleanup to CLI `clean`.
- Restore-default mode: baseline omitted fallback effects; inline/resource route the exact-key
  mutation to `awa_mode_remove` and warn that a matching glob can re-emerge before `default_mode`.
- Repair legacy settings: baseline incorrectly said invalid values are dropped; inline/resource
  route to `awa_mode_repair`, normalize legacy/invalid values to protected `on`, drop unsafe keys,
  and do not scan repos.
- Ensure: baseline had no route; inline/resource route lifecycle adoption/creation to CLI `ensure`.
- Doctor: baseline had no route; inline/resource route full health to CLI `doctor`.
- Clean: baseline had no safe route; inline/resource route cleanup to CLI `clean` and deny any
  inference that lease or guard output authorizes cleanup.

The resource did not improve this 8/8 inline score because it intentionally repeats the inline
guidance. Its retained value is the separately proven, explicit on-demand operator document. No
model-routing benefit was proven.

## Limitation

An independent Cursor Agent CLI prompt-output matrix could not be scored. Both the installed
`cursor-agent` (`2026.02.27-e7d2ef6`) and Cursor Desktop's bundled
`2026.07.09-a3815c0` binary returned:

```text
Error: Authentication required. Please run 'agent login' first, or set CURSOR_API_KEY environment variable.
```

No API key was present, no model output was substituted, and no simulated model evidence is
claimed. The Desktop discovery/resource path above was available, live, and sufficient for the
resource's explicit-utility retention criterion.

## Verification

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  engine.tests.test_mcp engine.tests.test_egress_surfaces
  -> Ran 36 tests in 2.576s; OK

make verify-install
  -> installed MCP initialize/list/read OK
  -> verify-install: OK
```

The candidate's full `make verify && make verify-install` run also completed before this gate with
380 tests passing, `verify: OK`, and `verify-install: OK`.

## Restoration proof

The original runtime directory was held by rename during one unsuccessful restart probe and moved
back unchanged. The temporary Cursor MCP config was likewise held by rename and restored. Before
and after values matched:

```text
runtime directory inode                       321931269
current/engine/mcp_server.py SHA-256          d0e0d1539d19d7e98fd7b18b0de796a7b2eb637d0fa7d6bdee8c78dbef359e5a
release-pointer.json SHA-256                  50bacb205bceee8b85c11adccdcf535431f86ba3d0f9969e4e356bca0bfa7ea4
~/.config/awa/env SHA-256                     45944777ece6fa52bd2712f95e3f7e8c872722dbe28a44427decf0c372b048ba
~/.cursor/mcp.json SHA-256                    5c470c66f0ab5c4cc8ace8b39294817afece5755e9ae71551daeaef925134630
```

After restoration, `GetMcpTools(pattern="awa-live")` returned no matches, the real `user-awa`
server was ready with baseline descriptions, its guide fetch again returned `resource not found`,
Cursor removed the temporary generated MCP catalogs, and the throwaway root was deleted
(`TEMP_CLEANUP_OK`). No plan, GCB, repo outside this evidence file, release, tag, commit, or push
was changed.
