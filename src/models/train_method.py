"""
Train a 3-class method-of-victory model (KO/TKO, Submission, Decision) on the
WINNER's perspective of each historical fight -- i.e. "given that fighter X
beat fighter Y, how did it end?" Reuses the win model's diff features (from
model_features.csv, filtered to label==1 rows, which are exactly the
winner-oriented diffs) plus the favorite/underdog method-alignment features
from src.features.method_features.

Also retrains the PREVIOUS feature set (diffs + alignment only) side by side
and prints the class-base-rate log loss, so every retrain shows how much the
extra method features (see method_features.METHOD_EXTRA_COLS) are adding.
Log loss vs. base rates is the metric that matters here, not accuracy:
submissions are ~20% of outcomes, so even a perfect model would rarely name
one as the single most likely result.

Run: python -m src.models.train_method
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, log_loss
from xgboost import XGBClassifier

from src.features.build_features import FEATURE_COLS, FIGHTER_LEVEL_FIELDS
from src.features.method_features import ALIGNMENT_COLS, METHOD_EXTRA_COLS, METHOD_HISTORY_COLS, division_context

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "models" / "artifacts"

TRAIN_CUTOFF = "2022-01-01"
TEST_CUTOFF = "2024-01-01"
DIFF_COLS = [f"{c}_diff" for c in FEATURE_COLS]
METHOD_FEATURE_COLS = DIFF_COLS + ALIGNMENT_COLS + METHOD_EXTRA_COLS


def load_training_table():
    model_features = pd.read_csv(PROCESSED_DIR / "model_features.csv", parse_dates=["event_date"])
    winner_rows = model_features[model_features["label"] == 1]

    # method_long's "win" rows are the winner's perspective: its own columns
    # are the winner's, its opp_ columns the loser's.
    method_long = pd.read_csv(PROCESSED_DIR / "method_long.csv")
    wins = method_long[method_long["result"] == "win"].copy()
    for tier in ("last5", "career"):
        for m in ("ko", "sub"):
            wins[f"winner_{tier}_win_{m}"] = wins[f"{tier}_win_{m}"]
            wins[f"loser_{tier}_loss_{m}"] = wins[f"opp_{tier}_loss_{m}"]
    winner_method = wins[["fight_id", "fighter_id", "opponent_id", "method_bucket"] + ALIGNMENT_COLS + METHOD_HISTORY_COLS]

    df = winner_rows.merge(winner_method, on="fight_id", how="inner")
    df = df.dropna(subset=["method_bucket"])

    levels = pd.read_csv(PROCESSED_DIR / "fighter_fight_levels.csv")
    for side, id_col in (("winner", "fighter_id"), ("loser", "opponent_id")):
        renamed = levels.rename(columns={"fighter_id": id_col, **{f: f"{side}_{f}" for f in FIGHTER_LEVEL_FIELDS}})
        df = df.merge(renamed, on=["fight_id", id_col], how="left")

    fights = pd.read_csv(PROCESSED_DIR / "fights.csv", usecols=["fight_id", "weightclass", "time_format"])
    ctx = fights["weightclass"].map(division_context)
    fights["division_lbs"] = [c[0] for c in ctx]
    fights["is_womens"] = [c[1] for c in ctx]
    fights["scheduled_rounds"] = fights["time_format"].str.extract(r"(\d+)\s*Rnd")[0].astype(float)
    df = df.merge(fights[["fight_id", "division_lbs", "is_womens", "scheduled_rounds"]], on="fight_id", how="left")
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

    y_test_all = test["method_bucket"].map(class_to_idx)
    base_rates = train["method_bucket"].map(class_to_idx).value_counts(normalize=True).reindex(range(len(classes))).to_numpy()
    prior_ll = log_loss(y_test_all, np.tile(base_rates, (len(test), 1)), labels=list(range(len(classes))))
    majority_acc = (test["method_bucket"] == majority_class).mean()
    print(f"\nbase rates only: test log_loss={prior_ll:.3f}   always '{majority_class}': test acc={majority_acc:.3f}")

    for feature_set_name, cols in [("previous (diffs + alignment)", DIFF_COLS + ALIGNMENT_COLS),
                                   ("current (+ context/levels/history)", METHOD_FEATURE_COLS)]:
        print(f"\n=== feature set: {feature_set_name} ===")
        X_train, y_train = train[cols], train["method_bucket"].map(class_to_idx)
        X_val, y_val = val[cols], val["method_bucket"].map(class_to_idx)
        X_test, y_test = test[cols], test["method_bucket"].map(class_to_idx)

        model = XGBClassifier(
            n_estimators=600, max_depth=4, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
            objective="multi:softprob", eval_metric="mlogloss",
            early_stopping_rounds=30, missing=float("nan"), random_state=42,
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

        model_classes = classes
        report("train", y_train, model.predict_proba(X_train), list(range(len(classes))))
        report("val", y_val, model.predict_proba(X_val), list(range(len(classes))))
        test_acc, test_ll = report("test (holdout)", y_test, model.predict_proba(X_test), list(range(len(classes))))
        print(f"  improvement over base rates: {(prior_ll - test_ll) / prior_ll:+.1%}")

        if feature_set_name.startswith("current"):
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
