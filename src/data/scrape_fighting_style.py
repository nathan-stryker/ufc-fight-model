"""
Scrape each active fighter's UFC.com-listed "Fighting style" (a single
short tag like "Sambo", "Kickboxer", "Wrestling", "Muay Thai" -- UFC's own
editorial label, not derived from our own stats) for the website's fighter
cards and the "record vs. opponent's style" feature.

Scoped to the active roster only, same population and same
get_active_fighters() as scrape_nationality.py -- for the identical reason
(a fighter's website card only needs this for people you could plausibly
book a fight for; historical opponents outside this window simply won't
have a known style, and any feature built on this data has to treat that
as "unknown", not "no style").

ufc.com's robots.txt sets a site-wide `crawl-delay: 15` (checked directly --
individual /athlete/<slug> pages are NOT in its Disallow list, only the
bulk /athletes/all?* listing is), so honored here at the same 15s pace.
For ~750-800 active fighters this is a 3+ hour run -- expected, same
tradeoff already accepted for Sherdog's nationality scrape, just slower
per-request. Resumable for the same reason (a multi-hour scrape WILL get
interrupted sometimes).

No compliant way to SEARCH ufc.com for a fighter by name (robots.txt also
disallows /search) -- unlike Sherdog's nationality scrape, there's no
search-page fallback available if a direct URL guess is wrong. The athlete
URL is guessed as a lowercase-hyphenated, ASCII-transliterated version of
the fighter's name (matches UFC.com's own slug convention for the fighters
checked by hand: "Islam Makhachev" -> /athlete/islam-makhachev). A wrong
guess 404s and is skipped, not force-matched -- same "omit, don't guess"
rule as the rest of this project's scrapers. Fighters whose UFC.com slug
uses a fuller legal name (e.g. "Jose Delgado" -> /athlete/jose-miguel-delgado)
will 404 on the plain guess and need a MANUAL_SLUGS entry, same pattern as
scrape_prefight_history.py's MANUAL_SHERDOG_URLS.

Run: python -m src.data.scrape_fighting_style
Writes: data/processed/fighter_style.csv
"""
import re
import time
import unicodedata
import socket
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.data.scrape_nationality import get_active_fighters

# requests' own per-call `timeout=` only bounds an already-established
# socket's connect/read phases -- it does NOT bound the OS-level DNS
# lookup (getaddrinfo) requests goes through first. Confirmed hitting this
# directly: this multi-hour scrape hung indefinitely twice in one session
# (each time coinciding with the machine coming back from sleep), with
# `timeout=15` on every call and the process still showing as "alive" but
# making zero progress for 40+ minutes -- a stale post-sleep DNS/socket
# state that outlives the per-request timeout. socket.setdefaulttimeout()
# applies to that lower-level call too, so a hang here now raises instead
# of blocking forever.
socket.setdefaulttimeout(30)

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
REQUEST_DELAY_SECONDS = 15.0  # ufc.com robots.txt: crawl-delay: 15 (site-wide)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal MMA-stats research script)"}
ATHLETE_URL = "https://www.ufc.com/athlete/{slug}"

# name -> known-correct slug, for fighters whose guessed slug 404s (UFC.com
# uses a fuller legal name in the URL than the short ring name elsewhere in
# this project's data). Confirmed by hand, same discipline as
# scrape_prefight_history.py's MANUAL_SHERDOG_URLS.
MANUAL_SLUGS = {
    "jose delgado": "jose-miguel-delgado",
}


def _slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    return re.sub(r"\s+", "-", s)


def get_fighting_style(session, name):
    """
    Returns the "Fighting style" bio field text, or None if the athlete
    page doesn't exist (wrong slug guess) or the field itself is missing
    (a freshly-signed prospect UFC.com hasn't tagged with a real style
    yet -- shows up as the generic "MMA" on the site, which IS a real,
    if uninformative, value, not something to filter out here).
    """
    key = re.sub(r"\s+", " ", name.strip().lower())
    slug = MANUAL_SLUGS.get(key, _slugify(name))
    resp = session.get(ATHLETE_URL.format(slug=slug), headers=HEADERS, timeout=15)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for field in soup.select("div.c-bio__field"):
        label = field.select_one(".c-bio__label")
        if label and label.get_text(strip=True).lower() == "fighting style":
            text_el = field.select_one(".c-bio__text")
            return text_el.get_text(strip=True) if text_el else None
    return None


def main():
    fighters = get_active_fighters()
    out_path = PROCESSED_DIR / "fighter_style.csv"

    # Resumable: same reasoning as scrape_nationality.py -- a 3+ hour run
    # WILL get interrupted (network blip, machine sleep) sometimes. Keep
    # already-resolved rows, only retry fighters with no style yet.
    done = {}
    if out_path.exists():
        prior = pd.read_csv(out_path)
        done = {r["fighter_id"]: r for r in prior.to_dict("records") if pd.notna(r.get("style"))}
        print(f"resuming: {len(done)} fighters already matched from a prior run, skipping those")

    todo = fighters[~fighters["fighter_id"].isin(done.keys())]
    print(f"{len(fighters)} active fighters total, {len(todo)} to (re)scrape "
          f"(~{len(todo) * REQUEST_DELAY_SECONDS / 3600:.1f}h at the required 15s/request pace)\n")

    session = requests.Session()
    rows = list(done.values())
    for i, row in enumerate(todo.itertuples(), 1):
        result = {"fighter_id": row.fighter_id, "name": row.name, "style": None}
        try:
            style = get_fighting_style(session, row.name)
            result["style"] = style
            print(f"[{i}/{len(todo)}] {row.name} -> {style if style else 'no match / no field'}")
        except Exception as e:
            print(f"[{i}/{len(todo)}] {row.name} -> ERROR {e}")
        rows.append(result)
        time.sleep(REQUEST_DELAY_SECONDS)

        if i % 25 == 0:
            pd.DataFrame(rows).to_csv(out_path, index=False)

    out = pd.DataFrame(rows)
    out.to_csv(out_path, index=False)
    matched = out["style"].notna().sum()
    print(f"\nmatched {matched}/{len(out)} ({matched / len(out):.1%})")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
