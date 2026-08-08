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
  echo "Created .env from .env.example. Change the secret key and administrator settings before production use."
fi

quantifire init

echo
echo "QUANTIFIRE installed."
echo "Activate: source .venv/bin/activate"
echo "Create admin: quantifire create-admin"
echo "Start: quantifire start"
