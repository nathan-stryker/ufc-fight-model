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
}


def fighter_mask(df, name):
    """Boolean mask over a frame with name/fighter_id columns: rows for this
    fighter by exact name, else by their known fighter_id after a rename."""
    mask = df["name"] == name
    if not mask.any() and name in OLD_NAME_TO_ID:
        mask = df["fighter_id"] == OLD_NAME_TO_ID[name]
    return mask
