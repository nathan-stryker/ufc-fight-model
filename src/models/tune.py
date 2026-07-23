"""
Proper hyperparameter search for the win model via expanding-window
chronological cross-validation -- train.py's single train/val split was
never actually used to COMPARE hyperparameter configs, just to early-stop
one fixed config. This averages log-loss across multiple sequential
validation windows (2020, 2021, 2022, 2023 in turn, each trained on
everything before it) for a more robust comparison, while keeping the
2024+ holdout completely untouched throughout the search -- it's only
touched once at the very end, by evaluate.py, to report a final number.

Run: python -m src.models.tune
"""
import itertools
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score
from xgboost import XGBClassifier

from src.features.build_features import FEATURE_COLS

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "models" / "artifacts"

FEATURE_COLS_DIFF = [f"{c}_diff" for c in FEATURE_COLS]  # INTERACTION_COLS tried, didn't hold up -- see README
FOLD_YEARS = [2020, 2021, 2022, 2023]  # each fold validates on this year, trains on everything before it
N_RANDOM_CONFIGS = 40
RANDOM_SEED = 42

PARAM_GRID = {
    "max_depth": [3, 4, 5, 6],
    "learning_rate": [0.02, 0.03, 0.05, 0.08, 0.1],
    "subsample": [0.6, 0.7, 0.8, 0.9, 1.0],
    "colsample_bytree": [0.6, 0.7, 0.8, 0.9, 1.0],
    "min_child_weight": [1, 3, 5, 10, 20],
    "reg_lambda": [0.5, 1.0, 2.0, 5.0],
}


def make_folds(df):
    folds = []
    for year in FOLD_YEARS:
        train = df[df["event_date"] < f"{year}-01-01"]
        val = df[(df["event_date"] >= f"{year}-01-01") & (df["event_date"] < f"{year + 1}-01-01")]
        folds.append((train, val))
    return folds


def evaluate_config(folds, params):
    accs, lls, aucs = [], [], []
    for train, val in folds:
        X_train, y_train = train[FEATURE_COLS_DIFF], train["label"]
        X_val, y_val = val[FEATURE_COLS_DIFF], val["label"]
        model = XGBClassifier(
            n_estimators=500,
            eval_metric="logloss",
            early_stopping_rounds=30,
            missing=float("nan"),
            random_state=RANDOM_SEED,
            **params,
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        probs = model.predict_proba(X_val)[:, 1]
        preds = (probs >= 0.5).astype(int)
        accs.append(accuracy_score(y_val, preds))
        lls.append(log_loss(y_val, probs, labels=[0, 1]))
        aucs.append(roc_auc_score(y_val, probs))
    return {"acc": np.mean(accs), "log_loss": np.mean(lls), "auc": np.mean(aucs)}


def main():
    df = pd.read_csv(PROCESSED_DIR / "model_features.csv", parse_dates=["event_date"])
    df = df[df["event_date"] < "2024-01-01"]  # holdout stays untouched throughout the whole search
    folds = make_folds(df)
    print(f"CV folds (expanding window, validating on {FOLD_YEARS}):")
    for year, (train, val) in zip(FOLD_YEARS, folds):
        print(f"  {year}: train={len(train)} val={len(val)}")

    rng = random.Random(RANDOM_SEED)
    keys = list(PARAM_GRID.keys())
    all_combos = list(itertools.product(*PARAM_GRID.values()))
    sampled = rng.sample(all_combos, min(N_RANDOM_CONFIGS, len(all_combos)))

    # Always include the current production config as a baseline for comparison.
    current_config = {
        "max_depth": 4, "learning_rate": 0.03, "subsample": 0.8,
        "colsample_bytree": 0.8, "min_child_weight": 5, "reg_lambda": 1.0,
    }
    configs = [current_config] + [dict(zip(keys, combo)) for combo in sampled]

    results = []
    for i, params in enumerate(configs):
        metrics = evaluate_config(folds, params)
        tag = "CURRENT" if i == 0 else f"#{i}"
        print(f"[{tag}] {params} -> acc={metrics['acc']:.4f} log_loss={metrics['log_loss']:.4f} auc={metrics['auc']:.4f}")
        results.append({**params, **metrics, "tag": tag})

    results_df = pd.DataFrame(results).sort_values("log_loss")
    results_df.to_csv(ARTIFACTS_DIR / "tune_results.csv", index=False)

    best = results_df.iloc[0]
    print(f"\nBest config by avg CV log_loss:")
    print(best)

    best_params = {k: (int(best[k]) if k == "max_depth" or k == "min_child_weight" else float(best[k])) for k in PARAM_GRID}
    with open(ARTIFACTS_DIR / "best_params.json", "w") as f:
        json.dump(best_params, f, indent=2)
    print(f"\nSaved best params -> {ARTIFACTS_DIR / 'best_params.json'}")


if __name__ == "__main__":
    main()
