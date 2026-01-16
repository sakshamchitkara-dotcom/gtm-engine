#!/usr/bin/env bash
# Commit staged changes with a chosen date.
#   scripts/backdate.sh "2026-09-03T14:12:00" "feat: add scoring"
# Git stores two timestamps per commit; set both or `git log` and GitHub will disagree.
set -euo pipefail
[ $# -eq 2 ] || { echo "usage: $0 <ISO-date> <message>" >&2; exit 1; }
GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1" git commit -m "$2"
