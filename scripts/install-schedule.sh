#!/usr/bin/env bash
# Install a weekly launchd job that re-crawls the Hermes docs.
# Default: every Sunday at 18:00. Override with WEEKDAY (0=Sun..6=Sat), HOUR, MINUTE.
#   WEEKDAY=5 HOUR=18 scripts/install-schedule.sh   # e.g. Friday 18:00
set -euo pipefail

WEEKDAY="${WEEKDAY:-0}"   # 0 = Sunday
HOUR="${HOUR:-18}"        # 18 = 6 PM
MINUTE="${MINUTE:-0}"

LABEL="com.hermes-docs.crawl"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$DIR/.crawl-logs"
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$DIR/scripts/sync-docs.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$DIR</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>$WEEKDAY</integer>
        <key>Hour</key>
        <integer>$HOUR</integer>
        <key>Minute</key>
        <integer>$MINUTE</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/launchd.err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST_EOF

UID_NUM="$(id -u)"
# Reload cleanly if already installed.
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST"
launchctl enable "gui/$UID_NUM/$LABEL"

DAYS=(Sunday Monday Tuesday Wednesday Thursday Friday Saturday)
printf 'Installed %s\n' "$PLIST"
printf 'Schedule: every %s at %02d:%02d\n' "${DAYS[$WEEKDAY]}" "$HOUR" "$MINUTE"
echo "Verify:   launchctl print gui/$UID_NUM/$LABEL | grep -A3 'runatload\\|periodic\\|state'"
echo "Run now:  launchctl kickstart gui/$UID_NUM/$LABEL"
echo "Remove:   scripts/uninstall-schedule.sh"
