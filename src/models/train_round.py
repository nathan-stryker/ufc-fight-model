"""
Train a round-of-finish model: given a fight ends in a finish (KO/TKO or
Submission), which round does it happen in? Decisions aren't modeled here --
they trivially go the distance to the last scheduled round.

Classes are {1,2,3,4,5}, with `scheduled_rounds` (3 for most fights, 5 for
title/main-event fights) and `is_ko`/`is_sub` given as input features so a
single model can learn both fight-length formats and both finish types. At
prediction time (see predict.py), this is queried twice -- once as if it
were a KO, once as if it were a submission -- and mixed together using the
method model's P(ko)/P(sub) as weights.

Run: python -m src.models.train_round
"""
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, log_loss
from xgboost import XGBClassifier

from src.models.train_method import DIFF_COLS, load_training_table
from src.features.method_features import ALIGNMENT_COLS

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "models" / "artifacts"

TRAIN_CUTOFF = "2022-01-01"
TEST_CUTOFF = "2024-01-01"
FEATURE_COLS = DIFF_COLS + ALIGNMENT_COLS + ["scheduled_rounds", "is_ko", "is_sub"]


def load_round_training_table():
    df = load_training_table()  # fight_id, event_date, DIFF_COLS, ALIGNMENT_COLS, method_bucket
    finishes = df[df["method_bucket"].isin(["ko", "sub"])].copy()

    fights = pd.read_csv(PROCESSED_DIR / "fights.csv")
    sched = fights["time_format"].str.extract(r"(\d+)\s*Rnd")[0].astype(float).fillna(1.0)
    fights = fights.assign(scheduled_rounds=sched)[["fight_id", "round", "scheduled_rounds"]]

    finishes = finishes.merge(fights, on="fight_id", how="left")
    finishes["is_ko"] = (finishes["method_bucket"] == "ko").astype(float)
    finishes["is_sub"] = (finishes["method_bucket"] == "sub").astype(float)
    finishes = finishes.dropna(subset=["round"])
    finishes["round_idx"] = finishes["round"].astype(int) - 1  # 0-indexed for XGBoost
    return finishes


def main():
    df = load_round_training_table()
    print(f"training table: {len(df)} finishes with a round label")
    print(df["round"].value_counts().sort_index().to_dict())

    train = df[df["event_date"] < TRAIN_CUTOFF]
    val = df[(df["event_date"] >= TRAIN_CUTOFF) & (df["event_date"] < TEST_CUTOFF)]
    test = df[df["event_date"] >= TEST_CUTOFF]
    print(f"train={len(train)}  val={len(val)}  test={len(test)}")

    n_classes = int(df["round_idx"].max()) + 1
    X_train, y_train = train[FEATURE_COLS], train["round_idx"]
    X_val, y_val = val[FEATURE_COLS], val["round_idx"]
    X_test, y_test = test[FEATURE_COLS], test["round_idx"]

    model = XGBClassifier(
        n_estimators=300, max_depth=3, learning_rate=0.03,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        objective="multi:softprob", num_class=n_classes, eval_metric="mlogloss",
        early_stopping_rounds=30, missing=float("nan"),
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    for name, X, y in [("train", X_train, y_train), ("val", X_val, y_val), ("test (holdout)", X_test, y_test)]:
        probs = model.predict_proba(X)
        pred = probs.argmax(axis=1)
        acc = accuracy_score(y, pred)
        ll = log_loss(y, probs, labels=list(range(n_classes)))
        print(f"  [{name}] n={len(y)}  acc={acc:.3f}  log_loss={ll:.3f}")

    majority_round = int(train["round"].mode()[0])
    majority_acc = (test["round"] == majority_round).mean()
    print(f"  majority-round baseline (always round {majority_round}) test acc = {majority_acc:.3f}")

    model.save_model(ARTIFACTS_DIR / "round_model.json")
    with open(ARTIFACTS_DIR / "round_feature_cols.json", "w") as f:
        json.dump(FEATURE_COLS, f, indent=2)
    print(f"\nSaved round model -> {ARTIFACTS_DIR}")


if __name__ == "__main__":
    main()
