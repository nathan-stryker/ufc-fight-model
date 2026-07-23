"""
Generate leakage-free, walk-forward (expanding-window) win probabilities for
every fight that has matched betting odds, so the backtest in
src/backtest/run_backtest.py compares the model against the market honestly.

Why not just use models/artifacts/xgb_model.json: that model was trained on
everything before 2024-01-01, so re-using it to "predict" a 2015 or 2019 fight
would be in-sample -- the model already saw that fight's outcome (and its
neighbors) during training. A real backtest needs, for every fight, a
prediction made by a model that only ever saw fights strictly before it.

Approach: yearly expanding-window folds, mirroring train.py's own
train/val/test split structure (val = the one year immediately before the
test year, for early stopping only) but sliding forward one year at a time:

  fold for test year Y:
    train < (Y-1)-01-01
    val    = [(Y-1)-01-01, Y-01-01)   (early stopping only)
    test   = [Y-01-01, (Y+1)-01-01)   (this fold's actual predictions)

Reuses the production-tuned hyperparameters (models/artifacts/best_params.json)
for every fold rather than re-tuning per fold -- consistent with how the real
pipeline already works, and re-tuning per fold would itself risk overfitting
the backtest.

Run: python -m src.backtest.walk_forward
Writes: data/processed/backtest_predictions.csv
"""
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier

from src.features.build_features import FEATURE_COLS
from src.models.evaluate import XGB_BLEND_WEIGHT, blend_with_elo_baseline

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
ARTIFACTS_DIR = ROOT / "models" / "artifacts"

FEATURE_COLS_DIFF = [f"{c}_diff" for c in FEATURE_COLS]
FOLD_YEARS = list(range(2015, 2024))  # matched odds run Nov 2014 - Dec 2023


def load_tuned_params():
    path = ARTIFACTS_DIR / "best_params.json"
    with open(path) as f:
        return json.load(f)


def own_fighter_id_map():
    """
    model_features.csv has fight_id + label but not fighter_id (dropped during
    export). Recover it: the label==1 row's "own" fighter is fights.csv's
    winner_id; the label==0 row's "own" fighter is whichever of the two
    fighters is NOT the winner.
    """
    fights = pd.read_csv(PROCESSED_DIR / "fights.csv")
    fights = fights[~fights["is_draw"] & ~fights["is_no_contest"]].copy()
    fights["loser_id"] = fights.apply(
        lambda r: r["fighter_2_id"] if r["winner_id"] == r["fighter_1_id"] else r["fighter_1_id"], axis=1
    )
    return fights.set_index("fight_id")[["winner_id", "loser_id"]]


def run():
    df = pd.read_csv(PROCESSED_DIR / "model_features.csv", parse_dates=["event_date"])
    id_map = own_fighter_id_map()
    df = df.join(id_map, on="fight_id")
    df["own_fighter_id"] = df["label"].map({1: None, 0: None})  # placeholder, filled below
    df.loc[df["label"] == 1, "own_fighter_id"] = df.loc[df["label"] == 1, "winner_id"]
    df.loc[df["label"] == 0, "own_fighter_id"] = df.loc[df["label"] == 0, "loser_id"]

    tuned_params = load_tuned_params()
    print(f"Using tuned hyperparameters: {tuned_params}\n")

    all_preds = []
    for year in FOLD_YEARS:
        train = df[df["event_date"] < f"{year - 1}-01-01"]
        val = df[(df["event_date"] >= f"{year - 1}-01-01") & (df["event_date"] < f"{year}-01-01")]
        test = df[(df["event_date"] >= f"{year}-01-01") & (df["event_date"] < f"{year + 1}-01-01")]
        if len(test) == 0:
            continue

        X_train, y_train = train[FEATURE_COLS_DIFF], train["label"]
        X_val, y_val = val[FEATURE_COLS_DIFF], val["label"]
        X_test = test[FEATURE_COLS_DIFF]

        baseline = LogisticRegression()
        baseline.fit(X_train[["elo_diff"]].fillna(0.0), y_train)

        model = XGBClassifier(
            n_estimators=500,
            eval_metric="logloss",
            early_stopping_rounds=30,
            missing=float("nan"),
            random_state=42,
            **tuned_params,
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

        xgb_prob = model.predict_proba(X_test)[:, 1]
        elo_prob = baseline.predict_proba(X_test[["elo_diff"]].fillna(0.0))[:, 1]
        model_prob = blend_with_elo_baseline(xgb_prob, elo_prob, XGB_BLEND_WEIGHT)

        fold = test[["fight_id", "own_fighter_id", "label"]].copy()
        fold["model_prob"] = model_prob

        # Symmetrize exactly like evaluate.py: average each row with (1 - its mirror row).
        fold = fold.sort_values("fight_id")
        mirror_prob = fold.groupby("fight_id")["model_prob"].transform(lambda s: s.iloc[::-1].to_numpy())
        fold["sym_prob"] = 0.5 * (fold["model_prob"] + (1 - mirror_prob))
        fold["fold_year"] = year

        print(f"[{year}] train={len(train)} val={len(val)} test={len(test)} (best_iter={model.best_iteration})")
        all_preds.append(fold)

    preds = pd.concat(all_preds, ignore_index=True)
    out_path = PROCESSED_DIR / "backtest_predictions.csv"
    preds.to_csv(out_path, index=False)
    print(f"\nwrote {out_path} ({len(preds)} rows across {preds['fight_id'].nunique()} fights)")


if __name__ == "__main__":
    run()
