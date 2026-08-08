#!/usr/bin/env bash
set -euo pipefail
OWNER="${1:-Slayde91}"
REPO="${2:-classifire}"
VISIBILITY="${3:-private}"

command -v gh >/dev/null 2>&1 || { echo "GitHub CLI (gh) is required." >&2; exit 1; }
gh auth status >/dev/null

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git init -b main
  git add .
  git commit -m "Initial QUANTIFIRE pre-production integration build"
fi

if gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$OWNER/$REPO.git"
  git push -u origin main
else
  gh repo create "$OWNER/$REPO" --"$VISIBILITY" --source . --remote origin --push
fi
