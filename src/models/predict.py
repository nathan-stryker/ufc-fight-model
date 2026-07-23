"""
Predict a hypothetical matchup between two named fighters: win probability,
method of victory (Decision/KO-TKO/Submission), and -- if a finish is more
likely than not -- which round it happens in.

Each fighter's features come from their most up-to-date snapshot
(data/processed/fighter_snapshot.csv and method_snapshot.csv, built by
src.features.build_features and src.features.method_features).

Win probability is symmetrized: we score (A,B) and (B,A) through the model
and average P(A wins) with 1 - P(B wins), which is guaranteed to sum to 1 and
cancels out boosting noise (see src/models/evaluate.py for why).

Method and round are conditioned on who wins, then marginalized:
  P(method) = P(A wins)*P(method|A wins) + P(B wins)*P(method|B wins)
  P(round|finish) similarly, further split across method (KO vs Submission).

Usage: python -m src.models.predict "Fighter A Name" "Fighter B Name" [--rounds 3|5]
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from src.features.elo import BASE_RATING
from src.features.method_features import ALIGNMENT_COLS, METHODS
from src.models.evaluate import XGB_BLEND_WEIGHT, blend_with_elo_baseline

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "models" / "artifacts"

STANCE_CATEGORIES = ["Orthodox", "Southpaw", "Switch"]

SNAPSHOT_FIELDS = [
    "elo", "fights_entering", "win_pct_entering", "finish_rate_entering", "current_streak_entering",
    "sig_str_landed_per_min", "sig_str_absorbed_per_min", "sig_str_acc",
    "td_avg_per15", "td_acc", "td_def", "sub_att_per15", "ctrl_pct",
]
METHOD_DIST_FIELDS = [f"{tier}_{outcome}_{m}" for tier in ("last5", "career") for outcome in ("win", "loss") for m in METHODS]

METHOD_NAMES = {"dec": "Decision", "ko": "KO/TKO", "sub": "Submission"}


def resolve_fighter(name: str, fighters: pd.DataFrame) -> pd.Series:
    matches = fighters[fighters["name"].str.lower() == name.lower()]
    if len(matches) == 0:
        raise SystemExit(f"No fighter found matching '{name}'.")
    if len(matches) > 1:
        options = "\n".join(f"  - {r.fighter_id} (dob {r.dob})" for r in matches.itertuples())
        raise SystemExit(
            f"'{name}' matches {len(matches)} different fighters in the data -- "
            f"disambiguate by editing this script to filter on fighter_id:\n{options}"
        )
    return matches.iloc[0]


# Defaults for a fighter with no matched fight history (a true UFC debut, or an
# older fighter whose one fight failed name-matching): base Elo, zero
# experience, and NaN for everything that requires prior fights -- XGBoost
# handles missing values natively, so the model falls back to whatever
# physical attributes and experience differential it does have.
DEBUT_DEFAULTS = {
    "elo": BASE_RATING,
    "fights_entering": 0,
    "win_pct_entering": np.nan,
    "finish_rate_entering": np.nan,
    "current_streak_entering": 0,
    "sig_str_landed_per_min": np.nan,
    "sig_str_absorbed_per_min": np.nan,
    "sig_str_acc": np.nan,
    "td_avg_per15": np.nan,
    "td_acc": np.nan,
    "td_def": np.nan,
    "sub_att_per15": np.nan,
    "ctrl_pct": np.nan,
}


def build_feature_row(fighter_row, snapshot: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    fid = fighter_row["fighter_id"]
    snap = snapshot[snapshot["fighter_id"] == fid]

    if len(snap) == 0:
        print(
            f"  note: no fight history found for {fighter_row['name']} -- "
            f"treating as a debut (base Elo, no rolling-form stats). Prediction "
            f"will lean heavily on physical attributes for this fighter."
        )
        feats = dict(DEBUT_DEFAULTS)
        feats["layoff_days_entering"] = np.nan
    else:
        snap = snap.iloc[0]
        feats = {f: snap[f] for f in SNAPSHOT_FIELDS}
        feats["layoff_days_entering"] = (as_of - pd.Timestamp(snap["last_fight_date"])).days

    feats["height_in"] = fighter_row["height_in"]
    feats["reach_in"] = fighter_row["reach_in"]
    dob = fighter_row["dob"]
    feats["age_years"] = (as_of - dob).days / 365.25 if pd.notna(dob) else np.nan

    stance = fighter_row["stance"]
    for cat in STANCE_CATEGORIES:
        feats[f"stance_{cat.lower()}"] = 1.0 if stance == cat else 0.0

    return feats


def build_method_dist(fighter_id: str, method_snapshot: pd.DataFrame, priors: dict) -> dict:
    snap = method_snapshot[method_snapshot["fighter_id"] == fighter_id]
    if len(snap) == 0:
        # No history -- fall back to sport-wide win/loss-by-method rates at both tiers.
        return {f"{tier}_{outcome}_{m}": priors[m] for tier in ("last5", "career") for outcome in ("win", "loss") for m in METHODS}
    snap = snap.iloc[0]
    return {f: snap[f] for f in METHOD_DIST_FIELDS}


def get_division_info(fighter_id: str, division_ratings: pd.DataFrame) -> dict | None:
    """
    Weight-class-specific Elo, shown as informational context only -- it
    didn't hold up as a training feature on holdout validation (95%
    correlated with the existing global Elo, added no measurable accuracy;
    see README), but a fighter's standing within their actual division is
    still a genuinely interesting stat on its own.
    """
    rows = division_ratings[division_ratings["fighter_id"] == fighter_id]
    if len(rows) == 0:
        return None
    current = rows.sort_values("last_fight_date").iloc[-1]
    division = current["weightclass"]
    in_division = division_ratings[division_ratings["weightclass"] == division].sort_values(
        "elo_rating", ascending=False
    ).reset_index(drop=True)
    rank = int(in_division[in_division["fighter_id"] == fighter_id].index[0]) + 1
    return {"weightclass": division, "elo_rating": current["elo_rating"], "rank": rank, "n_in_division": len(in_division)}


def compute_alignment_features(dist_a: dict, dist_b: dict, a_is_favorite: bool) -> dict:
    """Mirrors src.features.method_features.add_favorite_alignment_features for a single live matchup."""
    fav_dist, dog_dist = (dist_a, dist_b) if a_is_favorite else (dist_b, dist_a)
    align = {}
    for tier in ("last5", "career"):
        for m in METHODS:
            align[f"align_fav_{m}_{tier}"] = fav_dist[f"{tier}_win_{m}"] * dog_dist[f"{tier}_loss_{m}"]
            align[f"align_upset_{m}_{tier}"] = dog_dist[f"{tier}_win_{m}"] * fav_dist[f"{tier}_loss_{m}"]
    return align


def predict_full(name_a: str, name_b: str, scheduled_rounds: int = 3, as_of: pd.Timestamp = None):
    as_of = as_of or pd.Timestamp(datetime.now().date())

    fighters = pd.read_csv(PROCESSED_DIR / "fighters.csv", parse_dates=["dob"])
    snapshot = pd.read_csv(PROCESSED_DIR / "fighter_snapshot.csv", parse_dates=["last_fight_date"])
    method_snapshot = pd.read_csv(PROCESSED_DIR / "method_snapshot.csv")
    division_ratings = pd.read_csv(PROCESSED_DIR / "division_elo_ratings.csv", parse_dates=["last_fight_date"])
    with open(PROCESSED_DIR / "method_priors.json") as f:
        method_priors = json.load(f)
    with open(ARTIFACTS_DIR / "feature_cols.json") as f:
        win_feature_cols = json.load(f)
    with open(ARTIFACTS_DIR / "method_feature_cols.json") as f:
        method_feature_cols = json.load(f)
    with open(ARTIFACTS_DIR / "method_classes.json") as f:
        method_classes = json.load(f)
    with open(ARTIFACTS_DIR / "round_feature_cols.json") as f:
        round_feature_cols = json.load(f)

    a = resolve_fighter(name_a, fighters)
    b = resolve_fighter(name_b, fighters)

    # --- win probability (same as before) ---
    feats_a = build_feature_row(a, snapshot, as_of)
    feats_b = build_feature_row(b, snapshot, as_of)
    base_cols = [c[:-len("_diff")] for c in win_feature_cols]
    row_ab = {f"{c}_diff": feats_a[c] - feats_b[c] for c in base_cols}
    row_ba = {f"{c}_diff": feats_b[c] - feats_a[c] for c in base_cols}
    X_win = pd.DataFrame([row_ab, row_ba])[win_feature_cols]

    win_model = XGBClassifier()
    win_model.load_model(ARTIFACTS_DIR / "xgb_model.json")
    xgb_probs = win_model.predict_proba(X_win)[:, 1]

    baseline = joblib.load(ARTIFACTS_DIR / "baseline_elo_logreg.joblib")
    elo_probs = baseline.predict_proba(X_win[["elo_diff"]].fillna(0.0))[:, 1]
    blended = blend_with_elo_baseline(xgb_probs, elo_probs)
    prob_a_wins = 0.5 * (blended[0] + (1 - blended[1]))
    prob_b_wins = 1.0 - prob_a_wins

    # --- method of victory, conditioned on winner then marginalized ---
    dist_a = build_method_dist(a["fighter_id"], method_snapshot, method_priors)
    dist_b = build_method_dist(b["fighter_id"], method_snapshot, method_priors)
    a_is_favorite = feats_a["elo"] >= feats_b["elo"]
    align = compute_alignment_features(dist_a, dist_b, a_is_favorite)

    method_model = XGBClassifier()
    method_model.load_model(ARTIFACTS_DIR / "method_model.json")
    method_diff_cols = [c for c in method_feature_cols if c.endswith("_diff")]
    row_method_a = {**row_ab, **align}  # method | A wins
    row_method_b = {**row_ba, **align}  # method | B wins
    X_method = pd.DataFrame([row_method_a, row_method_b])[method_feature_cols]
    method_probs = method_model.predict_proba(X_method)  # rows: [given A wins, given B wins]

    p_method_given_a = dict(zip(method_classes, method_probs[0]))
    p_method_given_b = dict(zip(method_classes, method_probs[1]))
    method_overall = {
        m: prob_a_wins * p_method_given_a[m] + prob_b_wins * p_method_given_b[m] for m in method_classes
    }

    # --- round of finish, conditioned on (winner, method) then marginalized ---
    round_model = XGBClassifier()
    round_model.load_model(ARTIFACTS_DIR / "round_model.json")
    round_rows, round_weights = [], []
    for winner_label, row_diff, p_wins, p_method_given in [
        ("a", row_ab, prob_a_wins, p_method_given_a), ("b", row_ba, prob_b_wins, p_method_given_b)
    ]:
        for m in ("ko", "sub"):
            round_rows.append({**row_diff, **align, "scheduled_rounds": scheduled_rounds, "is_ko": float(m == "ko"), "is_sub": float(m == "sub")})
            round_weights.append(p_wins * p_method_given[m])

    X_round = pd.DataFrame(round_rows)[round_feature_cols]
    round_probs = round_model.predict_proba(X_round)  # shape (4, n_round_classes); rows: (a,ko),(a,sub),(b,ko),(b,sub)
    round_weights = np.array(round_weights)
    p_finish = round_weights.sum()
    if p_finish > 1e-9:
        round_dist = (round_probs * round_weights[:, None]).sum(axis=0) / p_finish
    else:
        round_dist = np.zeros(round_probs.shape[1])
    round_dist = round_dist[:scheduled_rounds]

    # Per-(fighter, method) conditional round distribution -- P(round=r | that
    # fighter wins by that specific method), not marginalized away like
    # round_given_finish above. Needed for prop markets like "Fighter A by
    # KO/TKO, Round 2": multiply round_given_win_method[side][method][r-1] by
    # method_given_a/b[method] to get the true joint probability.
    round_given_win_method = {
        "a": {"ko": round_probs[0][:scheduled_rounds], "sub": round_probs[1][:scheduled_rounds]},
        "b": {"ko": round_probs[2][:scheduled_rounds], "sub": round_probs[3][:scheduled_rounds]},
    }

    return {
        "name_a": a["name"], "name_b": b["name"],
        "prob_a_wins": prob_a_wins, "prob_b_wins": prob_b_wins,
        "method": method_overall,
        # Per-fighter method breakdown (P(A wins AND method=m), not just P(method=m)
        # overall) -- needed for prop markets like "Fighter A by Submission", which
        # method_overall alone can't answer since it's already marginalized over who wins.
        "method_given_a": {m: prob_a_wins * p_method_given_a[m] for m in method_classes},
        "method_given_b": {m: prob_b_wins * p_method_given_b[m] for m in method_classes},
        "round_given_win_method": round_given_win_method,
        "p_finish": p_finish,
        "round_given_finish": {i + 1: round_dist[i] for i in range(len(round_dist))},
        "scheduled_rounds": scheduled_rounds,
        "division_a": get_division_info(a["fighter_id"], division_ratings),
        "division_b": get_division_info(b["fighter_id"], division_ratings),
    }


def predict_matchup(name_a: str, name_b: str, as_of: pd.Timestamp = None):
    """Backwards-compatible win-probability-only entry point."""
    result = predict_full(name_a, name_b, as_of=as_of)
    return result["prob_a_wins"], result["name_a"], result["name_b"]


def main():
    parser = argparse.ArgumentParser(description="Predict a UFC matchup: winner, method, and round.")
    parser.add_argument("fighter_a")
    parser.add_argument("fighter_b")
    parser.add_argument("--rounds", type=int, default=3, choices=[3, 5], help="Scheduled rounds (5 for title/main-event fights)")
    args = parser.parse_args()

    r = predict_full(args.fighter_a, args.fighter_b, scheduled_rounds=args.rounds)

    def division_line(name, div):
        if div is None:
            return f"{name}: no division history"
        return f"{name}: {div['weightclass']} (#{div['rank']} of {div['n_in_division']} all-time by division Elo)"

    print(f"\n{division_line(r['name_a'], r['division_a'])}")
    print(division_line(r["name_b"], r["division_b"]))

    print(f"\n{r['name_a']}: {r['prob_a_wins']:.1%}")
    print(f"{r['name_b']}: {r['prob_b_wins']:.1%}")

    # Single declarative pick, derived from the same top-ranked method/round
    # printed below -- not a separately-computed per-winner conditional, so it
    # can never disagree with the breakdown that follows it.
    winner_name = r["name_a"] if r["prob_a_wins"] >= 0.5 else r["name_b"]
    top_method = max(r["method"], key=r["method"].get)
    verdict = f"{winner_name} by {METHOD_NAMES[top_method]}"
    if top_method != "dec" and r["round_given_finish"]:
        top_round = max(r["round_given_finish"], key=r["round_given_finish"].get)
        verdict += f", Round {top_round}"
    print(f"\nPredicted: {verdict}")

    print("\nMethod of victory:")
    for m in ["dec", "ko", "sub"]:
        print(f"  {METHOD_NAMES[m]}: {r['method'][m]:.1%}")

    print(f"\nGoes the distance ({r['scheduled_rounds']} rounds): {1 - r['p_finish']:.1%}")
    print(f"Ends in a finish: {r['p_finish']:.1%}")
    if r["p_finish"] > 0.01:
        print("  Round breakdown (given a finish happens):")
        for rnd, p in r["round_given_finish"].items():
            print(f"    Round {rnd}: {p:.1%}")


if __name__ == "__main__":
    main()
