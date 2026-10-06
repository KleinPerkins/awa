# AWA protected private runtime

This directory is the deterministic, runnerless source/build boundary frozen by
accepted registration plan v7.

- `sources.lock.json` is exact JCS+LF authority. Its SHA-256 is
  `a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72`.
- `manifest.py --check` and `build.sh --check` are read-only freeze checks.
- `build.sh --synthetic-fixture SOURCE WORK` is the only ordinary test path. It
  accepts a bounded nonprivileged fixture and normalizes it twice.
- Real input collection and build require the later exact-head
  `V7-C-RUNTIME-QUALIFY` gate in
  `AWA_PRIVATE_RUNTIME_QUALIFICATION_GO`. They are intentionally absent from
  `make verify`, CI, and implementation evidence.

Generated archives, manifests, signatures, SBOMs, license bundles,
transcripts, qualification packets, and private keys are never repository
artifacts. GitHub Actions runners are forbidden.
