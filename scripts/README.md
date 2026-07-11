# Hermes docs crawler

Fetches a fresh [`../llms.txt`](../llms.txt) from the live docs site, crawls every page
it lists, and saves each as Markdown under [`../docs/`](../docs/), mirroring the URL
paths. Re-running overwrites existing files in place, so it is safe to run on a schedule.

The weekly job (`sync-docs.sh`) does the whole loop: **fetch `llms.txt` → crawl → commit
→ push to GitHub**.

## Requirements

- `pandoc` — HTML → Markdown conversion (`brew install pandoc`)
- Python 3 — the wrapper creates a local virtualenv (`.venv-crawler/`) and installs
  `requests` + `beautifulsoup4` from `requirements.txt` on first run.

## Run manually

```bash
scripts/sync-docs.sh                  # full weekly job: fetch llms.txt -> crawl -> commit -> push
scripts/crawl-docs.sh                 # crawl only, using the current local llms.txt
scripts/crawl-docs.sh --refresh-llms  # fetch a fresh llms.txt first, then crawl (no git)
scripts/crawl-docs.sh --only cli      # only URLs containing "cli" (for testing)
scripts/crawl-docs.sh --workers 4     # fewer concurrent fetches
```

`sync-docs.sh` commits only `llms.txt` + `docs/`, and only when something actually
changed (a same-day re-run with no doc changes is a clean no-op). If a few pages fail to
crawl, their previous versions stay in place and the rest are still committed.

Logs are written to `.crawl-logs/` (last 12 kept). Both the venv and logs are gitignored.

## Git / push

`sync-docs.sh` pushes to `origin` on the current branch using your normal git
credentials. On macOS these come from the `osxkeychain` credential helper, which works
non-interactively while you are logged in — no token is stored in this repo. If a push
ever fails with an auth error, run `git push` once by hand to re-cache the credential.

## Weekly schedule — GitHub Actions (primary)

The scheduled run lives in [`../.github/workflows/sync-docs.yml`](../.github/workflows/sync-docs.yml)
and runs on GitHub's servers **every Sunday at 18:00 UTC** — no local machine needed. It
does the same fetch → crawl → commit → push loop and pushes as `github-actions[bot]`.

```bash
gh workflow run "Sync Hermes docs"        # run it now
gh run list --workflow "Sync Hermes docs" # see recent runs
gh run watch <run-id>                      # follow a run live
```

To change the time, edit the `cron:` line (it is UTC, no daylight-saving). Scheduled
workflows can start a few minutes late under load, and GitHub disables them after 60 days
with no repo activity — the weekly commits normally keep it alive, and you can re-enable
it from the repo's **Actions** tab if it ever pauses.

## Weekly schedule — macOS launchd (optional local alternative)

If you'd rather run it from a specific Mac instead of GitHub, install a launchd job to run
**every Sunday at 18:00** local time (don't run both — they'd both push to `main` and
collide):

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

`crawl_docs.py --refresh-llms` first downloads `llms.txt` from
`https://hermes-agent.nousresearch.com/docs/llms.txt`, validates it, and writes it
atomically (a transient download failure falls back to the existing file). Then, for
each doc URL it:

1. Fetches the rendered HTML (retrying transient failures).
   - Category pages listed as `.../index` are served at `...`, so it falls back to the
     suffix-stripped path on a 404.
   - Client-side redirect stubs (`<meta refresh>`) are followed to the real page.
2. Extracts the `<div class="theme-doc-markdown">` article body, stripping Docusaurus
   heading anchors, decorative inline SVG/`data:` icons, and copy buttons.
3. Converts to GitHub-Flavored Markdown with `pandoc`.
4. Rewrites internal doc links: references to other crawled pages become **local relative
   `.md` paths** (so the corpus is self-contained and navigable, e.g. in Obsidian); links
   to pages not in `llms.txt` become full `https://…` site URLs so they never dead-end.
5. Writes `docs/<mirrored path>.md` with front matter (`source`, `title`, `last_crawled`).

After crawling, it regenerates **`docs/INDEX.md`** — a table of contents mirroring
`llms.txt`'s sections, with each entry linked to its local file. A root **`CLAUDE.md`**
tells Claude Code how the mirror is laid out and how to search it.
