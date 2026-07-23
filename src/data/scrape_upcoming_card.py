"""
Scrape the next upcoming UFC event's fight card for the website's "This
Week's Card" home section.

Two sources, deliberately combined rather than picking one:
- Sherdog.com for event discovery + metadata (name/date/location) -- the
  established, vetted source in this project (unrestricted robots.txt,
  clean itemprop microdata), unchanged from the original version of this
  script.
- ufc.com for the actual bout list, card-segment membership (Main Card /
  Prelims / Early Prelims), and title-fight detection. This replaces the
  original fixed `MAIN_CARD_SIZE = 5` positional guess -- confirmed live
  while building this that real cards do NOT always have exactly 5 main
  card bouts (one real Fight Night card had 6), so the guess was silently
  wrong for any card that didn't match the "standard" count. ufc.com's
  event pages expose explicit `#main-card`/`#prelims-card`/`#early-prelims`
  containers with real segment membership instead of guessing from
  position, plus each bout's weight-class text distinguishes a normal bout
  ("Light Heavyweight Bout") from a title bout ("Welterweight Title Bout"),
  which Sherdog's listing doesn't expose at all.
  ufc.com's robots.txt has a 15s crawl-delay, ruled impractical earlier
  only for the ~800-fighter nationality bulk scrape -- fine here since this
  script only ever fetches ~2 ufc.com pages (the /events list + one event
  page) per run.

ufc.com is used opportunistically, not as a hard dependency: its segment
containers are only reliably populated once an event is close (a distant
future PPV can go months without a finalized main-card/prelims split, only
carrying one flat "how to watch" bout list instead) -- see
`scrape_card_ufc_com`. If ufc.com's event page doesn't parse cleanly, its
date doesn't match the Sherdog event we're looking for (guards against
silently mixing data from two different events), or its main-card segment
comes back empty, this falls back to the original Sherdog-only scrape +
positional tier heuristic so the card still ships (missing the real
segment/title-fight data, same degrade-gracefully philosophy as the flag
scraper) rather than the whole feature failing.

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
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal MMA-stats research script)"}
ORG_URL = "https://www.sherdog.com/organizations/Ultimate-Fighting-Championship-UFC-2"
UFC_EVENTS_URL = "https://www.ufc.com/events"

# Fallback-only now (used when ufc.com's segment data isn't available for the
# next event -- see module docstring). No longer the primary tiering method.
MAIN_CARD_SIZE = 5


def assign_tiers(bouts):
    """Positional fallback: main event=index 0, co-main=index 1, featured
    prelim=index MAIN_CARD_SIZE. Only used when ufc.com's real segment data
    (assign_tiers_ufc) isn't available for this event."""
    n = len(bouts)
    for i, b in enumerate(bouts):
        if i == 0:
            b["tier"] = "main_event"
        elif i == 1 and n > 1:
            b["tier"] = "co_main"
        elif i < MAIN_CARD_SIZE:
            b["tier"] = "main_card"
        elif i == MAIN_CARD_SIZE:
            b["tier"] = "featured_prelim"
        else:
            b["tier"] = "prelim"
        b["is_title_fight"] = False  # Sherdog's listing carries no title-fight signal
    return bouts


def _strip_bout_suffix(text):
    return re.sub(r"\s+(Title\s+)?Bout$", "", text).strip()


def find_next_ufc_com_event_url(session):
    """ufc.com's events page lists upcoming events in ascending date order,
    same convention as Sherdog's org page -- first event link in the
    upcoming block is the soonest."""
    resp = session.get(UFC_EVENTS_URL, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    container = soup.select_one("#events-list-upcoming")
    if not container:
        return None
    a = container.select_one('a[href^="/event/"]')
    if not a:
        return None
    return "https://www.ufc.com" + a["href"].split("#")[0]


def _extract_segment_bouts(container):
    if not container:
        return []
    bouts = []
    for f in container.select(".c-listing-fight"):
        red = f.select_one(".c-listing-fight__corner-name--red")
        blue = f.select_one(".c-listing-fight__corner-name--blue")
        if not red or not blue:
            continue
        cls_el = (
            f.select_one(".c-listing-fight__class--desktop .c-listing-fight__class-text")
            or f.select_one(".c-listing-fight__class-text")
        )
        wc_raw = cls_el.get_text(strip=True) if cls_el else None
        bouts.append({
            "fighter_a_name": red.get_text(" ", strip=True),
            "fighter_b_name": blue.get_text(" ", strip=True),
            "weight_class": _strip_bout_suffix(wc_raw) if wc_raw else None,
            "is_title_fight": bool(wc_raw) and "title" in wc_raw.lower(),
        })
    return bouts


def scrape_card_ufc_com(session, event_url, expected_date):
    """Returns None (triggering the Sherdog fallback) if the page doesn't
    parse as expected, its date doesn't match the Sherdog event we're
    looking for, or its main-card segment is empty (happens for distant
    future events that ufc.com hasn't broken into main-card/prelims yet)."""
    resp = session.get(event_url, headers=HEADERS, timeout=15)
    html = resp.text
    date_match = re.search(r"On ([A-Za-z]+ \d{1,2}, \d{4})", html)
    if not date_match:
        return None
    try:
        parsed_date = datetime.strptime(date_match.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None
    if parsed_date != expected_date:
        return None

    soup = BeautifulSoup(html, "html.parser")
    main_card = _extract_segment_bouts(soup.select_one("#main-card"))
    if not main_card:
        return None
    prelims = _extract_segment_bouts(soup.select_one("#prelims-card"))
    early_prelims = _extract_segment_bouts(soup.select_one("#early-prelims"))
    return {"main_card": main_card, "prelims": prelims, "early_prelims": early_prelims}


def assign_tiers_ufc(segments):
    """Real segment membership from ufc.com, not a position guess. Within
    each segment, bout order is prominence-descending (most prominent
    first) -- confirmed live: a Fight Night main-card's first listed bout
    was literally the event's own namesake main event -- so index 0 within
    main_card is the main event, index 1 the co-main; index 0 within
    prelims (or early_prelims if prelims is empty) is the featured prelim,
    same "most prominent prelim, fought last chronologically" convention
    the original positional heuristic used."""
    bouts = []
    for i, b in enumerate(segments["main_card"]):
        b["tier"] = "main_event" if i == 0 else ("co_main" if i == 1 else "main_card")
        bouts.append(b)

    prelim_list = segments["prelims"] if segments["prelims"] else segments["early_prelims"]
    leftover_early = segments["early_prelims"] if segments["prelims"] else []
    for i, b in enumerate(prelim_list):
        b["tier"] = "featured_prelim" if i == 0 else "prelim"
        bouts.append(b)
    for b in leftover_early:
        b["tier"] = "prelim"
        bouts.append(b)
    return bouts

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

    source = "sherdog (fallback)"
    bouts = None
    try:
        ufc_url = find_next_ufc_com_event_url(session)
        if ufc_url:
            segments = scrape_card_ufc_com(session, ufc_url, event["event_date"])
            if segments:
                bouts = assign_tiers_ufc(segments)
                source = "ufc.com"
    except requests.RequestException as e:
        print(f"ufc.com fetch failed ({e}), falling back to Sherdog")

    if bouts is None:
        bouts = assign_tiers(scrape_card(session, event["event_url"]))

    bouts = match_fighter_ids(bouts)

    rows = []
    for i, b in enumerate(bouts, 1):
        rows.append({**event, "bout_order": i, **b})
    out = pd.DataFrame(rows)
    out_path = PROCESSED_DIR / "upcoming_card.csv"
    out.to_csv(out_path, index=False)

    matched = sum(1 for b in bouts if b["fighter_a_id"] and b["fighter_b_id"])
    titles = sum(1 for b in bouts if b["is_title_fight"])
    print(f"{event['event_name']} ({event['event_date']}, {event['event_location']})")
    print(f"source: {source}")
    print(f"{len(bouts)} bouts, {matched} fully matched to our fighter data, {titles} title fight(s)")
    for b in bouts:
        tag = "" if (b["fighter_a_id"] and b["fighter_b_id"]) else "  <-- unmatched"
        belt = "  [TITLE]" if b["is_title_fight"] else ""
        print(f"  [{b['tier']:>14}] [{b['weight_class']}] {b['fighter_a_name']} vs {b['fighter_b_name']}{belt}{tag}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
