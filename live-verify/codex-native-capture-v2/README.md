# Controller-bound native Codex capture v2

This successor preserves v1 byte-for-byte in its original directory. It repairs
cross-session contamination of the A03 prompt control. Only A03 is executable;
this source does not qualify startup, other lifecycle events, tools, registration,
protection, or a compatibility profile.

Before the first control, the external controller obtains the exact target native
session id from the supported host interface. In memory it calculates
`HMAC-SHA256(salt, b"session\0" + session_id.encode("utf-8"))`, writes the 32 raw digest
bytes (the result of `.digest()`, never `.hexdigest()` or ASCII hex) to a new
private `capture/session.bin` file (0600), binds its SHA-256 as
`session_binding_sha256` in the private v2 run manifest, and prepopulates the
private equality map with exactly `{binding.hex(): "S1"}`. No raw identifier is
persisted. All three files are fixed before the pre-witness binds the manifest digest.
A missing, empty, mismatched, or unbound session is rejected without allocating a
label or appending an event. The observer still emits only `{}` and exits zero.

The complete native event enters the same observer process only through stdin;
there is no raw-payload replay, transcript read, controller-injected callback,
extra model context, or blocking decision. Timing buckets remain process-local.
The controller must use a process-shared monotonic clock for cross-process spans.

The same target session must deliver exactly one UserPromptSubmit callback in each
of BEFORE, ACTION and AFTER. Counts are never widened. Duplicate callbacks from
the target still fail. The action count is exactly one and the source catalog's
A03 action hash remains bound to the controller witness. Every exported event
has label S1; the export explicitly states `session_scope: CONTROLLER_BOUND`.
The binding file, salt and salted map are private ephemera, removed before offline verifier
execution. An export cannot establish host-wide absence or cross-session coverage.

Preallocate `capture/collector-contention.bin` as exactly one byte `b"0"`, mode
0600, before any callback can run. It remains until cleanup, including through
offline verification. If an observer cannot acquire the collector lock, it writes
and fsyncs the sticky byte `b"1"` before returning the same fail-open host response.
Any recorded contention makes the entire run ineligible for export, even if the
remaining event counts look exact or the witness declares health UNAVAILABLE.
Contention before session classification may conservatively invalidate the run;
it is never silently treated as a successful callback or relaxed count.
Never reset the flag, salvage a contended run, or use its absence as evidence of
coverage. The verifier requires the original private flag inode with value zero
at initial and final checks and reports `collector_contention: NOT_RECORDED`.
This records the collector's flag state, not proof that every possible host hook
invocation was delivered. Stop/disable all observers and prove them terminal
before verification, then recheck the flag before copying a verified export.

Use `/usr/bin/python3 -I -S -B` for the observer and offline verifier. The source
manifest binds these seven files. Retain all v1 descriptor, ownership, permission,
source, witness, same-route, ephemera-absence and forbidden-field checks.
Render the twelve definitions with the pure verifier helper, trust the exact
fixture through supported controls, and enable only UserPromptSubmit for A03.
Record the actual baseline source set; never silently disable other sources or
claim an unchanged baseline after an authorized repair. Any hook errors remain
visible and separate from the observer's own same-route health.

Execution uses the operator's existing standing authorization. Allocation,
trust, process ownership, shutdown, sanitized export, cleanup and normal App PR
review still require verified outcomes. User configuration, credentials and raw
transcripts are never copied. V2 must be reviewed and merged before live use.
