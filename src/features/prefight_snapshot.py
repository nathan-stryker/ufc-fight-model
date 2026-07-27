"""
Turns scraped pre-UFC fight history (data/processed/prefight_history.csv,
see src/data/scrape_prefight_history.py) into the same "_entering" snapshot
shape predict.py and export_web_model.py already expect for a UFC-experienced
fighter -- used as a partial override of a debut fighter's DEBUT_DEFAULTS
when their regional/other-promotion record is known, instead of a flat
population-average guess.

Deliberately only covers fights_entering/win_pct_entering/finish_rate_entering/
current_streak_entering/layoff_days_entering -- NOT elo (a regional Elo
rating isn't on the same scale as a UFC-calibrated one, so a debut fighter
always starts at BASE_RATING for that specific feature regardless of how
experienced they are elsewhere) and NOT the strike/grappling rate stats
(sig_str_landed_per_min, td_avg_per15, etc.), since non-UFC promotions
generally don't publish round-by-round strike/grappling data the way
UFCStats does -- those stay at their existing NaN fallback.

Uses the EXACT same Bayesian-shrinkage formula and K_FIGHTS constant as
src.features.build_features.build_current_snapshot(), and expects the SAME
population priors dict that function already computes (see
population_priors.json, written by build_features.py) -- a debut fighter's
derived stats need to sit on the identical numeric scale as everyone else's
for the model to make sense of them; drifting the formula here even
slightly would be a real train/apply skew, not just a style inconsistency.

Shared by both predict.py (live CLI/website predictions) and
export_web_model.py (the exported website roster) so they can never
compute a different answer for the same debut fighter.
"""
import numpy as np
import pandas as pd

K_FIGHTS = 3.0  # must match src.features.build_features.K_FIGHTS


def _shrink_ratio(numerator, denominator, prior, k):
    return (numerator + prior * k) / (denominator + k)


def build_debut_snapshots(prefight_history: pd.DataFrame, priors: dict, as_of: pd.Timestamp) -> dict:
    """
    Returns {fighter_id: {fights_entering, win_pct_entering, finish_rate_entering,
    current_streak_entering, layoff_days_entering, last_fight_date}} for every
    fighter_id present in prefight_history. Empty dict if prefight_history is
    empty/None (e.g. no debut fighters this week, or the scraper hasn't run yet)
    -- callers should treat a missing fighter_id here exactly like today's
    "no data at all" debut case, not an error.
    """
    if prefight_history is None or prefight_history.empty:
        return {}

    snapshots = {}
    for fid, grp in prefight_history.groupby("fighter_id"):
        grp = grp.sort_values("event_date")
        fights_entering = len(grp)

        decided = grp[grp["result"].isin(["win", "loss"])]
        wins = int((decided["result"] == "win").sum())
        losses = int((decided["result"] == "loss").sum())
        win_pct = _shrink_ratio(wins, wins + losses, priors["win_pct"], K_FIGHTS)

        is_finish_win = (decided["result"] == "win") & decided["method_bucket"].isin(["ko", "sub"])
        finishes = int(is_finish_win.sum())
        finish_rate = _shrink_ratio(finishes, wins, priors["finish_rate"], K_FIGHTS)

        # Same signed-streak logic as build_features.py's _streak/_streak_inclusive:
        # only win/loss rows move the streak, anything else (already excluded
        # via `decided` here) would pass through unchanged.
        streak_sign, streak_len = 0, 0
        for result in decided["result"]:
            if result == "win":
                streak_len = streak_len + 1 if streak_sign >= 0 else 1
                streak_sign = 1
            else:
                streak_len = streak_len + 1 if streak_sign <= 0 else 1
                streak_sign = -1
        current_streak = streak_sign * streak_len

        last_fight_date = grp["event_date"].max()
        layoff_days = (as_of - pd.Timestamp(last_fight_date)).days if pd.notna(last_fight_date) else np.nan

        snapshots[fid] = {
            "fights_entering": fights_entering,
            "win_pct_entering": float(win_pct),
            "finish_rate_entering": float(finish_rate),
            "current_streak_entering": int(current_streak),
            "layoff_days_entering": layoff_days,
            "last_fight_date": last_fight_date,
        }
    return snapshots
