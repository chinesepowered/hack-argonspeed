#!/usr/bin/env bash
# The hosted harness's command line (managed/agent.py), run with the repo's .venv.
#
#   scripts/managed.sh status
#   scripts/managed.sh --help
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
[ -x "$root/.venv/bin/python" ] || { echo "no .venv: run scripts/setup.sh" >&2; exit 2; }
exec "$root/.venv/bin/python" "$root/managed/agent.py" "$@"
