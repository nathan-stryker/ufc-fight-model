"""
Export a compact, self-contained JSON payload of the trained models +
current fighter data, for a fully client-side (no server) prediction
website. Strips XGBoost's native JSON dump down to only what a tree-walking
interpreter needs, and packs fighter data as parallel arrays instead of
repeated-key objects to keep the payload small.

Run: python -m src.export_web_model
Writes: web/model_data.json
"""
import json
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.data.scrape_nationality import ACTIVE_WINDOW_MONTHS
from src.features.build_features import FEATURE_COLS
from src.features.method_features import ALIGNMENT_COLS, METHODS

ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"
ARTIFACTS_DIR = ROOT / "models" / "artifacts"
WEB_DIR = ROOT / "web"

SIG_FIGS = 6

# Split thresholds and leaf values are decision-critical: rounding them to 6
# sig figs turned out to flip ~83% of thresholds by up to 3.3e-4, and for a
# fighter whose actual feature value landed in that tiny gap, a single
# flipped branch sends the tree walk to a completely different leaf --
# caught a genuine ~0.7 point win-probability discrepancy against Python
# this way. XGBoost's internal precision is float32 (~7 significant digits),
# so 9 sig figs preserves it exactly while still trimming float64's noise
# digits; only non-decision values (fighter stats, display data) use the
# more aggressive 6-sig-fig rounding.
TREE_SIG_FIGS = 9


def r(x, sig_figs=SIG_FIGS):
    if x is None:
        return None
    return float(f"{x:.{sig_figs}g}")


def strip_tree(t):
    return [
        t["left_children"],
        t["right_children"],
        t["split_indices"],
        [r(x, TREE_SIG_FIGS) for x in t["split_conditions"]],
        t["default_left"],
        [r(x, TREE_SIG_FIGS) for x in t["base_weights"]],
    ]


def _best_iteration(learner):
    """
    Early stopping keeps training past the best round before it actually
    stops (early_stopping_rounds=30), so the saved model has MORE trees than
    it should use at inference time -- sklearn's predict_proba() silently
    truncates to best_iteration+1 rounds, but the raw JSON dump has all of
    them. Skipping this truncation is a real bug, not a rounding nuance: it
    changes predictions materially (confirmed by comparing a manual walk of
    all-trees against xgboost's own predict_proba).
    """
    attrs = learner.get("attributes", {})
    if "best_iteration" in attrs:
        return int(attrs["best_iteration"])
    return None


def strip_binary_model(path):
    with open(path) as f:
        d = json.load(f)
    learner = d["learner"]
    base_score = float(learner["learner_model_param"]["base_score"].strip("[]"))
    base_logit = float(np.log(base_score / (1 - base_score))) if 0 < base_score < 1 else 0.0
    trees = learner["gradient_booster"]["model"]["trees"]
    best_iter = _best_iteration(learner)
    if best_iter is not None:
        trees = trees[: best_iter + 1]
    return {
        "features": learner["feature_names"],
        "base_logit": r(base_logit, TREE_SIG_FIGS),
        "trees": [strip_tree(t) for t in trees],
    }


def strip_multiclass_model(path, classes=None):
    with open(path) as f:
        d = json.load(f)
    learner = d["learner"]
    lmp = learner["learner_model_param"]
    num_class = int(lmp["num_class"])
    base_score = [float(x) for x in lmp["base_score"].strip("[]").split(",")]
    model = learner["gradient_booster"]["model"]
    trees = model["trees"]
    tree_info = model["tree_info"]
    best_iter = _best_iteration(learner)
    if best_iter is not None:
        n = (best_iter + 1) * num_class
        trees, tree_info = trees[:n], tree_info[:n]
    return {
        "features": learner["feature_names"],
        "num_class": num_class,
        "classes": classes,
        "base_score": [r(x, TREE_SIG_FIGS) for x in base_score],
        "tree_info": tree_info,
        "trees": [strip_tree(t) for t in trees],
    }


def _division_info_per_fighter():
    """
    Precompute each fighter's most-recent division + all-time rank within it,
    so the website can show it without shipping the full ~4500-row division
    ratings table or re-implementing the groupby/rank logic in JS. Shown as
    informational context only -- validated NOT to help the model itself
    (see README's division Elo section), so it's not part of prediction.
    """
    div = pd.read_csv(PROCESSED_DIR / "division_elo_ratings.csv", parse_dates=["last_fight_date"])
    div["rank"] = div.groupby("weightclass")["elo_rating"].rank(ascending=False, method="min").astype(int)
    n_in_division = div.groupby("weightclass")["fighter_id"].transform("count")
    div["n_in_division"] = n_in_division
    current = div.sort_values("last_fight_date").groupby("fighter_id").tail(1)
    return current[["fighter_id", "weightclass", "rank", "n_in_division"]]


def export_fighters():
    fighters = pd.read_csv(PROCESSED_DIR / "fighters.csv", parse_dates=["dob"])
    snapshot = pd.read_csv(PROCESSED_DIR / "fighter_snapshot.csv", parse_dates=["last_fight_date"])
    method_snapshot = pd.read_csv(PROCESSED_DIR / "method_snapshot.csv")
    division_info = _division_info_per_fighter()
    nationality_path = PROCESSED_DIR / "fighter_nationality.csv"
    nationality = pd.read_csv(nationality_path)[["fighter_id", "iso_code"]] if nationality_path.exists() else \
        pd.DataFrame(columns=["fighter_id", "iso_code"])

    df = fighters.merge(snapshot, on="fighter_id", how="left").merge(
        method_snapshot.drop(columns=["event_date"]), on="fighter_id", how="left"
    ).merge(division_info, on="fighter_id", how="left").merge(nationality, on="fighter_id", how="left")
    # Only ship fighters we have SOME data for (a profile at minimum -- height/reach/dob
    # may still be missing and are handled client-side same as predict.py's debut path).
    df = df[df["name"].notna()]
    # Website roster is active-fighters-only (fought within ACTIVE_WINDOW_MONTHS) --
    # NOT a filter on the underlying training data, which stays complete for every
    # fighter regardless of activity (an active fighter's Elo/rolling-form features
    # depend on fights against opponents who've since retired). This only trims what
    # the site's search box can select, and is the same window scrape_nationality.py
    # used to decide who needed a flag scraped in the first place.
    cutoff = pd.Timestamp.now() - pd.DateOffset(months=ACTIVE_WINDOW_MONTHS)
    keep = df["last_fight_date"] >= cutoff
    # Exception: always keep anyone actually booked on the upcoming card (see
    # scrape_upcoming_card.py), even if their PREVIOUS fight was long enough ago
    # to fail the window above -- a fighter returning from a real multi-year
    # layoff is unambiguously current the moment they're booked, and excluding
    # them defeats the point of showing that card on the home page at all.
    # Found by testing: several of the actual UFC Fight Night 282 card's fighters
    # (e.g. a couple returning from injury/layoff) matched by name but failed
    # this cutoff, silently breaking their "Call This Fight" button.
    upcoming_path = PROCESSED_DIR / "upcoming_card.csv"
    if upcoming_path.exists():
        upcoming = pd.read_csv(upcoming_path)
        booked_ids = pd.concat([upcoming["fighter_a_id"], upcoming["fighter_b_id"]]).dropna().unique()
        keep = keep | df["fighter_id"].isin(booked_ids)
    df = df[keep]

    win_snapshot_fields = [
        "elo", "fights_entering", "win_pct_entering", "finish_rate_entering", "current_streak_entering",
        "sig_str_landed_per_min", "sig_str_absorbed_per_min", "sig_str_acc",
        "td_avg_per15", "td_acc", "td_def", "sub_att_per15", "ctrl_pct",
    ]
    method_dist_fields = [f"{tier}_{outcome}_{m}" for tier in ("last5", "career") for outcome in ("win", "loss") for m in METHODS]

    fields = ["fighter_id", "name", "nickname", "dob_epoch_days", "height_in", "reach_in", "stance", "last_fight_epoch_days"] \
        + win_snapshot_fields + method_dist_fields + ["weightclass", "rank", "n_in_division", "iso_code"]

    epoch = pd.Timestamp("1970-01-01")
    df["dob_epoch_days"] = (df["dob"] - epoch).dt.days
    df["last_fight_epoch_days"] = (df["last_fight_date"] - epoch).dt.days

    def clean(v):
        if pd.isna(v):
            return None
        if isinstance(v, (float, np.floating)):
            return r(float(v))
        if isinstance(v, (int, np.integer)):
            return int(v)
        return v

    rows = []
    for _, row in df.iterrows():
        rows.append([clean(row[f]) for f in fields])

    return {"fields": fields, "rows": rows}, sorted({str(c).lower() for c in df["iso_code"].dropna().unique()})


def _upcoming_card_payload():
    """
    Reads the pre-scraped upcoming-card cache (data/processed/upcoming_card.csv,
    see src/data/scrape_upcoming_card.py) -- NOT scraped over the network
    here, this is a build step. Degrades to no home-page card section at all
    if the file doesn't exist yet or the scrape found nothing, rather than
    failing the whole export.
    """
    path = PROCESSED_DIR / "upcoming_card.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if df.empty:
        return None
    df = df.sort_values("bout_order")
    first = df.iloc[0]
    bouts = []
    for _, row in df.iterrows():
        bouts.append({
            "weightClass": row["weight_class"] if pd.notna(row["weight_class"]) else None,
            "nameA": row["fighter_a_name"],
            "idA": row["fighter_a_id"] if pd.notna(row["fighter_a_id"]) else None,
            "nameB": row["fighter_b_name"],
            "idB": row["fighter_b_id"] if pd.notna(row["fighter_b_id"]) else None,
            "tier": row["tier"] if pd.notna(row.get("tier")) else "prelim",
        })
    return {
        "eventName": first["event_name"],
        "eventDate": first["event_date"],
        "eventLocation": first["event_location"],
        "bouts": bouts,
    }


def _flags_payload(codes):
    """
    Reads the pre-fetched local cache (web/flags/, see src/fetch_flags.py --
    NOT fetched over the network here; this is a build step, not a scraper)
    for exactly the country codes the active-fighter roster actually uses,
    so the payload only carries flags that'll actually be shown.
    """
    flags = {}
    for code in codes:
        path = WEB_DIR / "flags" / f"{code}.svg"
        if not path.exists():
            print(f"  warning: no cached flag for '{code}' -- run `python -m src.fetch_flags` first")
            continue
        svg = path.read_text(encoding="utf-8")
        svg = re.sub(r'\s+id="[^"]*"', "", svg)  # drop the id attr -- unused, avoids duplicate-id if a country repeats
        flags[code.upper()] = svg.strip()
    return flags


def main():
    WEB_DIR.mkdir(parents=True, exist_ok=True)

    with open(ARTIFACTS_DIR / "method_classes.json") as f:
        method_classes = json.load(f)

    baseline = joblib.load(ARTIFACTS_DIR / "baseline_elo_logreg.joblib")

    with open(PROCESSED_DIR / "method_priors.json") as f:
        method_priors = json.load(f)

    fights = pd.read_csv(PROCESSED_DIR / "fights.csv")
    total_fights = int((~fights["is_draw"] & ~fights["is_no_contest"]).sum())

    payload = {
        "total_fights": total_fights,
        "win_model": strip_binary_model(ARTIFACTS_DIR / "xgb_model.json"),
        "method_model": strip_multiclass_model(ARTIFACTS_DIR / "method_model.json", classes=method_classes),
        "round_model": strip_multiclass_model(ARTIFACTS_DIR / "round_model.json"),
        "elo_logreg": {
            "coef": r(float(baseline.coef_[0][0]), TREE_SIG_FIGS),
            "intercept": r(float(baseline.intercept_[0]), TREE_SIG_FIGS),
        },
        "blend_weight": 0.9,
        "method_priors": method_priors,
        "feature_cols": [f"{c}_diff" for c in FEATURE_COLS],
        "alignment_cols": ALIGNMENT_COLS,
    }
    payload["fighters"], flag_codes = export_fighters()
    payload["flags"] = _flags_payload(flag_codes)
    payload["upcoming_card"] = _upcoming_card_payload()

    out_path = WEB_DIR / "model_data.json"
    with open(out_path, "w") as f:
        json.dump(payload, f, separators=(",", ":"))

    size_mb = out_path.stat().st_size / 1e6
    print(f"wrote {out_path} ({size_mb:.2f} MB)")
    print(f"  win_model: {len(payload['win_model']['trees'])} trees")
    print(f"  method_model: {len(payload['method_model']['trees'])} trees, classes={method_classes}")
    print(f"  round_model: {len(payload['round_model']['trees'])} trees")
    print(f"  fighters: {len(payload['fighters']['rows'])} rows, {len(payload['fighters']['fields'])} fields each (active roster only)")
    print(f"  flags: {len(payload['flags'])} countries")
    if payload["upcoming_card"]:
        n_matched = sum(1 for b in payload["upcoming_card"]["bouts"] if b["idA"] and b["idB"])
        print(f"  upcoming_card: {payload['upcoming_card']['eventName']}, "
              f"{len(payload['upcoming_card']['bouts'])} bouts ({n_matched} predictable)")
    else:
        print("  upcoming_card: none (run `python -m src.data.scrape_upcoming_card` first)")


if __name__ == "__main__":
    main()
