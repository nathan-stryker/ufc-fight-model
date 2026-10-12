"""
UFCStats renames fighters after the fact -- usually a debut fighter whose
card name differed from their legal/UFC name, renamed once they've fought
(2026-09-28: all three were UFC Fight Night 289 debuts). The manual_*
override scripts are keyed by name, so a rename silently stops an override
applying: the user-supplied reach/stance for Osmanli and Akylbek vanished
this way when load_data.py re-pulled the raw mirror.

OLD_NAME_TO_ID maps a name used in an override file to the fighter's stable
UFCStats fighter_id. fighter_mask() matches by name first, then by this id.
If an override script prints a name as "not found", add it here.
"""
UFCSTATS = "http://ufcstats.com/fighter-details/"

OLD_NAME_TO_ID = {
    "Mehemmedeli Osmanli": UFCSTATS + "2bbdbc925f4323ac",   # now "Mahammadali Osmanli"
    "Ilimbek Akylbek Uulu": UFCSTATS + "130b65b53f30f33c",  # now "Ilimbek Akylbek"
    "Valesca Machado": UFCSTATS + "a1a91dbf41a029c4",       # now "Tina Black"
    "Cameron Nelson": UFCSTATS + "34d4cae19105eb68",        # now "Cam Nelson"
    "Eduardo Henrique": UFCSTATS + "62f3039da2f92a8c",      # now "Eduardo Chapolin"
    "SuYoung You": UFCSTATS + "a474aade8eb3a8f0",           # shown as "Soo Young Yoo", see DISPLAY_NAMES
}

# fighter_id -> the name the user wants shown, where UFCStats' spelling is
# wrong or not the fighter's known name. load_data.py applies this to
# fighters.csv and fights.csv after the raw mirror is parsed (so every
# downstream file and the website use it), and scrape_upcoming_card.py to
# matched card names. Add the old name to OLD_NAME_TO_ID above as well so
# name-keyed override files keep applying.
DISPLAY_NAMES = {
    # User-supplied (2026-10-12, UFC Fight Night 291 card).
    UFCSTATS + "a474aade8eb3a8f0": "Soo Young Yoo",
}


def apply_display_names(fighters, fights):
    """Rewrite names in fighters.csv/fights.csv frames per DISPLAY_NAMES."""
    for fid, name in DISPLAY_NAMES.items():
        fighters.loc[fighters["fighter_id"] == fid, "name"] = name
        for n in ("1", "2"):
            fights.loc[fights[f"fighter_{n}_id"] == fid, f"fighter_{n}_name"] = name


def fighter_mask(df, name):
    """Boolean mask over a frame with name/fighter_id columns: rows for this
    fighter by exact name, else by their known fighter_id after a rename.
    A key that IS a UFCStats fighter URL matches that fighter_id directly --
    for two fighters sharing a name (the two Anthony Romeros, 2026-10-02)."""
    if name.startswith(UFCSTATS):
        return df["fighter_id"] == name
    mask = df["name"] == name
    if not mask.any() and name in OLD_NAME_TO_ID:
        mask = df["fighter_id"] == OLD_NAME_TO_ID[name]
    return mask
