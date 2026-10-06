#!/bin/sh
# Receiver route through the fixed root-owned v7 entrypoint.
set -u
unset ENV BASH_ENV

ENTRYPOINT="/Library/Application Support/AWA/bin/awa-registration"
[ "$#" -eq 0 ] || exit 2
[ -f "$ENTRYPOINT" ] && [ ! -L "$ENTRYPOINT" ] && [ -x "$ENTRYPOINT" ] ||
  exit 1
exec "$ENTRYPOINT" receiver
