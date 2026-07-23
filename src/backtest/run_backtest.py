"""
The actual profitability test: compare the model's leakage-free walk-forward
win probabilities (src/backtest/walk_forward.py) against real historical
sportsbook odds (src/backtest/match_odds.py), and simulate betting on the
divergence.

Two separate questions, both reported:
  1. Calibration/skill: is the model's probability a BETTER estimate of the
     true win probability than the market's own (vig-free) implied
     probability? (Brier score, log-loss, head-to-head "who called it
     better" rate.) This is the real test of whether there's a signal here
     at all, independent of any staking strategy.
  2. Profitability: if you'd bet only when the model disagreed with the
     market by more than some margin, using flat and fractional-Kelly
     staking, what would your ROI actually have been -- across various edge
     thresholds, since a real edge should show up more strongly (and with
     fewer, more selective bets) as the threshold rises, not vanish.

Run: python -m src.backtest.run_backtest
Writes: data/processed/backtest_report.csv (per-fight merged table)
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

KELLY_FRACTION = 0.25
EDGE_THRESHOLDS = [0.0, 0.02, 0.05, 0.08, 0.12]


def american_from_decimal(dec_odds):
    return np.where(dec_odds >= 2.0, (dec_odds - 1) * 100, -100 / (dec_odds - 1))


def load_merged():
    odds = pd.read_csv(PROCESSED_DIR / "fights_with_odds.csv", parse_dates=["event_date"])
    preds = pd.read_csv(PROCESSED_DIR / "backtest_predictions.csv")

    fav_preds = preds.rename(columns={"own_fighter_id": "favourite_id", "sym_prob": "model_prob_favourite"})
    merged = odds.merge(
        fav_preds[["fight_id", "favourite_id", "model_prob_favourite", "fold_year"]],
        on=["fight_id", "favourite_id"],
        how="inner",
    )

    # Vig-free (de-overrounded) market implied probability.
    raw_fav = 1.0 / merged["favourite_odds"]
    raw_dog = 1.0 / merged["underdog_odds"]
    overround = raw_fav + raw_dog
    merged["market_prob_favourite"] = raw_fav / overround
    merged["overround"] = overround - 1.0  # the book's edge, informational

    merged["model_prob_underdog"] = 1.0 - merged["model_prob_favourite"]
    merged["market_prob_underdog"] = 1.0 - merged["market_prob_favourite"]
    merged["edge_favourite"] = merged["model_prob_favourite"] - merged["market_prob_favourite"]
    merged["edge_underdog"] = merged["model_prob_underdog"] - merged["market_prob_underdog"]
    merged["favourite_won"] = merged["favourite_won"].astype(bool)

    bad = ~np.isfinite(merged["favourite_odds"]) | ~np.isfinite(merged["underdog_odds"])
    if bad.any():
        print(f"Dropping {bad.sum()} rows with non-finite odds (source data issue, e.g. inf placeholders)")
        merged = merged[~bad].copy()
    return merged


def report_calibration(df):
    print("=" * 70)
    print("1. CALIBRATION / SKILL -- model vs. vig-free market, all matched fights")
    print("=" * 70)
    y = df["favourite_won"].astype(int)
    model_p = df["model_prob_favourite"].clip(1e-6, 1 - 1e-6)
    market_p = df["market_prob_favourite"].clip(1e-6, 1 - 1e-6)

    print(f"n = {len(df)} fights, {df['fold_year'].min()}-{df['fold_year'].max()}\n")
    print(f"{'':20s} {'Brier':>10s} {'LogLoss':>10s} {'Acc @0.5':>10s} {'AUC':>10s}")
    for name, p in [("Model", model_p), ("Vig-free market", market_p)]:
        brier = brier_score_loss(y, p)
        ll = log_loss(y, p)
        acc = ((p >= 0.5).astype(int) == y).mean()
        auc = roc_auc_score(y, p)
        print(f"{name:20s} {brier:10.4f} {ll:10.4f} {acc:10.3f} {auc:10.3f}")
    print(
        "\n(AUC only measures rank-ordering -- which side a probability favors --"
        "\n and is unaffected by a uniform over/under-confidence bias, unlike Brier/LogLoss.)"
    )

    print(f"\nMean predicted probability -- model: {model_p.mean():.3f}  market: {market_p.mean():.3f}  actual favourite win rate: {y.mean():.3f}")
    frac_pos, mean_pred = calibration_curve(y, model_p, n_bins=8, strategy="quantile")
    print("\nModel calibration (quantile-binned, this odds-matched subset only):")
    for mp, fp in zip(mean_pred, frac_pos):
        flag = "  <-- underconfident" if fp - mp > 0.05 else ""
        print(f"  pred={mp:.3f}  actual={fp:.3f}{flag}")

    # Head-to-head: for each fight, whose probability was closer to the actual outcome?
    model_err = (y - model_p).abs()
    market_err = (y - market_p).abs()
    model_closer = (model_err < market_err).mean()
    market_closer = (market_err < model_err).mean()
    tie = (model_err == market_err).mean()
    print(f"\nHead-to-head (closer to actual 0/1 outcome per fight):")
    print(f"  model closer:  {model_closer:.1%}")
    print(f"  market closer: {market_closer:.1%}")
    print(f"  tie:           {tie:.1%}")

    print(f"\nAverage bookmaker overround (vig): {df['overround'].mean():.3%}")


def simulate_betting(df):
    print("\n" + "=" * 70)
    print("2. BETTING SIMULATION -- flat stake & fractional Kelly by edge threshold")
    print("=" * 70)

    rows = []
    for thresh in EDGE_THRESHOLDS:
        bet_fav = df["edge_favourite"] > thresh
        bet_dog = df["edge_underdog"] > thresh
        # A fight where both look +EV is impossible once de-vigged correctly outside
        # of noise; if it happens, skip (ambiguous which side the model actually favors).
        both = bet_fav & bet_dog
        bet_fav = bet_fav & ~both
        bet_dog = bet_dog & ~both

        bets = []
        for side, mask, odds_col, won_col, p_col in [
            ("favourite", bet_fav, "favourite_odds", "favourite_won", "model_prob_favourite"),
            ("underdog", bet_dog, "underdog_odds", "favourite_won", "model_prob_underdog"),
        ]:
            sub = df[mask]
            if len(sub) == 0:
                continue
            odds = sub[odds_col].to_numpy()
            p = sub[p_col].to_numpy()
            won = sub[won_col].to_numpy() if side == "favourite" else ~sub[won_col].to_numpy()

            b = odds - 1.0  # net decimal payout per unit
            kelly_full = np.clip((p * (b + 1) - 1) / b, 0, 1)
            kelly_stake = KELLY_FRACTION * kelly_full

            flat_profit = np.where(won, b, -1.0)
            kelly_profit = np.where(won, kelly_stake * b, -kelly_stake)

            bets.append(pd.DataFrame({
                "side": side, "won": won, "odds": odds, "flat_profit": flat_profit,
                "kelly_stake": kelly_stake, "kelly_profit": kelly_profit,
            }))

        if not bets:
            rows.append({"edge_threshold": thresh, "n_bets": 0})
            continue
        allbets = pd.concat(bets, ignore_index=True)
        n = len(allbets)
        flat_roi = allbets["flat_profit"].sum() / n
        kelly_staked = allbets["kelly_stake"].sum()
        kelly_roi = allbets["kelly_profit"].sum() / kelly_staked if kelly_staked > 0 else float("nan")
        rows.append({
            "edge_threshold": thresh,
            "n_bets": n,
            "win_rate": allbets["won"].mean(),
            "flat_total_profit_units": allbets["flat_profit"].sum(),
            "flat_roi_per_bet": flat_roi,
            "kelly_total_staked_units": kelly_staked,
            "kelly_total_profit_units": allbets["kelly_profit"].sum(),
            "kelly_roi": kelly_roi,
        })

    summary = pd.DataFrame(rows)
    with pd.option_context("display.float_format", "{:.4f}".format):
        print(summary.to_string(index=False))
    return summary


def by_year(df):
    print("\n" + "=" * 70)
    print("3. BY YEAR -- edge_favourite mean, calibration by fold")
    print("=" * 70)
    y = df["favourite_won"].astype(int)
    g = df.groupby("fold_year")
    yearly = pd.DataFrame({
        "n_fights": g.size(),
        "model_brier": g.apply(lambda x: brier_score_loss(x["favourite_won"].astype(int), x["model_prob_favourite"].clip(1e-6, 1 - 1e-6))),
        "market_brier": g.apply(lambda x: brier_score_loss(x["favourite_won"].astype(int), x["market_prob_favourite"].clip(1e-6, 1 - 1e-6))),
        "mean_edge_favourite": g["edge_favourite"].mean(),
    })
    print(yearly.to_string())


def main():
    df = load_merged()
    df.to_csv(PROCESSED_DIR / "backtest_report.csv", index=False)
    report_calibration(df)
    simulate_betting(df)
    by_year(df)
    print(f"\nWrote per-fight merged table -> {PROCESSED_DIR / 'backtest_report.csv'} ({len(df)} rows)")


if __name__ == "__main__":
    main()
