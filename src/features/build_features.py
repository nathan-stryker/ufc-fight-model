"""
Build a leakage-safe, corner-order-augmented feature table for model training.

Every feature is computed strictly from information available BEFORE a given
fight (career record, rolling form, Elo entering the fight). Features are
fighter_A - fighter_B differentials, and each historical fight contributes two
rows (A vs B and B vs A) so the model cannot learn a spurious corner bias.

Run: python -m src.features.build_features
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.elo import BASE_RATING, compute_division_elo, compute_elo

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

ROLLING_WINDOW = 5
FINISH_METHODS = {"KO/TKO", "Submission", "TKO - Doctor's Stoppage"}

STANCE_CATEGORIES = ["Orthodox", "Southpaw", "Switch"]

# Bayesian-shrinkage pseudo-counts: how many "prior" observations each rate
# stat is blended with before trusting the fighter's own small sample. A
# fighter with only 1 fight's worth of data gets pulled hard toward the
# sport-wide average; a 24-fight veteran barely moves. Without this, a single
# lucky/short fight can produce a stat line (e.g. 0 strikes absorbed/min, a
# 100% takedown rate) that the model treats as equally reliable as a
# multi-year track record.
K_FIGHTS = 3.0          # win_pct, finish_rate
K_STRIKE_ATTEMPTS = 40.0  # sig_str_acc (roughly half a fight's worth of attempts)
K_TD_ATTEMPTS = 2.0       # td_acc, td_def (takedown attempts are rare events)
K_MINUTES = 15.0          # per-minute/per-15 rate stats, ctrl_pct (~one 3-round fight)


def _shrink_ratio(numerator, denominator, prior, k):
    return (numerator + prior * k) / (denominator + k)


def _parse_mmss(val: str) -> float:
    if not isinstance(val, str) or ":" not in val:
        return np.nan
    m, s = val.strip().split(":")
    return int(m) * 60 + int(s)


def _round_lengths(time_format: str):
    if not isinstance(time_format, str):
        return []
    m = re.search(r"\((.*?)\)", time_format)
    if not m:
        return []
    return [int(x) for x in m.group(1).split("-") if x.strip().isdigit()]


def compute_fight_seconds(row) -> float:
    lengths = _round_lengths(row["time_format"])
    round_num = int(row["round"]) if pd.notna(row["round"]) else 1
    completed_minutes = sum(lengths[: round_num - 1]) if lengths else 0
    final_round_seconds = _parse_mmss(row["time"])
    if pd.isna(final_round_seconds):
        final_round_seconds = 0
    return completed_minutes * 60 + final_round_seconds


def build_fight_level_stats(round_stats: pd.DataFrame) -> pd.DataFrame:
    agg_cols = [c for c in round_stats.columns if c.endswith(("_landed", "_attempted"))] + [
        "kd", "sub_att", "rev", "ctrl_sec"
    ]
    agg = round_stats.groupby(["fight_id", "fighter_id"], as_index=False)[agg_cols].sum(min_count=1)
    return agg


def build_long_history(fights: pd.DataFrame, fight_stats: pd.DataFrame) -> pd.DataFrame:
    """One row per fighter per fight (both perspectives), with own + opponent stats."""
    fights = fights.copy()
    fights["fight_seconds"] = fights.apply(compute_fight_seconds, axis=1)

    base_cols = ["fight_id", "event_date", "weightclass", "method", "is_draw", "is_no_contest", "fight_seconds"]

    p1 = fights[base_cols + ["fighter_1_id", "fighter_2_id", "winner_id"]].rename(
        columns={"fighter_1_id": "fighter_id", "fighter_2_id": "opponent_id"}
    )
    p2 = fights[base_cols + ["fighter_2_id", "fighter_1_id", "winner_id"]].rename(
        columns={"fighter_2_id": "fighter_id", "fighter_1_id": "opponent_id"}
    )
    long_df = pd.concat([p1, p2], ignore_index=True)
    long_df = long_df.dropna(subset=["fighter_id", "opponent_id"])

    is_winner = (long_df["winner_id"] == long_df["fighter_id"]).fillna(False).to_numpy(dtype=bool)
    long_df["result"] = np.select(
        [long_df["is_no_contest"].to_numpy(dtype=bool), long_df["is_draw"].to_numpy(dtype=bool), is_winner],
        ["nc", "draw", "win"],
        default="loss",
    )
    long_df["is_finish_win"] = (long_df["result"] == "win") & long_df["method"].isin(FINISH_METHODS)

    own_stats = fight_stats.rename(columns={c: f"own_{c}" for c in fight_stats.columns if c not in ("fight_id", "fighter_id")})
    opp_stats = fight_stats.rename(
        columns={"fighter_id": "opponent_id", **{c: f"opp_{c}" for c in fight_stats.columns if c not in ("fight_id", "fighter_id")}}
    )

    long_df = long_df.merge(own_stats, on=["fight_id", "fighter_id"], how="left")
    long_df = long_df.merge(opp_stats, on=["fight_id", "opponent_id"], how="left")

    long_df = long_df.sort_values(["fighter_id", "event_date"], kind="stable").reset_index(drop=True)
    return long_df


def compute_population_priors(long_df: pd.DataFrame) -> dict:
    """
    Sport-wide average rates, used to shrink small-sample fighter stats toward
    a sensible baseline instead of trusting e.g. a 1-fight 100% takedown rate.
    Computed once from the full dataset (not outcome-dependent, so this is not
    a leakage concern -- it's a fixed physical-average constant, identical for
    every fighter and both corner-augmented rows of every fight).
    """
    total_seconds = long_df["fight_seconds"].sum()
    total_minutes = total_seconds / 60.0
    decided = long_df["result"].isin(["win", "loss"])

    return {
        "win_pct": 0.5,  # exactly half of all decided fights are wins, by construction
        "finish_rate": long_df.loc[long_df["result"] == "win", "is_finish_win"].mean(),
        "sig_str_acc": long_df["own_sig_str_landed"].sum() / long_df["own_sig_str_attempted"].sum(),
        "td_acc": long_df["own_td_landed"].sum() / long_df["own_td_attempted"].sum(),
        "td_def": 1.0 - long_df["opp_td_landed"].sum() / long_df["opp_td_attempted"].sum(),
        "sig_str_landed_per_min": long_df["own_sig_str_landed"].sum() / total_minutes,
        "sig_str_absorbed_per_min": long_df["opp_sig_str_landed"].sum() / total_minutes,
        "td_avg_per15": long_df["own_td_landed"].sum() / total_minutes * 15.0,
        "sub_att_per15": long_df["own_sub_att"].sum() / total_minutes * 15.0,
        "ctrl_pct": long_df["own_ctrl_sec"].sum() / total_seconds,
    }


def add_pre_fight_career_features(long_df: pd.DataFrame, priors: dict) -> pd.DataFrame:
    g = long_df.groupby("fighter_id", sort=False)

    long_df["fights_entering"] = g.cumcount()
    is_decided = long_df["result"].isin(["win", "loss"])
    win_flag = (long_df["result"] == "win").astype(float)

    long_df["wins_entering"] = g["result"].transform(lambda s: (s == "win").cumsum().shift(1).fillna(0))
    long_df["losses_entering"] = g["result"].transform(lambda s: (s == "loss").cumsum().shift(1).fillna(0))
    decided_entering = long_df["wins_entering"] + long_df["losses_entering"]
    long_df["win_pct_entering"] = _shrink_ratio(
        long_df["wins_entering"], decided_entering, priors["win_pct"], K_FIGHTS
    )

    finishes_cum = g["is_finish_win"].transform(lambda s: s.cumsum().shift(1).fillna(0))
    long_df["finish_rate_entering"] = _shrink_ratio(
        finishes_cum, long_df["wins_entering"], priors["finish_rate"], K_FIGHTS
    )

    def _streak(results):
        streaks = []
        cur_sign, cur_len = 0, 0
        for r in results:
            streaks.append(cur_sign * cur_len)
            if r == "win":
                cur_len = cur_len + 1 if cur_sign >= 0 else 1
                cur_sign = 1
            elif r == "loss":
                cur_len = cur_len + 1 if cur_sign <= 0 else 1
                cur_sign = -1
            else:
                continue
        return pd.Series(streaks, index=results.index)

    long_df["current_streak_entering"] = g["result"].transform(_streak)

    long_df["prev_fight_date"] = g["event_date"].shift(1)
    long_df["layoff_days_entering"] = (long_df["event_date"] - long_df["prev_fight_date"]).dt.days

    rate_cols = {
        "own_sig_str_landed": "sig_str_landed",
        "own_sig_str_attempted": "sig_str_attempted",
        "opp_sig_str_landed": "sig_str_absorbed",
        "own_td_landed": "td_landed",
        "own_td_attempted": "td_attempted",
        "opp_td_landed": "opp_td_landed",
        "opp_td_attempted": "opp_td_attempted",
        "own_sub_att": "sub_att",
        "own_ctrl_sec": "ctrl_sec",
    }
    for src, alias in rate_cols.items():
        long_df[f"roll_{alias}"] = g[src].transform(
            lambda s: s.rolling(ROLLING_WINDOW, min_periods=1).sum().shift(1)
        )
    long_df["roll_fight_seconds"] = g["fight_seconds"].transform(
        lambda s: s.rolling(ROLLING_WINDOW, min_periods=1).sum().shift(1)
    )

    minutes = long_df["roll_fight_seconds"] / 60.0
    long_df["sig_str_landed_per_min"] = _shrink_ratio(
        long_df["roll_sig_str_landed"], minutes, priors["sig_str_landed_per_min"], K_MINUTES
    )
    long_df["sig_str_absorbed_per_min"] = _shrink_ratio(
        long_df["roll_sig_str_absorbed"], minutes, priors["sig_str_absorbed_per_min"], K_MINUTES
    )
    long_df["sig_str_acc"] = _shrink_ratio(
        long_df["roll_sig_str_landed"], long_df["roll_sig_str_attempted"], priors["sig_str_acc"], K_STRIKE_ATTEMPTS
    )
    long_df["td_avg_per15"] = _shrink_ratio(
        long_df["roll_td_landed"], minutes, priors["td_avg_per15"] / 15.0, K_MINUTES
    ) * 15.0
    long_df["td_acc"] = _shrink_ratio(
        long_df["roll_td_landed"], long_df["roll_td_attempted"], priors["td_acc"], K_TD_ATTEMPTS
    )
    long_df["td_def"] = 1.0 - _shrink_ratio(
        long_df["roll_opp_td_landed"], long_df["roll_opp_td_attempted"], 1.0 - priors["td_def"], K_TD_ATTEMPTS
    )
    long_df["sub_att_per15"] = _shrink_ratio(
        long_df["roll_sub_att"], minutes, priors["sub_att_per15"] / 15.0, K_MINUTES
    ) * 15.0
    long_df["ctrl_pct"] = _shrink_ratio(
        long_df["roll_ctrl_sec"], long_df["roll_fight_seconds"], priors["ctrl_pct"], K_MINUTES * 60.0
    )

    return long_df


def attach_static_attributes(long_df: pd.DataFrame, fighters: pd.DataFrame) -> pd.DataFrame:
    fighters = fighters.set_index("fighter_id")
    long_df = long_df.join(fighters[["dob", "height_in", "reach_in", "stance"]], on="fighter_id")
    long_df["age_years"] = (long_df["event_date"] - long_df["dob"]).dt.days / 365.25
    for cat in STANCE_CATEGORIES:
        long_df[f"stance_{cat.lower()}"] = (long_df["stance"] == cat).astype(float)
    return long_df


FEATURE_COLS = [
    "elo", "height_in", "reach_in", "age_years",
    "fights_entering", "win_pct_entering", "finish_rate_entering", "current_streak_entering",
    "layoff_days_entering",
    "sig_str_landed_per_min", "sig_str_absorbed_per_min", "sig_str_acc",
    "td_avg_per15", "td_acc", "td_def", "sub_att_per15", "ctrl_pct",
    "stance_orthodox", "stance_southpaw", "stance_switch",
]


def _elo_per_fight_to_long(elo_per_fight: pd.DataFrame, fights: pd.DataFrame, pre_col_1: str, pre_col_2: str, out_col: str) -> pd.DataFrame:
    elo_with_ids = elo_per_fight.merge(
        fights[["fight_id", "fighter_1_id", "fighter_2_id"]], on="fight_id", how="left"
    )
    return pd.concat(
        [
            elo_with_ids.rename(columns={pre_col_1: out_col, "fighter_1_id": "fighter_id"})[["fight_id", "fighter_id", out_col]],
            elo_with_ids.rename(columns={pre_col_2: out_col, "fighter_2_id": "fighter_id"})[["fight_id", "fighter_id", out_col]],
        ],
        ignore_index=True,
    )


INTERACTION_COLS = ["wrestling_edge_diff", "striking_edge_diff"]


def _compute_interactions(a, b) -> dict:
    """
    Style-matchup cross-features: does fighter A's specific offensive strength
    line up against fighter B's specific defensive weakness (and vice versa)?
    Same "does X's strength align with Y's weakness" pattern as the method
    model's favorite/underdog alignment features (src/features/method_features.py),
    which measurably improved that model -- a simple diff of td_avg_per15 and a
    separate diff of td_def each tell the tree half the story, but their
    CROSS-product (A's takedown rate against B's specific takedown defense)
    is the actual matchup-specific signal, and isn't something a max_depth=4
    tree reliably rediscovers on its own from the two diffs alone.
    """
    wrestling_edge = a["td_avg_per15"] * (1 - b["td_def"]) - b["td_avg_per15"] * (1 - a["td_def"])
    striking_edge = (
        a["sig_str_landed_per_min"] * b["sig_str_absorbed_per_min"]
        - b["sig_str_landed_per_min"] * a["sig_str_absorbed_per_min"]
    )
    return {"wrestling_edge_diff": wrestling_edge, "striking_edge_diff": striking_edge}


def build_model_table(
    long_df: pd.DataFrame, elo_per_fight: pd.DataFrame, division_elo_per_fight: pd.DataFrame, fights: pd.DataFrame
) -> pd.DataFrame:
    elo_long = _elo_per_fight_to_long(elo_per_fight, fights, "fighter_1_elo_pre", "fighter_2_elo_pre", "elo")
    long_df = long_df.merge(elo_long, on=["fight_id", "fighter_id"], how="left")

    division_elo_long = _elo_per_fight_to_long(
        division_elo_per_fight, fights, "fighter_1_division_elo_pre", "fighter_2_division_elo_pre", "division_elo"
    )
    long_df = long_df.merge(division_elo_long, on=["fight_id", "fighter_id"], how="left")

    # "elo" (global) is always kept regardless of FEATURE_COLS -- the Elo-only
    # logistic regression baseline and the extrapolation-fix blend (see
    # evaluate.py) both key off elo_diff specifically, independent of whatever
    # feature set the main model uses.
    extra_cols = [c for c in ["elo", "division_elo"] if c not in FEATURE_COLS]
    keep = ["fight_id", "event_date", "weightclass", "fighter_id", "opponent_id", "result"] + FEATURE_COLS + extra_cols
    long_df = long_df[keep]

    rows = []
    fight_groups = long_df.groupby("fight_id")
    for fight_id, grp in fight_groups:
        if len(grp) != 2 or grp["result"].isin(["draw", "nc"]).any():
            continue
        a, b = grp.iloc[0], grp.iloc[1]
        row = {"fight_id": fight_id, "event_date": a["event_date"], "weightclass": a["weightclass"]}
        for col in FEATURE_COLS + extra_cols:
            row[f"{col}_diff"] = a[col] - b[col]
        row.update(_compute_interactions(a, b))
        row["label"] = 1 if a["result"] == "win" else 0
        rows.append(row)
        row2 = {"fight_id": fight_id, "event_date": b["event_date"], "weightclass": b["weightclass"]}
        for col in FEATURE_COLS + extra_cols:
            row2[f"{col}_diff"] = b[col] - a[col]
        row2.update(_compute_interactions(b, a))
        row2["label"] = 1 if b["result"] == "win" else 0
        rows.append(row2)

    return pd.DataFrame(rows)


def build_current_snapshot(long_df: pd.DataFrame, current_ratings: pd.DataFrame, priors: dict) -> pd.DataFrame:
    """
    One row per fighter with their most up-to-date profile, for live predict.py
    lookups -- unlike the "_entering" features used for training (which exclude
    the fight they're attached to, to avoid leakage), these rolling/cumulative
    stats INCLUDE each fighter's most recent fight, since predicting a future
    matchup should use everything known about them as of today.
    """
    g = long_df.groupby("fighter_id", sort=False)

    snap = pd.DataFrame(index=long_df.index)
    snap["fighter_id"] = long_df["fighter_id"]
    snap["event_date"] = long_df["event_date"]

    is_win = (long_df["result"] == "win").astype(float)
    is_loss = (long_df["result"] == "loss").astype(float)
    snap["fights_count"] = g.cumcount() + 1
    snap["wins"] = g["result"].transform(lambda s: (s == "win").cumsum())
    snap["losses"] = g["result"].transform(lambda s: (s == "loss").cumsum())
    decided = snap["wins"] + snap["losses"]
    snap["win_pct"] = _shrink_ratio(snap["wins"], decided, priors["win_pct"], K_FIGHTS)
    finishes_cum = g["is_finish_win"].transform(lambda s: s.cumsum())
    snap["finish_rate"] = _shrink_ratio(finishes_cum, snap["wins"], priors["finish_rate"], K_FIGHTS)
    snap["current_streak"] = g["result"].transform(_streak_inclusive)
    snap["last_fight_date"] = long_df["event_date"]

    rate_cols = {
        "own_sig_str_landed": "sig_str_landed",
        "own_sig_str_attempted": "sig_str_attempted",
        "opp_sig_str_landed": "sig_str_absorbed",
        "own_td_landed": "td_landed",
        "own_td_attempted": "td_attempted",
        "opp_td_landed": "opp_td_landed",
        "opp_td_attempted": "opp_td_attempted",
        "own_sub_att": "sub_att",
        "own_ctrl_sec": "ctrl_sec",
    }
    for src, alias in rate_cols.items():
        snap[f"roll_{alias}"] = g[src].transform(lambda s: s.rolling(ROLLING_WINDOW, min_periods=1).sum())
    snap["roll_fight_seconds"] = g["fight_seconds"].transform(
        lambda s: s.rolling(ROLLING_WINDOW, min_periods=1).sum()
    )

    minutes = snap["roll_fight_seconds"] / 60.0
    snap["sig_str_landed_per_min"] = _shrink_ratio(
        snap["roll_sig_str_landed"], minutes, priors["sig_str_landed_per_min"], K_MINUTES
    )
    snap["sig_str_absorbed_per_min"] = _shrink_ratio(
        snap["roll_sig_str_absorbed"], minutes, priors["sig_str_absorbed_per_min"], K_MINUTES
    )
    snap["sig_str_acc"] = _shrink_ratio(
        snap["roll_sig_str_landed"], snap["roll_sig_str_attempted"], priors["sig_str_acc"], K_STRIKE_ATTEMPTS
    )
    snap["td_avg_per15"] = _shrink_ratio(
        snap["roll_td_landed"], minutes, priors["td_avg_per15"] / 15.0, K_MINUTES
    ) * 15.0
    snap["td_acc"] = _shrink_ratio(
        snap["roll_td_landed"], snap["roll_td_attempted"], priors["td_acc"], K_TD_ATTEMPTS
    )
    snap["td_def"] = 1.0 - _shrink_ratio(
        snap["roll_opp_td_landed"], snap["roll_opp_td_attempted"], 1.0 - priors["td_def"], K_TD_ATTEMPTS
    )
    snap["sub_att_per15"] = _shrink_ratio(
        snap["roll_sub_att"], minutes, priors["sub_att_per15"] / 15.0, K_MINUTES
    ) * 15.0
    snap["ctrl_pct"] = _shrink_ratio(
        snap["roll_ctrl_sec"], snap["roll_fight_seconds"], priors["ctrl_pct"], K_MINUTES * 60.0
    )

    snap = snap.sort_values(["fighter_id", "event_date"], kind="stable").groupby("fighter_id").tail(1)
    snap = snap.rename(columns={"fights_count": "fights_entering", "win_pct": "win_pct_entering",
                                 "finish_rate": "finish_rate_entering", "current_streak": "current_streak_entering"})
    snap = snap.merge(current_ratings[["fighter_id", "elo_rating"]], on="fighter_id", how="left")
    snap = snap.rename(columns={"elo_rating": "elo"})

    keep = ["fighter_id", "last_fight_date", "elo", "fights_entering", "win_pct_entering",
            "finish_rate_entering", "current_streak_entering",
            "sig_str_landed_per_min", "sig_str_absorbed_per_min", "sig_str_acc",
            "td_avg_per15", "td_acc", "td_def", "sub_att_per15", "ctrl_pct"]
    return snap[keep].reset_index(drop=True)


def _streak_inclusive(results):
    streaks = []
    cur_sign, cur_len = 0, 0
    for r in results:
        if r == "win":
            cur_len = cur_len + 1 if cur_sign >= 0 else 1
            cur_sign = 1
        elif r == "loss":
            cur_len = cur_len + 1 if cur_sign <= 0 else 1
            cur_sign = -1
        streaks.append(cur_sign * cur_len)
    return pd.Series(streaks, index=results.index)


def main():
    fighters = pd.read_csv(PROCESSED_DIR / "fighters.csv", parse_dates=["dob"])
    fights = pd.read_csv(
        PROCESSED_DIR / "fights.csv",
        parse_dates=["event_date"],
        dtype={"fighter_1_id": "string", "fighter_2_id": "string", "winner_id": "string"},
    )
    round_stats = pd.read_csv(PROCESSED_DIR / "round_stats.csv", dtype={"fighter_id": "string"})

    fight_stats = build_fight_level_stats(round_stats)

    elo_per_fight, current_ratings = compute_elo(fights)
    current_ratings.to_csv(PROCESSED_DIR / "elo_ratings.csv", index=False)

    division_elo_per_fight, current_division_ratings = compute_division_elo(fights)
    current_division_ratings.to_csv(PROCESSED_DIR / "division_elo_ratings.csv", index=False)

    long_df = build_long_history(fights, fight_stats)
    priors = compute_population_priors(long_df)
    print("population priors (shrinkage targets):", {k: round(v, 4) for k, v in priors.items()})

    long_df = add_pre_fight_career_features(long_df, priors)
    long_df = attach_static_attributes(long_df, fighters)

    model_df = build_model_table(long_df, elo_per_fight, division_elo_per_fight, fights)
    model_df.to_csv(PROCESSED_DIR / "model_features.csv", index=False)

    print(f"model_features: {len(model_df)} rows -> {PROCESSED_DIR / 'model_features.csv'}")
    print(f"label balance: {model_df['label'].mean():.3f} (should be ~0.5 after corner augmentation)")
    print(f"missing elo_diff: {model_df['elo_diff'].isna().sum()}")

    snapshot = build_current_snapshot(long_df, current_ratings, priors)
    snapshot.to_csv(PROCESSED_DIR / "fighter_snapshot.csv", index=False)
    print(f"fighter_snapshot: {len(snapshot)} rows -> {PROCESSED_DIR / 'fighter_snapshot.csv'}")


if __name__ == "__main__":
    main()
