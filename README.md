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

## Recipe viewer (docs/recipe/)

`docs/recipe/index.html` is a private recipe viewer for Apple HomeView.  The "Open on HomeView" Shortcut takes the text Paprika shares, puts it in the link after `#r=`, and opens `https://carpenterinkc.github.io/feeds/recipe/`.  The page turns that text into a readable recipe with schema.org Recipe data so Safari on HomeView offers its cooking view.  Recipes live only in the link fragment, which browsers never send to the server, so nothing is stored here.  The ½×, 1×, 2× and 3× buttons scale ingredient quantities and update the link.
