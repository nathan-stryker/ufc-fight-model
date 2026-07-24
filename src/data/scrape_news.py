"""
Scrape recent UFC news headlines from ufc.com/news for the website's News
tab.

robots.txt allows /news and /news?page=N (checked for this script;
crawl-delay: 15s, respected below with a sleep between page fetches) --
ufc.com is already a vetted source in this project (used for the
upcoming-card scraper's segment/title/rank data).

Each article card exposes a clean, consistent structure: headline, teaser
blurb, a category tag (e.g. "Weigh-in", "Fight Coverage"), a thumbnail
image, and a link to the full article. Only that preview data is scraped --
never the article body -- and the site always links out to the real
article on ufc.com rather than reproducing its text, consistent with this
project's policy of never reproducing copyrighted material at length.
Thumbnail images are embedded by URL (hotlinked to ufc.com's own hosting,
same as any news aggregator), not downloaded/re-hosted.

The site's own timestamps ("10 hours ago") are relative to scrape time and
would read as flatly wrong on a site that only refreshes on a schedule
(weekly) -- discarded entirely here rather than displayed stale; the
website instead shows "As of <the date this payload was built>".

Run: python -m src.data.scrape_news
Writes: data/processed/news.csv
"""
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal MMA-stats research script)"}
NEWS_URL = "https://www.ufc.com/news"
PAGES_TO_FETCH = 2  # ~15-20 unique articles -- plenty for a "latest news" list
CRAWL_DELAY_SECONDS = 15  # matches ufc.com's robots.txt


def _absolute_image_url(src):
    if not src:
        return None
    return src if src.startswith("http") else "https://www.ufc.com" + src


def scrape_news(session):
    articles = []
    seen_hrefs = set()
    for page in range(PAGES_TO_FETCH):
        url = NEWS_URL if page == 0 else f"{NEWS_URL}?page={page}"
        resp = session.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.select("a.c-card--grid-card-trending"):
            href = card.get("href", "")
            # Only real /news/ articles -- the same card grid also mixes in
            # /video/ entries (e.g. ceremonial weigh-ins), which have no
            # teaser and aren't a text article to link out to.
            if not href.startswith("/news/") or href in seen_hrefs:
                continue
            headline_el = card.select_one(".c-card--grid-card-trending__headline")
            if not headline_el:
                continue
            seen_hrefs.add(href)
            teaser_el = card.select_one(".field--name-teaser")
            tag_el = card.select_one(".c-card--grid-card-trending__info-prefix")
            img_el = card.select_one("img")
            articles.append({
                "headline": headline_el.get_text(strip=True),
                "teaser": teaser_el.get_text(strip=True) if teaser_el else None,
                "tag": tag_el.get_text(strip=True) if tag_el else None,
                "image_url": _absolute_image_url(img_el.get("src")) if img_el else None,
                "url": "https://www.ufc.com" + href,
            })
        if page < PAGES_TO_FETCH - 1:
            time.sleep(CRAWL_DELAY_SECONDS)
    return articles


def main():
    session = requests.Session()
    articles = scrape_news(session)
    out = pd.DataFrame(articles)
    out_path = PROCESSED_DIR / "news.csv"
    # Explicit UTF-8: pandas defaults to the OS locale encoding on Windows
    # (cp1252), which silently mangles non-ASCII headline characters (e.g.
    # UFC's own "…" truncation marker) on write.
    out.to_csv(out_path, index=False, encoding="utf-8")
    print(f"{len(articles)} articles scraped")
    for a in articles[:8]:
        print(f"  [{a['tag']}] {a['headline']}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
