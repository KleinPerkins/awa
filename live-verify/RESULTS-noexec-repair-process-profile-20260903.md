# Noexec repair process-profile evidence — 2026-09-03

## Purpose

This is the fresh bounded process observation required after the guard-boundary
producer changed during the AWA noexec repair. It replaces no historical result
and does not alter the hypothesis-only timing or inventory fields in
`performance-baseline.v1.json`.

## Producer

Run once from the repair worktree with no competing AWA test suite:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  -m engine.tests.guard_boundary_profile \
  --boundary source \
  --count-git \
  --json-out /tmp/awa-noexec-process-profile.json
```

- Measured at: `2026-09-03T16:21:34Z`
- Branch: `fix/awa-v4-named-hooks-noexec-20260902`
- Base HEAD: `802c889dc9618478488d4476ca7677c15824f4cb`
- Platform: `macOS-26.6.2-arm64-arm-64bit-Mach-O`
- Python: `3.14.6`
- Git: `git version 2.50.1 (Apple Git-155)`

The measurement used the reviewed tracked working tree above that base HEAD.
For reproducible provenance, the source-tree digest below hashes every tracked
path and its current bytes in sorted order, each length-prefixed with eight
big-endian bytes. It excludes only the generated baseline and this evidence
record, so adding those two outputs cannot change the measured-subject identity.

- Measured-subject files: `258`
- Measured-subject SHA-256: `48a154d4c59d59416b4dec3097fec8cce735ff262c56a499b75386301b436a43`
- Excluded paths:
  - `engine/tests/performance-baseline.v1.json`
  - `live-verify/RESULTS-noexec-repair-process-profile-20260903.md`

## Bound source identities

- Raw profile producer: `e705a3f2046084317053f7d7842c1bf3b44d28da86dd390addc306306d075aa4`
- Validator: `7d915a3544711c518553efff5f50429dcedbb6d921d51c298e1bdb9e1f43ed6a`
- Combined performance producer: `da65feeb123cc1e8164d73009abc65a94202c50298b085eb29b88a49be3a5a7b`
- Case manifest: `eb4e7662f096cecc6d0a99717d71e1868552596f22abe1db61536e61d4476435`
- Source guard: `aeee0c147f08976f20ea600d6fd3c891030346554871bdf7f39b6bf1e42baedf`
- Source checker: `d8fa3055714d785e84b5650b9a10fdfec4e467b0454074ccc76ff64b3231315e`
- Default policy: `dbc06510525f69a5cd51d6f7c8e9a0c9ea6d888e35a854f45a06bc4168337870`

## Result

- Schema: `awa-guard-boundary-profile/v1`
- Boundary: `source`
- Counter scope: `PATH-resolved git children only`
- Outcome: `passed`
- Git processes: `62`
- Case outcomes:
  - `maintenance_allow`: `allow` (`15` Git processes)
  - `maintenance_dirty_deny`: `deny` (`14`)
  - `maintenance_near_miss_deny`: `deny` (`11`)
  - `mutation_deny`: `deny` (`19`)
  - `readonly_allow`: `allow` (`3`)

`performance_policy.process_measurement_from_profile()` validated the raw
document and derived the exact process-measurement object committed in the
baseline. The disposable raw JSON was retained only long enough to perform that
validation.
