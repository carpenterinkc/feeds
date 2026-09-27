# Feeds

Turns web pages that have no RSS feed into RSS feeds for Readwise Reader.

- `feeds.toml` lists the sites. Each `[[feed]]` block becomes `https://carpenterinkc.github.io/feeds/<slug>.xml`.
- `build_feeds.py` scrapes each page (Python standard library only), remembers posts in `data/`, and writes feeds to `docs/`.
- `.github/workflows/update-feeds.yml` runs it every 3 hours and commits any changes. GitHub Pages serves `docs/`.

## Adding a site
Add a `[[feed]]` block to `feeds.toml` with a unique `slug`, the page `url`, and a `link_pattern` regex that matches the site's post URLs. Push, then subscribe to the new URL in Reader.

## When something breaks
If a feed finds zero posts or can't load its page, the run fails and GitHub emails the owner. The last good feed is kept, so Reader never goes blank. The usual cause is a site redesign; the `link_pattern` or parser needs a small update.

The public feed list lives at https://carpenterinkc.github.io/feeds/
