# Post-UAT item 4 — Phase 5 adopted-worktree cleanup

Status: **fixed in the ordinary cleanup kernel**

## Direct UAT evidence

The preserved UAT ledger records, in order:

1. Phase 5 Step 5.6: `git status --short --branch` showed only `?? .awa/`; `git diff`
   produced no output.
2. `reset --hard` could not remove the untracked directory.
3. `dev-worktree.sh clean --bundle --delete-branch` exited 1 with
   `refusing to remove dirty worktree`.
4. Phase 5 Step 5.7: the raw `git clean -fd` workaround was correctly blocked by Cursor's AWA
   guard, and the product cleanup refused again.
5. Phase 5 Step 5.8: Terminal.app manually removed `.awa/`; the same product cleanup then
   bundled ignored child state, removed the merged worktree, and atomically deleted its branch.

The exact code path was direct: `engine/lifecycle.py::adopt()` writes `.awa/lease.json`, while the
ordinary clean path rejected any non-empty `git status --porcelain` before it identified or
validated AWA-owned state. The stale upstream's `ahead 1` display was not Git dirtiness and is not
part of this root cause.

## Fix and refusal boundaries

Ordinary clean now recognizes one AWA-owned file only after proving:

- Git tracks no `.awa` path.
- `.awa` is an owned mode-0700 real directory containing exactly `lease.json`.
- The lease is an owned mode-0600, single-link regular file with bounded valid JSON.
- Its schema, identity hash, worktree path, branch, and Git common directory match the live target.

The proof is repeated under the shared lifecycle lock immediately before a no-follow,
directory-relative unlink of `lease.json`. The empty directory is left for Git's worktree removal.
Malformed/mismatched leases, links, mode drift, sibling `.awa` content, unrelated untracked content,
active roots, and unshared commits all preserve the worktree. Unrelated ignored content still uses
the existing bundle-or-refuse path.

## Controlled executable replay

Closest executable replay of the failed UAT path:

```text
python3 -m unittest -v \
  engine.tests.test_clean_kernel.CleanKernelTest.test_adopted_merged_worktree_bundle_clean_owns_only_validated_lease \
  engine.tests.test_clean_kernel.CleanKernelTest.test_adopted_unmerged_worktree_preserves_lease_on_commit_safety_refusal \
  engine.tests.test_clean_kernel.CleanKernelTest.test_ignored_validated_lease_is_removed_not_recovery_bundled \
  engine.tests.test_clean_kernel.CleanKernelTest.test_adopted_worktree_with_extra_awa_content_refuses_and_preserves_all \
  engine.tests.test_clean_kernel.CleanKernelTest.test_adopted_worktree_with_unrelated_untracked_file_refuses_and_preserves_all \
  engine.tests.test_clean_kernel.CleanKernelTest.test_malformed_or_identity_mismatched_lease_is_never_owned \
  engine.tests.test_clean_kernel.CleanKernelTest.test_symlinked_lease_is_never_owned_or_followed
```

Result: **PASS**. The success case creates and adopts a disposable linked worktree, squash-merges
its change, leaves ignored operator child state, and runs the exact
`clean --bundle --delete-branch` command. It verifies worktree and branch removal, the recovery
manifest's preserved ignored path, and exclusion of `.awa` from that archive.

The success regression was also run with only the cleanup-kernel patch reversed. It failed at the
pre-fix dirty gate with the exact UAT message, then passed after restoration:

```text
AssertionError: 1 != 0 :
dev-worktree.sh: refusing to remove dirty worktree: <disposable adopted worktree>
BITING: regression failed against pre-fix clean path as expected
```

This is a controlled integration replay, not a claim of new live Cursor Desktop operator proof.

Full repository gate after the focused replay:

```text
make verify
Ran 771 tests ... OK (skipped=15)
Ran 15 dashboard tests ... OK
awa-contract-freeze: OK
awa --check: OK
verify-live-verify: OK
verify: OK
```
