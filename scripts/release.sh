#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 x.y.z" >&2
  exit 2
fi

NEW_VERSION=$1
echo "Prepare release $NEW_VERSION"

echo "Update the version fields in these files locally, run tests, commit, tag, and push:" 
echo "  - buster/__init__.py"
echo "  - pyproject.toml"
echo
echo "Suggested commands (run after verifying tests pass):"
echo "  git add pyproject.toml buster/__init__.py"
echo "  git commit -m 'chore(release): $NEW_VERSION'"
echo "  git tag v$NEW_VERSION"
echo "  git push origin main --tags"
echo "  python -m build"

echo "Note: this script is a helper; it does not modify files or push for you."
