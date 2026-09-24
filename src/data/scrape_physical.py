"""
Fill in height/reach for active fighters that UFCStats' raw mirror has no
measurement for, from each fighter's UFC.com athlete page ("Height" and
"Reach" bio fields, in inches -- e.g. Marek Bujlo: 76.00 / 77.00).

Only fighters who are active (scrape_nationality.get_active_fighters) AND
missing height or reach in fighters.csv are fetched -- ~80 fighters, so
~20 minutes at UFC.com's required crawl-delay of 15s (same as
scrape_fighting_style.py). Resumable.

UFC.com's own bio fields do have typos (Gable Steveson's page lists his
weight as 73.00), so each value is sanity-checked before being kept:
height 58-86in, reach 58-90in, and reach within -6..+12in of height.
Anything outside that is written as NaN with a note, not trusted -- "omit,
don't guess", same rule as the rest of this project's scrapers.

Then a second pass over Sherdog (height only -- Sherdog has no reach):
cross-checks UFC.com's height and fills height where UFC.com has none. On
the first run (2026-09-24) the two agreed within 1in for 38 of 44 fighters;
where they disagree UFC.com is kept, since Sherdog was the wrong one on
both heights already verified by hand (Rahiki, Steveson).

The result is applied fill-only by manual_physical_overrides.py (which
load_data.py runs after rewriting fighters.csv), so it never overwrites a
real UFCStats value and survives a fresh re-pull of the raw data.

Run: python -m src.data.scrape_physical
Writes: data/processed/fighter_physical_ufccom.csv
"""
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.data.scrape_fighting_style import ATHLETE_URL, HEADERS, MANUAL_SLUGS, REQUEST_DELAY_SECONDS, _slugify
from src.data.scrape_nationality import _camel_split, _reversed_name, get_active_fighters

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
OUT_PATH = PROCESSED_DIR / "fighter_physical_ufccom.csv"

# name -> UFC.com slug where no automatic guess below resolves (confirmed by
# hand). Merged over scrape_fighting_style.MANUAL_SLUGS.
PHYSICAL_MANUAL_SLUGS = {}


def _candidate_slugs(name):
    key = " ".join(name.lower().split())
    manual = {**MANUAL_SLUGS, **PHYSICAL_MANUAL_SLUGS}
    if key in manual:
        return [manual[key]]
    out = []
    for variant in [name, _camel_split(name), _reversed_name(name), _reversed_name(_camel_split(name))]:
        slug = _slugify(variant)
        if slug not in out:
            out.append(slug)
    return out


def _bio_fields(html):
    soup = BeautifulSoup(html, "html.parser")
    fields = {}
    for field in soup.select("div.c-bio__field"):
        label, text = field.select_one(".c-bio__label"), field.select_one(".c-bio__text")
        if label and text:
            fields[label.get_text(strip=True).lower()] = text.get_text(strip=True)
    return fields


def _num(s):
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _validate(height, reach):
    """Returns (height, reach, note) with implausible values dropped."""
    notes = []
    if height is not None and not 58 <= height <= 86:
        notes.append(f"height {height} out of range")
        height = None
    if reach is not None and not 58 <= reach <= 90:
        notes.append(f"reach {reach} out of range")
        reach = None
    if height is not None and reach is not None and not -6 <= reach - height <= 12:
        notes.append(f"reach-height gap {reach - height:+.1f} implausible")
        height = reach = None
    return height, reach, "; ".join(notes) or None


def fetch(session, name):
    for i, slug in enumerate(_candidate_slugs(name)):
        if i:
            time.sleep(REQUEST_DELAY_SECONDS)
        resp = session.get(ATHLETE_URL.format(slug=slug), headers=HEADERS, timeout=15)
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        f = _bio_fields(resp.text)
        height, reach, note = _validate(_num(f.get("height")), _num(f.get("reach")))
        return {"slug": slug, "height_in": height, "reach_in": reach, "note": note}
    return {"slug": None, "height_in": None, "reach_in": None, "note": "no UFC.com page found"}


SHERDOG_DELAY_SECONDS = 1.0  # same pace as scrape_nationality.py; Sherdog's robots.txt allows crawling
MAX_HEIGHT_DISAGREEMENT_IN = 1.5


def _sherdog_urls():
    from src.data.scrape_prefight_history import MANUAL_SHERDOG_URLS
    nat = pd.read_csv(PROCESSED_DIR / "fighter_nationality.csv")
    by_id = dict(zip(nat["fighter_id"], nat["sherdog_url"]))
    by_name = {k: (v if v.startswith("http") else f"https://www.sherdog.com/fighter/{v}") for k, v in MANUAL_SHERDOG_URLS.items()}
    return by_id, by_name


def sherdog_height(session, url):
    """Sherdog's bio 'HEIGHT 6'2" / 187.96 cm' -> 74.0 (from the cm, rounded to 0.5in)."""
    resp = session.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
    m = re.search(r"HEIGHT\s+\d+'\s*\d+\"\s*/\s*([\d.]+)\s*cm", text)
    h = round(float(m.group(1)) / 2.54 * 2) / 2 if m else None
    return h if h and h >= 58 else None  # Sherdog shows 0'0" when it has no height


def add_sherdog_heights(rows):
    """Second source for height: cross-checks UFC.com's number, and fills
    height (only) where UFC.com's page has none. Sherdog has no reach."""
    by_id, by_name = _sherdog_urls()
    session = requests.Session()
    for r in rows:
        url = by_id.get(r["fighter_id"])
        if not (isinstance(url, str) and url.startswith("http")):  # "manual" = nationality set by hand, no URL
            url = by_name.get(" ".join(r["name"].lower().split()))
        h = None
        if isinstance(url, str):
            try:
                h = sherdog_height(session, url)
            except Exception as e:
                print(f"  sherdog error for {r['name']}: {e}")
            time.sleep(SHERDOG_DELAY_SECONDS)
        r["sherdog_height_in"] = h
        if isinstance(r.get("note"), str) and "Sherdog" in r["note"]:
            r["note"] = None  # re-derived below
        # Raw UFC.com value kept in its own column so a rerun re-derives
        # height_in from the two sources, not from an already-merged value.
        if "ufc_height_in" not in r:
            r["ufc_height_in"] = r.get("height_in")
        ufc_h = r["ufc_height_in"] if pd.notna(r["ufc_height_in"]) else None
        r["height_in"], r["height_source"] = ufc_h, "ufc.com" if ufc_h is not None else None
        # UFC.com wins a disagreement: Sherdog was the one that was wrong on
        # both heights already verified by hand (Rahiki 70 vs 68, Steveson 73
        # vs 71), so a disagreement is reported for review, not dropped.
        if h is not None and ufc_h is not None and abs(h - ufc_h) > MAX_HEIGHT_DISAGREEMENT_IN:
            r["note"] = f"UFC.com {ufc_h} vs Sherdog {h} height disagree -- kept UFC.com"
        elif ufc_h is None and h is not None and 58 <= h <= 86:
            r["height_in"], r["height_source"] = h, "sherdog"
    return rows


def main():
    fighters = pd.read_csv(PROCESSED_DIR / "fighters.csv")
    active = fighters[fighters["fighter_id"].isin(get_active_fighters()["fighter_id"])]
    missing = active[active["height_in"].isna() | active["reach_in"].isna()]

    done = {}
    if OUT_PATH.exists():
        prior = pd.read_csv(OUT_PATH)
        done = {r["fighter_id"]: r for r in prior.to_dict("records") if pd.notna(r.get("slug"))}
    todo = missing[~missing["fighter_id"].isin(done.keys())]
    print(f"{len(missing)} active fighters missing height/reach, {len(todo)} to fetch "
          f"(~{len(todo) * REQUEST_DELAY_SECONDS / 60:.0f} min at 15s/request)\n")

    session = requests.Session()
    rows = list(done.values())
    for i, row in enumerate(todo.itertuples(), 1):
        try:
            result = fetch(session, row.name)
        except Exception as e:
            result = {"slug": None, "height_in": None, "reach_in": None, "note": f"error: {e}"}
        rows.append({"fighter_id": row.fighter_id, "name": row.name, **result})
        print(f"[{i}/{len(todo)}] {row.name} -> {result['height_in']} / {result['reach_in']}"
              f"{'  (' + result['note'] + ')' if result['note'] else ''}", flush=True)
        pd.DataFrame(rows).to_csv(OUT_PATH, index=False)
        time.sleep(REQUEST_DELAY_SECONDS)

    print("\ncross-checking height against Sherdog...")
    rows = add_sherdog_heights(rows)
    out = pd.DataFrame(rows)
    out.to_csv(OUT_PATH, index=False)
    disagree = out["note"].fillna("").str.contains("disagree")
    print(f"sherdog height found {out['sherdog_height_in'].notna().sum()}/{len(out)}, "
          f"disagreements (>{MAX_HEIGHT_DISAGREEMENT_IN}in, UFC.com kept): {disagree.sum()}")
    for r in out[disagree].itertuples():
        print(f"  {r.name}: {r.note}")
    print(f"\nheight found {out['height_in'].notna().sum()}/{len(out)}, reach found {out['reach_in'].notna().sum()}/{len(out)}")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
