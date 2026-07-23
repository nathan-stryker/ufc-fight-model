"""
Scrape the next upcoming UFC event's fight card from Sherdog.com, for the
website's "This Week's Card" home section.

Same source and due-diligence as scrape_nationality.py: Sherdog's
robots.txt allows unrestricted crawling (checked again for this script),
whereas ufc.com's own events pages carry a 15s crawl-delay -- fine for a
handful of pages, but Sherdog is already the vetted, established source in
this project, so reused for consistency rather than adding a second scraper
pattern for one feature.

Fighter names are matched against our own fighters.csv by EXACT normalized
name only -- no fuzzy fallback. This mirrors the explicit decision made for
the nationality gap (see manual_nationality_overrides.py's docstring): a
plausible-but-wrong automated match is the worst failure mode for a name
matcher, and unlike that one-time backlog, this runs unattended every week
with no one to sanity-check individual guesses. A genuine UFC debutant is
ALSO expected to miss here (they have no fight history in our data at all,
so there'd be nothing to predict from even with a perfect name match) --
the site shows unmatched fighters as plain text with no "Call This Fight"
button rather than guessing.

Run: python -m src.data.scrape_upcoming_card
Writes: data/processed/upcoming_card.csv
"""
import re
import unicodedata
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal MMA-stats research script)"}
ORG_URL = "https://www.sherdog.com/organizations/Ultimate-Fighting-Championship-UFC-2"

# Hand-verified name variants between Sherdog's card listing and our own
# UFCStats-derived fighters.csv (e.g. a fuller/shorter form of the same
# given name) -- extend this dict, don't add fuzzy matching, if a future
# week reports an unmatched fighter you can personally confirm is the same
# person. Keyed by Sherdog's normalized name -> our normalized name.
NAME_ALIASES = {
    # Sherdog lists his full given name; UFCStats/our fighters.csv has the
    # short form. Same Uzbek fighter (also in manual_nationality_overrides.py
    # as "Ramazan Temirov" -> Uzbekistan) -- confirmed by weight class +
    # opponent match on the UFC Fight Night 282 card, not a guess.
    "ramazonbek temirov": "ramazan temirov",
}


def normalize_name(name):
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def find_next_event(session):
    """Sherdog's org page lists upcoming events in ascending date order --
    the first row in the 'Upcoming Events' tab is always the soonest."""
    resp = session.get(ORG_URL, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    upcoming_tab = soup.select_one("#upcoming_tab")
    row = upcoming_tab.select_one("tr[itemscope]")
    name = row.select_one('[itemprop="name"]').get_text(strip=True)
    date = row.select_one('[itemprop="startDate"]')["content"][:10]
    location = row.select_one('[itemprop="location"]').get_text(strip=True)
    url = "https://www.sherdog.com" + row.select_one('a[itemprop="url"]')["href"]
    return {"event_name": name, "event_date": date, "event_location": location, "event_url": url}


def scrape_card(session, event_url):
    """Bout order in the page is card billing order (main event first) --
    both the header main-event block and every table row below carry an
    itemprop="subEvent" node with its own meta[itemprop=name] content
    formatted as 'Fighter A vs Fighter B', which sidesteps needing two
    different parsers for the header's plain-text names vs the table's
    <br>-split ones."""
    resp = session.get(event_url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    bouts = []
    for node in soup.select('[itemprop="subEvent"]'):
        name_meta = node.select_one('meta[itemprop="name"]')
        if not name_meta or " vs " not in name_meta.get("content", ""):
            continue
        fighter_a, fighter_b = name_meta["content"].split(" vs ", 1)
        wc_el = node.select_one(".weight_class")
        bouts.append({
            "fighter_a_name": fighter_a.strip(),
            "fighter_b_name": fighter_b.strip(),
            "weight_class": wc_el.get_text(strip=True) if wc_el else None,
        })
    return bouts


def match_fighter_ids(bouts):
    fighters = pd.read_csv(PROCESSED_DIR / "fighters.csv")
    by_norm_name = {}
    for row in fighters.itertuples():
        by_norm_name.setdefault(normalize_name(row.name), row.fighter_id)

    for b in bouts:
        for side in ("fighter_a_name", "fighter_b_name"):
            key = normalize_name(b[side])
            key = NAME_ALIASES.get(key, key)
            b[side.replace("_name", "_id")] = by_norm_name.get(key)
    return bouts


def main():
    session = requests.Session()
    event = find_next_event(session)
    bouts = scrape_card(session, event["event_url"])
    bouts = match_fighter_ids(bouts)

    rows = []
    for i, b in enumerate(bouts, 1):
        rows.append({**event, "bout_order": i, **b})
    out = pd.DataFrame(rows)
    out_path = PROCESSED_DIR / "upcoming_card.csv"
    out.to_csv(out_path, index=False)

    matched = sum(1 for b in bouts if b["fighter_a_id"] and b["fighter_b_id"])
    print(f"{event['event_name']} ({event['event_date']}, {event['event_location']})")
    print(f"{len(bouts)} bouts, {matched} fully matched to our fighter data")
    for b in bouts:
        tag = "" if (b["fighter_a_id"] and b["fighter_b_id"]) else "  <-- unmatched"
        print(f"  [{b['weight_class']}] {b['fighter_a_name']} vs {b['fighter_b_name']}{tag}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
