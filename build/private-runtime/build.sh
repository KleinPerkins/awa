#!/usr/bin/env bash
# Deterministic private-runtime build driver.
#
# Ordinary repository verification is deliberately source-only or synthetic.
# Real input collection/build is impossible unless the later exact-head
# qualification gate is supplied explicitly; this implementation task does
# not set that gate and must never execute either qualification subcommand.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd -P)"
ROOT="$(cd "$SELF_DIR/../.." && pwd -P)"
MANIFEST="$SELF_DIR/manifest.py"
SOURCE_LOCK="$SELF_DIR/sources.lock.json"
EXPECTED_LOCK_SHA256="a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72"
QUALIFICATION_GATE="V7-C-RUNTIME-QUALIFY"

usage() {
  cat >&2 <<'EOF'
usage:
  build.sh --check
  build.sh --synthetic-fixture SOURCE_DIR WORK_DIR
  build.sh --qualification-inputs CACHE_DIR
  build.sh --qualification-build CACHE_DIR WORK_DIR

The last two forms require the separately authorized exact-head qualification
gate. They are never part of make verify or ordinary local implementation.
EOF
  exit 2
}

die() {
  printf 'private-runtime-build: %s\n' "$*" >&2
  exit 1
}

require_exact_lock() {
  local observed
  observed="$(/usr/bin/shasum -a 256 "$SOURCE_LOCK" | /usr/bin/awk '{print $1}')"
  [ "$observed" = "$EXPECTED_LOCK_SHA256" ] ||
    die "accepted source-lock hash mismatch"
  /usr/bin/python3 -I -S -B "$MANIFEST" \
    --source-lock "$SOURCE_LOCK" --check >/dev/null
}

require_qualification_gate() {
  [ "${AWA_PRIVATE_RUNTIME_QUALIFICATION_GO:-}" = "$QUALIFICATION_GATE" ] ||
    die "real input collection/build requires the later $QUALIFICATION_GATE gate"
  [ "${GITHUB_ACTIONS:-}" != "true" ] ||
    die "GitHub Actions runners are forbidden"
  [ "$(/usr/bin/uname -s)" = "Darwin" ] ||
    die "qualification requires Darwin"
  [ "$(/usr/bin/uname -m)" = "arm64" ] ||
    die "qualification requires arm64"
}

require_empty_private_directory() {
  local path="$1"
  case "$path" in
    /*) ;;
    *) die "qualification directory must be absolute" ;;
  esac
  if [ -e "$path" ]; then
    [ -d "$path" ] && [ ! -L "$path" ] ||
      die "qualification directory is not a real directory"
    [ -z "$(/bin/ls -A "$path")" ] ||
      die "qualification directory must be empty"
  else
    /bin/mkdir -m 700 "$path"
  fi
  [ "$(/usr/bin/stat -f '%Lp:%l' "$path")" = "700:2" ] ||
    die "qualification directory metadata refused"
}

lock_value() {
  local key="$1"
  /usr/bin/python3 -I -S -B - "$SOURCE_LOCK" "$key" <<'PY'
import json
import sys
with open(sys.argv[1], "rb") as handle:
    value = json.load(handle)[sys.argv[2]]
if isinstance(value, bool) or not isinstance(value, (str, int)):
    raise SystemExit(2)
print(value)
PY
}

verify_file() {
  local path="$1" size="$2" digest="$3" observed_size observed_digest
  [ -f "$path" ] && [ ! -L "$path" ] ||
    die "missing regular qualification input: $path"
  observed_size="$(/usr/bin/stat -f '%z' "$path")"
  observed_digest="$(/usr/bin/shasum -a 256 "$path" | /usr/bin/awk '{print $1}')"
  [ "$observed_size" = "$size" ] ||
    die "qualification input size mismatch: $path"
  [ "$observed_digest" = "$digest" ] ||
    die "qualification input hash mismatch: $path"
}

collect_inputs() {
  local cache="$1"
  require_empty_private_directory "$cache"
  local artifact_name artifact_url full_name full_url sums_url
  artifact_name="$(lock_value artifact_name)"
  artifact_url="$(lock_value artifact_url)"
  full_name="$(lock_value full_build_archive_name)"
  full_url="$(lock_value full_build_archive_url)"
  sums_url="$(lock_value sha256sums_url)"

  /usr/bin/curl --fail --location --proto '=https' --tlsv1.2 \
    --output "$cache/$artifact_name" "$artifact_url"
  /usr/bin/curl --fail --location --proto '=https' --tlsv1.2 \
    --output "$cache/$full_name" "$full_url"
  /usr/bin/curl --fail --location --proto '=https' --tlsv1.2 \
    --output "$cache/SHA256SUMS" "$sums_url"

  # GitHub CLI emits the Sigstore bundle without placing auth in repository
  # bytes. The selector/validator consumes every downloaded record and requires
  # exactly one accepted SLSA-v1 record.
  /usr/bin/env -i HOME="${HOME:?}" PATH=/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin \
    gh attestation download \
      --repo astral-sh/python-build-standalone \
      --digest "sha256:$(lock_value artifact_sha256)" \
      --format json >"$cache/attestation-bundle.json"

  verify_file "$cache/$artifact_name" \
    "$(lock_value artifact_size)" "$(lock_value artifact_sha256)"
  verify_file "$cache/$full_name" \
    "$(lock_value full_build_archive_size)" \
    "$(lock_value full_build_archive_sha256)"
  verify_file "$cache/SHA256SUMS" \
    "$(lock_value sha256sums_size)" "$(lock_value sha256sums_sha256)"
  /usr/bin/python3 -I -S -B "$MANIFEST" \
    --source-lock "$SOURCE_LOCK" \
    --verify-qualification-cache "$cache"
}

qualification_build() {
  local cache="$1" work="$2"
  [ -d "$cache" ] && [ ! -L "$cache" ] ||
    die "qualification cache is not a real directory"
  require_empty_private_directory "$work"
  /usr/bin/python3 -I -S -B "$MANIFEST" \
    --source-lock "$SOURCE_LOCK" \
    --qualification-build "$cache" "$work"
}

case "${1:-}" in
  --check)
    [ "$#" -eq 1 ] || usage
    require_exact_lock
    ;;
  --synthetic-fixture)
    [ "$#" -eq 3 ] || usage
    require_exact_lock
    /usr/bin/python3 -I -S -B "$MANIFEST" \
      --source-lock "$SOURCE_LOCK" --synthetic-fixture "$2" "$3"
    ;;
  --qualification-inputs)
    [ "$#" -eq 2 ] || usage
    require_exact_lock
    require_qualification_gate
    collect_inputs "$2"
    ;;
  --qualification-build)
    [ "$#" -eq 3 ] || usage
    require_exact_lock
    require_qualification_gate
    qualification_build "$2" "$3"
    ;;
  *)
    usage
    ;;
esac
