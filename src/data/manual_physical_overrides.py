"""
Hand-supplied physical measurements (height/reach/DOB) for active fighters
that UFCStats' own raw mirror doesn't have on file at all -- confirmed real
gaps (the fighter has real UFC fights, per fights.csv), not a fighter who
should just be treated as a debut. Sourced from Tapology and UFC.com,
cross-checked against each other before trusting a number (same "verify
against a second source" discipline as manual_nationality_overrides.py's
own history of getting this wrong from a single unreliable page).

Stance is normally left alone here -- Tapology/UFC.com didn't have it on
file for Rahiki/Tarin, and it's a categorical guess with no independent
source to cross-verify, so the default is to leave it NaN (XGBoost's
native missing-value handling) rather than guess. The two entries below
are the one exception: the user supplied both directly, having presumably
watched them fight -- a real, informed source, just not a cross-checkable
second website the way the height/reach numbers above are.

Only fills fields that are ACTUALLY missing (NaN) -- never overwrites a
real scraped value, even one that looks slightly different from what a
second source reports (e.g. a 66.0" vs 66.9" reach discrepancy across
sources is normal noise, not a sign the scraped value is wrong).

Safe to rerun: touches only the fighters listed below (by exact
fighters.csv name), idempotent. Kept as a real, rerunnable script (not a
one-off shell edit to data/raw/*.csv) specifically because a raw-file edit
gets silently wiped the next time the raw mirror is re-pulled fresh (hit
this directly with an earlier fighter-name fix this same project) --
this script re-applies every time right after load_data.py instead.

Also fills from data/processed/fighter_physical_ufccom.csv (UFC.com bio
height/reach, see scrape_physical.py) the same fill-only way.

Runs automatically at the end of load_data.py (it used to be a separate
manual step, and got silently skipped -- a load_data rerun wiped Rahiki,
Tarin, King III and Steveson's fills until 2026-09-24).
Run standalone: python -m src.data.manual_physical_overrides
"""
from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

# name -> {field: value}. Every field here was confirmed missing (NaN) in
# fighters.csv AND cross-checked against a second source before being
# added -- never guessed. Extend as new gaps are flagged (see
# feedback_flag_incomplete_data_for_non_debut_fighters memory).
MANUAL = {
    # UFC.com: 68.00in height, 72.00in reach (exact match to Tapology's
    # 5'8"/72.0"). Tapology-only: DOB May 10, 2002 -- cross-checked against
    # UFC.com's own "24 years old" (as of this card, 2026-09-12), consistent.
    # Stance user-supplied, 2026-09-10.
    "Marwan Rahiki": {"height_in": 68.0, "reach_in": 72.0, "dob": "2002-05-10", "stance": "Orthodox"},
    # UFC.com: 67.00in height, 66.00in reach. (DOB already on file.)
    # Stance user-supplied, 2026-09-10.
    "Regina Tarin": {"height_in": 67.0, "reach_in": 66.0, "stance": "Southpaw"},
    # UFC.com/RotoWire: 72.00in height. Reach initially held back pending a
    # height/reach mix-up concern (an unverified aggregator claimed 71.0in
    # reach, no site had a reach figure at all), but the user directly
    # checked a tale-of-the-tape graphic from one of his actual past fights
    # and confirmed reach 72in too -- a real primary source, and a 1:1
    # height:reach ratio ("ape index" 0) is itself unremarkable, not a red
    # flag (2026-09-10).
    "Sean King III": {"height_in": 72.0, "reach_in": 72.0},
    # UFC.com's own bio page: HEIGHT 71.00 (5'11"), REACH 74.00 -- exact
    # match to what the user gave directly (2026-09-15).
    "Gable Steveson": {"height_in": 71.0, "reach_in": 74.0},
    # UFC.com bio: HEIGHT 69.00, REACH 73.50 (Sherdog: 5'10"; UFC.com kept,
    # same rule as scrape_physical.py). Short-notice debut, 2026-09-26.
    # Stance user-supplied (2026-09-25) -- no outside source available
    # lists it (see src/audit_card.py).
    "Luis Hernandez": {"height_in": 69.0, "reach_in": 73.5, "stance": "Southpaw"},
    # UFC.com bio REACH 78.00 -- not on the page yet at the 2026-09-24
    # scrape_physical run, there by the 2026-09-25 card audit. Stance
    # user-supplied (2026-09-25).
    "Christian Edwards": {"reach_in": 78.0, "stance": "Southpaw"},
    "Mehemmedeli Osmanli": {"stance": "Southpaw"},
    "Ilimbek Akylbek Uulu": {"stance": "Orthodox"},
    # User's default, not a confirmed stance ("just put orthodox") --
    # replace if her real stance turns up.
    "Melissa Amaya": {"stance": "Orthodox"},
}


# Corrections that REPLACE an existing value -- only where the user has
# decided between two conflicting sources (src/audit_card.py flags these).
REPLACE = {
    # UFCStats 75.0 vs UFC.com bio 77.5 -- user chose UFC.com (2026-09-25).
    "Rodolfo Bellato": {"reach_in": 77.5},
    # UFC.com has two pages for him: /athlete/ilimbek-akylbek-uulu (66.5,
    # what scrape_physical.py used) and /athlete/ilimbek-akylbek (65.0, the
    # one the UFC Fight Night 289 card links). User chose UFC.com's card
    # page (2026-09-25).
    "Ilimbek Akylbek Uulu": {"reach_in": 65.0},
}


def main():
    path = PROCESSED_DIR / "fighters.csv"
    df = pd.read_csv(path)

    applied, filled_fields, not_found = 0, 0, []
    for name, fields in MANUAL.items():
        mask = df["name"] == name
        if not mask.any():
            not_found.append(name)
            continue
        for field, value in fields.items():
            if df.loc[mask, field].isna().all():
                df.loc[mask, field] = value
                filled_fields += 1
        applied += 1
    print(f"manual: applied to {applied} fighter(s), {filled_fields} field(s) filled (not found: {not_found})")

    # Then UFC.com's own bio height/reach (src/data/scrape_physical.py), by
    # fighter_id, same fill-only rule.
    scraped_path = PROCESSED_DIR / "fighter_physical_ufccom.csv"
    if scraped_path.exists():
        scraped = pd.read_csv(scraped_path).set_index("fighter_id")
        scraped_filled = 0
        for field in ["height_in", "reach_in"]:
            fill = df["fighter_id"].map(scraped[field])
            mask = df[field].isna() & fill.notna()
            df.loc[mask, field] = fill[mask]
            scraped_filled += int(mask.sum())
        print(f"UFC.com: {scraped_filled} field(s) filled")

    replaced = []
    for name, fields in REPLACE.items():
        mask = df["name"] == name
        for field, value in fields.items():
            if mask.any():
                replaced.append(f"{name} {field}: {df.loc[mask, field].iloc[0]} -> {value}")
                df.loc[mask, field] = value
    print(f"replaced: {replaced}")

    df.to_csv(path, index=False)


if __name__ == "__main__":
    main()
