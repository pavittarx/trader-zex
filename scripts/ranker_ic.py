"""
scripts/ranker_ic.py

Measures the Information Coefficient (IC) of the StockRanker composite score
against forward returns, using walk-forward point-in-time ranking.

IC = Spearman rank correlation between composite_score and next-day return.
Mean IC > 0.05 with t-stat > 2 is the minimum bar for the ranker to have
predictive value.

Usage
-----
    # Requires Fyers credentials (.env + ~/.fyers_token.json)
    uv run python scripts/ranker_ic.py --symbols NSE:RELIANCE-EQ NSE:TCS-EQ NSE:INFY-EQ \\
        --date-from 2024-06-01 --date-to 2024-09-30

    # Use config.DEFAULT_SYMBOLS (default):
    uv run python scripts/ranker_ic.py --date-from 2024-06-01 --date-to 2024-09-30

Output
------
    IC time series (one value per trading day)
    Mean IC, std IC, t-statistic
    Verdict: informative / weak / no edge
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import config
from core.brokers.fyers.client import FyersClient
from core.operators.ranker import StockRanker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def trading_days(date_from: date, date_to: date, step: int = 5) -> list[date]:
    """Return a list of weekdays between date_from and date_to, sampled every `step` days."""
    days = []
    d = date_from
    while d <= date_to:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
        d += timedelta(days=step)
    return days


def fetch_forward_returns(
    client: FyersClient,
    symbols: list[str],
    dates: list[date],
) -> pd.DataFrame:
    """
    Fetch daily close prices for all symbols over the full date range,
    then compute next-day forward returns for each (symbol, date) pair.

    Returns a DataFrame with columns: date, symbol, fwd_return_1d
    """
    log.info("Fetching daily prices for %d symbols ...", len(symbols))
    date_from = min(dates) - timedelta(days=10)
    date_to = max(dates) + timedelta(days=10)

    rows = []
    for sym in symbols:
        try:
            df = client.get_history(sym, "D", date_from=date_from, date_to=date_to)
            if df.empty or len(df) < 2:
                continue
            df = df.sort_index()
            close = df["close"]
            fwd = close.shift(-1) / close - 1
            for d in dates:
                # Find the closest date at or before d
                mask = close.index.normalize() <= pd.Timestamp(d)
                if not mask.any():
                    continue
                idx = close.index[mask][-1]
                pos = close.index.get_loc(idx)
                if pos + 1 < len(close):
                    rows.append({
                        "date": d,
                        "symbol": sym,
                        "fwd_return_1d": float(fwd.iloc[pos]),
                    })
        except Exception as exc:
            log.debug("Forward return fetch failed for %s: %s", sym, exc)

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["date", "symbol", "fwd_return_1d"])


def compute_ic_series(
    client: FyersClient,
    symbols: list[str],
    dates: list[date],
    fwd_df: pd.DataFrame,
) -> pd.Series:
    """
    For each date in `dates`, compute scores point-in-time and correlate with
    next-day forward returns. Returns a Series of IC values indexed by date.
    """
    ranker = StockRanker(client, n_top=len(symbols))
    ic_values: dict[date, float] = {}

    for i, d in enumerate(dates, 1):
        log.info("[%d/%d] Computing scores as_of %s ...", i, len(dates), d)
        try:
            scores_df = ranker.compute_scores(symbols, as_of_date=d)
            if scores_df.empty:
                log.warning("  No scores for %s -- skipping", d)
                continue

            # Get forward returns for this date
            fwd_today = fwd_df[fwd_df["date"] == d][["symbol", "fwd_return_1d"]]
            if fwd_today.empty:
                continue

            merged = scores_df.merge(fwd_today, on="symbol", how="inner")
            if len(merged) < 5:
                log.warning("  Only %d symbols with both score and return -- skipping", len(merged))
                continue

            ic, _ = stats.spearmanr(merged["composite_score"], merged["fwd_return_1d"])
            ic_values[d] = ic
            log.info("  IC = %.4f (n=%d)", ic, len(merged))

        except Exception as exc:
            log.warning("  Score computation failed for %s: %s", d, exc)

    return pd.Series(ic_values, name="IC")


def print_report(ic: pd.Series) -> None:
    if ic.empty:
        print("\nNo IC values computed -- check data and credentials.")
        return

    mean_ic = ic.mean()
    std_ic = ic.std()
    n = len(ic)
    tstat = mean_ic / (std_ic / np.sqrt(n)) if std_ic > 0 else 0.0

    print(f"\n{'='*60}")
    print("  RANKER INFORMATION COEFFICIENT (IC) REPORT")
    print(f"{'='*60}")
    print(f"  Dates evaluated : {n}")
    print(f"  Mean IC         : {mean_ic:+.4f}")
    print(f"  Std IC          : {std_ic:.4f}")
    print(f"  t-statistic     : {tstat:+.2f}")
    print(f"  IC > 0 fraction : {(ic > 0).mean():.1%}")
    print()

    if abs(tstat) >= 2 and mean_ic > 0.05:
        verdict = "INFORMATIVE -- ranker score has detectable predictive value."
    elif abs(tstat) >= 2 and mean_ic > 0:
        verdict = "WEAK -- statistically significant but economically small IC."
    elif mean_ic > 0:
        verdict = "INCONCLUSIVE -- positive mean IC but not statistically significant."
    else:
        verdict = "NO EDGE -- ranker score does not predict forward returns."

    print(f"  Verdict: {verdict}")
    print()

    print("  IC time series:")
    for d, v in ic.items():
        bar = "=" * int(abs(v) * 50)
        sign = "+" if v >= 0 else "-"
        print(f"  {d}  {sign}{bar:<25}  {v:+.4f}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ranker IC walk-forward validation")
    parser.add_argument("--symbols", nargs="+", default=config.DEFAULT_SYMBOLS,
                        help="Fyers symbols to rank (default: config.DEFAULT_SYMBOLS)")
    parser.add_argument("--date-from", type=date.fromisoformat, required=True,
                        help="Start date YYYY-MM-DD")
    parser.add_argument("--date-to", type=date.fromisoformat,
                        default=date.today(), help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--step", type=int, default=5,
                        help="Sample every N trading days (default: 5 = weekly)")
    args = parser.parse_args()

    client = FyersClient()
    dates = trading_days(args.date_from, args.date_to, step=args.step)
    log.info("Evaluating IC over %d dates from %s to %s",
             len(dates), args.date_from, args.date_to)

    fwd_df = fetch_forward_returns(client, args.symbols, dates)
    if fwd_df.empty:
        print("Could not fetch forward returns -- check credentials.")
        sys.exit(1)

    ic = compute_ic_series(client, args.symbols, dates, fwd_df)
    print_report(ic)


if __name__ == "__main__":
    main()
