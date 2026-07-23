"""
Scrape fighter nationality (for country flags on the website) from
Sherdog.com, for currently-active UFC fighters only -- deliberately
narrow scope: our own historical fight data has to stay complete for
EVERY fighter regardless of activity status (an active fighter's Elo and
rolling-form features depend on fights against opponents who have since
retired, so nothing gets deleted from the training pipeline), but the
website's fighter picker only needs flags for people you could plausibly
book a fight for at this point.

"Active" = fought within the last ACTIVE_WINDOW_MONTHS, using data already
in fighter_snapshot.csv -- no new source needed for that half of this.

Sherdog's robots.txt allows unrestricted crawling (checked before writing
this -- ufc.com's own roster pages specify a 15s crawl-delay, which would
take 3+ hours for ~800 fighters and was ruled out for that reason). Still
rate-limited politely here regardless of what's technically allowed.

Sherdog fighter URLs aren't guessable from a name (verified the hard way --
an early manual test guessed a URL and silently landed on a *different*
fighter's profile). Every fighter is looked up via Sherdog's own search
first, matched by exact normalized name against the search results, and
skipped (not guessed) if nothing matches exactly.

Run: python -m src.data.scrape_nationality
Writes: data/processed/fighter_nationality.csv
"""
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
ACTIVE_WINDOW_MONTHS = 24
REQUEST_DELAY_SECONDS = 1.0
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal MMA-stats research script)"}
SEARCH_URL = "https://www.sherdog.com/stats/fightfinder?SearchTxt={query}"


def normalize_name(name):
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def get_active_fighters():
    fighters = pd.read_csv(PROCESSED_DIR / "fighters.csv")
    snapshot = pd.read_csv(PROCESSED_DIR / "fighter_snapshot.csv", parse_dates=["last_fight_date"])
    cutoff = pd.Timestamp.now() - pd.DateOffset(months=ACTIVE_WINDOW_MONTHS)
    active_ids = snapshot.loc[snapshot["last_fight_date"] >= cutoff, "fighter_id"]
    return fighters[fighters["fighter_id"].isin(active_ids)][["fighter_id", "name"]].reset_index(drop=True)


def _camel_split(name):
    """'SeungWoo Choi' -> 'Seung Woo Choi' -- UFCStats concatenates some
    Korean given names with no space; Sherdog lists them spaced."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)


def _reversed_name(name):
    """'Zhang Weili' -> 'Weili Zhang' -- UFCStats lists some Chinese
    fighters surname-first; Sherdog lists them given-name-first."""
    parts = name.split()
    return " ".join(reversed(parts)) if len(parts) > 1 else name


def _search_once(session, query):
    resp = session.get(SEARCH_URL.format(query=quote(query)), headers=HEADERS, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    return soup.select("table.fightfinder_result a[href^='/fighter/']")


def find_sherdog_url(session, name):
    """
    Sherdog's own search has no relevance ranking -- results are a plain
    alphabetical-by-first-name listing, 20 per page, with no way to query
    first/last name separately. For a common surname this makes the right
    person arbitrarily deep (confirmed by hand: "Jon Jones" is on page 22),
    so blindly paging through search results isn't a viable general fix.
    What IS cheap and general: two known, systematic name-format mismatches
    between our data and Sherdog's -- concatenated Korean given names
    (_camel_split) and surname-first Chinese names (_reversed_name). Tried
    in order; each is one extra request only if the previous one missed.
    """
    for query in (name, _camel_split(name), _reversed_name(name)):
        candidates = _search_once(session, query)
        target = normalize_name(query)
        for a in candidates:
            if normalize_name(a.get_text()) == target:
                return "https://www.sherdog.com" + a["href"]
        if query != name:
            time.sleep(REQUEST_DELAY_SECONDS)
    return None


def get_nationality(session, url):
    resp = session.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    nat_el = soup.select_one('[itemprop="nationality"]')
    flag_el = soup.select_one("img.big_flag")
    nationality = nat_el.get_text(strip=True) if nat_el else None
    iso_code = None
    if flag_el and flag_el.get("src"):
        m = re.search(r"/([a-zA-Z]{2})\.(?:png|gif|svg)$", flag_el["src"])
        if m:
            iso_code = m.group(1).upper()
    return nationality, iso_code


def main():
    fighters = get_active_fighters()
    out_path = PROCESSED_DIR / "fighter_nationality.csv"

    # Resumable: a prior run may have died partway (this happened for real --
    # a mid-run network/DNS outage killed ~80% of the first attempt). Keep
    # already-matched rows as-is and only retry fighters without a match yet,
    # rather than re-hitting Sherdog for everyone from scratch.
    done = {}
    if out_path.exists():
        prior = pd.read_csv(out_path)
        done = {r["fighter_id"]: r for r in prior.to_dict("records") if pd.notna(r.get("iso_code"))}
        print(f"resuming: {len(done)} fighters already matched from a prior run, skipping those")

    todo = fighters[~fighters["fighter_id"].isin(done.keys())]
    print(f"{len(fighters)} active fighters total, {len(todo)} to (re)scrape\n")

    session = requests.Session()
    rows = list(done.values())
    for i, row in enumerate(todo.itertuples(), 1):
        result = {"fighter_id": row.fighter_id, "name": row.name, "sherdog_url": None, "nationality": None, "iso_code": None}
        try:
            url = find_sherdog_url(session, row.name)
            time.sleep(REQUEST_DELAY_SECONDS)
            if url is None:
                print(f"[{i}/{len(todo)}] {row.name} -> no exact match")
            else:
                nationality, iso_code = get_nationality(session, url)
                time.sleep(REQUEST_DELAY_SECONDS)
                result.update({"sherdog_url": url, "nationality": nationality, "iso_code": iso_code})
                print(f"[{i}/{len(todo)}] {row.name} -> {nationality} ({iso_code})")
        except Exception as e:
            print(f"[{i}/{len(todo)}] {row.name} -> ERROR {e}")
        rows.append(result)

        if i % 25 == 0:
            pd.DataFrame(rows).to_csv(out_path, index=False)

    out = pd.DataFrame(rows)
    out.to_csv(out_path, index=False)
    matched = out["iso_code"].notna().sum()
    print(f"\nmatched {matched}/{len(out)} ({matched / len(out):.1%})")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
