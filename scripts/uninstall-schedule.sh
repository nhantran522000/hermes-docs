#!/usr/bin/env bash
# Remove the weekly launchd crawl job.
set -euo pipefail
LABEL="com.hermes-docs.crawl"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "Removed weekly schedule ($LABEL)."
