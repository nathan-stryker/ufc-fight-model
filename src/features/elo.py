"""
Sequential Elo rating system for UFC fighters.

Ratings are updated fight-by-fight in chronological order. Each fight gets the
*pre-fight* rating of both fighters as a feature (the rating BEFORE that
fight's result is applied), so there is no leakage of the fight's own outcome
into its own features.

Run: python -m src.features.elo (writes data/processed/elo_ratings.csv for inspection)
"""
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

BASE_RATING = 1500.0
K_FACTOR = 32.0
FINISH_BONUS = 1.2  # extra weight for KO/TKO/Submission wins vs decisions
FINISH_METHODS = {"KO/TKO", "Submission", "TKO - Doctor's Stoppage"}


def compute_elo(
    fights: pd.DataFrame,
    k: float = K_FACTOR,
    base_rating: float = BASE_RATING,
    finish_bonus: float = FINISH_BONUS,
):
    """
    fights must have columns: fight_id, event_date, fighter_1_id, fighter_2_id,
    winner_id, is_draw, is_no_contest, method.

    Returns:
      per_fight: DataFrame[fight_id, fighter_1_elo_pre, fighter_2_elo_pre]
      current_ratings: DataFrame[fighter_id, elo_rating, last_fight_date]
    """
    fights_sorted = fights.sort_values("event_date", kind="stable").reset_index(drop=True)

    ratings = defaultdict(lambda: base_rating)
    last_fight_date = {}
    pre_elo_1, pre_elo_2 = [], []

    for row in fights_sorted.itertuples():
        f1, f2 = row.fighter_1_id, row.fighter_2_id
        r1 = ratings[f1] if isinstance(f1, str) else np.nan
        r2 = ratings[f2] if isinstance(f2, str) else np.nan
        pre_elo_1.append(r1)
        pre_elo_2.append(r2)

        if not (isinstance(f1, str) and isinstance(f2, str)):
            continue
        if row.is_no_contest:
            continue

        expected_1 = 1.0 / (1.0 + 10 ** ((r2 - r1) / 400.0))
        expected_2 = 1.0 - expected_1

        if row.is_draw:
            score_1, score_2 = 0.5, 0.5
        elif row.winner_id == f1:
            score_1, score_2 = 1.0, 0.0
        elif row.winner_id == f2:
            score_1, score_2 = 0.0, 1.0
        else:
            continue  # unresolved winner (bad join) -- skip rating update

        k_eff = k * finish_bonus if row.method in FINISH_METHODS else k
        ratings[f1] = r1 + k_eff * (score_1 - expected_1)
        ratings[f2] = r2 + k_eff * (score_2 - expected_2)
        last_fight_date[f1] = row.event_date
        last_fight_date[f2] = row.event_date

    fights_sorted["fighter_1_elo_pre"] = pre_elo_1
    fights_sorted["fighter_2_elo_pre"] = pre_elo_2

    per_fight = fights_sorted[["fight_id", "fighter_1_elo_pre", "fighter_2_elo_pre"]]

    current_ratings = pd.DataFrame(
        {
            "fighter_id": list(ratings.keys()),
            "elo_rating": list(ratings.values()),
        }
    )
    current_ratings["last_fight_date"] = current_ratings["fighter_id"].map(last_fight_date)

    return per_fight, current_ratings


CARRY_OVER = 0.75  # fraction of a fighter's rating that transfers when they change weight class


def compute_division_elo(
    fights: pd.DataFrame,
    k: float = K_FACTOR,
    base_rating: float = BASE_RATING,
    finish_bonus: float = FINISH_BONUS,
    carry_over: float = CARRY_OVER,
):
    """
    Same sequential Elo update as compute_elo, but rated PER WEIGHT CLASS
    (fights must also have a `weightclass` column) instead of one global
    rating per fighter -- a fighter's lightweight skill and heavyweight skill
    aren't the same thing, and conflating them under one rating understates
    how well-matched two same-division fighters actually are.

    When a fighter enters a division for the first time, their rating isn't
    reset to base_rating from scratch -- it's seeded from CARRY_OVER of their
    most recent rating in whatever division they last fought in (shrunk
    toward base_rating by (1 - carry_over), same shrinkage pattern used
    elsewhere in this project), since skill mostly transfers across weight
    changes even though it isn't perfectly 1:1. A fighter's first-ever fight
    still starts at exactly base_rating.

    Returns:
      per_fight: DataFrame[fight_id, fighter_1_division_elo_pre, fighter_2_division_elo_pre]
      current_division_ratings: DataFrame[fighter_id, weightclass, elo_rating, last_fight_date]
    """
    fights_sorted = fights.sort_values("event_date", kind="stable").reset_index(drop=True)

    division_ratings = {}  # (fighter_id, weightclass) -> rating
    division_last_date = {}  # (fighter_id, weightclass) -> date of their last fight in that division
    last_seen = {}  # fighter_id -> (weightclass, rating, date), most recent fight in ANY division
    pre_elo_1, pre_elo_2 = [], []

    def get_or_seed(fighter_id, weightclass):
        key = (fighter_id, weightclass)
        if key in division_ratings:
            return division_ratings[key]
        if fighter_id in last_seen:
            _, prior_rating, _ = last_seen[fighter_id]
            seeded = carry_over * prior_rating + (1 - carry_over) * base_rating
        else:
            seeded = base_rating
        division_ratings[key] = seeded
        return seeded

    for row in fights_sorted.itertuples():
        f1, f2, wc = row.fighter_1_id, row.fighter_2_id, row.weightclass
        r1 = get_or_seed(f1, wc) if isinstance(f1, str) else np.nan
        r2 = get_or_seed(f2, wc) if isinstance(f2, str) else np.nan
        pre_elo_1.append(r1)
        pre_elo_2.append(r2)

        if not (isinstance(f1, str) and isinstance(f2, str)):
            continue
        if row.is_no_contest:
            continue

        expected_1 = 1.0 / (1.0 + 10 ** ((r2 - r1) / 400.0))
        expected_2 = 1.0 - expected_1

        if row.is_draw:
            score_1, score_2 = 0.5, 0.5
        elif row.winner_id == f1:
            score_1, score_2 = 1.0, 0.0
        elif row.winner_id == f2:
            score_1, score_2 = 0.0, 1.0
        else:
            continue

        k_eff = k * finish_bonus if row.method in FINISH_METHODS else k
        new_r1 = r1 + k_eff * (score_1 - expected_1)
        new_r2 = r2 + k_eff * (score_2 - expected_2)
        division_ratings[(f1, wc)] = new_r1
        division_ratings[(f2, wc)] = new_r2
        division_last_date[(f1, wc)] = row.event_date
        division_last_date[(f2, wc)] = row.event_date
        last_seen[f1] = (wc, new_r1, row.event_date)
        last_seen[f2] = (wc, new_r2, row.event_date)

    fights_sorted["fighter_1_division_elo_pre"] = pre_elo_1
    fights_sorted["fighter_2_division_elo_pre"] = pre_elo_2
    per_fight = fights_sorted[["fight_id", "fighter_1_division_elo_pre", "fighter_2_division_elo_pre"]]

    current_division_ratings = pd.DataFrame(
        [
            {
                "fighter_id": fid, "weightclass": wc, "elo_rating": rating,
                "last_fight_date": division_last_date.get((fid, wc)),
            }
            for (fid, wc), rating in division_ratings.items()
            if (fid, wc) in division_last_date  # drop divisions only ever "seeded" via carry-over, never actually fought
        ]
    )

    return per_fight, current_division_ratings


def main():
    fights = pd.read_csv(PROCESSED_DIR / "fights.csv", parse_dates=["event_date"])
    _, current_ratings = compute_elo(fights)
    current_ratings = current_ratings.sort_values("elo_rating", ascending=False)
    current_ratings.to_csv(PROCESSED_DIR / "elo_ratings.csv", index=False)
    print(current_ratings.head(20).to_string(index=False))

    _, current_division_ratings = compute_division_elo(fights)
    current_division_ratings = current_division_ratings.sort_values("elo_rating", ascending=False)
    current_division_ratings.to_csv(PROCESSED_DIR / "division_elo_ratings.csv", index=False)
    print("\nTop division ratings:")
    print(current_division_ratings.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
