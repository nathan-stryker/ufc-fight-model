"""
Hand-supplied "Fighting style" for active fighters that ufc.com itself
simply doesn't have the bio field for (src/data/scrape_fighting_style.py
scraped them successfully -- real page, no 404 -- there's just nothing
under "Fighting style" on their profile; confirmed by hand for a couple of
established veterans, ruling out a scraper bug).

Unlike manual_physical_overrides.py's height/reach numbers, there's no
independent second website to cross-check a "fighting style" tag against
-- it's ufc.com's own editorial label, not a physical measurement. These
are user-supplied directly (having watched the fighters, in one case
specifically from how they're introduced during fight announcements), a
real informed source, just not a cross-checkable one -- same category of
exception manual_physical_overrides.py already carved out for stance.

Safe to rerun: only fills a fighter's style if it's still genuinely blank
(never overwrites a real scraped value), idempotent. Applied directly to
fighter_style.csv since that file is the scraper's own output -- rerun
this any time after scrape_fighting_style.py in case that file gets
regenerated from scratch.

Run: python -m src.data.manual_style_overrides (after scrape_fighting_style.py)
"""
from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

# name -> style. Confirmed missing (blank, not a 404) in fighter_style.csv
# before being added -- never guessed. Extend as new gaps are flagged (see
# feedback_flag_incomplete_data_for_non_debut_fighters memory).
MANUAL = {
    "Jose Delgado": "MMA",
    # Announced during fight introductions as "Galvan Combat Style" (an
    # unofficial/gym-specific term, not one of ufc.com's own style tags) --
    # user chose the generic "MMA" bucket instead of inventing a category
    # ufc.com doesn't actually use elsewhere.
    "David Martinez": "MMA",
    "Muslim Salikhov": "Sanda",
    "Djorden Santos": "MMA",
    "Drakkar Klose": "MMA",
    "Tommy Gantt": "Freestyle",
    "Regina Tarin": "Striker",
}


def main():
    path = PROCESSED_DIR / "fighter_style.csv"
    df = pd.read_csv(path)

    applied, not_found = 0, []
    for name, style in MANUAL.items():
        mask = df["name"] == name
        if not mask.any():
            not_found.append(name)
            continue
        if df.loc[mask, "style"].isna().all():
            df.loc[mask, "style"] = style
            applied += 1

    df.to_csv(path, index=False)
    print(f"applied to {applied} fighter(s) (not found: {not_found})")


if __name__ == "__main__":
    main()
