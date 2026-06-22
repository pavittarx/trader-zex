# Cross-Sectional Momentum Strategy

**Status:** Hypothesis → Backtest → Live  
**Universe:** Nifty 500 constituents + delisted names (survivorship-free)  
**Rebalance:** Quarterly (63-day cadence, anchored to Friday EOD)  
**Turnover gate:** Only trade if portfolio drift > 1.5% (throttles costs)

---

## The Hypothesis

> Nifty 500 constituents exhibit 12-1 month cross-sectional momentum: stocks ranked by 12-month total returns, excluding the past month, deliver predictable outperformance the following month. The edge persists despite costs (~40–65 bps round-trip STT + spreads + slippage) because:
> - Turnover filter (rebalance only if drift > 1.5%) throttles execution friction
> - Quarterly cadence reduces cost drag while retaining trend persistence
> - Factor exposure (quality, low vol, size) drives the continuation

---

## Edge & Failure Regimes

| Factor | Benefit | Risk |
|--------|---------|------|
| **Lookback window (12-1 mo)** | Captures multi-month trends, captures factor exposure | Sharp V-reversals in a single month kills the rank; crowded trades reverse faster |
| **Weekly rebalance** | Fresh signal weekly, avoids stale ranks | Execution friction; costs eat the edge if turnover spikes |
| **Turnover filter** | Throttles rebalancing churn (only trade if drift > 1.5%) | Misses regime transitions; delayed entry/exit on sharp gaps |
| **Top quintile (long only)** | High conviction, lower execution costs than L/S | Missing short edge; unidirectional bet (fails in downturns) |

**Falsifiers (kill the strategy immediately):**
- Net Sharpe ≤ 0 after retail costs in OOS walk-forward
- Drawdown > 15% in live trading
- Win rate < 45% over 20 trades (edge no longer covers costs)

---

## Configuration

All parameters live in `manifest.py:MANIFEST.params`. This ensures backtest, paper-trade, and live all use the same config.

### Key params

```python
{
    "lookback_months": 12,           # 12-month return window
    "ranking_months": 1,              # exclude past 1 month from rank
    "quintile": 1,                    # trade top quintile (1 = top 20%)
    "rebalance_freq": "quarterly",    # 63-day cadence anchored on Friday
    "turnover_threshold_pct": 1.5,    # only trade if portfolio weight drift > 1.5%
    "max_single_position_pct": 5,     # position cap: 5% of portfolio
}
```

### Derived at runtime

`config.py` computes:
- **Target hold count:** `round(nifty_500_size / quintile_size)` ≈ 100 stocks (if quintile=1)
- **Rebalance universe:** Point-in-time Nifty 500 constituent list for the week
- **Cost model:** 40–65 bps round-trip (STT 15–20 bps + half-spread 10–30 bps + slippage 5–15 bps)

Point-in-time universe is loaded from SQLite registry (`~/.trader_zex/data/momentum_universe.sqlite`):

```bash
uv run python -m strategies.momentum.research.universe_registry init
uv run python -m strategies.momentum.research.universe_registry import-csv --csv strategies/momentum/research/nifty500_universe_template.csv
uv run python -m strategies.momentum.research.universe_registry isins-at-date --date 2024-06-28
```

---

## Backtest Workflow

1. **Load EOD data** (Fyers API, cached in Parquet)
2. **Compute 12-1 returns** (expanding window, no look-ahead)
3. **Rank weekly** (Friday) → select top quintile
4. **Compute rebalance trades** (vs current portfolio)
5. **Filter by turnover gate** (drop trades if total drift < 1.5%)
6. **Execute at next-day VWAP** (realistic fill model)
7. **Track P&L, costs, slippage** → compare to model

---

## Deployment

### Paper trade (1–3 months)
- Live Fyers EOD feed → quarterly signal compute
- Simulate fills at next-day VWAP
- Monitor realized costs, win rate, drawdown
- **Gate:** metrics match backtest prior ±1 SE

Run one paper cycle:

```bash
uv run python -m runners.paper momentum --as-of 2024-06-28 --n-symbols 50
```

### Shadow live (1–3 months)
- Place 10% position sizing in live market
- Real fills from Fyers
- Track TCA (slippage vs model)
- **Gate:** realized fills within 2× model std dev

### Full live
- **Gate:** Shadow trade metrics match backtest
- Auto-rebalance every Friday 3:30 PM IST
- **Kill-switch:** drawdown > 15%, slippage > 2× model, stale feed, win rate < 45%

---

## Key Files

| File | Purpose |
|------|---------|
| `manifest.py` | Stage, broker, universe, params, kill_criteria (the contract) |
| `config.py` | Runtime config: universe roster, rebalance logic, cost model |
| `signal.py` | 12-1 momentum compute (expanding window, no look-ahead) |
| `strategy.py` | NautilusTrader Strategy class (backtest + live) |
| `backtest.py` | Runner entry point (calls core.backtest.engine) |
| `research/README.md` | Research script map (triage, walk-forward, verification, experiments) |
| `PLAYBOOK.md` | Detailed position sizing, kill-switch rules, OOS interpretation |
| `STATUS.md` | Stage history, findings log, kill log (updated per phase) |

---

## References

- [PIPELINE.md](../../docs/PIPELINE.md) — Stage gates + lifecycle
- [PEAD_PLAYBOOK.md](../../docs/PEAD_PLAYBOOK.md) — Deployment ladder (apply same pattern)
- [core.backtest.engine](../../core/backtest/engine.py) — Backtest harness (NautilusTrader)
- [core.research.stats](../../core/research/stats.py) — Sharpe, IC, max-DD metrics
- [core.research.cost](../../core/research/cost.py) — Cost models (bps → fractions)
