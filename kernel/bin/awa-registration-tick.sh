#!/bin/sh
# One-shot registration tick through the fixed root-owned v7 entrypoint.
set -u
unset ENV BASH_ENV

ENTRYPOINT="/Library/Application Support/AWA/bin/awa-registration"
[ -f "$ENTRYPOINT" ] && [ ! -L "$ENTRYPOINT" ] && [ -x "$ENTRYPOINT" ] ||
  exit 0
exec "$ENTRYPOINT" tick
