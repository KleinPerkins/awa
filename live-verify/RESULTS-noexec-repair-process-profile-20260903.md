# Current source-checker process-profile evidence — 2026-09-13

## Purpose

This is the fresh bounded process observation required after M2.2 extended the
source checker with digest-bound expected-identity guards. It replaces the prior
observation at this canonical evidence path and does not alter the hypothesis-only
timing or inventory fields in `performance-baseline.v1.json`.

## Producer

Run once from the live-evidence worktree with no competing AWA test suite:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  -m engine.tests.guard_boundary_profile \
  --boundary source \
  --count-git \
  --json-out /tmp/awa-m2-2-process-profile.json
```

- Measured at: `2026-09-13T06:17:21Z`
- Branch: `feat/awa-integrity-m2-2-repair`
- Base HEAD: `28b1e9ca2b9776b90c8da95950e75d7f1ed78e1e`
- Platform: `macOS-26.6.2-arm64-arm-64bit-Mach-O`
- Python: `3.14.6`
- Git: `git version 2.50.1 (Apple Git-155)`

The measurement used the candidate tracked working tree above that base HEAD.
For reproducible provenance, the source-tree digest below hashes every tracked
path and its current bytes in sorted order, each length-prefixed with eight
big-endian bytes. It excludes only the generated baseline and this evidence
record, so adding those two outputs cannot change the measured-subject identity.

- Measured-subject files: `264`
- Measured-subject SHA-256: `c7f1aa8a6877ffd26897e15f1db43f70411f8bbfbc7064157e51d9752c805d47`
- Excluded paths:
  - `engine/tests/performance-baseline.v1.json`
  - `live-verify/RESULTS-noexec-repair-process-profile-20260903.md`

## Bound source identities

- Raw profile producer: `e705a3f2046084317053f7d7842c1bf3b44d28da86dd390addc306306d075aa4`
- Validator: `7d915a3544711c518553efff5f50429dcedbb6d921d51c298e1bdb9e1f43ed6a`
- Combined performance producer: `da65feeb123cc1e8164d73009abc65a94202c50298b085eb29b88a49be3a5a7b`
- Case manifest: `eb4e7662f096cecc6d0a99717d71e1868552596f22abe1db61536e61d4476435`
- Source guard: `aeee0c147f08976f20ea600d6fd3c891030346554871bdf7f39b6bf1e42baedf`
- Source checker: `25ca38e6214fd4746b80f8585a7fd2fbbef75b4cd9fd65486060376fa3e382c3`
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
