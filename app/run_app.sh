#!/usr/bin/env bash
# Start the CADSmith web application.
#
#   ./app/run_app.sh              # serve on http://127.0.0.1:8000
#   PORT=9000 ./app/run_app.sh    # somewhere else
#   ./app/run_app.sh --reload     # reload on source changes, for development
#
# Expects a virtualenv at .venv in the repository root; see app/README.md.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
# Accept either name: ".venv" is this project's convention, "venv" is the
# other common one. $PYTHON overrides both.
if [ -z "${PYTHON:-}" ]; then
  for candidate in "$ROOT/.venv/bin/python" "$ROOT/venv/bin/python"; do
    if [ -x "$candidate" ]; then PYTHON="$candidate"; break; fi
  done
fi

if [ -z "${PYTHON:-}" ] || [ ! -x "$PYTHON" ]; then
  echo "No virtualenv found in $ROOT (looked for .venv and venv)" >&2
  echo "Create one with:" >&2
  echo "  python3 -m venv .venv" >&2
  echo "  .venv/bin/python -m pip install -r app/requirements-app.txt" >&2
  echo "Or point at an existing one:  PYTHON=/path/to/python ./app/run_app.sh" >&2
  exit 1
fi

probe=$("$PYTHON" -c "import cadquery, vtk; print('CADSMITH_IMPORT_OK', cadquery.__version__, vtk.VTK_VERSION)" 2>&1)
if [[ "$probe" != *CADSMITH_IMPORT_OK* ]]; then
  echo "Could not import CadQuery and VTK with $PYTHON" >&2
  echo "$probe" >&2
  echo >&2
  echo "  .venv/bin/pip install -r app/requirements-app.txt" >&2
  exit 1
fi

# Load ANTHROPIC_API_KEY (and anything else) from .env if present. The agents
# read it through python-dotenv too, but exporting it here means the health
# check reports the truth before the first run starts.
#
# A variable already exported wins over the file, so a stale value in .env
# cannot quietly replace one just set in this shell - which, for short-lived
# AWS credentials, reads as an expired token with no explanation. That is
# also python-dotenv's own default, which the agents load with.
if [ -f "$ROOT/.env" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ""|\#*) continue ;; esac
    name=${line%%=*}
    [ "$name" = "$line" ] && continue
    name=$(printf '%s' "$name" | tr -d '[:space:]')
    printf '%s' "$name" | grep -qE '^[A-Za-z_][A-Za-z0-9_]*$' || continue
    eval "current=\${$name-}"
    [ -n "$current" ] && continue
    value=${line#*=}
    value=${value#"${value%%[![:space:]]*}"}
    value=${value%"${value##*[![:space:]]}"}
    case "$value" in
      \"*\") value=${value#\"}; value=${value%\"} ;;
      \'*\') value=${value#\'}; value=${value%\'} ;;
    esac
    export "$name=$value"
  done < "$ROOT/.env"
fi

echo "CADSmith → http://${HOST}:${PORT}"
exec "$PYTHON" -m uvicorn app.server.app:app \
  --host "$HOST" --port "$PORT" --log-level info "$@"
