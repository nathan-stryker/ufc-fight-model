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

from src.data.fighter_renames import fighter_mask

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
    # --- Heavyweight (male), 2026-09-16 ---
    # 7 names cross-listed with light heavyweight (Aleksandar Rakic, Alex
    # Pereira, Alexander Poppeck, Felipe Franco, Johnny Walker, Tanner
    # Boser, Uran Satybaldiev) were already set in that pass above and
    # intentionally excluded from this round at the user's request, not
    # re-touched here. "lourenco" -> "Gabriel Lorenco" (our transliteration
    # of the same Portuguese name, no diacritic) -- only candidate in
    # position, unambiguous. Tai Tuivasa's own earlier "Street Fighter"
    # (set 2026-09-15, before this recategorization project existed) gets
    # overwritten with "Brawler" here -- the user revising their own
    # earlier call, same as any other deliberate overwrite this project.
    "Alexander Volkov": "Distance Striker",
    "Allen Frye Jr.": "Boxer",
    "Ante Delija": "Aggressive MMA",
    "Anthony Wint": "Explosive MMA",
    "Brando Pericic": "Power Striker",
    "Ciryl Gane": "Striker",
    "Curtis Blaydes": "Wrestler",
    "Denzel Freeman": "Karate",
    "Elisha Ellison": "Jiu-Jitsu",
    "Gable Steveson": "Explosive MMA",
    "Gabriel Lorenco": "MMA",
    "Guilherme Uriel": "MMA",
    "Javad Mahjoub": "Judo",
    "Jose Montanha": "Grappler",
    "Josh Hokit": "Pressure Wrestler",
    "Jovan Leka": "Aggressive Striker",
    "Kennedy Nzechukwu": "Striker",
    "Louie Sutherland": "Timid Brawler",
    "Lucas Armand": "MMA",
    "Marcus Buchecha": "Explosive Grappler",
    "RJ Harris": "Brawler",
    "Rizvan Kuniev": "MMA",
    "Sergei Pavlovich": "Aggressive Striker",
    "Steven Asplund": "MMA",
    "Tai Tuivasa": "Brawler",
    "Tallison Teixeira": "Muay Thai",
    "Terrance Chatman": "Counter Striker",
    "Thomas Petersen": "MMA",
    "Tom Aspinall": "MMA",
    "Tyrell Fortune": "Grappler",
    "Valter Walker": "Grappler",
    "Vitor Petrino": "Pressure Fighter",
    "Waldo Cortes Acosta": "Power Striker",
    # --- Middleweight (male), 2026-09-16 ---
    # 13 names cross-listed with an earlier completed division (welterweight/
    # light heavyweight/heavyweight) were excluded from the list shown to
    # the user, same as the heavyweight pass. "CLD" = Christian Leroy
    # Duncan, "DDP" = Dricus Du Plessis -- both unambiguous initials, not
    # guesses. Two "hernandez" and two "rodrigues"/"magomedov"/
    # "oleksiejczuk" mentions this round all resolved cleanly by message
    # order against distinct people already in the list (Anthony Hernandez
    # vs Luis Hernandez, Gregory Rodrigues vs Modestino Rodrigues, Abus
    # Magomedov vs Shara Magomedov, Michal Oleksiejczuk -- Cezary
    # Oleksiejczuk was never mentioned and stays untouched) -- no
    # contradiction to flag this time, unlike the Rodriguez/Walker cases
    # in earlier passes. Name variants resolved before this list was even
    # shown: roster.watch's "Joseph Kropschot"/"Nick Galanti"/"Treston
    # Vines"/"Yi Sak Lee"/"Zachary Reese" -> our "Joe Kropschot"/"Nicholas
    # Galanti"/"Tre'ston Vines"/"YiSak Lee"/"Zach Reese"; "Luis Dias de
    # Assis" -> "Luis Felipe Dias" is the weaker match of the six (same
    # weight class, no other candidate, but not independently confirmed
    # the way the others are).
    "Abus Magomedov": "Explosive MMA",
    "Aliaskhab Khizriev": "Wrestler",
    "Andre Petroski": "Wrestler",
    "Andrey Pulyaev": "Striker",
    "Anthony Hernandez": "Pressure Fighter",
    "Ateba Gautier": "Kickboxer",
    "Azamat Bekoev": "Wrestle-Boxer",
    "Baisangur Susurkaev": "Kickboxer",
    "Ben Johnston": "Striker",
    "Brendan Allen": "Pressure Grappler",
    "Brunno Ferreira": "Pressure Fighter",
    "Cam Rowston": "MMA",
    "Cesar Almeida": "Kickboxer",
    "Christian Leroy Duncan": "Rangy Kickboxer",
    "Damian Pinas": "Pressure Boxer",
    "Djorden Santos": "Pressure Fighter",
    "Donte Johnson": "Pressure Striker",
    "Dricus Du Plessis": "Pressure Fighter",
    "Dusko Todorovic": "Striker",
    "Dustin Stoltzfus": "MMA",
    "Edmen Shahbazyan": "Explosive Striker",
    "Eric McConico": "Pressure Fighter",
    "Gregory Rodrigues": "Pressure Striker",
    "Ismail Naurdiev": "MMA",
    "Israel Adesanya": "Counter-Striker",
    "Jacob Malkoun": "Wrestler",
    "Jared Cannonier": "Power Striker",
    "Joe Pyfer": "MMA",
    "Joe Kropschot": "Jiu-Jitsu",
    "Julien Leblanc": "MMA",
    "JunYong Park": "Pressure Fighter",
    "Kelvin Gastelum": "Pressure Striker",
    "Kyle Daukaus": "Jiu-Jitsu",
    "Luis Hernandez": "Pressure Fighter",
    "Mantas Kondratavicius": "Aggressive Striker",
    "Marc-Andre Barriault": "Pressure Striker",
    "Marco Tulio": "Pressure Striker",
    "Martin Kozak": "Kickboxer",
    "Marvin Vettori": "Pressure Fighter",
    "Matthieu Duclos": "MMA",
    "Michal Oleksiejczuk": "Pressure Striker",
    "Modestino Rodrigues": "MMA",
    "Nicholas Galanti": "Grappler",
    "Nursulton Ruziboev": "MMA",
    "Ozzy Diaz": "Striker",
    "Robert Valentin": "MMA",
    "Roman Kopylov": "Striker",
    "Ryan Gandra": "MMA",
    "Sean Strickland": "Pressure Boxer",
    "Sedriques Dumas": "Rangy Kickboxer",
    "Shara Magomedov": "Kickboxer",
    "Trent Miller": "MMA",
    "Vlasto Cepo": "Aggressive Striker",
    "Wes Schultz": "Wrestler",
    "YiSak Lee": "Pressure Fighter",
    "Yilizhati Maimaitijiang": "Grappler",
    "Zach Reese": "Aggressive MMA",
    # --- Women's Bantamweight, 2026-09-23 ---
    # roster.watch's "Nikolija Milosevic" -> our "Nina Milosevic" (135 lbs,
    # only Milosevic on file). Two "nunes" mentions resolved by message
    # order (Amanda Nunes then Josiane Nunes). The final bare "santos -
    # striker" can only be Yana Santos: Luana Santos's position in the
    # list already passed earlier in the message without a match, and the
    # sequential message-order convention this whole project has used
    # never goes backward -- not a genuine ambiguity like the Walker/
    # Rodriguez cases, so not asked about.
    "Ailin Perez": "Pressure Grappling",
    "Alex Apodaca": "Brawler",
    "Alice Pereira": "Kickboxer",
    "Amanda Nunes": "Aggressive MMA",
    "Chelsea Chandler": "Pressure MMA",
    "Daria Zhelezniakova": "MMA",
    "Josiane Nunes": "MMA",
    "Julianna Pena": "Pressure MMA",
    "Klaudia Sygula": "Volume Striker",
    "Lucia Szabova": "MMA",
    "Nina Milosevic": "Pressure Fighter",
    "Norma Dumont": "MMA",
    "Yana Santos": "Striker",
    # UFC Fight Night 289 (2026-09-26), user-supplied directly (2026-09-23).
    "Brady Hiestand": "MMA",
    "Ilimbek Akylbek Uulu": "Wrestler",
    "Mehemmedeli Osmanli": "MMA",
    "Valesca Machado": "Aggressive Striker",
    "Melissa Amaya": "MMA",
    "Raul Rosas Jr.": "Freestyle",
    # UFC 332 (2026-10-03), user-supplied directly (2026-09-28).
    "Bruce Whitehead": "Brawler",
    # --- Bantamweight (male), 2026-09-29 -- ASSIGNED BY CLAUDE, not the user ---
    # The user asked Claude to categorize this division rather than supply
    # labels. A stats-only classifier trained on the user's own labels from the
    # other divisions only matched their label family 31-33% of the time in
    # cross-validation (19% baseline), so these are reputation-based calls for
    # well-known fighters and stat-profile calls (UFC striking output, takedown
    # rate, control time, finish methods) for newer ones, defaulting to "MMA"
    # when nothing stands out. Vocabulary kept to labels the user already uses.
    # David Martinez and Rob Font keep the styles the user gave them earlier.
    "Merab Dvalishvili": "Pressure Wrestler",
    "Sean O'Malley": "Rangy Striker",
    "Petr Yan": "Pressure Boxer",
    "Mario Bautista": "Aggressive MMA",
    "Song Yadong": "Boxer",
    "Montel Jackson": "MMA",
    "Farid Basharat": "Wrestler",
    "Cory Sandhagen": "Dynamic Striker",
    "Umar Nurmagomedov": "Sambo",
    "Marlon Vera": "Counter-Striker",
    "Raoni Barcelos": "Aggressive MMA",
    "Bryce Mitchell": "Grappler",
    "Deiveson Figueiredo": "Aggressive MMA",
    "Daniel Marcos": "MMA",
    "Aiemann Zahabi": "Boxer",
    "Payton Talbott": "Dynamic Striker",
    "Adrian Yanez": "Boxer",
    "Marcus McGhee": "Explosive Striker",
    "Jonathan Martinez": "Kickboxer",
    "Elijah Smith": "MMA",
    "Jean Matsumoto": "Aggressive MMA",
    "Said Nurmagomedov": "Striker",
    "Chris Gutierrez": "Kickboxer",
    "Charles Jourdain": "Aggressive Striker",
    "Davey Grant": "Pressure Fighter",
    "Alatengheili": "Wrestler",
    "Ricky Simon": "Pressure Wrestler",
    "Cody Garbrandt": "Boxer",
    "Victor Henry": "Volume Striker",
    "Jakub Wiklacz": "Grappler",
    "Cody Haddon": "Pressure Fighter",
    "Ethyn Ewing": "Volume Striker",
    "Kyler Phillips": "MMA",
    "Da'Mon Blackshear": "Grappler",
    "Aleksandre Topuria": "Boxer",
    "Javid Basharat": "Kickboxer",
    "Rinya Nakamura": "Wrestler",
    "SuYoung You": "Wrestler",
    "Pedro Munhoz": "Pressure Fighter",
    "Juan Diaz": "Wrestler",
    "Hector Santiago": "Striker",
    "Dan Ige": "Aggressive Striker",
    "Francesco Nuzzi": "Aggressive Striker",
    "Serhiy Sidey": "MMA",
    "Benardo Sopaj": "MMA",
    "Abdul Hussein": "Grappler",
    "Borislav Nikolic": "MMA",
    "ChangHo Lee": "Wrestler",
    "Santiago Luna": "MMA",
    "Hecher Sosa": "Volume Striker",
    "Malcolm Wellmaker": "Aggressive Striker",
    "Colby Thicknesse": "Grappler",
    "John Castaneda": "Aggressive MMA",
    "Henry Cejudo": "Wrestler",
    "Cody Stamann": "Wrestler",
    "Carlos Vera": "Jiu-Jitsu",
    "Jafel Filho": "Grappler",
    "Caolan Loughran": "Pressure Fighter",
    "Cristian Quinonez": "Grappler",
    "Lawrence Lui": "Wrestler",
    "Cameron Saaiman": "Aggressive Striker",
    "Jake Hadley": "MMA",
    "Timmy Cuamba": "MMA",
    "Muin Gafurov": "Sambo",
    "John Yannis": "Striker",
    "John Garza": "Striker",
    "Adrian Luna Martinetti": "Brawler",
    "Garrett Armfield": "MMA",
    "Mark Vologdin": "Karate",
    "Baergeng Jieleyisi": "MMA",
    "Sulangrangbo": "MMA",
    "Chad Anheliger": "MMA",
    "Jamie Siraj": "MMA",
    "Nathan Fletcher": "Grappler",
    "Bekzat Almakhan": "Karate",
    "Patchy Mix": "Grappler",
    "Aoriqileng": "Brawler",
    "AJ Cunningham": "MMA",
    "Brad Katona": "Pressure Fighter",
    "Quang Le": "MMA",
    "Pedro Falcao": "Wrestler",
    "Luan Lacerda": "Grappler",
    "Angel Pacheco": "Boxer",
    "Dan Argueta": "Wrestler",
    "Cameron Smotherman": "Striker",
    "Cortavious Romious": "Wrestler",
    "Toshiomi Kazama": "Grappler",
    "Josias Musasa": "Kickboxer",
    "Xiao Long": "Striker",
    "Vince Morales": "Striker",
    "Kris Moutinho": "Brawler",
    "Cody Gibson": "MMA",
    "Saimon Oliveira": "Grappler",
}

# --- Every other active fighter, 2026-09-29 -- ASSIGNED BY CLAUDE, not the user ---
# The user asked Claude to categorize everyone they hadn't labeled, using the
# same method as the bantamweight section above: reputation for well-known
# fighters, UFC stat profile for newer ones, the user's own label vocabulary,
# UFC.com's tag kept where it already fits. Applied BEFORE MANUAL, so any label
# the user gives (now or later) always wins. A pre-change copy of
# fighter_style.csv is at data/processed/fighter_style.before_claude_styles.csv.
# Skipped: the middleweight Bruno Silva (same name as the user-labeled
# flyweight one -- a name-keyed entry would hit both).
CLAUDE_ASSIGNED = {
    # Featherweight
    "Aaron Pico": "Wrestle-Boxer", "Alberto Montes": "MMA", "Alexander Volkanovski": "Pressure Fighter",
    "Aljamain Sterling": "Grappler", "Andre Fili": "MMA", "Arnold Allen": "Striker", "Austin Bashi": "Wrestler",
    "Bogdan Grad": "Grappler", "Calvin Kattar": "Boxer", "Chepe Mariscal": "Brawler", "Christian Rodriguez": "MMA",
    "Connor Matthews": "MMA", "Cub Swanson": "Aggressive Striker", "Damien Anderson": "MMA", "Daniel Pineda": "Grappler",
    "Daniel Santos": "Muay Thai", "Danny Silva": "Boxer", "Darren Elkins": "Pressure Wrestler", "Dennis Buzukja": "Striker",
    "Dooho Choi": "Power Striker", "Douglas Silva de Andrade": "Aggressive Striker", "Erik Silva": "MMA",
    "Ezra Elliott": "Wrestler", "Felipe Lima": "MMA", "Fernando Padilla": "Aggressive Striker", "Gabriel Miranda": "Grappler",
    "Gabriel Santos": "Wrestler", "Gaston Bolanos": "Kickboxer", "Gianni Vazquez": "MMA", "Giga Chikadze": "Kickboxer",
    "Hyder Amil": "Aggressive Striker", "Isaac Dulgarian": "Wrestler", "Isaac Thomson": "MMA", "Jack Jenkins": "MMA",
    "Jack Shore": "Grappler", "Jamall Emmers": "Aggressive MMA", "Javier Reyes": "Striker", "Jean Silva": "Aggressive Striker",
    "Jeka Saragih": "Striker", "JeongYeong Lee": "MMA", "Jessie Rosas": "Grappler", "Joanderson Brito": "Explosive MMA",
    "Jonathan Pearce": "Pressure Wrestler", "JooSang Yoo": "Striker", "Jose Aldo": "Kickboxer", "Jose Delano": "Volume Striker",
    "Josh Emmett": "Power Striker", "Julian Erosa": "Brawler", "Kaan Ofli": "Grappler", "Keiichiro Nakamura": "Striker",
    "Kevin Vallejos": "Aggressive Striker", "Kron Gracie": "Jiu-Jitsu", "Kurtis Campbell": "Wrestler",
    "Lerone Murphy": "Technical Striker", "Lerryan Douglas": "Aggressive Striker", "Losene Keita": "Striker",
    "Lucas Alexander": "Striker", "Lucas Almeida": "Striker", "Luke Riley": "Pressure Boxer", "Manolo Zecchini": "Striker",
    "Marcio Barbosa": "Aggressive Striker", "Marwan Rahiki": "Aggressive Striker", "Melquizael Costa": "MMA",
    "Melsik Baghdasaryan": "Kickboxer", "Miles Johns": "Boxer", "Mohammad Yahya": "MMA", "Morgan Charriere": "Aggressive Striker",
    "Movsar Evloev": "Pressure Wrestler", "Muhammad Naimov": "MMA", "Murtazali Magomedov": "Grappler",
    "Nathaniel Wood": "Pressure Fighter", "Ollie Schmid": "Striker", "Otari Tanzilovi": "Kickboxer", "Pat Sabatini": "Grappler",
    "Pavel Andrusca": "Wrestler", "Ramon Taveras": "Striker", "Ricardo Ramos": "MMA", "Ricky Turcios": "MMA",
    "Robert Ruchala": "MMA", "Rodrigo Vera": "MMA", "Ryan Kuse": "MMA", "Sean King III": "MMA", "Sean Woodson": "Rangy Striker",
    "Sebastian Szalay": "Striker", "SeungWoo Choi": "Striker", "Shane Collins": "Grappler", "Steve Garcia": "Power Striker",
    "Steven Nguyen": "Striker", "Tommy McMillen": "Volume Striker", "Victor Hugo": "MMA", "Vinicius Oliveira": "Aggressive Striker",
    "Westin Wilson": "Grappler", "William Gomis": "Kickboxer", "Yadier del Valle": "Grappler", "Yair Rodriguez": "Dynamic Striker",
    "Yizha": "MMA", "Youssef Zalal": "Grappler", "Zhu Kangjie": "Striker",
    # Women's Flyweight
    "Alexa Grasso": "Boxer", "Andrea Lee": "Muay Thai", "Anna Melisano": "MMA", "Ariane da Silva": "Muay Thai",
    "Brogan Walker": "MMA", "Carli Judice": "Aggressive Striker", "Casey O'Neill": "Pressure Fighter",
    "Diana Belbita": "Volume Striker", "Dione Barbosa": "Grappler", "Eduarda Moura": "Jiu-Jitsu", "Erin Blanchfield": "Grappler",
    "Gabriella Fernandes": "Striker", "Ivana Petrovic": "MMA", "JJ Aldrich": "Striker", "Jamey-Lyn Horth": "Kickboxer",
    "Jasmine Jasudavicius": "Pressure Grappler", "Jeisla Chaves": "MMA", "Juliana Miller": "Grappler",
    "Julija Stoliarenko": "Grappler", "Karine Silva": "Grappler", "Lauren Murphy": "MMA", "Manon Fiorot": "Karate",
    "Maycee Barber": "Pressure Fighter", "Melissa Gatto": "Aggressive MMA", "Miranda Maverick": "Grappler",
    "Natalia Silva": "Taekwondo", "Ravena Oliveira": "MMA", "Rose Namajunas": "Technical Striker", "Tereza Bleda": "Wrestler",
    "Tracy Cortez": "Wrestler", "Valentina Shevchenko": "Muay Thai", "Veronica Hardy": "MMA", "Viviane Araujo": "MMA",
    "Wang Cong": "Kickboxer", "Yuneisy Duben": "MMA", "Zhang Weili": "Sanda",
    # Welterweight (not on the user's welterweight list)
    "Austin Vanderford": "Wrestler", "Bassil Hafez": "MMA", "Cam Nelson": "Wrestler", "Carlos Leal": "Brawler",
    "Carlston Harris": "MMA", "Colby Covington": "Pressure Wrestler", "Court McGee": "Pressure Fighter",
    "Daniel Frunza": "Muay Thai", "Ding Meng": "MMA", "Farman Hasanov": "Wrestler", "Geoff Neal": "Power Striker",
    "Islam Dulatov": "Striker", "Islam Makhachev": "Sambo", "Jack Hermansson": "Pressure Fighter", "Jacobe Smith": "Explosive MMA",
    "Jake Matthews": "Grappler", "Jared Gooden": "Brawler", "Joaquin Buckley": "Power Striker", "Jonathan Micallef": "MMA",
    "Jose Souza": "MMA", "Khaos Williams": "Power Striker", "Leon Edwards": "Technical Striker", "Leon Shahbazyan": "MMA",
    "Levan Chokheli": "Aggressive Striker", "Matthew Semelsberger": "Striker", "Max Griffin": "Kickboxer",
    "Michael Chiesa": "Grappler", "Michael Morales": "Power Striker", "Michael Oliveira": "Kickboxer", "Mickey Gall": "Grappler",
    "Mike Malott": "MMA", "Myktybek Orolbai": "Wrestler", "Niko Price": "Brawler", "Nikolay Veretennikov": "Striker",
    "Oban Elliott": "MMA", "Phil Rowe": "Power Striker", "Preston Parsons": "Grappler", "Punahele Soriano": "Aggressive MMA",
    "Sam Patterson": "MMA", "Santiago Ponzinibbio": "Aggressive Striker", "Saygid Izagakhmaev": "Sambo", "Sean Brady": "Grappler",
    "Shavkat Rakhmonov": "Aggressive MMA", "Song Kenan": "Striker", "Stephen Thompson": "Karate", "Theodor Berggren": "MMA",
    "Tim Means": "Muay Thai", "Ty Miller": "Aggressive Striker",
    # Lightweight
    "Anshul Jubli": "Aggressive Striker", "Austin Hubbard": "MMA", "Axel Sola": "Karate", "Beneil Dariush": "Grappler",
    "Chase Hooper": "Grappler", "Clay Guida": "Pressure Wrestler", "Damian Rzepecki": "Wrestler", "Damon Jackson": "Grappler",
    "Dustin Poirier": "Boxer", "Edson Barboza": "Muay Thai", "Elves Brener": "Aggressive MMA", "Evan Elder": "Striker",
    "Francis Marshall": "Wrestler", "Guram Kutateladze": "Kickboxer", "Ismael Bonfim": "Muay Thai",
    "Jamie Mullarkey": "Aggressive Striker", "Joe Solecki": "Grappler", "Jordan Vucenic": "MMA", "Kaue Fernandes": "Striker",
    "Kurt Holobaugh": "MMA", "Lando Vannata": "Dynamic Striker", "Lucas Brennan": "Grappler", "Ludovit Klein": "MMA",
    "Maheshate": "Striker", "Mark Choinski": "Wrestler", "Mason Jones": "Pressure Fighter", "Mateusz Gamrot": "Pressure Wrestler",
    "Matheus Camilo": "Wrestler", "Michael Johnson": "Boxer", "Mike Davis": "MMA", "Milos Janicic": "Striker",
    "Mitch Ramirez": "MMA", "Nikolas Motta": "Kickboxer", "Nurullo Aliev": "Wrestler", "Quillan Salkilld": "Explosive MMA",
    "Rafael Fiziev": "Muay Thai", "Richie Miranda": "Wrestler", "Rolando Bedoya": "Volume Striker", "Sangwook Kim": "MMA",
    "Shem Rock": "MMA", "Stan Dorsainvil": "Brawler", "Thiago Moises": "Grappler", "Viacheslav Borshchev": "Kickboxer",
    "Vinc Pichel": "MMA", "Yanal Ashmouz": "Wrestler",
    # Middleweight
    "Abdul Razak Alhassan": "Power Striker", "Andre Muniz": "Grappler", "Antonio Trocoli": "MMA", "Armen Petrosyan": "Kickboxer",
    "Bo Nickal": "Wrestler", "Brad Tavares": "MMA", "Caio Borralho": "MMA", "Cezary Oleksiejczuk": "Wrestler",
    "Cody Brundage": "Wrestler", "Danny Barlow": "Striker", "Dylan Budka": "Wrestler", "Eryk Anders": "Power Striker",
    "Gilbert Urbina": "Aggressive Striker", "Ihor Potieria": "Aggressive Striker", "Ikram Aliskerov": "Sambo",
    "Jackson McVey": "Aggressive MMA", "Jose Daniel Medina": "MMA", "Julian Marquez": "Grappler", "Kamaru Usman": "Pressure Wrestler",
    "Khamzat Chimaev": "Pressure Wrestler", "Luis Felipe Dias": "Striker", "Mansur Abdul-Malik": "Aggressive Striker",
    "Michael Page": "Karate", "Michel Pereira": "Dynamic Striker", "Nassourdine Imavov": "Technical Striker", "Nick Klein": "Wrestler",
    "Robert Bryczek": "Boxer", "Rodolfo Vieira": "Brazilian Jiu-Jitsu", "Ryan Loder": "Wrestler", "Torrez Finney": "Wrestler",
    "Tre'ston Vines": "MMA", "Tresean Gore": "MMA", "Vicente Luque": "Aggressive MMA", "Yousri Belgaroui": "Kickboxer",
    # Heavyweight
    "Alexandr Romanov": "Wrestler", "Alvin Hines": "Striker", "Chris Barnett": "Brawler", "Derrick Lewis": "Brawler",
    "Don'Tale Mayes": "Boxer", "Gokhan Saricam": "Boxer", "Guilherme Pat": "Striker", "Hamdy Abdelwahab": "Wrestler",
    "Jailton Almeida": "Pressure Grappler", "Jairzinho Rozenstruik": "Kickboxer", "Jamal Pogues": "Boxer", "Jhonata Diniz": "Kickboxer",
    "Jon Jones": "MMA", "Justin Tafa": "Power Striker", "Lukasz Brzeski": "Striker", "Marcin Tybura": "MMA", "Marek Bujlo": "Grappler",
    "Mario Pinto": "Aggressive MMA", "Martin Buday": "MMA", "Max Gimenis": "MMA", "Mick Parkin": "MMA", "Mohammed Usman": "MMA",
    "Robelis Despaigne": "Taekwondo", "Rodrigo Nascimento": "MMA", "Ryan Spann": "Aggressive MMA", "Sean Sharaf": "Brawler",
    "Serghei Spivac": "Wrestler", "Shamil Gaziev": "MMA", "Stipe Miocic": "Wrestle-Boxer", "Tanner Boser": "Kickboxer",
    # Flyweight
    "Alibi Idiris": "Wrestler", "Allan Nascimento": "Grappler", "Andre Lima": "Kickboxer", "Asu Almabayev": "Pressure Grappler",
    "Azat Maksum": "Wrestler", "Brandon Royval": "Aggressive MMA", "CJ Vergara": "Striker", "Carlos Hernandez": "MMA",
    "Daniel Barez": "Striker", "Fabia Sintes": "Grappler", "Felipe Bunes": "Grappler", "Felipe dos Santos": "Muay Thai",
    "HyunSung Park": "Aggressive MMA", "Jesus Aguilar": "MMA", "Jimmy Flick": "Grappler", "Jose Johnson": "MMA", "Kiru Sahota": "MMA",
    "Lone'er Kavanagh": "Kickboxer", "Lucas Rocha": "Muay Thai", "Manel Kape": "Explosive Striker",
    "Matheus Nicolau": "Technical Striker", "Namsrai Batbayar": "Striker", "Steve Erceg": "MMA", "Stewart Nicoll": "Wrestler",
    "Tagir Ulanbekov": "Wrestler",
    # Light Heavyweight
    "Anthony Smith": "Aggressive MMA", "Austen Lane": "MMA", "Billy Elekana": "MMA", "Bruno Lopes": "Wrestler",
    "Caio Machado": "Striker", "Carlos Ulberg": "Kickboxer", "Christian Edwards": "MMA", "Felipe Franco": "MMA",
    "Ivan Erslan": "Boxer", "Jan Blachowicz": "Power Striker", "Jimmy Crute": "Grappler", "Jiri Prochazka": "Aggressive Striker",
    "Julius Walker": "Wrestler", "Kevin Christian": "Striker", "Lucas Fernando": "Striker", "Magomed Gadzhiyasulov": "Wrestler",
    "Marcin Prachnio": "Karate", "Navajo Stirling": "Kickboxer", "Nikita Krylov": "Aggressive MMA", "Oumar Sy": "MMA",
    "Ovince Saint Preux": "MMA", "Paul Craig": "Grappler", "Rafael Cerqueira": "MMA", "Reinier de Ridder": "Grappler",
    "Tuco Tokkos": "Grappler",
    # Women's Bantamweight
    "Bia Mesquita": "Grappler", "Hailey Cowan": "Wrestler", "Irina Alekseeva": "MMA", "Jacqueline Cavalcanti": "Striker",
    "Joselyne Edwards": "Striker", "Julia Avila": "MMA", "Karol Rosa": "Muay Thai", "Kayla Harrison": "Judo", "Ketlen Vieira": "Judo",
    "Luana Carolina": "Muay Thai", "Luana Santos": "Judo", "Macy Chiasson": "MMA", "Mayra Bueno Silva": "Grappler",
    "Melissa Croden": "MMA", "Melissa Mullins": "MMA", "Michelle Montague": "Wrestler", "Miesha Tate": "Wrestler",
    "Montse Rendon": "MMA", "Nora Cornolle": "Muay Thai", "Priscila Cachoeira": "Brawler", "Raquel Pennington": "Pressure Fighter",
    "Tainara Lisboa": "Muay Thai", "Tamires Vidal": "Brazilian Jiu-Jitsu",
    # Women's Strawweight
    "Alexia Thainara": "Grappler", "Angela Hill": "Muay Thai", "Carol Foro": "Karate", "Delphine Benouaich": "Brawler",
    "Gigi Canuto": "Grappler", "Gillian Robertson": "Grappler", "Jaqueline Amorim": "Grappler", "Julia Polastri": "Striker",
    "Karolina Kowalkiewicz": "Muay Thai", "Ketlen Souza": "Boxer", "Loma Lookboonmee": "Muay Thai", "Luana Pinheiro": "Judo",
    "Mackenzie Dern": "Brazilian Jiu-Jitsu", "Mizuki": "Karate", "Nicolle Caliari": "MMA", "Polyana Viana": "Jiu-Jitsu",
    "Sam Hughes": "Pressure Fighter", "Shanelle Dyer": "Muay Thai", "Talita Alencar": "Grappler",
    "Vanessa Demopoulos": "Jiu-Jitsu", "Virna Jandiroba": "Grappler",
    # Catch weight (last fight at a catchweight)
    "Brian Ortega": "Jiu-Jitsu", "Chris Weidman": "Wrestler", "Eduardo Chapolin": "MMA", "Ernesta Kareckaite": "Striker",
    "James Llontop": "Striker", "Matt Schnell": "Brazilian Jiu-Jitsu", "Tim Elliott": "Wrestler",
    # On roster.watch's active rosters but not in the site's own "fought in the
    # last 24 months" set, so missed above (mostly TUF 34 cast / new signings with
    # no UFC tape). Labeled from their Sherdog pro win methods (identity checked
    # by DOB), UFC.com's tag where it had one, reputation for Yahya/Chookagian.
    "Marcos Degli": "Aggressive MMA", "Asaf Chopurov": "Aggressive MMA", "Louis Lee Scott": "Aggressive Striker",
    "Cody Chovancek": "MMA", "Louis Jourdain": "MMA", "Steven Koslow": "Grappler", "Ramiro Jimenez": "Aggressive MMA",
    "Tom Pagliarulo": "Aggressive Striker", "Taner Trembley": "Grappler", "Piero Guaylupo": "Power Striker",
    "Callum Connor": "Aggressive Striker", "Alvi Dasuyev": "Aggressive MMA", "Jonny Parsons": "Muay Thai",
    "Adam Darby": "Aggressive MMA", "Jaden Ortega": "Aggressive Striker", "Mayton Perea": "Aggressive MMA",
    "Igor Cavalcanti": "Power Striker", "Damian Piwowarczyk": "Aggressive MMA", "Roman Gabriel Puga": "Aggressive Striker",
    "Rani Yahya": "Grappler", "Katlyn Cerminara": "Volume Striker",
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
    # The 185 lbs (middleweight) Bruno Silva -- user-supplied (2026-09-29).
    "http://ufcstats.com/fighter-details/12ebd7d157e91701": "Pressure Striker",
    # Anthony "The Bully" Romero, UFC 332 debut (not the Canadian "The Genius"
    # Romero also in fighters.csv) -- user-supplied (2026-10-02).
    "http://ufcstats.com/fighter-details/4419acb81e6f0ea4": "Pressure Fighter",
}


def main():
    path = PROCESSED_DIR / "fighter_style.csv"
    df = pd.read_csv(path)
    fighters = pd.read_csv(PROCESSED_DIR / "fighters.csv")[["fighter_id", "name"]]

    set_count, cleared, inserted, not_found = 0, 0, 0, []
    new_rows = []
    # Claude's assignments first; the user's own MANUAL labels win on any overlap.
    for name, style in {**CLAUDE_ASSIGNED, **MANUAL}.items():
        mask = df["name"] == name
        if mask.any():
            df.loc[mask, "style"] = style
            if style is None:
                cleared += 1
            else:
                set_count += 1
            continue
        fmatch = fighters[fighter_mask(fighters, name)]
        if fmatch.empty:
            not_found.append(name)
            continue
        if (df["fighter_id"] == fmatch.iloc[0]["fighter_id"]).any():  # renamed; row exists under the new name
            df.loc[df["fighter_id"] == fmatch.iloc[0]["fighter_id"], "style"] = style
            set_count += 1
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
