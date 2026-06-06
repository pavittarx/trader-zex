"""Return-series statistics shared by all research scripts."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as _scipy_stats


def ann_return(daily_mean: float, periods: int = 252) -> float:
    """Annualized return (%) from a mean per-period return."""
    return ((1 + daily_mean) ** periods - 1) * 100


def sharpe(returns, periods: int = 252) -> float:
    r = np.asarray(returns, dtype=float)
    return (r.mean() / r.std()) * np.sqrt(periods) if r.std() > 0 else 0.0


def t_stat(returns) -> float:
    r = np.asarray(returns, dtype=float)
    return r.mean() / (r.std() / np.sqrt(len(r))) if len(r) and r.std() > 0 else 0.0


def max_drawdown(returns) -> float:
    """Max drawdown (negative fraction) of a per-period return series."""
    eq = np.cumprod(1 + np.asarray(returns, dtype=float))
    return float((eq / np.maximum.accumulate(eq) - 1).min())


def spearman_ic(x, y) -> tuple[float, float]:
    """Spearman IC and its t-stat."""
    ic, _ = _scipy_stats.spearmanr(x, y)
    n = len(x)
    t = ic * np.sqrt(n - 2) / np.sqrt(1 - ic**2) if abs(ic) < 1 else 0.0
    return float(ic), float(t)


def daily_metrics(daily: pd.Series) -> dict:
    """CAGR / Sharpe / maxDD / final multiple / %active from a daily P&L series.

    (Extracted from scripts/pead_backtest.py metrics().)
    """
    d = daily[daily.index >= daily[daily != 0].index.min()] if (daily != 0).any() else daily
    if len(d) < 20:
        return {}
    eq = (1 + d).cumprod()
    yrs = len(d) / 252
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    dd = (eq / eq.cummax() - 1).min()
    return {"cagr": cagr * 100, "sharpe": sharpe(d), "maxdd": dd * 100,
            "final": eq.iloc[-1], "active_days": (d != 0).mean() * 100, "days": len(d)}
