#!/usr/bin/env python3
"""Feed factory: turn web pages without RSS into RSS feeds.

Reads feeds.toml, scrapes each listing page, remembers what it has seen in
data/<slug>.json, and writes docs/<slug>.xml (served by GitHub Pages).

Standard library only, so there is nothing to install.
Exits non-zero if any feed fails, so GitHub Actions flags the run.
A failed feed keeps its last good XML; it is never overwritten with nothing.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import tomllib
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) feed-factory/1.0"
MAX_ITEMS = 50          # items kept in each feed
MAX_DETAIL_FETCHES = 20  # new posts per feed per run that get a description
DATE_RE = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? +\d{1,2}, +\d{4}"
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_date(text: str) -> datetime | None:
    m = DATE_RE.search(text or "")
    if not m:
        return None
    raw = re.sub(r"\s+", " ", m.group(0).replace(".", ""))
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            # Noon UTC so the date never slips to the previous day in US time zones.
            return datetime.strptime(raw, fmt).replace(hour=12, tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


class ListingParser(HTMLParser):
    """Collects post links in page order.

    Title: the nearest Finsweet 'heading' field, else data-cta-copy, else link text.
    Date: the nearest 'date' field, else any date-looking text since the last post.
    Works on Webflow blog listings and degrades gracefully elsewhere.
    """

    def __init__(self, base: str, pattern: re.Pattern):
        super().__init__(convert_charrefs=True)
        self.base, self.pattern = base, pattern
        self.posts: dict[str, dict] = {}
        self.order: list[str] = []
        self._field = None       # 'heading' | 'date' while inside such a div
        self._depth = 0
        self._heading = ""
        self._date = ""
        self._recent_text = ""
        self._in_link = None
        self._link_text = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self._field:
            self._depth += 1
        field = a.get("fs-list-field")
        if field in ("heading", "date") and not self._field:
            self._field, self._depth = field, 1
            if field == "heading":
                self._heading = ""
            else:
                self._date = ""
        if tag == "a" and a.get("href"):
            url = urljoin(self.base, a["href"].split("#")[0].split("?")[0])
            if self.pattern.search(url):
                self._in_link = url
                self._link_text = ""
                self._cta = a.get("data-cta-copy", "")

    def handle_endtag(self, tag):
        if self._field:
            self._depth -= 1
            if self._depth <= 0:
                self._field = None
        if tag == "a" and self._in_link:
            url = self._in_link
            title = (self._heading or self._cta or self._link_text).strip()
            date = parse_date(self._date) or parse_date(self._recent_text)
            post = self.posts.get(url)
            if post is None:
                self.posts[url] = {"url": url, "title": title, "date": date}
                self.order.append(url)
            else:
                if len(title) > len(post["title"]):
                    post["title"] = title
                post["date"] = post["date"] or date
            self._in_link = None
            self._recent_text = ""

    def handle_data(self, data):
        if self._field == "heading":
            self._heading += data
        elif self._field == "date":
            self._date += data
        if self._in_link:
            self._link_text += data
        self._recent_text = (self._recent_text + " " + data)[-400:]


def page_meta(url: str) -> dict:
    """Description and image from a post page's meta tags."""
    try:
        h = fetch(url)
    except Exception as e:  # a missing description is not worth failing the run
        print(f"  ! could not read {url}: {e}")
        return {}

    def meta(*names):
        for n in names:
            for pat in (
                rf'<meta[^>]+(?:property|name)="{n}"[^>]+content="([^"]*)"',
                rf'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="{n}"',
            ):
                m = re.search(pat, h)
                if m:
                    return html.unescape(m.group(1)).strip()
        return ""

    return {
        "description": meta("og:description", "description", "twitter:description"),
        "image": meta("og:image", "twitter:image"),
        "published": meta("article:published_time"),
    }


def build_rss(feed: dict, items: list[dict], self_url: str) -> str:
    now = format_datetime(datetime.now(timezone.utc))
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"<title>{escape(feed['title'])}</title>",
        f"<link>{escape(feed['url'])}</link>",
        f"<description>{escape(feed.get('description', 'Updates from ' + feed['url']))}</description>",
        f'<atom:link href="{escape(self_url)}" rel="self" type="application/rss+xml"/>',
        "<language>en</language>",
        f"<lastBuildDate>{now}</lastBuildDate>",
    ]
    for it in items:
        body = ""
        if it.get("image"):
            body += f'<p><img src="{html.escape(it["image"])}" alt=""/></p>'
        if it.get("description"):
            body += f"<p>{html.escape(it['description'])}</p>"
        body += f'<p><a href="{html.escape(it["url"])}">Read the full post</a></p>'
        out += [
            "<item>",
            f"<title>{escape(it['title'])}</title>",
            f"<link>{escape(it['url'])}</link>",
            f'<guid isPermaLink="true">{escape(it["url"])}</guid>',
            f"<pubDate>{format_datetime(datetime.fromisoformat(it['date']))}</pubDate>",
            f"<description>{escape(body)}</description>",
            "</item>",
        ]
    out += ["</channel>", "</rss>", ""]
    return "\n".join(out)


def run_feed(feed: dict, pages_base: str) -> None:
    slug = feed["slug"]
    print(f"• {slug}: {feed['url']}")
    pattern = re.compile(feed.get("link_pattern", r"/blog/[^/]+/?$"))
    parser = ListingParser(feed["url"], pattern)
    parser.feed(fetch(feed["url"]))
    found = [parser.posts[u] for u in parser.order if parser.posts[u]["title"]]
    if not found:
        raise RuntimeError("found 0 posts; the page layout may have changed")
    print(f"  found {len(found)} posts on the page")

    state_file = DATA / f"{slug}.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    fetched = 0
    for p in found:
        rec = state.get(p["url"])
        if rec is None:
            rec = {"url": p["url"], "first_seen": now.isoformat()}
            if fetched < MAX_DETAIL_FETCHES:
                rec.update(page_meta(p["url"]))
                fetched += 1
                time.sleep(1)  # be polite
            state[p["url"]] = rec
            print(f"  + new: {p['title']}")
        rec["title"] = p["title"]
        date = p["date"] or parse_date(rec.get("published", "")) or None
        rec["date"] = (date or datetime.fromisoformat(rec["first_seen"])).isoformat()

    items = sorted(state.values(), key=lambda r: r["date"], reverse=True)[:MAX_ITEMS]
    keep = {i["url"] for i in items}
    state = {u: r for u, r in state.items() if u in keep}

    DATA.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    self_url = f"{pages_base}/{slug}.xml"
    (DOCS / f"{slug}.xml").write_text(build_rss(feed, items, self_url))


def write_index(feeds: list[dict], pages_base: str) -> None:
    rows = "\n".join(
        f'<li><strong>{html.escape(f["title"])}</strong><br>'
        f'<code>{html.escape(pages_base)}/{f["slug"]}.xml</code><br>'
        f'<small>from <a href="{html.escape(f["url"])}">{html.escape(f["url"])}</a></small></li>'
        for f in feeds
    )
    (DOCS / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Feeds</title>"
        "<style>body{font:16px/1.5 -apple-system,sans-serif;max-width:720px;margin:40px auto;padding:0 16px}"
        "li{margin:0 0 18px}code{user-select:all}</style>"
        f"<h1>Feeds</h1><ul>{rows}</ul>\n"
    )


def main() -> int:
    cfg = tomllib.loads((ROOT / "feeds.toml").read_text())
    pages_base = cfg["pages_base"].rstrip("/")
    failures = []
    for feed in cfg["feed"]:
        try:
            run_feed(feed, pages_base)
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            failures.append(f"{feed['slug']}: {e}")
    DOCS.mkdir(exist_ok=True)
    (DOCS / ".nojekyll").write_text("")
    write_index(cfg["feed"], pages_base)
    if failures:
        print("\nFailed feeds (their last good version was kept):")
        print("\n".join(f"  - {f}" for f in failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
