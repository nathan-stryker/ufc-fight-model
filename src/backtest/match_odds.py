"""
Join the external jansen88/ufc-data odds table onto our own fights.csv, by
event date + fighter names. Odds and our scrape are two independent sources,
so names need normalizing (case, punctuation, whitespace) before matching --
this is NOT a leakage concern, just a join-key mismatch problem.

Run: python -m src.backtest.match_odds
Writes: data/processed/fights_with_odds.csv
"""
import re
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
EXTERNAL_DIR = ROOT / "data" / "external"

DATE_TOLERANCE_DAYS = 3  # odds timestamps are sometimes a day or two off the actual event date


def normalize_name(name):
    if pd.isna(name):
        return ""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_odds():
    odds = pd.read_csv(EXTERNAL_DIR / "cleaned_odds.csv", parse_dates=["date"])
    odds = odds.dropna(subset=["outcome"]).copy()
    odds["fav_norm"] = odds["favourite"].map(normalize_name)
    odds["dog_norm"] = odds["underdog"].map(normalize_name)
    return odds


def load_fights():
    fights = pd.read_csv(PROCESSED_DIR / "fights.csv", parse_dates=["event_date"])
    fights = fights[~fights["is_draw"] & ~fights["is_no_contest"]].copy()
    fights["f1_norm"] = fights["fighter_1_name"].map(normalize_name)
    fights["f2_norm"] = fights["fighter_2_name"].map(normalize_name)
    return fights


def match():
    odds = load_odds()
    fights = load_fights()

    # Build a lookup: (pair-of-normalized-names, frozenset) -> list of (fight rows) within date range.
    # Fighter pairs are rare enough that name-pair + date window is a safe key.
    fights_by_pair = {}
    for idx, row in fights.iterrows():
        key = frozenset([row["f1_norm"], row["f2_norm"]])
        fights_by_pair.setdefault(key, []).append(idx)

    matched_rows = []
    unmatched = []
    for _, orow in odds.iterrows():
        key = frozenset([orow["fav_norm"], orow["dog_norm"]])
        candidates = fights_by_pair.get(key, [])
        best = None
        best_delta = None
        for idx in candidates:
            frow = fights.loc[idx]
            delta = abs((frow["event_date"] - orow["date"]).days)
            if delta <= DATE_TOLERANCE_DAYS and (best_delta is None or delta < best_delta):
                best, best_delta = idx, delta
        if best is None:
            unmatched.append(orow)
            continue
        frow = fights.loc[best]
        fav_is_f1 = orow["fav_norm"] == frow["f1_norm"]
        fav_id = frow["fighter_1_id"] if fav_is_f1 else frow["fighter_2_id"]
        dog_id = frow["fighter_2_id"] if fav_is_f1 else frow["fighter_1_id"]
        fav_won = (orow["outcome"] == "favourite")
        matched_rows.append({
            "fight_id": frow["fight_id"],
            "event_date": frow["event_date"],
            "favourite_id": fav_id,
            "underdog_id": dog_id,
            "favourite_name": orow["favourite"],
            "underdog_name": orow["underdog"],
            "favourite_odds": orow["favourite_odds"],
            "underdog_odds": orow["underdog_odds"],
            "favourite_won": fav_won,
            "date_delta_days": best_delta,
        })

    matched_df = pd.DataFrame(matched_rows)
    # A handful of odds rows can legitimately match >1 fights.csv row (rematches on
    # the same card almost never happen, but guard anyway) -- keep the closest-date match,
    # already enforced above by best_delta per odds row; now drop any fight_id used twice.
    dupes = matched_df["fight_id"].duplicated(keep=False)
    if dupes.any():
        print(f"WARNING: {dupes.sum()} matched rows share a fight_id with another odds row (kept as-is):")
        print(matched_df[dupes][["fight_id", "favourite_name", "underdog_name", "event_date"]])

    out_path = PROCESSED_DIR / "fights_with_odds.csv"
    matched_df.to_csv(out_path, index=False)

    print(f"odds rows: {len(odds)}")
    print(f"matched:   {len(matched_df)} ({len(matched_df) / len(odds):.1%})")
    print(f"unmatched: {len(unmatched)}")
    print(f"wrote {out_path}")

    if unmatched:
        sample = pd.DataFrame(unmatched)[["date", "event", "favourite", "underdog"]].head(20)
        unmatched_path = PROCESSED_DIR / "unmatched_odds_sample.csv"
        pd.DataFrame(unmatched)[["date", "event", "favourite", "underdog"]].to_csv(unmatched_path, index=False)
        print(f"\nsample unmatched (see {unmatched_path} for all {len(unmatched)}):")
        print(sample.to_string())

    return matched_df


if __name__ == "__main__":
    match()
