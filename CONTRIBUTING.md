# Contributing

This repo is a **generated mirror** of the Hermes Agent docs, so most contributions are
small changes to the crawl setup — not edits to the docs themselves.

## What lives where

- `docs/` (including `docs/INDEX.md`) — **generated**, overwritten on every sync. Don't
  edit it by hand; your changes will be clobbered.
- `llms.txt` — the hand-maintained list of pages to crawl. **Edit this by hand** to add or
  remove a page: a `- [Title](https://…/docs/…)` line under the right `##` section.
- `scripts/` — the crawler and automation; see `scripts/README.md`.
- `CLAUDE.md` — notes on how the mirror is laid out and how to search it.

## Running locally

Requirements: `pandoc` (keep it on the same version the CI workflow pins, currently 3.9,
to avoid formatting churn) and Python 3. The wrapper creates a virtualenv and installs
`requests` + `beautifulsoup4` on first run.

```bash
scripts/crawl-docs.sh                 # crawl every page in llms.txt (no git)
scripts/crawl-docs.sh --only cli      # only URLs containing "cli" (quick test)
scripts/sync-docs.sh                  # full job: crawl -> commit -> push
```

Logs go to `.crawl-logs/` (gitignored). If the site's bot protection gives you
persistent 403s, wait a few minutes or lower `--workers`.

## Proposing a change

1. Fork / branch off `main`.
2. Make your change — e.g. edit `llms.txt` to add a page, or touch the scripts.
3. Test it: `scripts/crawl-docs.sh --only <slug>` for an added page, or a full
   `scripts/crawl-docs.sh` run, and check the resulting `docs/` diff.
4. Open a pull request describing what changed and why.

Sync commits are normally made by the weekly GitHub Actions job (or `sync-docs.sh`), so
PRs should stick to `llms.txt`, `scripts/`, and docs; never hand-edit `docs/`.
