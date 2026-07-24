#!/usr/bin/env bash
# Auto-sync the code/ directory to GitHub.
# Commits any changes and pushes. Safe to run repeatedly (no-op if nothing changed).
set -euo pipefail

REPO_DIR="/home/neo/Downloads/netrunner/code"
cd "$REPO_DIR"

# Nothing to do if there are no changes.
if [ -z "$(git status --porcelain)" ]; then
  exit 0
fi

git add -A
git commit -q -m "Auto-sync: $(date '+%Y-%m-%d %H:%M:%S')"
git push -q origin main
