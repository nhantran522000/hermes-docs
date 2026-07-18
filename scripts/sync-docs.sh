#!/usr/bin/env bash
# One-shot sync used by the weekly schedule:
#   1. crawl every page listed in the checked-in llms.txt into ./docs
#   2. commit docs changes and push to origin
#
# llms.txt is a hand-maintained page list — it is no longer fetched from the site.
# Edit it by hand to add/remove pages from the crawl.
#
# Safe to run manually too:  scripts/sync-docs.sh
set -euo pipefail

# Homebrew tools + git must be reachable under launchd/cron's minimal PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"

# 1: crawl every page in llms.txt. Don't abort the whole sync if a few pages fail
# (their previous versions stay in place); remember the status for the exit.
set +e
"$DIR/scripts/crawl-docs.sh" "$@"
crawl_status=$?
set -e
if [ "$crawl_status" -ne 0 ]; then
  echo "WARNING: crawl exited $crawl_status (some pages may not have updated). Committing what changed."
fi

# 2: commit + push the crawled docs, and only if something changed.
git add -A -- docs
if git diff --cached --quiet; then
  echo "No documentation changes to commit."
  exit "$crawl_status"
fi

STAMP="$(date +'%Y-%m-%d %H:%M %Z')"
git commit -q -m "docs: sync Hermes docs $STAMP" \
  -m "Automated: fetched llms.txt from the live site and re-crawled all pages."
echo "Committed documentation changes."

if git push -q origin "$BRANCH"; then
  echo "Pushed to origin/$BRANCH."
else
  echo "ERROR: git push to origin/$BRANCH failed (check credentials/network)." >&2
  exit 1
fi

exit "$crawl_status"
