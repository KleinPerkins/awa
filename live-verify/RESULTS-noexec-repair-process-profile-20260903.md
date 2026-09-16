# Current source-checker process-profile evidence — 2026-09-16

## Purpose

This is the fresh bounded process observation required after M2.4 changed the
source checker and generic default policy. It replaces the prior observation at
this canonical evidence path and does not alter the historical measured-subject,
hypothesis-only timing, or inventory fields in `performance-baseline.v1.json`.

## Producer

Run once from the live-evidence worktree with no competing AWA test suite:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  -m engine.tests.guard_boundary_profile \
  --boundary source \
  --count-git \
  --json-out /tmp/awa-m2-4-process-profile.json
```

- Measured at: `2026-09-16T19:20:29Z`
- Branch: `feat/awa-integrity-m2-4-entry-handoff`
- Base HEAD: `90e8d968a0f191691dd5f38dce5b5ac8bf5c6f13`
- Platform: `macOS-26.6.2-arm64-arm-64bit-Mach-O`
- Python: `3.14.6`
- Git: `git version 2.50.1 (Apple Git-155)`

The process measurement used the candidate working tree above that base HEAD.
The measured-subject count and digest below remain the explicitly historical
baseline identity pinned by the verifier; current producer identities are
separately rebound below.

- Measured-subject files: `264`
- Measured-subject SHA-256: `2131af9746b42b5f71fd02fbc9a43089082217837129ce1d9cca68fefab00b0e`
- Excluded paths:
  - `engine/tests/performance-baseline.v1.json`
  - `live-verify/RESULTS-noexec-repair-process-profile-20260903.md`

## Bound source identities

- Raw profile producer: `e705a3f2046084317053f7d7842c1bf3b44d28da86dd390addc306306d075aa4`
- Validator: `7d915a3544711c518553efff5f50429dcedbb6d921d51c298e1bdb9e1f43ed6a`
- Combined performance producer: `da65feeb123cc1e8164d73009abc65a94202c50298b085eb29b88a49be3a5a7b`
- Case manifest: `eb4e7662f096cecc6d0a99717d71e1868552596f22abe1db61536e61d4476435`
- Source guard: `aeee0c147f08976f20ea600d6fd3c891030346554871bdf7f39b6bf1e42baedf`
- Source checker: `561fc24fc7e6ba5fce39711b608fdc0cbdb9686cb5d49ee88d985fb2164c7daf`
- Default policy: `ce971012c1c8c1ffb821c08b4b3a70853a83f06247b0b9a3b7fbb5909ff66c04`

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
