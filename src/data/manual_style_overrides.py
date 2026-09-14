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

scrape_fighting_style.py only covers the "active roster" (fought within
the last ACTIVE_WINDOW_MONTHS -- same window as scrape_nationality.py),
so a retired/long-inactive fighter who shows up as a past OPPONENT in an
active fighter's fight history (feeding engine.js's recordVsStyle(), the
Breakdown panel's "Record vs. Opponent's Style") has no fighter_style.csv
row at all, not just a blank one -- their fight against an active fighter
silently drops out of that fighter's record-vs-style tally even though
the fight itself is right there in fights.csv (confirmed 2026-09-14: Giga
Chikadze's real 2-2 record vs strikers was showing incomplete because
Omar Morales, one of the 4 fights, had no style row to match against).
Falls back to inserting a brand new row when there's no existing one,
resolving fighter_id from fighters.csv by exact name -- same pattern
manual_nationality_overrides.py already uses for this.

Run: python -m src.data.manual_style_overrides (after scrape_fighting_style.py)
"""
from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

# name -> style. Confirmed missing (blank, or no row at all) in
# fighter_style.csv before being added -- never guessed. Extend as new gaps
# are flagged (see feedback_flag_incomplete_data_for_non_debut_fighters
# memory).
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
    # UFC 331 card (2026-09-19), user-supplied directly (2026-09-14).
    "Michael Aswell Jr.": "MMA",
    "Tai Tuivasa": "Street Fighter",
    "Patricio Pitbull": "MMA",
    # Past opponents (not on the active roster themselves) needed to
    # complete UFC 331 fighters' record-vs-style tallies -- user-supplied
    # directly, framed as each active fighter's own style-record math
    # (e.g. "giga chikadze is 2-2 vs strikers ... fought omar morales"),
    # not a standalone claim about the opponent's UFC.com bio (2026-09-14).
    "Omar Morales": "Striker",
    "Montserrat Conejo Ruiz": "MMA",
    "Zach Reese": "MMA",
    "John Lineker": "Striker",
    "Guido Cannetti": "Striker",
    # Also named by the user as fights that should count in this week's
    # card's record-vs-style tallies (Moicano/Ortega vs Cub Swanson, Ortega
    # vs Diego Lopes), but Diego Lopes -- unlike the 5 above -- has a real
    # ufc.com "Fighting style" bio field on file; scraped live rather than
    # asked for, since it's a verifiable fact, not an editorial judgment
    # call (2026-09-14). Cub Swanson already had "Brazilian Jiu-Jitsu" on
    # file before this pass, nothing to add for him.
    "Diego Lopes": "Jiu-Jitsu",
    "Rob Font": "Striker",
}


def main():
    path = PROCESSED_DIR / "fighter_style.csv"
    df = pd.read_csv(path)
    fighters = pd.read_csv(PROCESSED_DIR / "fighters.csv")[["fighter_id", "name"]]

    applied, inserted, not_found = 0, 0, []
    new_rows = []
    for name, style in MANUAL.items():
        mask = df["name"] == name
        if mask.any():
            if df.loc[mask, "style"].isna().all():
                df.loc[mask, "style"] = style
                applied += 1
            continue
        fmatch = fighters[fighters["name"] == name]
        if fmatch.empty:
            not_found.append(name)
            continue
        new_rows.append({"fighter_id": fmatch.iloc[0]["fighter_id"], "name": name, "style": style})
        inserted += 1

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    df.to_csv(path, index=False)
    print(f"filled {applied} existing row(s), inserted {inserted} new row(s) (not found in fighters.csv at all: {not_found})")


if __name__ == "__main__":
    main()
