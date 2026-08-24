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
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.data.scrape_nationality import ACTIVE_WINDOW_MONTHS
from src.features.build_features import FEATURE_COLS
from src.features.method_features import ALIGNMENT_COLS, METHODS
from src.features.prefight_snapshot import build_debut_snapshots

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

    # Real pre-UFC record for debut fighters (see src.data.scrape_prefight_history
    # / src.features.prefight_snapshot) -- overrides ONLY the experience/record
    # fields (fights_entering, win_pct_entering, finish_rate_entering,
    # current_streak_entering, last_fight_epoch_days) for a fighter whose "elo"
    # is still null (i.e. still a genuine UFC debut, no fighter_snapshot.csv
    # row). elo itself and the strike/grappling rate fields are deliberately
    # left untouched -- see that module's docstring for why. Degrades to a
    # no-op if the scraper hasn't run yet (prefight_history.csv missing) or
    # this fighter has no pre-UFC record on file, same as before this existed.
    prefight_history_path = PROCESSED_DIR / "prefight_history.csv"
    priors_path = PROCESSED_DIR / "population_priors.json"
    if prefight_history_path.exists() and priors_path.exists():
        prefight_history = pd.read_csv(prefight_history_path, parse_dates=["event_date"])
        with open(priors_path) as f:
            population_priors = json.load(f)
        debut_snapshots = build_debut_snapshots(prefight_history, population_priors, pd.Timestamp(datetime.now().date()))
        for fid, snap in debut_snapshots.items():
            mask = (df["fighter_id"] == fid) & df["elo"].isna()
            if not mask.any():
                continue
            df.loc[mask, "fights_entering"] = snap["fights_entering"]
            df.loc[mask, "win_pct_entering"] = snap["win_pct_entering"]
            df.loc[mask, "finish_rate_entering"] = snap["finish_rate_entering"]
            df.loc[mask, "current_streak_entering"] = snap["current_streak_entering"]
            if pd.notna(snap["last_fight_date"]):
                df.loc[mask, "last_fight_epoch_days"] = (pd.Timestamp(snap["last_fight_date"]) - epoch).days

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
            "isTitleFight": bool(row["is_title_fight"]) if pd.notna(row.get("is_title_fight")) else False,
            "rankA": row["rank_a"] if pd.notna(row.get("rank_a")) else None,
            "rankB": row["rank_b"] if pd.notna(row.get("rank_b")) else None,
        })
    return {
        "eventName": first["event_name"],
        "eventDate": first["event_date"],
        "eventLocation": first["event_location"],
        "bouts": bouts,
    }


def _recent_results_payload(upcoming_card_payload, n=5):
    """
    Last up-to-`n` UFC fight results per fighter appearing on the upcoming
    card (for the home page's hoverable W/L form badges) -- scoped to just
    those fighters for now rather than the whole active roster, matching
    where this is actually used; extend the scope here if this ever gets
    added to the main predictor's fighter cards too.

    All derived from fights.csv, already sitting in our own processed data
    -- no new scrape needed. winner_id is NaN for draws/no-contests (both
    already flagged by their own boolean columns), so those are checked
    first rather than falling through to a same-as-loss "not a win" default.
    """
    if not upcoming_card_payload:
        return {}
    fighter_ids = {
        fid
        for b in upcoming_card_payload["bouts"]
        for fid in (b["idA"], b["idB"])
        if fid
    }
    if not fighter_ids:
        return {}

    fights = pd.read_csv(PROCESSED_DIR / "fights.csv")
    fights = fights.sort_values("event_date", ascending=False)

    results = {}
    for fid in fighter_ids:
        mine = fights[(fights["fighter_1_id"] == fid) | (fights["fighter_2_id"] == fid)].head(n)
        rows = []
        for _, r in mine.iterrows():
            is_fighter_1 = r["fighter_1_id"] == fid
            opponent = r["fighter_2_name"] if is_fighter_1 else r["fighter_1_name"]
            if r["is_no_contest"]:
                outcome = "NC"
            elif r["is_draw"]:
                outcome = "D"
            elif pd.notna(r["winner_id"]) and r["winner_id"] == fid:
                outcome = "W"
            else:
                outcome = "L"
            rows.append({
                "result": outcome,
                "opponent": opponent,
                "method": r["method"] if pd.notna(r["method"]) else None,
                "round": int(r["round"]) if pd.notna(r["round"]) else None,
            })
        # Always set the key, even to an empty list -- distinguishes a
        # genuine "we checked, this fighter has zero recorded UFC fights"
        # (shown as "UFC Debut" on the site) from a fighter this payload
        # never looked up at all (key absent, which the frontend treats
        # differently: no badges AND no debut label).
        results[fid] = rows
    return results


def _prefight_records_payload(upcoming_card_payload):
    """
    Pre-UFC fight history for debut fighters on the upcoming card (see
    src.data.scrape_prefight_history / prefight_snapshot.py, which already
    turns this same file into shrunk numeric features for the model --
    this is the human-readable version of the same data, for the "Meet the
    Debut Fighters" bio cards). Scoped to just upcoming-card fighters, same
    convention as _recent_results_payload.

    Only debut fighters have any rows in prefight_history.csv at all (see
    scrape_prefight_history.py's get_debut_fighters()), so no separate
    elo-is-null check is needed here the way export_fighters() needs one --
    a fighter_id simply not appearing in this dict means either they're not
    a debut fighter, or we looked and found no pre-UFC record on file
    (same "omit, don't guess" convention as recent_results).
    """
    if not upcoming_card_payload:
        return {}
    path = PROCESSED_DIR / "prefight_history.csv"
    if not path.exists():
        return {}
    history = pd.read_csv(path, parse_dates=["event_date"])
    if history.empty:
        return {}

    fighter_ids = {
        fid
        for b in upcoming_card_payload["bouts"]
        for fid in (b["idA"], b["idB"])
        if fid
    }

    records = {}
    for fid, grp in history[history["fighter_id"].isin(fighter_ids)].groupby("fighter_id"):
        grp = grp.sort_values("event_date", ascending=False)
        decided = grp[grp["result"].isin(["win", "loss"])]
        fights = []
        for _, row in grp.iterrows():
            fights.append({
                "opponent": row["opponent_name"] if pd.notna(row["opponent_name"]) else None,
                "event": row["event"] if pd.notna(row["event"]) else None,
                "date": row["event_date"].strftime("%Y-%m-%d") if pd.notna(row["event_date"]) else None,
                "result": row["result"],
                "method": row["method_raw"] if pd.notna(row["method_raw"]) else None,
                "round": int(row["round"]) if pd.notna(row["round"]) else None,
            })
        records[fid] = {
            "wins": int((decided["result"] == "win").sum()),
            "losses": int((decided["result"] == "loss").sum()),
            "fights": fights,
        }
    return records


def _fight_stats(round_stats, fight_id, id_a, id_b):
    """
    Full per-fighter fight-level stat totals, summed across every round in
    round_stats.csv for one fight -- feeds the "Last Week's Results" page's
    strike-map panel: two body-diagram avatars (colored by strikes each
    fighter ABSORBED, i.e. the OTHER corner's landed total -- round_stats.csv
    only ever records what a fighter landed, never a separate "absorbed"
    column) plus a fuller middle stat comparison (sig. strikes by target,
    takedowns, control time, sub attempts, knockdowns) using each fighter's
    own LANDED totals.

    Returns None (not zeros) if this fight has no round_stats.csv rows at
    all, so the frontend can distinguish "genuinely a scoreless round"
    (impossible) from "we don't have detailed stats for this fight yet" --
    same "omit, don't guess" rule as the rest of this payload.
    """
    mine = round_stats[round_stats["fight_id"] == fight_id]
    if mine.empty:
        return None

    def totals(fighter_id):
        rows = mine[mine["fighter_id"] == fighter_id]
        return {
            "sigStrLanded": int(rows["sig_str_landed"].sum()),
            "sigStrAttempted": int(rows["sig_str_attempted"].sum()),
            "headLanded": int(rows["head_landed"].sum()),
            "headAttempted": int(rows["head_attempted"].sum()),
            "bodyLanded": int(rows["body_landed"].sum()),
            "bodyAttempted": int(rows["body_attempted"].sum()),
            "legLanded": int(rows["leg_landed"].sum()),
            "legAttempted": int(rows["leg_attempted"].sum()),
            "tdLanded": int(rows["td_landed"].sum()),
            "tdAttempted": int(rows["td_attempted"].sum()),
            "subAtt": int(rows["sub_att"].sum()),
            "kd": int(rows["kd"].sum()),
            "ctrlSec": int(rows["ctrl_sec"].sum()),
        }

    totals_a, totals_b = totals(id_a), totals(id_b)
    # Both empty means this fight_id matched but neither corner's id
    # appears in round_stats.csv (shouldn't happen if fights.csv and
    # round_stats.csv come from the same source, but don't guess if it does).
    if not any(totals_a.values()) and not any(totals_b.values()):
        return None
    return {"a": totals_a, "b": totals_b}


def _backfill_missing_stats(existing_results):
    """
    A cached last_results snapshot (see the "keep existing" fallback in
    main()) can predate round_stats.csv catching up with that event --
    found for real 2026-07-27: the event's own bout results/outcomes were
    already cached correctly, but every bout was missing strikes/stats
    because the historical mirror hadn't yet published round-by-round data
    when that snapshot was FIRST computed. Rather than staying permanently
    stats-less until the whole event eventually rotates out of view, retry
    computing _fight_stats() for any bout still missing it, using
    round_stats.csv/fights.csv AS THEY ARE RIGHT NOW (which may well have
    caught up since) -- matched by the bout's own idA/idB, same join
    fights.csv already uses elsewhere, no dependency on last_card.csv at
    all. No-ops instantly (one dict-key check per bout) once every bout
    already has stats, so this is safe to run on every single export.
    """
    if not existing_results or not existing_results.get("bouts"):
        return existing_results, 0
    if all("stats" in b for b in existing_results["bouts"]):
        return existing_results, 0

    fights = pd.read_csv(PROCESSED_DIR / "fights.csv")
    round_stats = pd.read_csv(PROCESSED_DIR / "round_stats.csv")
    filled = 0
    for bout in existing_results["bouts"]:
        if "stats" in bout:
            continue
        id_a, id_b = bout.get("idA"), bout.get("idB")
        if not id_a or not id_b:
            continue
        match = fights[
            ((fights["fighter_1_id"] == id_a) & (fights["fighter_2_id"] == id_b))
            | ((fights["fighter_1_id"] == id_b) & (fights["fighter_2_id"] == id_a))
        ]
        if match.empty:
            continue
        stats = _fight_stats(round_stats, match.iloc[0]["fight_id"], id_a, id_b)
        if not stats:
            continue
        bout["stats"] = stats
        bout["strikes"] = {
            "a": {"head": stats["b"]["headLanded"], "body": stats["b"]["bodyLanded"], "leg": stats["b"]["legLanded"]},
            "b": {"head": stats["a"]["headLanded"], "body": stats["a"]["bodyLanded"], "leg": stats["a"]["legLanded"]},
        }
        filled += 1
    return existing_results, filled


def _last_results_payload():
    """
    "Last week's card" plus its actual results -- entirely derived from
    data this project already collects, no separate results scraper.

    src/data/scrape_upcoming_card.py snapshots the CURRENT upcoming_card.csv
    to last_card.csv right before overwriting it with the next event's card,
    every time it runs. By the time this export step runs (later in the
    same weekly refresh, after fights.csv has already been rebuilt from the
    latest historical data -- see load_data.py), that snapshot's event has
    already happened, so its bouts should now have real results sitting in
    fights.csv. This just joins the two on the fighter-id pair. Per-bout
    strike/stat breakdowns (see _fight_stats()) come from the SAME
    round_stats.csv already built for training, from the SAME raw mirror
    data -- no separate scrape for that either.

    A bout that can't be matched (fights.csv's source hasn't picked up the
    event yet, a bout was scratched/postponed, or the original card scrape
    never resolved both fighter ids to begin with) is simply left out of
    the results list rather than shown as a guess -- same "omit, don't
    guess" philosophy as the rest of this scraping pipeline.

    Returning None here means "nothing confirmed YET" (the historical
    mirror commonly lags a real event by a day or more), not "there is
    genuinely nothing to show" -- see the fallback in export_all() that
    keeps the last known-good payload on disk instead of overwriting it
    with this None, so a same-day re-run (e.g. the daily news refresh,
    which calls this same export) can never blank out a page that was
    showing real results a moment ago.
    """
    path = PROCESSED_DIR / "last_card.csv"
    if not path.exists():
        return None
    last_card = pd.read_csv(path)
    if last_card.empty:
        return None

    fights = pd.read_csv(PROCESSED_DIR / "fights.csv")
    round_stats = pd.read_csv(PROCESSED_DIR / "round_stats.csv")

    bouts = []
    for _, row in last_card.sort_values("bout_order").iterrows():
        id_a, id_b = row.get("fighter_a_id"), row.get("fighter_b_id")
        if pd.isna(id_a) or pd.isna(id_b):
            continue
        match = fights[
            ((fights["fighter_1_id"] == id_a) & (fights["fighter_2_id"] == id_b))
            | ((fights["fighter_1_id"] == id_b) & (fights["fighter_2_id"] == id_a))
        ]
        if match.empty:
            continue
        fight = match.iloc[0]
        if fight["is_no_contest"]:
            outcome = "nc"
        elif fight["is_draw"]:
            outcome = "draw"
        elif pd.notna(fight["winner_id"]) and fight["winner_id"] == id_a:
            outcome = "a"
        elif pd.notna(fight["winner_id"]) and fight["winner_id"] == id_b:
            outcome = "b"
        else:
            continue
        bout = {
            "weightClass": row["weight_class"] if pd.notna(row["weight_class"]) else None,
            "nameA": row["fighter_a_name"], "idA": id_a,
            "nameB": row["fighter_b_name"], "idB": id_b,
            "tier": row["tier"] if pd.notna(row.get("tier")) else "prelim",
            "isTitleFight": bool(row["is_title_fight"]) if pd.notna(row.get("is_title_fight")) else False,
            "outcome": outcome,
            "method": fight["method"] if pd.notna(fight["method"]) else None,
            "round": int(fight["round"]) if pd.notna(fight["round"]) else None,
            "time": fight["time"] if pd.notna(fight["time"]) else None,
        }
        stats = _fight_stats(round_stats, fight["fight_id"], id_a, id_b)
        if stats:
            bout["stats"] = stats
            # Derived, not separately scraped: A's absorbed total for a zone
            # IS B's landed total for that same zone, and vice versa -- kept
            # as its own "strikes" key (rather than making the frontend
            # re-derive it) since the two body-diagram avatars need exactly
            # this shape and nothing else.
            bout["strikes"] = {
                "a": {"head": stats["b"]["headLanded"], "body": stats["b"]["bodyLanded"], "leg": stats["b"]["legLanded"]},
                "b": {"head": stats["a"]["headLanded"], "body": stats["a"]["bodyLanded"], "leg": stats["a"]["legLanded"]},
            }
        # What the model actually called BEFORE the fight happened (computed
        # at scrape time by scrape_upcoming_card.py's add_model_predictions(),
        # carried through the last_card.csv snapshot) -- a real prediction
        # made ahead of time, not a backtest. Older snapshots predating this
        # column just won't have it (row.get() returns None, not a KeyError),
        # so this degrades to no "model predicted" line for those bouts.
        pred_side = row.get("predicted_winner_side")
        pred_method = row.get("predicted_method")
        if pd.notna(pred_side) and pd.notna(pred_method):
            model_pick = {"side": pred_side, "method": pred_method}
            pred_round = row.get("predicted_round")
            if pd.notna(pred_round):
                model_pick["round"] = int(pred_round)
            bout["modelPick"] = model_pick
        bouts.append(bout)
    if not bouts:
        return None
    first = last_card.iloc[0]
    return {
        "eventName": first["event_name"],
        "eventDate": first["event_date"],
        "bouts": bouts,
    }


def _news_payload():
    """
    Reads the pre-scraped news cache (data/processed/news.csv, see
    src/data/scrape_news.py) -- NOT scraped over the network here, this is
    a build step. Degrades to no News tab at all if the file doesn't exist
    yet or the scrape found nothing, rather than failing the whole export.

    asOfDate is today (the export run), not anything from the scraped
    page -- the site shows "As of <asOfDate>" instead of ufc.com's own
    relative timestamps ("10 hours ago"), which would read as wrong by the
    time this only refreshes again next week.
    """
    path = PROCESSED_DIR / "news.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, encoding="utf-8")
    if df.empty:
        return None
    articles = []
    for _, row in df.iterrows():
        articles.append({
            "headline": row["headline"],
            "teaser": row["teaser"] if pd.notna(row["teaser"]) else None,
            "tag": row["tag"] if pd.notna(row["tag"]) else None,
            "imageUrl": row["image_url"] if pd.notna(row["image_url"]) else None,
            "url": row["url"],
        })
    return {
        "asOfDate": datetime.now().strftime("%Y-%m-%d"),
        "articles": articles,
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
        # Only drop the ROOT element's id ("flag-icons-xx", every file's own
        # unique prefix -- avoids a duplicate DOM id if a country repeats
        # across two badges on the same page). A blanket `id="..."` strip
        # here is a real bug, not just unused cruft: ~1 in 4 flags (China,
        # US, and 19 others) define inner shapes once in <defs>/<marker> and
        # repeat them via <use xlink:href="#id">/marker-mid="url(#id)" --
        # stripping THAT id leaves the reference pointing at nothing, so the
        # shape silently doesn't render at all. Hit this directly: China's
        # 5 stars (id="cn-a", referenced 5x) vanished, leaving just the red
        # field -- reported as the flag "just appears to be red, nothing
        # else". Anchored to the specific "flag-icons-" prefix (confirmed
        # against all 84 cached files) so inner ids are never touched.
        svg = re.sub(r'\s+id="flag-icons-[^"]*"', "", svg)
        # flag-icons ships every flag as a 4:3 viewBox with no preserveAspectRatio,
        # which defaults to "xMidYMid meet" -- the CSS (.fc-badge svg etc.) sets
        # object-fit: cover, but that property has no effect on an inline <svg>
        # (only on replaced elements like <img>), so every badge whose box isn't
        # EXACTLY 4:3 was letterboxing: thin gaps on the sides showing the badge's
        # background-color instead of flag. Barely visible on flags with light
        # colors at the edge, glaring on a solid edge-to-edge color like China's
        # red field (reported directly against China's flag looking "off").
        # "slice" makes the SVG actually crop-to-fill like CSS cover does, so this
        # is a real fix for every flag, not just China's -- China's was just the
        # most visually obvious case.
        svg = re.sub(r"^<svg ", '<svg preserveAspectRatio="xMidYMid slice" ', svg, count=1)
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
    payload["recent_results"] = _recent_results_payload(payload["upcoming_card"])
    payload["prefight_records"] = _prefight_records_payload(payload["upcoming_card"])
    payload["news"] = _news_payload()
    payload["last_results"] = _last_results_payload()
    # A None here means "not confirmed yet" (see _last_results_payload's
    # docstring) -- e.g. this same export gets re-run by the daily news
    # refresh, and the historical mirror can lag a real event by a day or
    # more. Keep whatever was already on disk from the last run that DID
    # find something, rather than regressing a page that was showing real
    # results to blank just because TODAY'S run came up empty. Resolves
    # itself automatically the next time a fresh computation succeeds.
    if payload["last_results"] is None:
        existing_results_path = WEB_DIR / "last_results_data.json"
        if existing_results_path.exists():
            try:
                with open(existing_results_path) as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = None
            if existing:
                existing, n_filled = _backfill_missing_stats(existing)
                payload["last_results"] = existing
                msg = f"  last_results: fresh computation found nothing yet, kept existing '{existing['eventName']}'"
                if n_filled:
                    msg += f" (backfilled strikes/stats for {n_filled} bout(s) now that round_stats.csv has them)"
                print(msg)

    out_path = WEB_DIR / "model_data.json"
    with open(out_path, "w") as f:
        json.dump(payload, f, separators=(",", ":"))

    # Also written standalone (not just embedded in model_data.json) so the
    # separate news.html/results.html pages can each embed just their own
    # small payload instead of the full multi-MB model_data.json they have
    # no other use for.
    news_out_path = WEB_DIR / "news_data.json"
    with open(news_out_path, "w") as f:
        json.dump(payload["news"], f, separators=(",", ":"))

    results_out_path = WEB_DIR / "last_results_data.json"
    with open(results_out_path, "w") as f:
        json.dump(payload["last_results"], f, separators=(",", ":"))

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
        n_with_history = sum(1 for v in payload["recent_results"].values() if v)
        print(f"  recent_results: {n_with_history} upcoming-card fighters with fight history")
    else:
        print("  upcoming_card: none (run `python -m src.data.scrape_upcoming_card` first)")
    if payload["news"]:
        print(f"  news: {len(payload['news']['articles'])} articles (as of {payload['news']['asOfDate']})")
    else:
        print("  news: none (run `python -m src.data.scrape_news` first)")
    if payload["last_results"]:
        print(f"  last_results: {payload['last_results']['eventName']}, "
              f"{len(payload['last_results']['bouts'])} results matched")
    else:
        print("  last_results: none (no last_card.csv snapshot yet, or none of its bouts matched fights.csv)")


if __name__ == "__main__":
    main()
