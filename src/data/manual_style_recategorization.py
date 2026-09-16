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
    # Marina Rodriguez / Piera Rodriguez and Xiong Jingnan were both
    # ambiguous/contradictory as first given (one bare "Rodriguez" set,
    # one cleared -- unclear which was which; Xiong Jingnan set then
    # "remove"d in the same message) -- asked the user rather than
    # guessed, resolved below. Tina Black still has no fighters.csv row at
    # all (checked the live upstream Greco1899 mirror directly, not just
    # our local copy -- she's not there either) -- can't add a real,
    # sourced entry for her without fabricating a fighter_id, so she's
    # left out until UFCStats actually has her on file.
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
    # Resolved: Piera = MMA, Marina = removed; Xiong Jingnan keeps her
    # earlier "Striker" instruction (per the user, 2026-09-15).
    "Piera Rodriguez": "MMA",
    "Marina Rodriguez": None,
    "Xiong Jingnan": "Striker",
    # --- Lightweight, 2026-09-16 ---
    # Roster pulled from roster.watch this pass (data/processed/
    # roster_watch.json, a local reference file, NOT part of the trained
    # pipeline -- see its own note in export_web_model.py/README if that
    # changes) rather than our own active-roster export, since the user
    # wants a comprehensive division list independent of our 24-month
    # activity window. Two names needed resolving against fighters.csv
    # first: roster.watch's "Thomas Gantt" -> our "Tommy Gantt" (already
    # had a style from way earlier this session) and "Cristian Perez
    # Gonzalez" -> our "Cristian Perez" (155 lbs, confirms same person).
    # "BSD" = Benoit Saint Denis, "RDA" = Rafael Dos Anjos -- both
    # unambiguous, widely-used abbreviations, not guesses. From here on
    # the user is giving more specific archetypes than the earlier
    # divisions' single-word buckets (e.g. "Pressure Striker" instead of
    # just "Striker") -- several of these overwrite a value this same
    # fighter already got in an earlier division's pass (e.g. Arman
    # Tsarukyan: "Kickboxer" from the welterweight pass -> "Pressure
    # Fighter" here); the later entry in this dict literal wins, which is
    # exactly the intended behavior for a deliberate re-recategorization.
    "Abdul-Kareem Al-Selwady": "Explosive MMA",
    "Adam Livingston": "MMA",
    "Akbar Abdullaev": "Muay Thai",
    "Alex Reyes": "Aggressive MMA",
    "Alexander Hernandez": "Aggressive Striker",
    "Arman Tsarukyan": "Pressure Fighter",
    "Artur Minev": "MMA",
    "Benoit Saint Denis": "Pressure Fighter",
    "Billy Quarantillo": "Pressure Fighter",
    "Bolaji Oki": "Aggressive Striker",
    "Charles Oliveira": "Muay Thai / Jiu-Jitsu",
    "Charlie Campbell": "Pressure Striker",
    "Chris Duncan": "Pressure Striker",
    "Chris Padilla": "Pressure Fighter",
    "Claudio Puelles": "Grappler",
    "Conor McGregor": "Counter-Striker",
    "Cristian Perez": "MMA",
    "Dakota Hope": "MMA",
    "Damir Hadzovic": "Aggressive Striker",
    "Dan Hooker": "Kickboxer",
    "Daniel Zellhuber": "Technical Striker",
    "Darrius Flowers": "Pressure Striker",
    "David Onama": "Aggressive MMA",
    "Diego Ferreira": "MMA",
    "Dom Mar Fan": "Grappler",
    "Drakkar Klose": "Pressure Fighter",
    "Drew Dober": "Pressure Striker",
    "Esteban Ribovics": "Aggressive Striker",
    "Fares Ziam": "Rangy Kickboxer",
    "Gabe Green": "Pressure Fighter",
    "Gauge Young": "Pressure Fighter",
    "Grant Dawson": "Pressure Grappler",
    "Harry Hardwick": "Pressure MMA",
    "Ignacio Bahamondes": "Aggressive Striker",
    "Ilia Topuria": "Pressure Boxer",
    "Jai Herbert": "Muay Thai",
    "Jalin Turner": "Striker",
    "Jared Gordon": "Freestyle",
    "Jefferson Nascimento": "MMA",
    "Jeremy Stephens": "Aggressive Striker",
    "Jim Miller": "MMA",
    "Joaquim Silva": "MMA",
    "Jordan Leavitt": "Grappler",
    "Josiah Harrell": "MMA",
    "Justin Gaethje": "Pressure Striker",
    "Kai Kamaka III": "MMA",
    "King Green": "Hood Boxing",
    "Kody Steele": "Pressure Fighter",
    "Kyle Nelson": "Pressure Striker",
    "Kyle Prepolec": "Striker",
    "Lance Gibson Jr.": "Pankration",
    "Magomed Zaynukov": "Muay Thai",
    "Mairon Santos": "MMA",
    "Mandel Nallo": "MMA",
    "Manoel Sousa": "Aggressive MMA",
    "Manuel Torres": "Aggressive Striker",
    "MarQuel Mederos": "Striker",
    "Mateusz Rebecki": "Aggressive MMA",
    "Matt Frevola": "Pressure Fighter",
    "Mauricio Ruffy": "Explosive Kickboxer",
    "Max Holloway": "Volume Striker",
    "Michael Chandler": "Chinny Wrestling",
    "Nasrat Haqparast": "Pressure Striker",
    "Nate Landwehr": "Pressure Striker",
    "Nazim Sadykhov": "Pressure Striker",
    "Noah Gugnon": "MMA",
    "Ottman Azaitar": "Aggressive Striker",
    "Paddy Pimblett": "Aggressive MMA",
    "Rafa Garcia": "Grappler",
    "Rafael Dos Anjos": "Pressure Fighter",
    "Renato Moicano": "MMA",
    "Roberto Romero": "Aggressive Striker",
    "Rongzhu": "Pressure Striker",
    "Salahdine Parnasse": "Striker",
    "Samuel Sanches": "MMA",
    "Silvestre Sanchez": "Striker",
    "Sodiq Yusuff": "Dynamic Striker",
    "Terrance McKinney": "Chinny Wrestling",
    "Tofiq Musayev": "Sanda",
    "Tom Nolan": "Long-Range Striker",
    "Trevor Peek": "Street Fighter",
    "Trey Ogden": "Grappler",
    # --- Flyweight (male), 2026-09-16 ---
    # "Rosas" in the user's message doesn't match anyone on the flyweight
    # list -- resolved as "Nilson Rojas" (position in the message lines up
    # exactly where Rojas falls in the roster.watch list, surrounded by
    # unambiguous matches on both sides: Mitch Raposo before, Nyamjargal
    # Tumendemberel after). Two bare "rodriguez" mentions this round, NOT
    # ambiguous like the strawweight pass's Rodriguez pair -- these land on
    # Imanol Rodriguez and Ronaldo Rodriguez respectively purely by
    # message order, both confirmed the same way (surrounding names on
    # both sides match cleanly, no contradiction to flag).
    "Alden Coria": "Freestyle",
    "Alessandro Costa": "Jiu-Jitsu",
    "Alex Perez": "MMA",
    "Alexandre Pantoja": "Jiu-Jitsu",
    "Amir Albazi": "Grappler",
    "Bilal Hasan": "Taekwondo",
    "Brandon Moreno": "MMA",
    "Charles Johnson": "Rangy Striker",
    "Christian Natividad": "MMA",
    "Clayton Carpenter": "Explosive MMA",
    "Cody Durden": "Pressure Wrestler",
    "DongHun Choi": "MMA",
    "Edgar Chairez": "Aggressive MMA",
    "Imanol Rodriguez": "Aggressive MMA",
    "Jose Ochoa": "Pressure Striker",
    "Joseph Morales": "Grappler",
    "Joshua Van": "Pressure Boxer",
    "Kai Asakura": "Dynamic Striker",
    "Kai Kara-France": "Aggressive Striker",
    "Kevin Borjas": "Aggressive Striker",
    "Kyoji Horiguchi": "Karate",
    "Luis Gurule": "Pressure Fighter",
    "Michael Aljarouj": "Kung Fu",
    "Mitch Raposo": "Grappler",
    "Nilson Rojas": "Wild Boxer",
    "Nyamjargal Tumendemberel": "Pressure Sambo",
    "Ode Osbourne": "Explosive MMA",
    "Rafael Estevam": "Pressure Grappler",
    "Ramazan Temirov": "Explosive Striker",
    "Rei Tsuruya": "Wrestler",
    "Ronaldo Rodriguez": "Aggressive MMA",
    "Sumudaerji": "Striker",
    "Tatsuro Taira": "Grappler",
    # --- Light Heavyweight (male), 2026-09-16 ---
    # roster.watch's "Ce Liu" / "Muhammad Said" -> our "Liu Ce" (Chinese
    # name order preserved in fighters.csv) / "Muhammad Saidov" (fuller
    # form), both confirmed at 205 lbs. A bare "Walker" this round is
    # genuinely ambiguous (Johnny Walker AND Julius Walker are both on
    # this list, only one "Walker" mention given) -- held back rather than
    # guessed, unlike every other name this pass, which resolved cleanly:
    # "fernandez" only matches Luke Fernandez (Lucas Fernando has a
    # different surname, not a collision).
    "Abdul Rakhman Yakhyaev": "Aggressive Finisher",
    "Aleksandar Rakic": "Kickboxer",
    "Alex Pereira": "Elite Kickboxer",
    "Alexander Poppeck": "MMA",
    "Alik Lorenz": "Aggressive Finisher",
    "Alonzo Menifield": "Explosive Striker",
    "Azamat Murzakanov": "Explosive Striker",
    "Bogdan Guskov": "Aggressive Striker",
    "Brendson Ribeiro": "Kill or Be Killed",
    "Diyar Nurgozhay": "MMA",
    "Dominick Reyes": "Boxer",
    "Dustin Jacoby": "Aggressive Patience",
    "Gerald Meerschaert": "Submission Specialist",
    "Ibo Aslan": "Aggressive Striker",
    "Ion Cutelaba": "Aggressive MMA",
    "Iwo Baraniewski": "Aggressive MMA",
    "Jamahal Hill": "Boxer",
    # Resolved: Johnny Walker, not Julius Walker (per the user, 2026-09-16).
    "Johnny Walker": "Aggressive Striker",
    "Junior Tafa": "Pressure Striker",
    "Khalil Rountree Jr.": "Aggressive Striker",
    "Levi Rodrigues Jr.": "Brawler",
    "Liu Ce": "Kickboxer",
    "Luke Fernandez": "MMA",
    "Magomed Ankalaev": "Counter-Striker",
    "Magomed Tuchalov": "MMA",
    "Modestas Bukauskas": "Long-Range Kickboxer",
    "Muhammad Saidov": "Judo",
    "Paulo Costa": "Aggressive Striker",
    "Quentin Pasley": "Boxer",
    "Rafael Tobias": "Aggressive Grappler",
    "Robert Whittaker": "Striker",
    "Rodolfo Bellato": "Pressure Fighter",
    "Roman Dolidze": "Explosive MMA",
    "Uran Satybaldiev": "Judo",
    "Volkan Oezdemir": "Aggressive Striker",
    "Zhang Mingyang": "Aggressive Striker",
}

# Rare escape hatch for a duplicate fighters.csv name where the two real
# people are genuinely different (load_fights.py's own docstring names
# this exact pair as its example) -- name-only matching in MANUAL above
# would silently apply to BOTH. Keyed by fighter_id instead.
MANUAL_BY_ID = {
    # "Bruno Gustavo da Silva" (roster.watch's fuller name) = the 125 lbs
    # Bruno Silva, not the 185 lbs one -- confirmed by weight_lbs in
    # fighters.csv, per the user (2026-09-16).
    "http://ufcstats.com/fighter-details/294aa73dbf37d281": "Aggressive MMA",
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

    by_id_set = 0
    for fid, style in MANUAL_BY_ID.items():
        mask = df["fighter_id"] == fid
        if mask.any():
            df.loc[mask, "style"] = style
            by_id_set += 1
        else:
            fmatch = fighters[fighters["fighter_id"] == fid]
            if not fmatch.empty:
                df = pd.concat([df, pd.DataFrame([{
                    "fighter_id": fid, "name": fmatch.iloc[0]["name"], "style": style,
                }])], ignore_index=True)
                by_id_set += 1
            else:
                not_found.append(fid)

    df.to_csv(path, index=False)
    print(f"set {set_count}, cleared {cleared}, inserted {inserted} new row(s), "
          f"{by_id_set} by fighter_id "
          f"(not found in fighters.csv at all: {not_found})")


if __name__ == "__main__":
    main()
