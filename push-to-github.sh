#!/usr/bin/env bash
set -euo pipefail
OWNER="${1:-Slayde91}"
REPO="${2:-quantifire}"
VISIBILITY="${3:---private}"
command -v git >/dev/null 2>&1 || { echo "Git is required." >&2; exit 1; }
command -v gh >/dev/null 2>&1 || { echo "GitHub CLI (gh) is required: https://cli.github.com/" >&2; exit 1; }
if [ ! -d .git ]; then
  git init -b main
  git config user.name "${GIT_AUTHOR_NAME:-QUANTIFIRE Publisher}"
  git config user.email "${GIT_AUTHOR_EMAIL:-slayde@ceasefire.com.au}"
  git add -A
  git commit -m "Initial QUANTIFIRE development preview"
fi
gh auth status >/dev/null 2>&1 || gh auth login
if gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
  git remote remove origin 2>/dev/null || true
  git remote add origin "https://github.com/$OWNER/$REPO.git"
  git push -u origin main
else
  gh repo create "$OWNER/$REPO" "$VISIBILITY" --source . --remote origin --push
fi
