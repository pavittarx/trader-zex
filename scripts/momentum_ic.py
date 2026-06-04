"""Cross-sectional momentum (trend-following) edge test for NSE equities.

Edge hypothesis (see docs/MOMENTUM_THESIS.md): stocks that outperformed their
peers over the past ~12 months (skipping the most recent month) keep
outperforming next month, because investors underreact / anchor. Monthly
rebalance => LOW turnover, so cost is paid rarely (the repo's binding constraint).

This is the cheap Stage-1/2/3 screen, mirroring scripts/pead_event_ic.py:
  - 12-1 momentum  = return from t-252 to t-21 trading days (skip last month).
  - Monthly rebalance; hold to next rebalance.
  - Pooled cross-sectional Spearman IC(momentum, fwd return) + t-stat   <- edge.
  - Dollar-neutral L/S quintile spread (beta ~ 0): annualized ret / Sharpe / DD,
    net of turnover-based cost                                          <- pure premium.
  - Long-only top quintile vs equal-weight "market": alpha / beta       <- is it just beta?
  - Sub-period split (robust if it holds in BOTH halves).
  - Cost sensitivity at 1x / 1.5x / 2x.

--self-test runs the whole pipeline on synthetic panels (no market data): one
with a PLANTED momentum effect (expect IC>0, t>2) and one of pure NOISE
(expect IC~0). This proves the measurement code has power and does not
manufacture signal.
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import urllib.request
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
logging.disable(logging.WARNING)

LOOKBACK = 252   # ~12 months of trading days
SKIP = 21        # skip most recent ~1 month (controls for short-term reversal)
COST_RT_BPS = 30.0   # round-trip cost baseline (NSE large-cap, multi-day hold)


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def fetch_daily(client, sym, frm, to, chunk_days=360):
    """Daily close history in <=chunk_days windows (Fyers caps 1D at 366/req)."""
    parts, cur = [], frm
    while cur <= to:
        end = min(cur + timedelta(days=chunk_days - 1), to)
        try:
            df = client.get_history(sym, "D", date_from=cur, date_to=end)
            if not df.empty:
                parts.append(df)
        except Exception:
            pass
        cur = end + timedelta(days=1)
    if not parts:
        return pd.Series(dtype=float)
    allp = pd.concat(parts).sort_index()
    allp = allp[~allp.index.duplicated()]
    return allp["close"]


# --------------------------------------------------------------------------- #
# Alternative data source: public split-ADJUSTED NSE daily dataset on GitHub.
# Real NIFTY500 daily Adj Close, 2012-2021 (Yahoo-derived). Used when Fyers
# creds / a live data host are unreachable. Provenance is documented in the
# run output; results carry the dataset's window + survivorship caveats.
# --------------------------------------------------------------------------- #
GH_REPO = "Ratnesh-bhosale/NIFTY500_dataset"
GH_RAW = f"https://raw.githubusercontent.com/{GH_REPO}/main/Dataset"
GH_TREE = f"https://github.com/{GH_REPO}/tree/main/Dataset"
_CACHE = "/tmp/nifty500_cache"


def _http_get(url, timeout=30):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=timeout
    ).read()


def _gh_file_list():
    import re
    html = _http_get(GH_TREE).decode("utf-8", "replace")
    return sorted(set(re.findall(r"(\d{3}_[A-Z0-9&\-]+\.csv)", html)))


def _gh_close(fname):
    """Fetch one CSV (cached) -> Adj Close Series indexed by date."""
    os.makedirs(_CACHE, exist_ok=True)
    path = os.path.join(_CACHE, fname)
    if os.path.exists(path):
        raw = open(path, "rb").read()
    else:
        raw = _http_get(f"{GH_RAW}/{fname}")
        open(path, "wb").write(raw)
    df = pd.read_csv(io.StringIO(raw.decode("utf-8", "replace")), parse_dates=["Date"])
    s = df.set_index("Date")["Adj Close"].astype(float)
    s.index = s.index.normalize()
    return s[s > 0]


def load_panel_github(universe="allsymbols", top_n=200):
    """Wide Adj-Close panel from the public GitHub NIFTY500 dataset."""
    files = _gh_file_list()
    sym2file = {f.split("_", 1)[1][:-4]: f for f in files}  # SYMBOL -> NNN_SYMBOL.csv
    if universe == "allsymbols":
        import config
        plains = [s.replace("NSE:", "").replace("-EQ", "") for s in config.ALL_SYMBOLS]
        chosen = [(p, sym2file[p]) for p in plains if p in sym2file]
        missing = [p for p in plains if p not in sym2file]
        if missing:
            print(f"  (not in dataset, skipped: {', '.join(missing)})")
    elif universe == "top":
        chosen = [(f.split("_", 1)[1][:-4], f) for f in files[:top_n]]
    else:  # "all"
        chosen = [(f.split("_", 1)[1][:-4], f) for f in files]
    closes = {}
    for sym, f in chosen:
        try:
            s = _gh_close(f)
            if len(s) > LOOKBACK + SKIP + 21:
                closes[sym] = s
        except Exception:
            pass
    return pd.DataFrame(closes).sort_index()


def load_panel(symbols, years):
    """Return a wide (dates x symbols) close-price DataFrame from Fyers."""
    from fyers_client import FyersClient
    client = FyersClient()
    to = date.today()
    frm = to - timedelta(days=int(years * 365) + 60)
    closes = {}
    for s in symbols:
        c = fetch_daily(client, s, frm, to)
        if len(c) > LOOKBACK + SKIP + 21:
            c.index = c.index.normalize()
            closes[s] = c
    return pd.DataFrame(closes).sort_index()


# --------------------------------------------------------------------------- #
# Core analysis  (takes a wide close-price panel; data-source agnostic)
# --------------------------------------------------------------------------- #
def rebalance_positions(px: pd.DataFrame) -> list[int]:
    """Integer positions of the last trading day of each month."""
    idx = px.index
    months = pd.Series(idx, index=idx).groupby([idx.year, idx.month]).max()
    return sorted(idx.get_loc(d) for d in months.values)


def build_records(px: pd.DataFrame) -> pd.DataFrame:
    """One row per (rebalance, symbol): momentum signal + forward return."""
    reb = rebalance_positions(px)
    vals = px.values
    cols = px.columns
    idx = px.index
    rows = []
    for k in range(len(reb) - 1):
        p = reb[k]
        p_next = reb[k + 1]
        if p - LOOKBACK < 0:
            continue
        for j, sym in enumerate(cols):
            p0 = vals[p - LOOKBACK, j]      # 12 months ago
            p_skip = vals[p - SKIP, j]      # ~1 month ago
            p_now = vals[p, j]              # rebalance close
            p_fwd = vals[p_next, j]         # next rebalance close
            if not np.all(np.isfinite([p0, p_skip, p_now, p_fwd])) or p0 <= 0 or p_now <= 0:
                continue
            rows.append({
                "reb": k,
                "date": idx[p],
                "symbol": sym,
                "mom": p_skip / p0 - 1.0,        # 12-1 momentum
                "fwd": p_fwd / p_now - 1.0,      # next-month return
            })
    return pd.DataFrame(rows)


def pooled_ic(rec: pd.DataFrame) -> tuple[float, float, int]:
    """Mean per-rebalance cross-sectional Spearman IC(mom, fwd) and its t-stat."""
    ics = []
    for _, g in rec.groupby("reb"):
        sub = g[["mom", "fwd"]].dropna()
        if len(sub) >= 5:
            ic, _ = stats.spearmanr(sub["mom"], sub["fwd"])
            if np.isfinite(ic):
                ics.append(ic)
    ics = np.array(ics)
    if len(ics) < 3:
        return float("nan"), float("nan"), len(ics)
    t = ics.mean() / (ics.std(ddof=1) / np.sqrt(len(ics))) if ics.std(ddof=1) > 0 else 0.0
    return float(ics.mean()), float(t), len(ics)


def quintile_legs(rec: pd.DataFrame, q: float = 0.2):
    """Per rebalance: (longs set, shorts set, ls_gross, long_ret, mkt_ret)."""
    out = []
    for k, g in rec.groupby("reb"):
        g = g.dropna(subset=["mom", "fwd"])
        n = len(g)
        if n < 5:
            continue
        nq = max(1, int(round(n * q)))
        s = g.sort_values("mom")
        shorts = s.iloc[:nq]
        longs = s.iloc[-nq:]
        ls = longs["fwd"].mean() - shorts["fwd"].mean()
        out.append({
            "reb": k, "date": g["date"].iloc[0],
            "longs": set(longs["symbol"]), "shorts": set(shorts["symbol"]),
            "ls_gross": ls, "long_ret": longs["fwd"].mean(), "mkt_ret": g["fwd"].mean(),
        })
    return pd.DataFrame(out)


def turnover_series(legs: pd.DataFrame) -> np.ndarray:
    """Fraction of the L/S book replaced each rebalance (one-way name turnover)."""
    to = []
    prev_l, prev_s = set(), set()
    for _, r in legs.iterrows():
        changed = len(r["longs"] ^ prev_l) + len(r["shorts"] ^ prev_s)
        book = len(r["longs"]) + len(r["shorts"])
        to.append(changed / (2 * book) if book else 0.0)
        prev_l, prev_s = r["longs"], r["shorts"]
    return np.array(to)


def annualized(monthly: np.ndarray, ppy: int = 12):
    monthly = np.asarray(monthly, float)
    if len(monthly) == 0:
        return float("nan"), float("nan"), float("nan"), float("nan")
    ann_ret = monthly.mean() * ppy
    ann_vol = monthly.std(ddof=1) * np.sqrt(ppy) if len(monthly) > 1 else float("nan")
    sharpe = ann_ret / ann_vol if ann_vol and np.isfinite(ann_vol) and ann_vol > 0 else float("nan")
    curve = np.cumprod(1 + monthly)
    dd = float((curve / np.maximum.accumulate(curve) - 1).min())
    return ann_ret, ann_vol, sharpe, dd


def alpha_beta(y: np.ndarray, x: np.ndarray):
    """OLS y = a + b*x. Returns (alpha_monthly, beta, t_alpha)."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 3:
        return float("nan"), float("nan"), float("nan")
    b, a = np.polyfit(x, y, 1)
    resid = y - (a + b * x)
    sx = np.sum((x - x.mean()) ** 2)
    se_a = np.sqrt(np.sum(resid ** 2) / (len(x) - 2) * (1 / len(x) + x.mean() ** 2 / sx)) if sx > 0 else float("nan")
    t_a = a / se_a if se_a and np.isfinite(se_a) and se_a > 0 else float("nan")
    return float(a), float(b), float(t_a)


def report(rec: pd.DataFrame, cost_rt_bps: float = COST_RT_BPS, label: str = "") -> dict:
    n_sym = rec["symbol"].nunique()
    n_reb = rec["reb"].nunique()
    print(f"\n=== {label} ===" if label else "")
    print(f"symbols={n_sym}  rebalances={n_reb}  obs={len(rec)}")
    if n_reb < 6:
        print("Too few rebalances for a verdict (need >=6).")
        return {}

    ic, ic_t, ndays = pooled_ic(rec)
    print(f"\nPooled cross-sectional IC(12-1 mom, next-month ret): "
          f"{ic:+.4f}  t={ic_t:+.2f}  (n={ndays} rebalances)")

    legs = quintile_legs(rec)
    to = turnover_series(legs)
    avg_to = float(np.mean(to))
    ls_gross = legs["ls_gross"].values
    # turnover-based cost per rebalance: replaced fraction pays a round trip
    cost = to * (cost_rt_bps / 1e4)
    ls_net = ls_gross - cost

    gr = annualized(ls_gross); ne = annualized(ls_net)
    print(f"\nDollar-neutral L/S quintile spread (beta~0, the pure premium):")
    print(f"  avg monthly turnover     : {avg_to*100:5.1f}%  (annual cost ~ "
          f"{12*avg_to*cost_rt_bps/100:.2f}% at {cost_rt_bps:.0f} bps RT)")
    print(f"  GROSS  ann.ret {gr[0]*100:+6.1f}%  vol {gr[1]*100:5.1f}%  "
          f"Sharpe {gr[2]:+.2f}  maxDD {gr[3]*100:+5.1f}%")
    print(f"  NET    ann.ret {ne[0]*100:+6.1f}%  vol {ne[1]*100:5.1f}%  "
          f"Sharpe {ne[2]:+.2f}  maxDD {ne[3]*100:+5.1f}%")
    hit = float((ls_net > 0).mean())
    print(f"  net hit rate (months up) : {hit*100:5.1f}%")

    # Is the long-only leg just beta?
    a, b, t_a = alpha_beta(legs["long_ret"].values, legs["mkt_ret"].values)
    print(f"\nLong-only top quintile vs equal-weight 'market' (the NSE-cash form):")
    print(f"  alpha {a*100:+.2f}%/mo (t={t_a:+.2f})   beta {b:+.2f}   "
          f"-> {'ALPHA beyond beta' if np.isfinite(t_a) and t_a > 2 else 'NOT distinguishable from beta'}")

    # Sub-period robustness
    mid = legs["reb"].median()
    h1 = ls_net[legs["reb"] <= mid]; h2 = ls_net[legs["reb"] > mid]
    def shp(x):
        x = np.asarray(x, float)
        return (x.mean()*12) / (x.std(ddof=1)*np.sqrt(12)) if len(x) > 1 and x.std(ddof=1) > 0 else float("nan")
    print(f"\nSub-period split (robust if BOTH > 0):")
    print(f"  H1 net ann.ret {h1.mean()*12*100:+6.1f}%  Sharpe {shp(h1):+.2f}  (n={len(h1)})")
    print(f"  H2 net ann.ret {h2.mean()*12*100:+6.1f}%  Sharpe {shp(h2):+.2f}  (n={len(h2)})")

    # Cost sensitivity
    print(f"\nCost sensitivity (net L/S annualized return):")
    for mult in (1.0, 1.5, 2.0):
        net = ls_gross - to * (cost_rt_bps * mult / 1e4)
        print(f"  {mult:>3.1f}x ({cost_rt_bps*mult:4.0f} bps RT): {net.mean()*12*100:+6.1f}%  Sharpe {annualized(net)[2]:+.2f}")

    return {"ic": ic, "ic_t": ic_t, "ls_net_sharpe": ne[2], "alpha_t": t_a, "avg_turnover": avg_to}


# --------------------------------------------------------------------------- #
# Self-test  (synthetic panels — proves the harness, needs no market data)
# --------------------------------------------------------------------------- #
def _synth_panel(n_sym=30, n_days=900, momentum=True, seed=0) -> pd.DataFrame:
    """Daily close panel. If momentum=True, each name has a slow AR(1) trend
    component so 12-1 momentum predicts forward returns; else pure noise."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-01-01", periods=n_days)
    closes = {}
    for j in range(n_sym):
        if momentum:
            # persistent trend: AR(1) latent state drives daily drift
            trend = np.zeros(n_days)
            phi, sig = 0.98, 0.0015
            for t in range(1, n_days):
                trend[t] = phi * trend[t-1] + rng.normal(0, sig)
            daily = trend + rng.normal(0, 0.012, n_days)
        else:
            daily = rng.normal(0, 0.012, n_days)
        closes[f"SYN{j:02d}"] = pd.Series(100 * np.cumprod(1 + daily), index=idx)
    return pd.DataFrame(closes)


def self_test() -> None:
    print("#" * 70)
    print("# SELF-TEST — proving the instrument on synthetic data (no market data)")
    print("#" * 70)

    print("\n[A] PLANTED momentum panel — expect IC > 0, t > 2:")
    rec = build_records(_synth_panel(momentum=True, seed=1))
    ra = report(rec, label="planted momentum")

    print("\n[B] PURE-NOISE panel — expect IC ~ 0, |t| small:")
    rec = build_records(_synth_panel(momentum=False, seed=2))
    rb = report(rec, label="pure noise")

    print("\n" + "=" * 70)
    ok_power = np.isfinite(ra.get("ic_t", np.nan)) and ra["ic"] > 0 and ra["ic_t"] > 2
    ok_null = np.isfinite(rb.get("ic_t", np.nan)) and abs(rb["ic_t"]) < 2
    print(f"POWER  (planted -> IC>0, t>2)   : {'PASS' if ok_power else 'FAIL'}  "
          f"(IC {ra.get('ic'):+.3f}, t {ra.get('ic_t'):+.2f})")
    print(f"NO-FALSE-POSITIVE (noise -> t~0): {'PASS' if ok_null else 'FAIL'}  "
          f"(IC {rb.get('ic'):+.3f}, t {rb.get('ic_t'):+.2f})")
    print("Both PASS => the harness measures real signal and does not invent it.")
    print("Point it at live data (--all-symbols) and a null is a real null.")


# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+")
    p.add_argument("--all-symbols", action="store_true",
                   help="use config.ALL_SYMBOLS")
    p.add_argument("--years", type=float, default=4.0)
    p.add_argument("--cost-bps", type=float, default=COST_RT_BPS)
    p.add_argument("--self-test", action="store_true",
                   help="run synthetic-data instrument validation (no market data)")
    p.add_argument("--github", action="store_true",
                   help="use the public split-adjusted GitHub NIFTY500 dataset "
                        "(2012-2021) instead of Fyers")
    p.add_argument("--universe", choices=["allsymbols", "top", "all"],
                   default="allsymbols", help="--github universe selector")
    p.add_argument("--top-n", type=int, default=200,
                   help="N names for --universe top (market-cap ranked)")
    args = p.parse_args()

    if args.self_test:
        self_test()
        return

    if args.github:
        print(f"Data source: GitHub {GH_REPO} (split-adjusted Adj Close, 2012-2021).")
        px = load_panel_github(args.universe, args.top_n)
        src = f"GitHub NIFTY500 [{args.universe}{'/'+str(args.top_n) if args.universe=='top' else ''}]"
    else:
        if args.all_symbols:
            import config
            symbols = config.ALL_SYMBOLS
        elif args.symbols:
            symbols = args.symbols
        else:
            p.error("pass --symbols, --all-symbols, --github, or --self-test")
        px = load_panel(symbols, args.years)
        src = f"Fyers, {args.years:g}y"

    if px.shape[1] < 5:
        print(f"Only {px.shape[1]} symbols loaded — need >=5 for cross-sectional IC.")
        return
    span = f"{px.index.min().date()}..{px.index.max().date()}"
    rec = build_records(px)
    report(rec, cost_rt_bps=args.cost_bps,
           label=f"LIVE [{src}]: {px.shape[1]} symbols, {span}")


if __name__ == "__main__":
    main()
