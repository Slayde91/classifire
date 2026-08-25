#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("QUANTIFIRE requires Python 3.11 or later.")
PY

if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip setuptools
python -m pip install --no-build-isolation -e .

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from the local-development example. Review it before running CLASSIFIRE."
fi

echo
echo "QUANTIFIRE installed."
echo "No database seed or administrator account was created."
echo "Activate: source .venv/bin/activate"
echo "Review: .env"
echo '1. Create admin: classifire create-admin --email "admin@your-company.example" --operator-reference "initial-admin-provisioning"'
echo '2. Initialise: classifire init --administrator-email "admin@your-company.example" --operator-reference "initial-database-bootstrap"'
echo "3. Start: classifire start"
echo "Production requirements: docs/PRODUCTION_CONFIGURATION.md"
