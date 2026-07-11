# Hermes docs crawler

Crawls every documentation page listed in [`../llms.txt`](../llms.txt) and saves it as
Markdown under [`../docs/`](../docs/), mirroring the URL paths. Re-running overwrites
existing files in place, so it is safe to run on a schedule.

## Requirements

- `pandoc` — HTML → Markdown conversion (`brew install pandoc`)
- Python 3 — the wrapper creates a local virtualenv (`.venv-crawler/`) and installs
  `requests` + `beautifulsoup4` from `requirements.txt` on first run.

## Run manually

```bash
scripts/crawl-docs.sh                 # crawl everything in llms.txt
scripts/crawl-docs.sh --only cli      # only URLs containing "cli" (for testing)
scripts/crawl-docs.sh --workers 4     # fewer concurrent fetches
```

Logs are written to `.crawl-logs/` (last 12 kept). Both the venv and logs are gitignored.

## Weekly schedule (macOS launchd)

Installed to run **every Sunday at 18:00**:

```bash
scripts/install-schedule.sh                       # Sunday 18:00 (default)
WEEKDAY=5 HOUR=18 scripts/install-schedule.sh     # change day/time (0=Sun..6=Sat)
scripts/uninstall-schedule.sh                     # remove the schedule
```

Useful launchctl commands (UID is your `id -u`, e.g. 501):

```bash
launchctl list | grep hermes-docs                        # is it registered?
launchctl print gui/$(id -u)/com.hermes-docs.crawl       # full state + schedule
launchctl kickstart gui/$(id -u)/com.hermes-docs.crawl   # run now, out of schedule
```

launchd runs a missed job when the Mac next wakes, so a weekly run won't be skipped
just because the machine was asleep at 18:00.

## How it works

For each doc URL, `crawl_docs.py`:

1. Fetches the rendered HTML (retrying transient failures).
   - Category pages listed as `.../index` are served at `...`, so it falls back to the
     suffix-stripped path on a 404.
   - Client-side redirect stubs (`<meta refresh>`) are followed to the real page.
2. Extracts the `<div class="theme-doc-markdown">` article body, stripping Docusaurus
   heading anchors, decorative inline SVG/`data:` icons, and copy buttons.
3. Converts to GitHub-Flavored Markdown with `pandoc`.
4. Writes `docs/<mirrored path>.md` with front matter (`source`, `title`, `last_crawled`).

Internal doc links keep their site-absolute form (e.g. `/docs/...`) — they point at the
live site, not the local files.
