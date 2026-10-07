#!/usr/bin/env bash
set -euo pipefail
command -v node >/dev/null 2>&1 || {
  printf '%s\n' 'Node.js >=20 is required; install it before deployment.' >&2
  exit 1
}
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec node "${SCRIPT_DIR}/deploy.mjs" "$@"
