# hermes-docs

A local Markdown mirror of the **Hermes Agent** documentation
(<https://hermes-agent.nousresearch.com/docs>), auto-synced weekly. Use it as the source
of truth when answering questions about Hermes Agent.

## Layout

- `docs/` — one Markdown file per docs page, mirroring the site's URL paths
  (e.g. `docs/user-guide/features/skills.md`). Each file starts with front matter giving
  its `source` URL, `title`, and `last_crawled` date.
- `docs/INDEX.md` — generated table of contents: every page's title + one-line
  description, linked to its local file, grouped by section. **Start here** to map a
  topic to a file.
- `llms.txt` — the hand-maintained, checked-in page list the crawl is driven from (a set
  of `- [Title](url)` links grouped under `##` sections). It is **not** generated or fetched
  from the site; edit it by hand to add/remove pages from the crawl.
- `scripts/` — the crawler and automation; see `scripts/README.md`.

## Answering questions about Hermes

1. Open `docs/INDEX.md` and find the topic, **or**
2. Full-text search the corpus: `rg -i "<term>" docs/`

Then read the matching file(s). Internal links between crawled pages are local relative
paths (e.g. `../reference/cli-commands.md`), so you can follow references directly; links
to pages not in `llms.txt` remain full `https://…` site URLs.

## Important

- Everything under `docs/` (including `docs/INDEX.md`) is **generated** — do not edit it
  by hand. It is overwritten on every sync: weekly via GitHub Actions
  (`.github/workflows/sync-docs.yml`), or on demand with `scripts/sync-docs.sh`.
- To refresh manually: `scripts/sync-docs.sh` (crawl → commit → push) or
  `scripts/crawl-docs.sh` (crawl only, no git). `llms.txt` itself is edited by hand, not
  refreshed by these scripts.
