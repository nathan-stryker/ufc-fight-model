"""
Train a baseline (Elo-only logistic regression) and a main XGBoost model on
fighter_A - fighter_B differential features, using a CHRONOLOGICAL split
(never random k-fold, since fight outcomes aren't i.i.d. over time).

  train:      fights before TRAIN_CUTOFF
  validation: TRAIN_CUTOFF <= fights < TEST_CUTOFF   (early stopping only)
  test:       fights >= TEST_CUTOFF                   (untouched holdout, see evaluate.py)

Run: python -m src.models.train
"""
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score
from xgboost import XGBClassifier

from src.features.build_features import FEATURE_COLS, INTERACTION_COLS

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "models" / "artifacts"

TRAIN_CUTOFF = "2022-01-01"
TEST_CUTOFF = "2024-01-01"


def load_splits():
    df = pd.read_csv(PROCESSED_DIR / "model_features.csv", parse_dates=["event_date"])
    # Explicitly FEATURE_COLS-driven, not "every _diff column in the CSV" --
    # model_features.csv can carry extra _diff columns (e.g. elo_diff is
    # always present for the baseline/blend below even when FEATURE_COLS
    # doesn't include "elo") that shouldn't silently leak into the main model.
    feature_cols = [f"{c}_diff" for c in FEATURE_COLS]  # INTERACTION_COLS tried, didn't hold up -- see README

    train = df[df["event_date"] < TRAIN_CUTOFF]
    val = df[(df["event_date"] >= TRAIN_CUTOFF) & (df["event_date"] < TEST_CUTOFF)]
    test = df[df["event_date"] >= TEST_CUTOFF]

    return train, val, test, feature_cols


def report(name, y_true, y_prob):
    y_pred = (y_prob >= 0.5).astype(int)
    print(
        f"  [{name}] n={len(y_true)}  acc={accuracy_score(y_true, y_pred):.3f}  "
        f"log_loss={log_loss(y_true, y_prob, labels=[0, 1]):.3f}  "
        f"auc={roc_auc_score(y_true, y_prob):.3f}"
    )


def main():
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    train, val, test, feature_cols = load_splits()
    print(f"train={len(train)}  val={len(val)}  test={len(test)}  features={len(feature_cols)}")

    X_train, y_train = train[feature_cols], train["label"]
    X_val, y_val = val[feature_cols], val["label"]

    # --- Baseline: Elo-only logistic regression ---
    baseline = LogisticRegression()
    elo_train = X_train[["elo_diff"]].fillna(0.0)
    elo_val = X_val[["elo_diff"]].fillna(0.0)
    baseline.fit(elo_train, y_train)
    print("Baseline (Elo-only logistic regression):")
    report("train", y_train, baseline.predict_proba(elo_train)[:, 1])
    report("val", y_val, baseline.predict_proba(elo_val)[:, 1])

    # --- Main model: XGBoost on full differential feature set ---
    # Hyperparameters come from src.models.tune's expanding-window CV search
    # (models/artifacts/best_params.json) when available, falling back to
    # these defaults otherwise -- rerun `python -m src.models.tune` after
    # adding/removing features, since the best config can shift.
    default_params = {
        "max_depth": 4, "learning_rate": 0.03, "subsample": 0.8,
        "colsample_bytree": 0.8, "min_child_weight": 5, "reg_lambda": 1.0,
    }
    best_params_path = ARTIFACTS_DIR / "best_params.json"
    if best_params_path.exists():
        with open(best_params_path) as f:
            tuned_params = json.load(f)
        print(f"Using tuned hyperparameters from {best_params_path}: {tuned_params}")
    else:
        tuned_params = default_params

    model = XGBClassifier(
        n_estimators=500,
        eval_metric="logloss",
        early_stopping_rounds=30,
        missing=float("nan"),
        random_state=42,
        **tuned_params,
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    print(f"\nXGBoost (best_iteration={model.best_iteration}):")
    report("train", y_train, model.predict_proba(X_train)[:, 1])
    report("val", y_val, model.predict_proba(X_val)[:, 1])

    joblib.dump(baseline, ARTIFACTS_DIR / "baseline_elo_logreg.joblib")
    model.save_model(ARTIFACTS_DIR / "xgb_model.json")
    with open(ARTIFACTS_DIR / "feature_cols.json", "w") as f:
        json.dump(feature_cols, f, indent=2)

    print(f"\nSaved model + baseline + feature list to {ARTIFACTS_DIR}")
    print("Run `python -m src.models.evaluate` for the untouched holdout test report.")


if __name__ == "__main__":
    main()
