#!/bin/sh
# Quiet refusal through the fixed root-owned v7 entrypoint.
set -u
unset ENV BASH_ENV

ENTRYPOINT="/Library/Application Support/AWA/bin/awa-registration"
[ -f "$ENTRYPOINT" ] && [ ! -L "$ENTRYPOINT" ] && [ -x "$ENTRYPOINT" ] ||
  exit 1
exec "$ENTRYPOINT" admission 2>/dev/null
