"""
Two-axis fighting style -- a STRIKING style and a GRAPPLING style -- derived
from each fighter's UFC career stats with plain, inspectable rules, instead of
one hand-picked word per fighter (user's revamp idea, 2026-10-05).

Every stat is turned into a percentile within the fighter's own division
(reference pool: fighters with >= MIN_FIGHTS UFC fights whose last fight was
2019 or later), because output and takedown rates differ a lot between
flyweight and heavyweight. Rules are applied in a fixed order; the first that
fits wins. Fighters with fewer than MIN_FIGHTS UFC fights get no axis labels
(too little data) -- the site falls back to their single hand/Claude label.

Display only: not a model feature.
"""
import numpy as np
import pandas as pd

MIN_FIGHTS = 3
REFERENCE_SINCE = "2019-01-01"
FINISH_KO = {"KO/TKO", "TKO - Doctor's Stoppage"}

STRIKING = ["Power", "Pressure", "Volume", "Counter", "Technical", "Balanced", "Minimal"]
GRAPPLING = ["Wrestler", "Submission", "Takedown Defense", "Balanced", "Minimal"]


def _career_totals(fights: pd.DataFrame, round_stats: pd.DataFrame) -> pd.DataFrame:
    from src.features.build_features import compute_fight_seconds
    fights = fights.copy()
    fights["fight_seconds"] = fights.apply(compute_fight_seconds, axis=1)
    cols = ["sig_str_landed", "sig_str_attempted", "td_landed", "td_attempted", "sub_att", "ctrl_sec", "kd",
            "distance_landed", "distance_attempted", "clinch_landed", "clinch_attempted"]
    per = round_stats.dropna(subset=["fighter_id"]).groupby(["fight_id", "fighter_id"], as_index=False)[cols].sum(min_count=1)
    opp = per.rename(columns={"fighter_id": "opp_id", **{c: f"opp_{c}" for c in cols}})
    both = per.merge(opp, on="fight_id")
    both = both[both.fighter_id != both.opp_id].merge(
        fights[["fight_id", "fight_seconds", "event_date", "weightclass", "winner_id", "method"]], on="fight_id")
    both["ko_win"] = (both.winner_id == both.fighter_id) & both.method.isin(FINISH_KO)
    both["sub_win"] = (both.winner_id == both.fighter_id) & (both.method == "Submission")
    g = both.sort_values("event_date").groupby("fighter_id")
    t = g[cols + [f"opp_{c}" for c in cols] + ["fight_seconds", "ko_win", "sub_win"]].sum()
    t["n_fights"] = g.size()
    t["last_fight"] = g["event_date"].max()
    t["division"] = g["weightclass"].last()
    m = t.fight_seconds / 60
    # Striking uses STANDING strikes only (distance + clinch): ground-and-pound
    # inflates a wrestler's "output" (Kayla Harrison read as a Volume striker).
    st_l = t.distance_landed + t.clinch_landed
    st_a = t.distance_attempted + t.clinch_attempted
    o_st_l = t.opp_distance_landed + t.opp_clinch_landed
    o_st_a = t.opp_distance_attempted + t.opp_clinch_attempted
    out = pd.DataFrame({
        "n_fights": t.n_fights, "last_fight": t.last_fight, "division": t.division,
        "slpm": st_l / m, "sapm": o_st_l / m,
        "str_acc": st_l / st_a, "str_def": 1 - o_st_l / o_st_a,
        "kd15": t.kd / m * 15, "ko_rate": t.ko_win / t.n_fights,
        "td15": t.td_landed / m * 15, "td_def": 1 - t.opp_td_landed / t.opp_td_attempted, "opp_td_att": t.opp_td_attempted,
        "sub15": t.sub_att / m * 15, "sub_rate": t.sub_win / t.n_fights, "ctrl": t.ctrl_sec / t.fight_seconds,
    })
    return out.replace([np.inf, -np.inf], np.nan)


PCT_COLS = ["slpm", "sapm", "str_acc", "str_def", "kd15", "ko_rate", "td15", "td_def", "sub15", "sub_rate", "ctrl"]


def _percentiles(t: pd.DataFrame) -> pd.DataFrame:
    """Each fighter's percentile vs the reference pool of their division (or all
    divisions if the division's pool is small)."""
    ref = t[(t.n_fights >= MIN_FIGHTS) & (t.last_fight >= REFERENCE_SINCE)]
    out = pd.DataFrame(index=t.index)
    for c in PCT_COLS:
        vals = pd.Series(np.nan, index=t.index)
        for div, grp in t.groupby("division"):
            pool = ref[ref.division == div][c].dropna()
            if len(pool) < 25:
                pool = ref[c].dropna()
            srt = np.sort(pool.values)
            vals.loc[grp.index] = np.searchsorted(srt, grp[c].values, side="right") / len(srt)
        vals[t[c].isna()] = np.nan
        out[c] = vals
    return out


def striking_style(p, r):
    # Order matters: output/defense shape first, then knockout power, so a
    # high-volume finisher (Holloway) reads as volume/pressure, not "Power".
    ko_wins = r.ko_rate * r.n_fights
    if p.ko_rate >= .9 and p.kd15 >= .8 and ko_wins >= 3:
        return "Power"             # elite finishers (Pereira, Aspinall) even with high output
    if p.slpm >= .6 and p.sapm >= .75:
        return "Pressure"          # high output both ways -- trades to land
    if p.slpm >= .75:
        return "Volume"
    if p.ko_rate >= .8 and p.kd15 >= .7 and ko_wins >= 2:
        return "Power"
    efficient = p.str_acc >= .75 and p.str_def >= .6
    if p.slpm <= .3 and p.td15 >= .7 and not efficient:
        return "Minimal"           # striking is just a way into the takedown
    # (low-output but very accurate and hard to hit -- Shevchenko, Makhachev --
    # falls through to Counter instead)
    if p.str_def >= .65 and p.sapm <= .35 and p.slpm <= .6:
        return "Counter"           # hard to hit, doesn't need volume
    if p.str_acc >= .6 and p.str_def >= .55:
        return "Technical"
    return "Balanced"


def grappling_style(p, r):
    wr = max(p.td15, p.ctrl if p.td15 >= .5 else 0)
    sb = max(p.sub15, p.sub_rate if r.sub_rate * r.n_fights >= 2 else 0)
    if wr >= .7 or sb >= .75:
        return "Wrestler" if wr >= sb else "Submission"
    if p.td_def >= .7 and p.td15 <= .4 and r.opp_td_att >= 5:
        return "Takedown Defense"
    if p.td15 <= .25 and p.sub15 <= .4 and p.ctrl <= .35:
        return "Minimal"
    return "Balanced"


def compute_axes(fights: pd.DataFrame, round_stats: pd.DataFrame) -> pd.DataFrame:
    t = _career_totals(fights, round_stats)
    p = _percentiles(t)
    rows = []
    for fid in t.index:
        r, q = t.loc[fid], p.loc[fid]
        if r.n_fights < MIN_FIGHTS:
            rows.append((fid, None, None))
            continue
        rows.append((fid, striking_style(q, r), grappling_style(q, r)))
    return pd.DataFrame(rows, columns=["fighter_id", "strike_style", "grapple_style"]).set_index("fighter_id")
