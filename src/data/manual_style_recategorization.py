"""
User's own weight-class-by-weight-class recategorization of "Fighting
style," replacing UFC.com's own editorial tag entirely rather than just
filling gaps (see manual_style_overrides.py for that, a separate, narrower
project this does NOT touch). Started 2026-09-15 after the user judged
UFC.com's own tags unreliable even when present -- e.g. UFC.com lists
Aljamain Sterling as a "Kickboxer" despite him being a wrestling-heavy
grappler. Going division by division; welterweight first.

Unlike manual_style_overrides.py, this UNCONDITIONALLY overwrites
fighter_style.csv's style column for every name below, real UFC.com value
or not -- that IS the point here, the user is substituting their own
judgment for UFC.com's. A value of None means "clear to blank": the user
judged the current tag specifically wrong with no confident replacement
of their own, so genuinely unknown is more honest than a wrong label.

Run AFTER manual_style_overrides.py if regenerating fighter_style.csv from
scratch (that file's fill-only-if-blank inserts for retired PAST
OPPONENTS -- e.g. Omar Morales -- are unrelated and untouched by this
file).

Safe to rerun: idempotent, only touches names listed below.

Run: python -m src.data.manual_style_recategorization
"""
from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

# name -> style, or None to clear to blank. User-supplied directly, no
# independent source to verify an editorial "fighting style" label against
# (same exception carved out in manual_style_overrides.py).
MANUAL = {
    # --- Welterweight, 2026-09-15 ---
    "Ian Machado Garry": "MMA",
    "Carlos Prates": "Muay Thai",
    "Max Holloway": "Boxer",
    "Jack Della Maddalena": "Boxer",
    "Gabriel Bonfim": "MMA",
    "Belal Muhammad": "MMA",
    "Yaroslav Amosov": "Sambo",
    "Uros Medic": "Striker",
    "Abubakar Vagaev": "Wrestler",
    "Adam Fugitt": None,
    "Alex Morono": None,
    "Andreas Gustafsson": None,
    "Ange Loosa": None,
    "Billy Ray Goff": "MMA",
    "Bryan Battle": None,
    # A real, informal grappling-nickname term (not a UFC.com tag) -- used
    # literally, per the user, same "MMA"-bucket exception already carved
    # out for gym-specific/announcer terms elsewhere (see David Martinez in
    # manual_style_overrides.py) but here the user chose to keep the actual
    # term rather than bucket it.
    "Charles Radtke": "Thugjitsu",
    "Chidi Njokuani": "Muay Thai",
    "Chris Curtis": "Striker",
    "Christopher Alvidrez": "Karate",
    "Conor McGregor": "Striker",
    "Daniel Rodriguez": "Striker",
    "Daniil Donchenko": "Striker",
    "Elizeu Zaleski dos Santos": None,
    "Eric Nolan": "MMA",
    "Francisco Prado": "Street Fighter",
    "Gilbert Burns": None,
    "Gunnar Nelson": "MMA",
    "Ignacio Bahamondes": "Kickboxer",
    "Isaac Moreno": "MMA",
    "Jean-Paul Lebosnoyani": "MMA",
    "Jeremiah Wells": "MMA",
    "Joel Alvarez": "Brazilian Jiu-Jitsu",
    "Kaik Brito": "Striker",
    "Kevin Holland": "MMA",
    "Kevin Jousset": None,
    "Kiefer Crosbie": None,
    "Li Jingliang": "MMA",
    "Neil Magny": "Striker",
    "Nicolas Dalby": "Karate",
    "Pete Rodriguez": "Jiu-Jitsu",
    "Rafael Dos Anjos": "MMA",
    "Ramiz Brahimaj": "Grappler",
    "Randy Brown": "Striker",
    "Roberto Soldic": "Striker",
    "Rhys McKee": None,
    "Rinat Fakhretdinov": None,
    "Rodrigo Sezinando": "MMA",
    # A ring nickname, not a discipline -- used literally, per the user
    # (same call as "Charles Radtke": "Thugjitsu" above).
    "Ronald Humphrey": "The Punisher",
    "Sean Clancy Jr.": "MMA",
    "Seokhyeon Ko": "MMA",
    "Tahir Abdullayev": "MMA",
    "Taiyilake Nueraji": "Striker",
    "Themba Gorimbo": None,
    "Trevin Giles": None,
    "Trey Waters": None,
    "Victor Valenzuela": "Kickboxer",
    "Wellington Turman": "Brazilian Jiu-Jitsu",
    "Zachary Scroggin": None,
    # --- Women's Strawweight, 2026-09-15 ---
    # Marina Rodriguez / Piera Rodriguez (one gets a value, one gets
    # cleared) and Xiong Jingnan (set to "Striker" then "remove"d in the
    # same message) are still pending -- ambiguous/contradictory as given,
    # asked the user rather than guessed. Tina Black has no fighters.csv
    # row at all (not even under a name variant) -- can't be added until
    # she's actually in our data.
    "Alice Ardelean": "MMA",
    "Amanda Lemos": "Striker",
    "Amanda Ribas": "MMA",
    "Ariane Carnelossi": None,
    "Carla Esparza": None,
    "Cory McKenna": None,
    "Denise Gomes": "Muay Thai",
    "Elise Reed": "Kickboxer",
    "Fatima Kline": "MMA",
    "Feng Xiaocan": None,
    "Iasmin Lucindo": "MMA",
    "Istela Nunes": None,
    "Jessica Andrade": "Brawler",
    "Jessica Penne": None,
    "Josefine Knutsson": None,
    "Loopy Godinez": "MMA",
    "Marina Spasic": "Kickboxer",
    "Marnic Mann": "MMA",
    "Melissa Amaya": "MMA",
    "Melissa Martinez": None,
    "Molly McCann": None,
    "Montserrat Conejo Ruiz": "Grappler",
    "Puja Tomar": "Wushu",
    "Rayanne dos Santos": "MMA",
    "Shauna Bannon": "Kickboxer",
    # User wrote "Shi Min" -- our roster has "Shi Ming" (115 lbs,
    # strawweight), no "Shi Min" at all -- same person, minor typo.
    "Shi Ming": "MMA",
    "Sofia Montenegro": "MMA",
    "Stephanie Luciano": "Muay Thai",
    "Tabatha Ricci": "Grappler",
    "Tatiana Suarez": "Wrestler",
    "Tecia Pennington": None,
    "Viktoriia Dudakova": None,
    "Yan Xiaonan": "Sanda",
    "Yazmin Jauregui": "Boxer",
}


def main():
    path = PROCESSED_DIR / "fighter_style.csv"
    df = pd.read_csv(path)
    fighters = pd.read_csv(PROCESSED_DIR / "fighters.csv")[["fighter_id", "name"]]

    set_count, cleared, inserted, not_found = 0, 0, 0, []
    new_rows = []
    for name, style in MANUAL.items():
        mask = df["name"] == name
        if mask.any():
            df.loc[mask, "style"] = style
            if style is None:
                cleared += 1
            else:
                set_count += 1
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
    print(f"set {set_count}, cleared {cleared}, inserted {inserted} new row(s) "
          f"(not found in fighters.csv at all: {not_found})")


if __name__ == "__main__":
    main()
