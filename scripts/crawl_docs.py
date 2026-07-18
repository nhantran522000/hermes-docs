#!/usr/bin/env python3
"""Crawl the Hermes Agent documentation listed in llms.txt into local Markdown.

llms.txt is a hand-maintained, checked-in list of pages to crawl (it is NOT fetched
from the site). For every doc URL it lists, this fetches the rendered page, extracts
the main article content, converts it to GitHub-Flavored Markdown with pandoc, and
writes it to docs/<mirrored path>.md. Re-running overwrites existing files, so it
is safe to schedule weekly. Edit llms.txt by hand to add or remove pages.

Requires: requests, beautifulsoup4 (see requirements.txt) and the `pandoc` binary.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LLMS = ROOT / "llms.txt"
DEFAULT_OUT = ROOT / "docs"
DOMAIN = "hermes-agent.nousresearch.com"
DOCS_PREFIX = "/docs/"
SITE = f"https://{DOMAIN}"

TIMEOUT = 30
RETRIES = 4
# Statuses worth retrying with backoff: the docs host has bot protection that can
# briefly 403/429 under load.
RETRYABLE_STATUS = {403, 429, 503}
USER_AGENT = "hermes-docs-crawler/1.0 (+local archival)"
# Force English so output is identical regardless of where the crawl runs (the site
# otherwise localizes by IP, which would make local vs CI crawls churn).
ACCEPT_LANGUAGE = "en-US,en;q=0.9"

# Markdown link: [label](url)
LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^\s)]+)\)")
# <meta http-equiv="refresh" content="0; url=/some/path">
META_REFRESH_RE = re.compile(
    r"http-equiv=[\"']refresh[\"'][^>]*content=[\"'][^\"']*url=([^\"'>]+)", re.I
)
# SSR fallback a few client-only embeds (video tutorials) leave behind: an
# "An error occurred / Unable to execute JavaScript" block, optionally followed by a
# horizontal rule. Localized by the host, so cover the locales we've observed.
ERROR_BOUNDARY_RE = re.compile(
    r"^#{1,6}[ \t]*(?:An error occurred|Đã xảy ra lỗi)\.?[ \t]*\n+"
    r"(?:Unable to execute JavaScript|Không thể chạy JavaScript)\.?[ \t]*\n+"
    r"(?:-{3,}[ \t]*\n+)?",
    re.M,
)

_thread_local = threading.local()


def session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": ACCEPT_LANGUAGE})
        _thread_local.session = s
    return s


def extract_urls(text: str) -> list[str]:
    """Return de-duplicated doc URLs (under the docs domain) in first-seen order."""
    seen: set[str] = set()
    urls: list[str] = []
    for m in LINK_RE.finditer(text):
        u = m.group(1).split("#")[0].rstrip("/")
        p = urlparse(u)
        if p.netloc == DOMAIN and p.path.startswith(DOCS_PREFIX):
            if u not in seen:
                seen.add(u)
                urls.append(u)
    return urls


def url_to_key(url: str) -> str:
    """The '<mirrored path>' key (no .md) a doc URL maps to."""
    path = urlparse(url).path
    rel = path[len(DOCS_PREFIX):] if path.startswith(DOCS_PREFIX) else path.lstrip("/")
    return rel.strip("/") or "index"


def url_to_path(url: str, outdir: Path) -> Path:
    """Map a doc URL to docs/<mirrored path>.md."""
    return outdir / (url_to_key(url) + ".md")


def doc_keys(urls: list[str]) -> set[str]:
    """The set of '<mirrored path>' keys (no .md) for every crawled URL."""
    return {url_to_key(u) for u in urls}


def _resolve_local_key(rel: str, known: set[str]) -> str | None:
    """Given a docs-relative path (no leading /docs/), return the crawled doc key
    it maps to, or None. Handles category pages linked without their /index."""
    rel = rel.strip("/")
    if rel in known:
        return rel
    if f"{rel}/index" in known:
        return f"{rel}/index"
    return None


def rewrite_links(md: str, out: Path, outdir: Path, known: set[str]) -> str:
    """Rewrite in-content doc links: crawled pages -> local relative .md paths
    (so the corpus is self-contained and Obsidian-navigable); non-crawled pages ->
    full clickable site URLs (so they don't become dead local links)."""
    out_dir = out.parent

    def repl(m: "re.Match[str]") -> str:
        url = m.group(1)
        if url.startswith(DOCS_PREFIX):
            docs_path = url
        elif url.startswith(f"{SITE}{DOCS_PREFIX}"):
            docs_path = url[len(SITE):]
        else:
            return m.group(0)  # external / root / anchor-only link: leave as-is
        path_part, sep, frag = docs_path.partition("#")
        if "?" in path_part:
            return m.group(0)
        key = _resolve_local_key(path_part[len(DOCS_PREFIX):], known)
        if key is not None:
            new = Path(os.path.relpath(outdir / f"{key}.md", out_dir)).as_posix()
        else:
            new = f"{SITE}{path_part}"
        return f"]({new}{'#' + frag if sep else ''})"

    return re.sub(r"\]\(([^)\s]+)\)", repl, md)


def _index_link(url: str, known: set[str]) -> str:
    """Link target for INDEX.md (which lives in outdir): local .md path if the URL
    was crawled, else the original URL."""
    p = urlparse(url)
    if p.netloc != DOMAIN or not p.path.startswith(DOCS_PREFIX):
        return url
    key = _resolve_local_key(p.path[len(DOCS_PREFIX):], known)
    return f"{key}.md" if key else url


def generate_index(llms_text: str, outdir: Path, known: set[str], when: str) -> Path:
    """Build docs/INDEX.md by mirroring llms.txt's structure with local links."""
    out_lines = [
        "# Hermes Docs — Local Index",
        "",
        f"> Auto-generated by the crawler on {when}. Rebuilt on every sync — do not edit "
        "by hand. Links point at the local Markdown files in this folder.",
        "",
    ]
    item_re = re.compile(r"^(\s*[-*]\s*)\[([^\]]+)\]\((https?://[^)]+)\)(.*)$")
    dropped_title = False
    for line in llms_text.splitlines():
        if not dropped_title and line.startswith("# "):
            dropped_title = True  # drop llms.txt's own H1; we supply our own above
            continue
        m = item_re.match(line)
        if m:
            prefix, title, url, rest = m.groups()
            out_lines.append(f"{prefix}[{title}]({_index_link(url, known)}){rest}")
        else:
            out_lines.append(line)
    dest = outdir / "INDEX.md"
    dest.write_text("\n".join(out_lines).rstrip() + "\n", encoding="utf-8")
    return dest


def _get(url: str) -> str:
    """GET with retries. Rate-limit/bot statuses (403/429/503) and transient network
    failures are retried with growing backoff; other 4xx raise immediately."""
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            r = session().get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text
        except requests.HTTPError as e:
            sc = e.response.status_code if e.response is not None else None
            if sc is not None and 400 <= sc < 500 and sc not in RETRYABLE_STATUS:
                raise
            last = e
        except requests.RequestException as e:
            last = e
        time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"failed after {RETRIES} attempts: {last}")


def fetch(url: str) -> tuple[str, str]:
    """Return (resolved_url, html).

    Handles two Docusaurus quirks:
      * category pages listed as `.../index` are actually served at `...` (the
        `/index` variant 404s), so fall back to the suffix-stripped path;
      * some guide slugs are client-side redirect stubs (<meta refresh>), which
        we follow to the real page (up to 3 hops).
    """
    candidates = [url]
    if url.endswith("/index"):
        candidates.append(url[: -len("/index")])

    html: str | None = None
    resolved = url
    last: Exception | None = None
    for cand in candidates:
        try:
            html = _get(cand)
            resolved = cand
            break
        except requests.HTTPError as e:
            last = e  # try next candidate (e.g. drop /index)
    if html is None:
        raise RuntimeError(f"failed after {RETRIES} attempts: {last}")

    for _ in range(3):
        m = META_REFRESH_RE.search(html)
        if not m:
            break
        resolved = urljoin(resolved, m.group(1).strip())
        html = _get(resolved)
    return resolved, html


def html_to_markdown(html: str) -> tuple[str, str]:
    """Extract the article body and return (title, markdown)."""
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one("div.theme-doc-markdown") or soup.find("article")
    if node is None:
        raise ValueError("could not locate article content container")

    # Strip Docusaurus "Direct link to heading" anchors.
    for a in node.select("a.hash-link"):
        a.decompose()
    # Drop decorative icons: inline <svg> (pandoc would base64-encode these as
    # data-URI images) and any <img> with a data: source, plus UI buttons.
    for svg in node.find_all("svg"):
        svg.decompose()
    for img in node.find_all("img"):
        if (img.get("src") or "").startswith("data:"):
            img.decompose()
    for btn in node.find_all("button"):
        btn.decompose()

    proc = subprocess.run(
        ["pandoc", "-f", "html", "-t", "gfm-raw_html", "--wrap=none"],
        input=str(node),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pandoc failed: {proc.stderr.strip()}")

    md = proc.stdout
    # Safety net: drop any base64 data-URI images pandoc still emitted.
    md = re.sub(r"!\[[^\]]*\]\(data:[^)]*\)", "", md)
    # Drop client-only-embed SSR error fallbacks.
    md = ERROR_BOUNDARY_RE.sub("", md)
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    m = re.search(r"^#\s+(.+)$", md, re.M)
    title = m.group(1).strip() if m else ""
    return title, md


def front_matter(url: str, title: str, when: str) -> str:
    safe_title = title.replace('"', "'")
    return (
        "---\n"
        f'source: "{url}"\n'
        f'title: "{safe_title}"\n'
        f"last_crawled: {when}\n"
        "---\n\n"
    )


def process(url: str, outdir: Path, when: str, known: set[str]) -> Path:
    resolved, html = fetch(url)
    title, md = html_to_markdown(html)
    if not title:
        title = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    out = url_to_path(url, outdir)
    md = rewrite_links(md, out, outdir, known)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(front_matter(resolved, title, when) + md + "\n", encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Crawl Hermes docs from llms.txt into Markdown.")
    ap.add_argument("--llms", type=Path, default=DEFAULT_LLMS, help="Path to llms.txt")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output docs directory")
    ap.add_argument("--workers", type=int, default=6, help="Concurrent fetches")
    ap.add_argument("--only", default=None, help="Only crawl URLs containing this substring (for testing)")
    args = ap.parse_args()

    if subprocess.run(["pandoc", "--version"], capture_output=True).returncode != 0:
        print("ERROR: pandoc is required but not runnable.", file=sys.stderr)
        return 2

    if not args.llms.exists():
        print(f"ERROR: {args.llms} not found.", file=sys.stderr)
        return 2

    llms_text = args.llms.read_text(encoding="utf-8")
    all_urls = extract_urls(llms_text)
    # Link rewriting keys off the full corpus, so results are identical whether or
    # not --only narrows what actually gets fetched.
    known = doc_keys(all_urls)
    urls = [u for u in all_urls if args.only in u] if args.only else all_urls
    if not urls:
        print("No doc URLs found to crawl.", file=sys.stderr)
        return 1

    when = datetime.date.today().isoformat()
    print(f"Crawling {len(urls)} pages -> {args.out} (workers={args.workers})")

    ok: list[Path] = []
    failed: list[tuple[str, str]] = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process, u, args.out, when, known): u for u in urls}
        for fut in cf.as_completed(futures):
            u = futures[fut]
            try:
                path = fut.result()
                ok.append(path)
                print(f"  ok   {path.relative_to(ROOT)}")
            except Exception as e:  # noqa: BLE001
                failed.append((u, str(e)))
                print(f"  FAIL {u}\n         {e}", file=sys.stderr)

    print(f"\nDone: {len(ok)} saved, {len(failed)} failed.")

    # Regenerate the local index from the full page list (skip during --only tests).
    if not args.only:
        index = generate_index(llms_text, args.out, known, when)
        print(f"Wrote {index.relative_to(ROOT)}")

    if failed:
        print("Failures:", file=sys.stderr)
        for u, e in failed:
            print(f"  {u} :: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
