"""
Hand-supplied nationality for active fighters that src/data/scrape_nationality.py
couldn't resolve automatically -- Sherdog's own search has no relevance
ranking (a common surname can be 20+ pages deep, confirmed by hand for
"Jon Jones"), and heuristic fixes (name-order reversal, camelCase
splitting) risk silently mismatching people for exactly the ambiguous
Chinese/Korean-style names where getting it wrong is easiest, so this was
done as a direct question-and-answer with the user instead of automated
guessing.

Safe to rerun: only touches the fighters listed below (by exact name),
leaves every scraped row untouched, and is idempotent. Kept as a real,
rerunnable script (not just a one-off shell command) so this data survives
if fighter_nationality.csv is ever regenerated from scratch -- run this
right after scrape_nationality.py in that case.

Run: python -m src.data.manual_nationality_overrides
"""
from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

# name -> (nationality display name, ISO code)
MANUAL = {
    "Alexandr Romanov": ("Moldova", "MD"),
    "Benoit Saint Denis": ("France", "FR"),
    "Casey O'Neill": ("Australia", "AU"),
    "Dooho Choi": ("South Korea", "KR"),
    "Ian Machado Garry": ("Ireland", "IE"),
    "Jon Jones": ("United States", "US"),
    "Khalil Rountree Jr.": ("United States", "US"),
    "Li Jingliang": ("China", "CN"),
    "Loma Lookboonmee": ("Thailand", "TH"),
    "Loopy Godinez": ("Mexico", "MX"),
    "Marcus Buchecha": ("Brazil", "BR"),
    "Mizuki": ("Japan", "JP"),
    "Ovince Saint Preux": ("United States", "US"),
    "Patricio Pitbull": ("Brazil", "BR"),
    "Paul Craig": ("Scotland", "SCT"),
    "Renato Moicano": ("Brazil", "BR"),
    "Song Kenan": ("China", "CN"),
    "Song Yadong": ("China", "CN"),
    "Waldo Cortes Acosta": ("Dominican Republic", "DO"),
    "Xiong Jingnan": ("China", "CN"),
    "Yan Xiaonan": ("China", "CN"),
    "Zhang Weili": ("China", "CN"),
    "AJ Cunningham": ("United States", "US"),
    "Abdul Rakhman Yakhyaev": ("Turkey", "TR"),
    "Alatengheili": ("China", "CN"),
    "Allen Frye Jr.": ("United States", "US"),
    "Aoriqileng": ("China", "CN"),
    "Ariane da Silva": ("Brazil", "BR"),
    "Ateba Gautier": ("Cameroon", "CM"),
    "Baergeng Jieleyisi": ("Kazakhstan", "KZ"),
    "Benardo Sopaj": ("Albania", "AL"),
    "Bia Mesquita": ("Brazil", "BR"),
    "Billy Ray Goff": ("United States", "US"),
    "CJ Vergara": ("United States", "US"),
    "Cam Rowston": ("Australia", "AU"),
    "ChangHo Lee": ("South Korea", "KR"),
    "Chepe Mariscal": ("United States", "US"),
    "Chris Duncan": ("Scotland", "SCT"),
    "Daria Zhelezniakova": ("Russia", "RU"),
    "Ding Meng": ("China", "CN"),
    "DongHun Choi": ("South Korea", "KR"),
    "Felipe Lima": ("Brazil", "BR"),
    "Feng Xiaocan": ("China", "CN"),
    "Gabe Green": ("United States", "US"),
    "HyunSung Park": ("South Korea", "KR"),
    "JJ Aldrich": ("United States", "US"),
    "JeongYeong Lee": ("South Korea", "KR"),
    "Jesus Aguilar": ("Mexico", "MX"),
    "JooSang Yoo": ("South Korea", "KR"),
    "Jose Daniel Medina": ("Bolivia", "BO"),
    "Jose Delano": ("Brazil", "BR"),
    "Josefine Knutsson": ("Sweden", "SE"),
    "Josh Culibao": ("Australia", "AU"),
    "JunYong Park": ("South Korea", "KR"),
    "Khaos Williams": ("United States", "US"),
    "Kiru Sahota": ("England", "EN"),
    "Levi Rodrigues Jr.": ("Brazil", "BR"),
    "Maheshate": ("China", "CN"),
    "Michael Aswell Jr.": ("United States", "US"),
    "Montse Rendon": ("Mexico", "MX"),
    "Montserrat Conejo Ruiz": ("Mexico", "MX"),
    "Muhammad Naimov": ("Tajikistan", "TJ"),
    "Ollie Schmid": ("New Zealand", "NZ"),
    "Ozzy Diaz": ("United States", "US"),
    "Patchy Mix": ("United States", "US"),
    "Phil Rowe": ("United States", "US"),
    "RJ Harris": ("United States", "US"),
    "Rafael Cerqueira": ("Brazil", "BR"),
    "Ramazan Temirov": ("Uzbekistan", "UZ"),
    "Rongzhu": ("China", "CN"),
    "Sangwook Kim": ("South Korea", "KR"),
    "Seokhyeon Ko": ("South Korea", "KR"),
    "SeungWoo Choi": ("South Korea", "KR"),
    "Shara Magomedov": ("Russia", "RU"),
    "Shem Rock": ("England", "EN"),
    "Shi Ming": ("China", "CN"),
    "SuYoung You": ("South Korea", "KR"),
    "Sulangrangbo": ("China", "CN"),
    "Sumudaerji": ("China", "CN"),
    "Tainara Lisboa": ("Brazil", "BR"),
    "Taiyilake Nueraji": ("China", "CN"),
    "Timmy Cuamba": ("United States", "US"),
    "Tommy Gantt": ("United States", "US"),
    "Tre'ston Vines": ("United States", "US"),
    "Tuco Tokkos": ("England", "EN"),
    "Ty Miller": ("United States", "US"),
    "Viktoriia Dudakova": ("Russia", "RU"),
    "Wang Cong": ("China", "CN"),
    "Wes Schultz": ("United States", "US"),
    "Xiao Long": ("China", "CN"),
    "YiSak Lee": ("South Korea", "KR"),
    "Yizha": ("China", "CN"),
    "Zachary Scroggin": ("United States", "US"),
    "Zhang Mingyang": ("China", "CN"),
    "Zhu Kangjie": ("China", "CN"),
    # Both genuinely multi-national -- confirmed via web search, then a
    # direct question to the user rather than picking one automatically
    # (same policy as every other entry in this file). Vlasto Cepo: born in
    # Serbia; sources described him as now representing Slovakia, which is
    # what the user originally picked -- they later corrected themselves
    # ("vlasto cepo should have a serbian flag i know you asked me before
    # my bad") back to Serbia, so that's the value that sticks. Nina
    # Milosevic: ties to Serbia (birth, IMMAF national team), Sweden (her
    # own stated identity), and Australia (where she trains) -- user chose
    # Serbia.
    "Vlasto Cepo": ("Serbia", "RS"),
    "Nina Milosevic": ("Serbia", "RS"),
    # Sherdog's own itemprop=nationality field says "United States" for him
    # (he fights out of Anchorage, AK) but he was born and raised in Novi
    # Sad, Serbia and is Serbian -- confirmed via web search (Wikipedia,
    # EssentiallySports) after the user flagged the site showing the wrong
    # flag. Not a matching bug (the automated search found the correct
    # Sherdog profile, nickname "The Doctor" matches) -- Sherdog's own data
    # conflates fights-out-of location with nationality here.
    "Uros Medic": ("Serbia", "RS"),
    # Three brand new UFC debut fighters (added to this week's card after
    # ufc.com hadn't posted it yet -- see the upcoming_card.csv patch),
    # never scraped by scrape_nationality.py at all since they weren't on
    # any "active" roster before this card. User-supplied directly, same as
    # every other entry in this file.
    "Marina Spasic": ("Serbia", "RS"),
    "Noah Gugnon": ("France", "FR"),
    "Milos Janicic": ("Montenegro", "ME"),
    # Replaced Max Gimenis as Jovan Leka's opponent (Poppeck stepped in) --
    # another true UFC debut with no prior row here, same as the three above.
    "Alexander Poppeck": ("Germany", "DE"),
}


def main():
    path = PROCESSED_DIR / "fighter_nationality.csv"
    df = pd.read_csv(path)
    before = df["iso_code"].notna().sum()

    # scrape_nationality.py only ever processes the "active" roster (fought
    # within the last ACTIVE_WINDOW_MONTHS) -- a fighter making their actual
    # UFC debut this week has NO row here at all yet, not just a blank
    # iso_code, so a plain update-by-name (the original behavior) would
    # silently no-op for them. Falls back to inserting a brand new row,
    # resolving fighter_id from fighters.csv by exact name (fine here since
    # every name below was confirmed by hand against a specific real
    # fighter, same as the update path already assumes).
    fighters = pd.read_csv(PROCESSED_DIR / "fighters.csv")[["fighter_id", "name"]]

    applied, inserted, not_found = 0, 0, []
    new_rows = []
    for name, (nat, iso) in MANUAL.items():
        mask = df["name"] == name
        if mask.any():
            df.loc[mask, "nationality"] = nat
            df.loc[mask, "iso_code"] = iso
            df.loc[mask, "sherdog_url"] = "manual"
            applied += 1
            continue
        fmatch = fighters[fighters["name"] == name]
        if fmatch.empty:
            not_found.append(name)
            continue
        new_rows.append({
            "fighter_id": fmatch.iloc[0]["fighter_id"], "name": name,
            "sherdog_url": "manual", "nationality": nat, "iso_code": iso,
        })
        inserted += 1

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    after = df["iso_code"].notna().sum()
    df.to_csv(path, index=False)
    print(f"updated {applied} existing row(s), inserted {inserted} new row(s) "
          f"(not found in fighters.csv at all: {not_found})")
    print(f"matched: {before} -> {after} / {len(df)}")


if __name__ == "__main__":
    main()
