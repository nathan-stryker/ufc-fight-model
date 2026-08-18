"""
One-off experiment: does restricting the WIN model's training rows to a
"modern era" cutoff improve holdout accuracy, vs training on the full
1994-> history like the production model does?

Elo ratings and rolling/career-stat features are still computed over each
fighter's COMPLETE history in model_features.csv (unchanged) -- this
script only restricts which ROWS get used to FIT the model, never
truncates the underlying feature computation. Truncating the raw history
itself would corrupt those features for any fighter whose career started
before the cutoff (wrong entering-Elo, wrong record/streak, etc.) -- same
class of bug already found and fixed elsewhere in this project (see the
duplicate-name fighter fix).

Uses the SAME fixed holdout (fights on/after TEST_CUTOFF), the SAME
train/val split point (TRAIN_CUTOFF), and the SAME production tuned
hyperparameters (models/artifacts/best_params.json, read-only) as
train.py/evaluate.py, so results are a fair apples-to-apples comparison
against the live model's known holdout numbers. Does NOT write anything
to models/artifacts/ -- this never touches the deployed model.

Caveat: hyperparameters were tuned for the FULL-history dataset via
src.models.tune's expanding-window CV search. A smaller, restricted-era
training set might do even better with its own re-tuned hyperparameters
-- that's a slower, separate experiment, not run here.

Run: python -m src.models.experiment_train_cutoff
"""
import json
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from xgboost import XGBClassifier

from src.features.build_features import FEATURE_COLS

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "models" / "artifacts"

TRAIN_CUTOFF = "2022-01-01"  # same as train.py
TEST_CUTOFF = "2024-01-01"  # same as train.py / evaluate.py
XGB_BLEND_WEIGHT = 0.9  # same as evaluate.py

CUTOFFS = {
    "full history (production baseline)": None,
    "2005-01-01 (modern-era skillset)": "2005-01-01",
    "2008-10-18 (Jim Miller's UFC debut)": "2008-10-18",
    "2010-01-01": "2010-01-01",
}


def report(name, y_true, y_prob):
    y_pred = (y_prob >= 0.5).astype(int)
    print(
        f"  [{name}] n={len(y_true)}  acc={accuracy_score(y_true, y_pred):.3f}  "
        f"log_loss={log_loss(y_true, y_prob, labels=[0, 1]):.3f}  "
        f"brier={brier_score_loss(y_true, y_prob):.3f}  "
        f"auc={roc_auc_score(y_true, y_prob):.3f}"
    )


def blend_with_elo_baseline(xgb_prob, elo_prob, w=XGB_BLEND_WEIGHT):
    return w * xgb_prob + (1 - w) * elo_prob


def run_one(df, feature_cols, tuned_params, train_start, label):
    train = df[df["event_date"] < TRAIN_CUTOFF]
    if train_start is not None:
        train = train[train["event_date"] >= train_start]
    val = df[(df["event_date"] >= TRAIN_CUTOFF) & (df["event_date"] < TEST_CUTOFF)]
    test = df[df["event_date"] >= TEST_CUTOFF]

    X_train, y_train = train[feature_cols], train["label"]
    X_val, y_val = val[feature_cols], val["label"]
    X_test, y_test = test[feature_cols], test["label"]

    # Elo-only baseline, refit per cutoff -- mirrors train.py's own procedure
    # so the blend comparison stays apples-to-apples at every cutoff.
    baseline = LogisticRegression()
    elo_train = X_train[["elo_diff"]].fillna(0.0)
    elo_test = X_test[["elo_diff"]].fillna(0.0)
    baseline.fit(elo_train, y_train)
    baseline_prob = baseline.predict_proba(elo_test)[:, 1]

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
    blended_prob = blend_with_elo_baseline(xgb_prob, baseline_prob)

    print(f"\n=== {label} ===")
    print(f"  train rows: {len(train)}  "
          f"(from {train['event_date'].min().date()} to {train['event_date'].max().date()})")
    print(f"  val rows:   {len(val)}")
    print(f"  test rows:  {len(test)}  (identical across every cutoff)")
    print(f"  best_iteration: {model.best_iteration}")
    report("Elo-only baseline", y_test, baseline_prob)
    report(f"XGBoost ({XGB_BLEND_WEIGHT:.0%} XGB / {1 - XGB_BLEND_WEIGHT:.0%} Elo blend)", y_test, blended_prob)

    return {
        "cutoff": label,
        "train_n": len(train),
        "acc": accuracy_score(y_test, (blended_prob >= 0.5).astype(int)),
        "log_loss": log_loss(y_test, blended_prob, labels=[0, 1]),
        "brier": brier_score_loss(y_test, blended_prob),
        "auc": roc_auc_score(y_test, blended_prob),
    }


def main():
    df = pd.read_csv(PROCESSED_DIR / "model_features.csv", parse_dates=["event_date"])
    feature_cols = [f"{c}_diff" for c in FEATURE_COLS]

    with open(ARTIFACTS_DIR / "best_params.json") as f:
        tuned_params = json.load(f)
    print(f"Using production tuned hyperparameters (read-only, not modified): {tuned_params}")
    print(f"Fixed holdout: fights on/after {TEST_CUTOFF} (identical across every run below)\n")

    results = [run_one(df, feature_cols, tuned_params, cutoff, label) for label, cutoff in CUTOFFS.items()]

    print("\n\n=== SUMMARY (vs. production full-history baseline) ===")
    summary = pd.DataFrame(results)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
