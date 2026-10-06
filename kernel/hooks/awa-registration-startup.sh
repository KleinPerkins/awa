#!/bin/sh
# Quiet refusal through the fixed root entrypoint.
set -u
unset ENV BASH_ENV

ENTRYPOINT="/Library/Application Support/AWA/bin/awa-registration"
[ -f "$ENTRYPOINT" ] && [ ! -L "$ENTRYPOINT" ] && [ -x "$ENTRYPOINT" ] ||
  exit 1
exec "$ENTRYPOINT" startup >/dev/null 2>&1
