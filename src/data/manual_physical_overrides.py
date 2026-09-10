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

Run: python -m src.data.manual_physical_overrides (right after load_data.py)
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

    df.to_csv(path, index=False)
    print(f"applied to {applied} fighter(s), {filled_fields} field(s) filled (not found: {not_found})")


if __name__ == "__main__":
    main()
