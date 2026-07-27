"""
Scrape pre-UFC professional fight history (regional/other-promotion record)
for fighters making their UFC debut on the current upcoming card -- from
Sherdog.com, the same permitted, already-integrated source scrape_nationality.py
uses (robots.txt allows unrestricted crawling; still rate-limited politely
here regardless of what's technically allowed).

Why this exists: predict.py's debut-fighter fallback previously had NOTHING
to go on besides physical attributes -- a flat population-average baseline
for win rate, finish rate, experience, and a neutral (BASE_RATING) Elo. Most
UFC "debutants" actually have a real professional record (regional
promotions like Oktagon, Cage Warriors, etc.) that Sherdog already tracks in
full, with opponent/event/method/round/date -- this project just never
looked at it before. See src/features/prefight_snapshot.py for how this
gets turned into the same "_entering" snapshot shape a UFC-experienced
fighter's real history produces.

Honest limitation: Sherdog's regional-promotion listings don't carry
round-by-round strike/grappling data the way UFCStats does, so this can
only ever inform record-based stats (experience, win rate, finish rate,
current streak, time since last fight) -- NOT sig_str_landed_per_min,
td_avg_per15, etc. Those stay at their existing NaN fallback regardless.
Also deliberately does NOT feed a "regional Elo" into the real Elo system --
a win/loss record against Oktagon-caliber opposition isn't on the same
scale as a UFC-calibrated Elo rating, so debut fighters always start at
BASE_RATING for that specific feature, exactly as before.

Debut fighters are, by definition, a small and transient set (a handful
per card, each one relevant for exactly one week before either fighting in
the UFC for real or dropping off the card) -- so unlike scrape_nationality.py,
this does a full rewrite every run rather than maintaining an ever-growing
incremental cache. The cost of re-fetching a fighter who turns out to have
zero pre-UFC fights on file is negligible at this scale.

Run: python -m src.data.scrape_prefight_history
Writes: data/processed/prefight_history.csv
"""
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.data.scrape_nationality import HEADERS, REQUEST_DELAY_SECONDS, find_sherdog_url, normalize_name

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

# find_sherdog_url()'s automated search covers two distinct failure modes:
# (1) a fighter listed under a materially different name (a full legal name
# vs. the short form our data uses) -- find_sherdog_url() returns None, we
# fill the gap. (2) MULTIPLE fighters sharing the exact same name -- Sherdog
# has no relevance ranking, so find_sherdog_url() returns the first exact
# match in page order, which is not necessarily the right person (found the
# hard way: "Michael Oliveira" matched a near-empty profile with no
# nickname/fights instead of the real "PQD / The Missile", 9-0, because the
# wrong one simply appeared earlier in Sherdog's search results). Checked
# FIRST in main(), ahead of find_sherdog_url(), for exactly this reason --
# a manual entry must be able to override a "successful" but wrong
# automated match, not just fill in when automated search finds nothing.
# Same class of problem as manual_nationality_overrides.py, just for THIS
# script's specific need (a resolvable Sherdog URL, not just a known
# nationality). Each entry confirmed by hand -- verified against the
# fighter's own nickname/record on the page, not guessed. Extend as new
# debut fighters hit either gap.
MANUAL_SHERDOG_URLS = {
    # Sherdog lists him under his full given name; confirmed via matching
    # nickname "El Chapo" (UFC Fight Night 283 card, 2026-08-01).
    "vlasto cepo": "https://www.sherdog.com/fighter/Vlastislav-Cepo-330615",
    # Sherdog lists her under her full given name; confirmed via matching
    # nickname "Queen Beast" (UFC Fight Night 283 card, 2026-08-01).
    "nina milosevic": "https://www.sherdog.com/fighter/Nina-Nikolija-Milosevic-399822",
    # Name collision: Sherdog has several unrelated "Michael Oliveira"
    # profiles. Confirmed via matching nickname "PQD / The Missile" and a
    # 9-0 record ending in a Dana White's Contender Series win, matching
    # what the user reported by hand (UFC Fight Night 283 card, 2026-08-01).
    "michael oliveira": "https://www.sherdog.com/fighter/Michael-Oliveira-400985",
}


def get_debut_fighters():
    """
    Anyone booked on the current upcoming card with zero rows in fights.csv
    -- the same "genuine UFC debut" signal the website's own "UFC Debut"
    badge and the "Meet the Debut Fighters" section already use.
    """
    upcoming_path = PROCESSED_DIR / "upcoming_card.csv"
    if not upcoming_path.exists():
        return pd.DataFrame(columns=["fighter_id", "name"])
    upcoming = pd.read_csv(upcoming_path)
    fights = pd.read_csv(PROCESSED_DIR / "fights.csv")
    ufc_experienced = set(fights["fighter_1_id"]) | set(fights["fighter_2_id"])

    pairs = pd.concat([
        upcoming[["fighter_a_id", "fighter_a_name"]].rename(columns={"fighter_a_id": "fighter_id", "fighter_a_name": "name"}),
        upcoming[["fighter_b_id", "fighter_b_name"]].rename(columns={"fighter_b_id": "fighter_id", "fighter_b_name": "name"}),
    ]).dropna(subset=["fighter_id"])
    pairs = pairs.drop_duplicates(subset=["fighter_id"])
    return pairs[~pairs["fighter_id"].isin(ufc_experienced)].reset_index(drop=True)


def _method_bucket(method_text):
    if not method_text:
        return None
    lower = method_text.strip().lower()
    # Substring, not just prefix -- "Technical Submission (Armbar)" and
    # "TKO (Doctor Stoppage)" both need to match despite not literally
    # starting with the bucket keyword. Checked in this priority order
    # since "submission"/"decision" never collide with "ko" as substrings
    # in the method vocabulary Sherdog actually uses.
    if "submission" in lower:
        return "sub"
    if "ko" in lower:  # catches both "KO" and "TKO"
        return "ko"
    if "decision" in lower:
        return "dec"
    return None


def _parse_result(text):
    lower = (text or "").strip().lower()
    if lower in ("win", "loss", "draw"):
        return lower
    if "contest" in lower or lower == "nc":
        return "nc"
    return "other"


def _parse_date(text):
    try:
        return datetime.strptime(text.strip(), "%b / %d / %Y")
    except (ValueError, AttributeError):
        return None


def parse_fight_history(html):
    """
    Parses every table.new_table.fighter module on a Sherdog fighter page
    (there can be more than one -- Sherdog sometimes splits a long record
    across multiple tables/eras) into one flat list of pre-UFC fight rows.
    Reads specific child elements (the result <span>, the event's own
    itemprop=award <span>, the method's own <b> tag) rather than the
    concatenated cell text, which glues the event name to its date and the
    method to the referee's name with no separating whitespace.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for table in soup.select("table.new_table.fighter"):
        for tr in table.select("tr"):
            cells = tr.select("td")
            if len(cells) != 6:
                continue  # header row
            result_el = cells[0].select_one("span.final_result")
            opponent_el = cells[1].select_one("a")
            event_el = cells[2].select_one('span[itemprop="award"]')
            date_el = cells[2].select_one("span.sub_line")
            method_el = cells[3].select_one("b")
            round_text = cells[4].get_text(strip=True)
            time_text = cells[5].get_text(strip=True)

            event_date = _parse_date(date_el.get_text() if date_el else None)
            if event_date is None:
                continue  # can't place this fight in time -- skip rather than guess
            method_text = method_el.get_text(strip=True) if method_el else None
            rows.append({
                "opponent_name": opponent_el.get_text(strip=True) if opponent_el else None,
                "event": event_el.get_text(strip=True) if event_el else None,
                "event_date": event_date,
                "method_raw": method_text,
                "method_bucket": _method_bucket(method_text),
                "round": round_text or None,
                "time": time_text or None,
                "result": _parse_result(result_el.get_text() if result_el else None),
            })
    return rows


def main():
    debut_fighters = get_debut_fighters()
    out_path = PROCESSED_DIR / "prefight_history.csv"
    if debut_fighters.empty:
        print("no debut fighters on the current upcoming card -- nothing to scrape")
        pd.DataFrame(columns=[
            "fighter_id", "name", "opponent_name", "event", "event_date",
            "method_raw", "method_bucket", "round", "time", "result",
        ]).to_csv(out_path, index=False)
        return

    print(f"{len(debut_fighters)} debut fighter(s) on the current card to look up\n")
    session = requests.Session()
    all_rows = []
    for i, row in enumerate(debut_fighters.itertuples(), 1):
        try:
            url = MANUAL_SHERDOG_URLS.get(normalize_name(row.name))
            if url is None:
                url = find_sherdog_url(session, row.name)
                time.sleep(REQUEST_DELAY_SECONDS)
            if url is None:
                print(f"[{i}/{len(debut_fighters)}] {row.name} -> no exact Sherdog match, no pre-UFC record available")
                continue
            resp = session.get(url, headers=HEADERS, timeout=15)
            time.sleep(REQUEST_DELAY_SECONDS)
            fights = parse_fight_history(resp.text)
            print(f"[{i}/{len(debut_fighters)}] {row.name} -> {len(fights)} pre-UFC fight(s) found")
            for f in fights:
                f["fighter_id"] = row.fighter_id
                f["name"] = row.name
                all_rows.append(f)
        except Exception as e:
            print(f"[{i}/{len(debut_fighters)}] {row.name} -> ERROR {e}")

    out = pd.DataFrame(all_rows, columns=[
        "fighter_id", "name", "opponent_name", "event", "event_date",
        "method_raw", "method_bucket", "round", "time", "result",
    ])
    out.to_csv(out_path, index=False)
    n_fighters_with_history = out["fighter_id"].nunique()
    print(f"\n{len(out)} pre-UFC fight rows for {n_fighters_with_history}/{len(debut_fighters)} debut fighter(s)")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
