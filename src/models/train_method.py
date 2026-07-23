"""
Train a 3-class method-of-victory model (KO/TKO, Submission, Decision) on the
WINNER's perspective of each historical fight -- i.e. "given that fighter X
beat fighter Y, how did it end?" Reuses the win model's diff features (from
model_features.csv, filtered to label==1 rows, which are exactly the
winner-oriented diffs) plus the favorite/underdog method-alignment features
from src.features.method_features.

Also trains an ablation model WITHOUT the alignment features, to check
whether they add real signal beyond what's already in the diff features --
a direct test of the matchup heuristic they're built from.

Run: python -m src.models.train_method
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, log_loss
from xgboost import XGBClassifier

from src.features.build_features import FEATURE_COLS
from src.features.method_features import ALIGNMENT_COLS

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "models" / "artifacts"

TRAIN_CUTOFF = "2022-01-01"
TEST_CUTOFF = "2024-01-01"
DIFF_COLS = [f"{c}_diff" for c in FEATURE_COLS]


def load_training_table():
    model_features = pd.read_csv(PROCESSED_DIR / "model_features.csv", parse_dates=["event_date"])
    winner_rows = model_features[model_features["label"] == 1]

    method_long = pd.read_csv(PROCESSED_DIR / "method_long.csv")
    winner_method = method_long[method_long["result"] == "win"][["fight_id", "method_bucket"] + ALIGNMENT_COLS]

    df = winner_rows.merge(winner_method, on="fight_id", how="inner")
    df = df.dropna(subset=["method_bucket"])
    return df


def report(name, y_true, y_prob, classes):
    y_pred_idx = y_prob.argmax(axis=1)
    y_pred = [classes[i] for i in y_pred_idx]
    acc = accuracy_score(y_true, y_pred)
    ll = log_loss(y_true, y_prob, labels=classes)
    print(f"  [{name}] n={len(y_true)}  acc={acc:.3f}  log_loss={ll:.3f}")
    return acc, ll


def main():
    df = load_training_table()
    print(f"training table: {len(df)} fights with a clean method label")
    print(df["method_bucket"].value_counts(normalize=True).round(3).to_dict())

    train = df[df["event_date"] < TRAIN_CUTOFF]
    val = df[(df["event_date"] >= TRAIN_CUTOFF) & (df["event_date"] < TEST_CUTOFF)]
    test = df[df["event_date"] >= TEST_CUTOFF]
    print(f"train={len(train)}  val={len(val)}  test={len(test)}")

    classes = sorted(df["method_bucket"].unique())  # ['dec', 'ko', 'sub']
    class_to_idx = {c: i for i, c in enumerate(classes)}
    majority_class = df["method_bucket"].value_counts().idxmax()

    for feature_set_name, cols in [("full (+ alignment)", DIFF_COLS + ALIGNMENT_COLS), ("ablation (no alignment)", DIFF_COLS)]:
        print(f"\n=== feature set: {feature_set_name} ===")
        X_train, y_train = train[cols], train["method_bucket"].map(class_to_idx)
        X_val, y_val = val[cols], val["method_bucket"].map(class_to_idx)
        X_test, y_test = test[cols], test["method_bucket"].map(class_to_idx)

        model = XGBClassifier(
            n_estimators=400, max_depth=4, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
            objective="multi:softprob", eval_metric="mlogloss",
            early_stopping_rounds=30, missing=float("nan"),
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

        model_classes = classes
        report("train", y_train, model.predict_proba(X_train), list(range(len(classes))))
        report("val", y_val, model.predict_proba(X_val), list(range(len(classes))))
        test_acc, test_ll = report("test (holdout)", y_test, model.predict_proba(X_test), list(range(len(classes))))

        majority_acc = (test["method_bucket"] == majority_class).mean()
        print(f"  majority-class baseline (always '{majority_class}') test acc = {majority_acc:.3f}")

        if feature_set_name.startswith("full"):
            model.save_model(ARTIFACTS_DIR / "method_model.json")
            with open(ARTIFACTS_DIR / "method_feature_cols.json", "w") as f:
                json.dump(cols, f, indent=2)
            with open(ARTIFACTS_DIR / "method_classes.json", "w") as f:
                json.dump(model_classes, f, indent=2)
            y_pred_idx = model.predict_proba(X_test).argmax(axis=1)
            cm = confusion_matrix(y_test, y_pred_idx, labels=list(range(len(classes))))
            print(f"  confusion matrix (rows=actual, cols=predicted, order={model_classes}):\n{cm}")

    print(f"\nSaved method model + feature list + classes -> {ARTIFACTS_DIR}")


if __name__ == "__main__":
    main()
