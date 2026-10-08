# Native Entry Durable Registration

- **Version:** v14
- **Status:** ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO
- **Date:** 2026-10-07
- **Supersedes if accepted:** accepted, frozen
  [`native-entry-durable-registration-v13.md`](native-entry-durable-registration-v13.md),
  preserved byte-identically at SHA-256
  `bb9fb7baf6e9bace5a0e03364f01ac99dfe286b3bdc95b36249ed2a4421b1811`.
- **Inherited evidence:** accepted, frozen
  [`native-entry-durable-registration-v12.md`](native-entry-durable-registration-v12.md)
  at SHA-256
  `ddb659b8a700ddc7fd265bb380497918550821184ebfc2e4c427222ac4e5285b`.
- **Repository / delivery:** `KleinPerkins/awa`; branch
  `impl/native-entry-durable-registration-v7-runtime-bootstrap`; Draft PR
  [#183](https://github.com/KleinPerkins/awa/pull/183).

> **Governance stop:** authoring V14 permits only this DRAFT file and its one
> DRAFT README row. It does not review, accept or deliver V14; continue
> implementation; edit V13, V12, code, tests, contracts, source lock or
> evidence; stage, commit, push or mutate PR state; replay Gate 5; qualify,
> ready or merge; or release, install, activate, roll out or run actual R0.

---

## 1. Purpose and precedence

Accepted V13 requires implementation preflight to revalidate the retained
V12 Gate 5 root identity while also forbidding recreation, replacement or
reuse. The recorded OS-temporary root is now absent, so that filesystem
precondition cannot be satisfied as written.

V14 makes one evidence-policy correction: after contemporaneous receipt
verification, continued liveness of that temporary root is nonbinding.
Preflight revalidates the durable receipt records and Git identities instead.
This is not an architecture or implementation change.

Drafting V14 does not supersede V13. Unless and until V14 is independently
reviewed and accepted, V13 remains controlling and frozen byte-identically.
If V14 is accepted, it supersedes V13 only by this stated evidence-policy
correction and otherwise incorporates V13 exactly.

The current instruction to `continue with implementation` cannot override
the accepted V13 contradiction and authorizes no implementation. Work may
continue only after V14 is reviewed, accepted and separately delivered, then
only under a fresh implementation decision.

---

## 2. Authoring preflight

The 2026-10-07 authoring preflight reproduced:

```text
branch                    impl/native-entry-durable-registration-v7-runtime-bootstrap
HEAD / local / remote /
PR head                   43fb95fc51f389ccfafa182b1920ef3a18de1a0b
HEAD tree                 dbd22ea014fb12e4d5a0f1b5bf5a74ecd43117e7
HEAD parent               ccfab428fff50703299b98fc2f7b308eb1e85385
PR #183                   OPEN, Draft, auto-merge unarmed
PR comparison base        03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d
local / GitHub merge base 03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d
live main observed        f8c4714e3817c86c012f067e2fc869f8b5775be7
worktree / staging        clean / empty
README                    82 lines / 11430 bytes /
                          27b03e3cbcd568cd2b6b36019f713207845e5d86834096ac67faccf967d9c068
V13                       643 lines / 31940 bytes /
                          bb9fb7baf6e9bace5a0e03364f01ac99dfe286b3bdc95b36249ed2a4421b1811
V12                       743 lines / 43271 bytes /
                          ddb659b8a700ddc7fd265bb380497918550821184ebfc2e4c427222ac4e5285b
V14 file / index row      absent / absent
retained root             absent
```

Live main is a moving observation. Its advancement is not implementation
drift while the comparison base and merge base remain the bound OID above.

---

## 3. Historical Gate 5 evidence

The exact recorded root was:

```text
/var/folders/_q/4vp8ssd11zbg_jclqgkgyqr00000gq/T//awa-v12-gate5.tTAZyP
```

The frozen V13 record binds these historical V12 Gate 5 receipts
(`lines / bytes / SHA-256`):

```text
authority receipt  70 / 11680 / 10149224cfd384773557d6afc8057ba7c83f0a11d24ec1d7dad3042809d9a10f
root.txt receipt     1 /    71 / 48613fd93f47d0218ba7699074c67520365b8e90303351a7891f2300b778ed47
command receipts    10 /  2741 / 9caa3adb668a5b9433744bedd441dc6d2fc6ad751a15eebb5f6c9b5ccd63e14f
```

The same record binds a clean retained clone at head
`ccfab428fff50703299b98fc2f7b308eb1e85385`, tree
`6d8de830842e6f1359e0f7a5bacd662471f71ef9`; commands 01–10 exiting zero;
Bugbot review `9cc660f1-7726-4fd4-9857-13d9afa5724f` with two confirmed
findings; Security Review not launched under fail-fast; and verdict
`NONPASS`.

The root's absence was observed after a reported macOS reboot. This session
independently verified absence only; neither the reboot nor any particular OS
cleanup mechanism can be proved as the cause.

Those contemporaneously verified, frozen receipt records remain authoritative
historical evidence. The vanished files cannot now be reread, but their
continued filesystem liveness is not an authority input after receipt
verification. Absence alone is not implementation drift and does not alter
the `NONPASS` verdict.

The root and its contents must not be recreated, restored, replaced,
reconstructed, relocated, operationally reused or presented as live evidence.
The failed Gate 5 must never be treated as `PASS`.

---

## 4. Exact inherited correction

V14 changes only V13's retained-root liveness requirement. To resume the
inherited correction after V14 governance delivery, each implementation or
corrective preflight must:

1. revalidate the exact frozen V13 and V12 bytes and receipt values above;
2. revalidate the bound branch, local/remote/PR head, comparison base,
   merge base, clean status, empty staging and Draft/unarmed PR state; and
3. treat the historical path as a nonbinding label, never as a required live
   filesystem object or a recovery target.

All other V13 requirements and stops are incorporated by exact reference,
without semantic change. In particular:

- V13 §§3–5 retain the exact four-path ceiling:
  `build/private-runtime/build.sh`,
  `engine/registration_hook_runtime.py`,
  `engine/tests/test_private_runtime_build.py`, and
  `engine/tests/test_registration_host_c.py`;
- V13 §4's two bounded production corrections and §5's tests-first,
  same-command expected-red then green sequence remain exact;
- the other 59 C-RUNTIME paths remain byte-exact under count/digest
  `59 / d4d14c7669c281ba49f056331fc8c255770d3b56da63839b0660e0cbdc721758`;
- V13 §§2 and 6 retain every manifest, map, exclusion, set and union,
  including delivered runtime manifest
  `63 / 4358beae4dc48f42dbc58399c47fc9f886254ec35efffbfd0baf097052143ccd`,
  delivered materialization map
  `58 / 0acf21c10bf3078e81e43c16e328b4ca9b60cafe206f04674e3d1f4a5ade0402`,
  and the V13 68-path PR union projection
  `84e3f35d9b5484c0f7dd465edfd37513c54caf746eb6d0ad24613d40366d074b`;
- V14 itself is the sole documentation path outside that inherited union
  projection and changes no inherited member or implementation byte;
- PR #183 remains Draft and auto-merge unarmed throughout governance and
  corrective delivery; and
- after corrective delivery, an entirely fresh exact-head Gate 5 must run
  all ten lanes plus fresh Bugbot and Security Review. Historical V12
  receipts satisfy no part of that future gate.

A fifth corrective path, changed implementation semantics, preserved-byte
drift, weakened assertion, stale or partial Gate 5, or any attempt to recover
the vanished root stops.

---

## 5. Separate decisions and postconditions

Each decision is explicit, one-use and non-transitive:

1. **Review V14:** read-only review confirms the evidence-policy correction,
   non-recreation rule, unchanged four-path implementation and mandatory fresh
   Gate 5. Postcondition: findings only; no status or repository mutation.
2. **Accept V14:** the owner separately accepts the reviewed exact draft.
   Postcondition: V14 is accepted, the README records V13 as superseded by
   V14, and V13 bytes remain unchanged. No delivery or implementation follows.
3. **Deliver governance:** a later owner decision permits delivery of only
   V14 and README to the existing branch/PR. Postcondition: one docs-only
   commit; PR remains Draft and unarmed.
4. **Run tests first:** a later decision permits only V13's two test paths and
   exact expected-red command. Postcondition: valid red receipt and frozen
   test bytes.
5. **Implement correction:** a later decision permits only V13's two
   production paths. Postcondition: the identical focused command is green
   with the exact four-path ceiling preserved.
6. **Deliver correction:** a later decision permits only reviewed four-path
   delivery. Postcondition: exact manifests, map, 59-path preservation and
   V13's 68-path union projection reproduce at one Draft/unarmed PR head,
   with V14 as the sole additional documentation path.
7. **Run Gate 5:** a later decision permits one fresh isolated exact-head
   Gate 5. Postcondition: all ten lanes and both fresh reviews produce a new
   verdict; nothing downstream is implied.
8. **Prepare qualification:** after a fresh Gate 5 `PASS`, a separate
   decision binds the clean reviewed head/PR, absent fresh user-owned packet
   root, two clean local builds, one disposable qualification-only synthetic
   keypair, Q1/Q2 and packet-v2 material. It permits no owner key, prompt,
   privilege or final packet.
9. **Run privileged qualification:** one separate decision permits exactly
   one native SecurityAgent prompt and one privilege attempt against only the
   disposable qualification root.
10. **Finalize packet:** a separate decision binds successful qualification,
    closes and proves absence of the disposable private key, and creates the
    inherited evidence index, packet and `FINALIZE_READBACK`.
11. **Accept packet:** a separate decision binds the packet, head, PR, source
    and scope bytes and permits only the inherited nonmutating
    `ACCEPT_READBACK`.
12. **Ready C-RUNTIME:** a separate owner decision naming the immutable packet
    and fresh Gate 5 permits one `READY_READBACK` and the sole Draft-to-Ready
    transition. Postcondition: readiness only; no agent arms or merges.
13. **Reviewer-App merge:** after READY, the reviewer App alone approves,
    arms native auto-merge and merges under inherited passing conditions.
    Postcondition: exact reviewed C-RUNTIME is on live main.
14. **C-FINAL:** starts only from merged C-RUNTIME live main under its own
    24-path implementation, delivery, Gate 5, qualification and readiness
    gates; desktop UAT remains deferred there.
15. **Actual R0:** requires a separate post-merge GO and the inherited exact
    R0 authority and evidence sequence.
16. **Release/tag/publication:** requires a separate exact artifact/revision
    GO.
17. **Installation:** requires a separate released-artifact/target GO.
18. **Host activation:** requires a separate installed-artifact/host-wiring
    GO.
19. **R1 canary:** requires a separate live-target GO.
20. **C1 clearance:** is evidence only.
21. **R2 rollout:** requires a separate rollout GO.

Qualification order is fixed:

```text
PREPARE -> exactly one privileged prompt -> FINALIZE -> ACCEPT -> READY
```

Release/tag/publication and every later stage above may begin only after both
C-FINAL and actual R0 have completed under their own gates.

No decision authorizes or implies the next.

---

## 6. Acceptance ledger

| ID | Required evidence | Refusal |
|---|---|---|
| V14-A01 | Frozen V13/V12 bytes reproduce the exact historical path, receipts, Git identities and `NONPASS`; path liveness is nonbinding after contemporaneous verification | Live-path dependency, causal claim or lost receipt authority |
| V14-A02 | The vanished root is never recreated, restored, replaced, reconstructed, relocated, reused or represented as `PASS` evidence | Any recovery or operational reuse |
| V14-A03 | V13's exact four paths, requirements, red/green sequence, 59-path preservation, manifests/maps/68-path union projection and Draft/unarmed policy remain unchanged; only the V14 document sits outside that projection | Fifth corrective path, changed inherited member, semantic change or preserved drift |
| V14-A04 | Corrective delivery is followed by a wholly fresh exact-head Gate 5 with ten lanes and fresh Bugbot and Security Review | Replayed V12 receipt, partial rerun or stale review |

---

## 7. Non-goals and review provenance

V14 adds no schema, digest domain, receipt format, authority object, key,
privilege mechanism, dependency, service, contract, implementation path or
rollout stage. It neither resolves the current PR conflict nor authorizes
implementation, delivery, Gate 5, qualification, readiness, merge, release,
installation, activation, rollout or actual R0.

This draft records no review or acceptance clearance. Its only irreducible
uncertainty is historical: because the OS-temporary root is absent, its bytes
cannot be independently reread today, and the cause of disappearance is
unprovable. V14 intentionally relies on the accepted frozen receipt record
rather than inventing replacement evidence.
