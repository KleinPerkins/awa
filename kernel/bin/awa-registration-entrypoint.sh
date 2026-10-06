#!/bin/sh
# Root-owned registration entrypoint. It performs no runtime selection itself.
set -u
unset ENV BASH_ENV PYTHONPATH PYTHONHOME PYTHONUSERBASE PYTHONSTARTUP \
  PYTHONINSPECT PYTHONBREAKPOINT PYTHONWARNINGS PYTHONHASHSEED \
  DYLD_LIBRARY_PATH DYLD_FRAMEWORK_PATH DYLD_INSERT_LIBRARIES \
  AWA_REGISTRATION_RUNTIME_CONFIG AWA_REGISTRATION_BUNDLE_ROOT \
  AWA_REGISTRATION_ACTIVE_BUNDLE CDPATH
PATH=/usr/bin:/bin
LANG=C
LC_ALL=C
export PATH LANG LC_ALL

case "${1:-}" in
  admission|receiver|startup|tick) route="$1" ;;
  *) exit 2 ;;
esac
[ "$#" -eq 1 ] || exit 2

exec /usr/bin/python3 -I -S -B \
  "/Library/Application Support/AWA/bootstrap/v1/bootstrap.py" "$route"
