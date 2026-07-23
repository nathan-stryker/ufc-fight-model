"""
Parse the raw UFCStats.com CSV mirror (github.com/Greco1899/scrape_ufc_stats)
into three tidy tables written to data/processed/:

  fighters.csv     one row per fighter: physical attributes
  fights.csv       one row per fight: date, weight class, winner, method
  round_stats.csv  one row per fighter per round: strikes/grappling stats

Run: python -m src.data.load_data
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

HEIGHT_RE = re.compile(r"(\d+)'\s*(\d+)\"")
X_OF_Y_RE = re.compile(r"(\d+)\s+of\s+(\d+)")

# Ordered longest-first so "Light Heavyweight" is checked before "Heavyweight"
# (which is a substring match target, not "Light Heavyweight"). Raw WEIGHTCLASS
# values include noise like "UFC Welterweight" (title bouts), "UFC Interim
# Heavyweight", and early-era "Ultimate Fighter 33 Welterweight Tournament" /
# "UFC 6 Tournament" -- stripping only "Bout"/"Title Bout" suffixes (as before)
# leaves these as separate categories from their real division, which breaks
# any per-division analysis (e.g. weight-class-aware Elo).
DIVISION_KEYWORDS = [
    "Light Heavyweight", "Heavyweight", "Middleweight", "Welterweight",
    "Lightweight", "Featherweight", "Bantamweight", "Flyweight", "Strawweight",
]


def _normalize_weightclass(raw: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return "Unknown"
    lower = raw.lower()
    is_womens = "women" in lower
    for kw in DIVISION_KEYWORDS:
        if kw.lower() in lower:
            return f"Women's {kw}" if is_womens else kw
    if "catch" in lower:
        return "Catch Weight"
    return "Open Weight"


def _strip_cols(df: pd.DataFrame, cols) -> pd.DataFrame:
    for c in cols:
        df[c] = df[c].astype(str).str.strip()
    return df


def _parse_height(val: str) -> float:
    if not isinstance(val, str) or val.strip() == "--":
        return np.nan
    m = HEIGHT_RE.search(val)
    if not m:
        return np.nan
    feet, inches = int(m.group(1)), int(m.group(2))
    return feet * 12 + inches


def _parse_reach(val: str) -> float:
    if not isinstance(val, str) or val.strip() == "--":
        return np.nan
    return float(val.replace('"', "").strip())


def _parse_weight(val: str) -> float:
    if not isinstance(val, str) or val.strip() == "--":
        return np.nan
    m = re.search(r"(\d+)", val)
    return float(m.group(1)) if m else np.nan


def _parse_pct(val: str) -> float:
    if not isinstance(val, str) or val.strip() in ("--", "---", ""):
        return np.nan
    return float(val.replace("%", "").strip()) / 100.0


def _parse_x_of_y(val: str):
    if not isinstance(val, str):
        return np.nan, np.nan
    m = X_OF_Y_RE.search(val)
    if not m:
        return np.nan, np.nan
    return float(m.group(1)), float(m.group(2))


def _parse_ctrl_seconds(val: str) -> float:
    if not isinstance(val, str) or val.strip() in ("--", "---", ""):
        return np.nan
    parts = val.strip().split(":")
    if len(parts) != 2:
        return np.nan
    mins, secs = parts
    try:
        return int(mins) * 60 + int(secs)
    except ValueError:
        return np.nan


def load_fighters() -> pd.DataFrame:
    details = pd.read_csv(RAW_DIR / "ufc_fighter_details.csv")
    tott = pd.read_csv(RAW_DIR / "ufc_fighter_tott.csv")

    details = _strip_cols(details, ["FIRST", "LAST", "NICKNAME", "URL"])
    tott = _strip_cols(tott, ["FIGHTER", "URL"])

    details["name"] = (details["FIRST"].fillna("") + " " + details["LAST"].fillna("")).str.strip()

    fighters = tott.merge(
        details[["URL", "name", "NICKNAME"]], on="URL", how="left"
    )
    fighters["name"] = fighters["name"].fillna(fighters["FIGHTER"])

    fighters = fighters.rename(columns={"URL": "fighter_id", "NICKNAME": "nickname", "STANCE": "stance"})
    fighters["height_in"] = fighters["HEIGHT"].apply(_parse_height)
    fighters["reach_in"] = fighters["REACH"].apply(_parse_reach)
    fighters["weight_lbs"] = fighters["WEIGHT"].apply(_parse_weight)
    fighters["dob"] = pd.to_datetime(fighters["DOB"], format="%b %d, %Y", errors="coerce")
    fighters["stance"] = fighters["stance"].replace("", np.nan)

    fighters = fighters[
        ["fighter_id", "name", "nickname", "dob", "height_in", "reach_in", "weight_lbs", "stance"]
    ].drop_duplicates(subset="fighter_id")

    return fighters


def load_fights(fighters: pd.DataFrame) -> pd.DataFrame:
    results = pd.read_csv(RAW_DIR / "ufc_fight_results.csv")
    events = pd.read_csv(RAW_DIR / "ufc_event_details.csv")

    results = _strip_cols(results, ["EVENT", "BOUT", "OUTCOME", "WEIGHTCLASS", "METHOD", "URL"])
    events = _strip_cols(events, ["EVENT", "LOCATION"])

    events["event_date"] = pd.to_datetime(events["DATE"], format="%B %d, %Y", errors="coerce")
    events = events.rename(columns={"LOCATION": "location"})[["EVENT", "event_date", "location"]]

    fights = results.merge(events, on="EVENT", how="left")

    bout_split = fights["BOUT"].str.split(r"\s+vs\.?\s+", n=1, regex=True, expand=True)
    fights["fighter_1_name"] = bout_split[0].str.strip()
    fights["fighter_2_name"] = bout_split[1].str.strip()

    name_to_id = fighters.dropna(subset=["name"]).drop_duplicates(subset="name", keep=False).set_index("name")["fighter_id"]
    fights["fighter_1_id"] = fights["fighter_1_name"].map(name_to_id)
    fights["fighter_2_id"] = fights["fighter_2_name"].map(name_to_id)

    outcome_split = fights["OUTCOME"].str.split("/", expand=True)
    fights["result_1"] = outcome_split[0]
    fights["result_2"] = outcome_split[1]

    def resolve_winner(row):
        if row["result_1"] == "W":
            return row["fighter_1_id"]
        if row["result_2"] == "W":
            return row["fighter_2_id"]
        return np.nan

    fights["winner_id"] = fights.apply(resolve_winner, axis=1)
    fights["is_draw"] = fights["OUTCOME"] == "D/D"
    fights["is_no_contest"] = fights["OUTCOME"] == "NC/NC"

    fights["weightclass"] = fights["WEIGHTCLASS"].apply(_normalize_weightclass)

    fights = fights.rename(
        columns={
            "URL": "fight_id",
            "EVENT": "event",
            "BOUT": "bout",
            "METHOD": "method",
            "ROUND": "round",
            "TIME": "time",
            "TIME FORMAT": "time_format",
            "REFEREE": "referee",
        }
    )

    fights = fights[
        [
            "fight_id", "event", "event_date", "location", "bout", "weightclass",
            "fighter_1_name", "fighter_1_id", "fighter_2_name", "fighter_2_id",
            "winner_id", "is_draw", "is_no_contest", "method", "round", "time",
            "time_format", "referee",
        ]
    ]

    return fights


def load_round_stats(fighters: pd.DataFrame) -> pd.DataFrame:
    stats = pd.read_csv(RAW_DIR / "ufc_fight_stats.csv")
    fight_details = pd.read_csv(RAW_DIR / "ufc_fight_details.csv")

    stats = _strip_cols(stats, ["EVENT", "BOUT", "ROUND", "FIGHTER"])
    fight_details = _strip_cols(fight_details, ["EVENT", "BOUT", "URL"])

    stats = stats.merge(fight_details, on=["EVENT", "BOUT"], how="left")

    name_to_id = fighters.dropna(subset=["name"]).drop_duplicates(subset="name", keep=False).set_index("name")["fighter_id"]
    stats["fighter_id"] = stats["FIGHTER"].map(name_to_id)

    xoy_cols = {
        "SIG.STR.": "sig_str",
        "TOTAL STR.": "total_str",
        "TD": "td",
        "HEAD": "head",
        "BODY": "body",
        "LEG": "leg",
        "DISTANCE": "distance",
        "CLINCH": "clinch",
        "GROUND": "ground",
    }
    for raw_col, out_prefix in xoy_cols.items():
        parsed = stats[raw_col].apply(_parse_x_of_y)
        stats[f"{out_prefix}_landed"] = [p[0] for p in parsed]
        stats[f"{out_prefix}_attempted"] = [p[1] for p in parsed]

    stats["sig_str_pct"] = stats["SIG.STR. %"].apply(_parse_pct)
    stats["td_pct"] = stats["TD %"].apply(_parse_pct)
    stats["ctrl_sec"] = stats["CTRL"].apply(_parse_ctrl_seconds)
    stats["round_num"] = stats["ROUND"].str.extract(r"(\d+)").astype(float)

    stats = stats.rename(
        columns={
            "URL": "fight_id",
            "EVENT": "event",
            "BOUT": "bout",
            "FIGHTER": "fighter_name",
            "KD": "kd",
            "SUB.ATT": "sub_att",
            "REV.": "rev",
        }
    )

    out_cols = [
        "fight_id", "event", "bout", "round_num", "fighter_name", "fighter_id",
        "kd", "sig_str_landed", "sig_str_attempted", "sig_str_pct",
        "total_str_landed", "total_str_attempted",
        "td_landed", "td_attempted", "td_pct",
        "sub_att", "rev", "ctrl_sec",
        "head_landed", "head_attempted", "body_landed", "body_attempted",
        "leg_landed", "leg_attempted", "distance_landed", "distance_attempted",
        "clinch_landed", "clinch_attempted", "ground_landed", "ground_attempted",
    ]
    return stats[out_cols]


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    fighters = load_fighters()
    fights = load_fights(fighters)
    round_stats = load_round_stats(fighters)

    fighters.to_csv(PROCESSED_DIR / "fighters.csv", index=False)
    fights.to_csv(PROCESSED_DIR / "fights.csv", index=False)
    round_stats.to_csv(PROCESSED_DIR / "round_stats.csv", index=False)

    print(f"fighters: {len(fighters)} rows -> {PROCESSED_DIR / 'fighters.csv'}")
    print(f"fights: {len(fights)} rows -> {PROCESSED_DIR / 'fights.csv'}")
    print(f"round_stats: {len(round_stats)} rows -> {PROCESSED_DIR / 'round_stats.csv'}")

    unmatched_1 = fights["fighter_1_id"].isna().sum()
    unmatched_2 = fights["fighter_2_id"].isna().sum()
    unmatched_winner = fights.loc[~fights["is_draw"] & ~fights["is_no_contest"], "winner_id"].isna().sum()
    print(f"unmatched fighter_1: {unmatched_1}, fighter_2: {unmatched_2}, unresolved winner (excl draw/NC): {unmatched_winner}")


if __name__ == "__main__":
    main()
