"""
Method-of-victory feature engineering, built on top of the same leakage-safe
long-format history used for the win model (src.features.build_features).

Implements a specific matchup heuristic: compare the FAVORITE's typical
winning method against the UNDERDOG's typical losing method (does the
favorite's style match how the underdog usually loses?), and the reverse
upset path (does the underdog's typical winning method match how the
favorite usually loses?) -- at two tiers, last-5 fights and full UFC career,
so the model can learn to fall back to career stats when recent form is thin.

Run: python -m src.features.method_features
"""
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.build_features import (
    PROCESSED_DIR,
    build_fight_level_stats,
    build_long_history,
)
from src.features.elo import compute_elo

METHOD_BUCKET = {
    "KO/TKO": "ko",
    "TKO - Doctor's Stoppage": "ko",
    "Submission": "sub",
    "Decision - Unanimous": "dec",
    "Decision - Split": "dec",
    "Decision - Majority": "dec",
}
METHODS = ["ko", "sub", "dec"]
ROLLING_WINDOW = 5


def add_method_distributions(long_df: pd.DataFrame) -> pd.DataFrame:
    """
    For each fighter-fight row, adds leakage-safe (pre-fight) fractions of
    their last-5 and career fights that were a win/loss by each method --
    e.g. last5_win_ko = fraction of the fighter's last 5 fights (before this
    one) that were wins by KO/TKO.
    """
    long_df = long_df.copy()
    long_df["method_bucket"] = long_df["method"].map(METHOD_BUCKET)

    for m in METHODS:
        long_df[f"is_win_{m}"] = ((long_df["result"] == "win") & (long_df["method_bucket"] == m)).astype(float)
        long_df[f"is_loss_{m}"] = ((long_df["result"] == "loss") & (long_df["method_bucket"] == m)).astype(float)

    g = long_df.groupby("fighter_id", sort=False)
    for m in METHODS:
        for outcome in ("win", "loss"):
            col = f"is_{outcome}_{m}"
            long_df[f"last5_{outcome}_{m}"] = g[col].transform(
                lambda s: s.rolling(ROLLING_WINDOW, min_periods=1).mean().shift(1)
            )
            long_df[f"career_{outcome}_{m}"] = g[col].transform(lambda s: s.expanding().mean().shift(1))

    return long_df


def add_current_method_snapshot(long_df: pd.DataFrame) -> pd.DataFrame:
    """Same distributions but INCLUDING each fighter's most recent fight, for live predict.py lookups."""
    long_df = long_df.copy()
    long_df["method_bucket"] = long_df["method"].map(METHOD_BUCKET)
    for m in METHODS:
        long_df[f"is_win_{m}"] = ((long_df["result"] == "win") & (long_df["method_bucket"] == m)).astype(float)
        long_df[f"is_loss_{m}"] = ((long_df["result"] == "loss") & (long_df["method_bucket"] == m)).astype(float)

    g = long_df.groupby("fighter_id", sort=False)
    snap = pd.DataFrame(index=long_df.index)
    snap["fighter_id"] = long_df["fighter_id"]
    snap["event_date"] = long_df["event_date"]
    for m in METHODS:
        for outcome in ("win", "loss"):
            col = f"is_{outcome}_{m}"
            snap[f"last5_{outcome}_{m}"] = g[col].transform(
                lambda s: s.rolling(ROLLING_WINDOW, min_periods=1).mean()
            )
            snap[f"career_{outcome}_{m}"] = g[col].transform(lambda s: s.expanding().mean())

    snap = snap.sort_values(["fighter_id", "event_date"], kind="stable").groupby("fighter_id").tail(1)
    return snap.reset_index(drop=True)


def add_favorite_alignment_features(long_df: pd.DataFrame, elo_per_fight: pd.DataFrame, fights: pd.DataFrame) -> pd.DataFrame:
    """
    For each fight, designates a favorite (higher pre-fight Elo) and underdog,
    then adds the matchup-alignment features: favorite's win-method rate x
    underdog's loss-method rate (does the favorite's style match how the
    underdog usually loses), and the reverse upset path. At both tiers.
    """
    elo_with_ids = elo_per_fight.merge(
        fights[["fight_id", "fighter_1_id", "fighter_2_id"]], on="fight_id", how="left"
    )
    fight_favorite = elo_with_ids.copy()
    fight_favorite["favorite_id"] = np.where(
        fight_favorite["fighter_1_elo_pre"] >= fight_favorite["fighter_2_elo_pre"],
        fight_favorite["fighter_1_id"], fight_favorite["fighter_2_id"],
    )
    fight_favorite["underdog_id"] = np.where(
        fight_favorite["fighter_1_elo_pre"] >= fight_favorite["fighter_2_elo_pre"],
        fight_favorite["fighter_2_id"], fight_favorite["fighter_1_id"],
    )
    fight_favorite = fight_favorite[["fight_id", "favorite_id", "underdog_id"]]

    long_df = long_df.merge(fight_favorite, on="fight_id", how="left")
    long_df["is_favorite"] = (long_df["fighter_id"] == long_df["favorite_id"]).astype(float)

    dist_cols = [f"{tier}_{outcome}_{m}" for tier in ("last5", "career") for outcome in ("win", "loss") for m in METHODS]
    own = long_df[["fight_id", "fighter_id"] + dist_cols]
    opp = own.rename(columns={"fighter_id": "opponent_id", **{c: f"opp_{c}" for c in dist_cols}})
    long_df = long_df.merge(opp, on=["fight_id", "opponent_id"], how="left")

    for tier in ("last5", "career"):
        for m in METHODS:
            fav_win = np.where(long_df["is_favorite"] == 1.0, long_df[f"{tier}_win_{m}"], long_df[f"opp_{tier}_win_{m}"])
            dog_loss = np.where(long_df["is_favorite"] == 1.0, long_df[f"opp_{tier}_loss_{m}"], long_df[f"{tier}_loss_{m}"])
            dog_win = np.where(long_df["is_favorite"] == 1.0, long_df[f"opp_{tier}_win_{m}"], long_df[f"{tier}_win_{m}"])
            fav_loss = np.where(long_df["is_favorite"] == 1.0, long_df[f"{tier}_loss_{m}"], long_df[f"opp_{tier}_loss_{m}"])

            long_df[f"align_fav_{m}_{tier}"] = fav_win * dog_loss
            long_df[f"align_upset_{m}_{tier}"] = dog_win * fav_loss

    return long_df


ALIGNMENT_COLS = [f"align_{side}_{m}_{tier}" for side in ("fav", "upset") for m in METHODS for tier in ("last5", "career")]


def compute_method_priors(long_df: pd.DataFrame) -> dict:
    """
    Population-wide win-by-method rates, used as a fallback for fighters with
    no matched fight history (debuts). Loss-by-method rates are numerically
    identical by construction -- every KO fight has exactly one win-by-KO row
    and one loss-by-KO row, so the population rates match exactly.
    """
    return {m: float(long_df[f"is_win_{m}"].mean()) for m in METHODS}


def main():
    fights = pd.read_csv(
        PROCESSED_DIR / "fights.csv",
        parse_dates=["event_date"],
        dtype={"fighter_1_id": "string", "fighter_2_id": "string", "winner_id": "string"},
    )
    round_stats = pd.read_csv(PROCESSED_DIR / "round_stats.csv", dtype={"fighter_id": "string"})
    fight_stats = build_fight_level_stats(round_stats)

    elo_per_fight, _ = compute_elo(fights)

    long_df = build_long_history(fights, fight_stats)
    long_df = add_method_distributions(long_df)
    long_df = add_favorite_alignment_features(long_df, elo_per_fight, fights)

    snapshot = add_current_method_snapshot(build_long_history(fights, fight_stats))

    long_df.to_csv(PROCESSED_DIR / "method_long.csv", index=False)
    snapshot.to_csv(PROCESSED_DIR / "method_snapshot.csv", index=False)

    priors = compute_method_priors(long_df)
    import json
    with open(PROCESSED_DIR / "method_priors.json", "w") as f:
        json.dump(priors, f, indent=2)

    print(f"method_long: {len(long_df)} rows -> {PROCESSED_DIR / 'method_long.csv'}")
    print(f"method_snapshot: {len(snapshot)} rows -> {PROCESSED_DIR / 'method_snapshot.csv'}")
    print(f"method_priors: {priors} -> {PROCESSED_DIR / 'method_priors.json'}")
    print(f"alignment feature missingness (%):")
    print((long_df[ALIGNMENT_COLS].isna().mean() * 100).round(1))


if __name__ == "__main__":
    main()
