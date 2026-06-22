"""
Prepare Nifty 500 historical data for triage IC testing.

Fetches OHLCV from Fyers API, caches as parquet for reuse.
Uses headless TOTP auth (no interactive prompts).

Usage:
  uv run python -m strategies.momentum.research.prepare_data --date-from 2015-01-01 --date-to 2024-06-30
"""
import argparse
from datetime import date, datetime
import logging
from pathlib import Path

import pandas as pd

from core.brokers.fyers.client import FyersClient
from core.research.data import fetch_daily

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Nifty 500 constituents (point-in-time list as of 2024-06-01)
# In production, fetch from NSE API; for now use a representative set
NIFTY_500 = [
    # NIFTY 50 (core)
    "NSE:RELIANCE-EQ", "NSE:TCS-EQ", "NSE:INFY-EQ", "NSE:HDFCBANK-EQ", "NSE:ICICIBANK-EQ",
    "NSE:HINDUNILVR-EQ", "NSE:SBIN-EQ", "NSE:BHARTIARTL-EQ", "NSE:KOTAKBANK-EQ", "NSE:ITC-EQ",
    "NSE:LT-EQ", "NSE:AXISBANK-EQ", "NSE:BAJFINANCE-EQ", "NSE:ASIANPAINT-EQ", "NSE:MARUTI-EQ",
    "NSE:WIPRO-EQ", "NSE:HCLTECH-EQ", "NSE:SUNPHARMA-EQ", "NSE:TITAN-EQ", "NSE:ULTRACEMCO-EQ",
    "NSE:TATAMOTORS-EQ", "NSE:TATASTEEL-EQ", "NSE:JSWSTEEL-EQ", "NSE:ADANIENT-EQ", "NSE:ADANIPORTS-EQ",
    "NSE:NTPC-EQ", "NSE:POWERGRID-EQ", "NSE:ONGC-EQ", "NSE:TECHM-EQ", "NSE:BAJAJFINSV-EQ",
    "NSE:HEROMOTOCO-EQ", "NSE:INDIGO-EQ", "NSE:GAIL-EQ", "NSE:IOC-EQ", "NSE:BPCL-EQ",
    "NSE:M&M-EQ", "NSE:BOSCHIND-EQ", "NSE:DRREDDY-EQ", "NSE:SUNTV-EQ", "NSE:SHREECEM-EQ",
    "NSE:DLF-EQ", "NSE:HINDALCO-EQ", "NSE:COALINDIA-EQ", "NSE:VEDL-EQ", "NSE:NMDC-EQ",
    "NSE:TATAPOWER-EQ", "NSE:EICHERMOT-EQ", "NSE:BAJAJHLDNG-EQ", "NSE:BRITANNIA-EQ", "NSE:NESTLEIND-EQ",
    
    # Mid-cap extension (sample)
    "NSE:BANKBARODA-EQ", "NSE:PNB-EQ", "NSE:FEDERALBNK-EQ", "NSE:INDUSINDBK-EQ", "NSE:YESBANK-EQ",
    "NSE:IDEA-EQ", "NSE:VODAFONE-EQ", "NSE:JSWSTEEL-EQ", "NSE:SAIL-EQ", "NSE:NATIONALAL-EQ",
    "NSE:BAJAJMOTOR-EQ", "NSE:TATA-EQ", "NSE:CEATLTD-EQ", "NSE:MRF-EQ", "NSE:GOODYEAR-EQ",
]

# Filter to those actually available on Fyers (will skip failures)
NIFTY_500_TEST = NIFTY_500[:50]  # Start with 50 for faster iteration


def prepare_data(
    date_from: date,
    date_to: date,
    n_symbols: int = 50,
    force_refetch: bool = False,
    client: FyersClient | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch and cache Nifty 500 OHLCV.
    
    Parameters
    ----------
    date_from : date
        Start date
    date_to : date
        End date
    n_symbols : int
        How many symbols to fetch (for testing, fetch all if > 500)
    force_refetch : bool
        If True, ignore cache and refetch from Fyers
    
    Returns
    -------
    dict[str, DataFrame]
        {symbol: daily_ohlcv_df} for all successfully fetched symbols
    """
    client = client or FyersClient()  # Uses headless TOTP by default
    
    symbols = NIFTY_500 if n_symbols > 500 else NIFTY_500_TEST[:n_symbols]
    universe_data = {}
    
    log.info(f"Preparing data for {len(symbols)} symbols, {date_from} to {date_to}")
    
    for i, sym in enumerate(symbols):
        try:
            print(f"  [{i+1:3d}/{len(symbols)}] {sym:20s} ... ", end="", flush=True)
            
            df = fetch_daily(client, sym, date_from, date_to, use_cache=not force_refetch)
            
            if len(df) > 60:  # Need at least 2 months of data
                universe_data[sym] = df
                print(f"✓ {len(df):3d} bars")
            else:
                print(f"✗ insufficient ({len(df):3d} bars)")
        
        except Exception as e:
            print(f"✗ {str(e)[:40]}")
    
    log.info(f"\n✅ Successfully fetched {len(universe_data)} symbols")
    return universe_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date-from", type=str, default="2015-01-01")
    parser.add_argument("--date-to", type=str, default="2024-06-30")
    parser.add_argument("--n-symbols", type=int, default=50, help="How many symbols to fetch")
    parser.add_argument("--force-refetch", action="store_true", help="Ignore cache, refetch from Fyers")
    args = parser.parse_args()
    
    date_from = datetime.strptime(args.date_from, "%Y-%m-%d").date()
    date_to = datetime.strptime(args.date_to, "%Y-%m-%d").date()
    
    data = prepare_data(date_from, date_to, args.n_symbols, args.force_refetch)
    print(f"\nReady: {len(data)} symbols cached")
