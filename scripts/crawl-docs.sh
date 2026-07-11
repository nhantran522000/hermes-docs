#!/usr/bin/env bash
# Crawl Hermes Agent docs from llms.txt into ./docs as Markdown.
# Safe to run repeatedly (weekly): existing files are overwritten.
#
# Usage:
#   scripts/crawl-docs.sh            # crawl everything in llms.txt
#   scripts/crawl-docs.sh --only installation   # test a subset
set -euo pipefail

# Make Homebrew-installed tools (pandoc, python3) reachable under launchd/cron,
# whose PATH is otherwise minimal.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$DIR/.venv-crawler"
LOG_DIR="$DIR/.crawl-logs"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/crawl-$TS.log"

log() { echo "$*" | tee -a "$LOG"; }

if ! command -v pandoc >/dev/null 2>&1; then
  log "ERROR: pandoc not found on PATH. Install it with: brew install pandoc"
  exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
  log "Creating Python virtualenv at $VENV ..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r "$DIR/scripts/requirements.txt"
fi

log "=== Hermes docs crawl started $TS ==="
set +e
"$VENV/bin/python" "$DIR/scripts/crawl_docs.py" "$@" 2>&1 | tee -a "$LOG"
status=${PIPESTATUS[0]}
set -e
log "=== Crawl finished (exit $status) at $(date +%Y%m%d-%H%M%S) ==="

# Keep only the 12 most recent logs.
ls -1t "$LOG_DIR"/crawl-*.log 2>/dev/null | tail -n +13 | xargs -I {} rm -f {} || true

exit "$status"
