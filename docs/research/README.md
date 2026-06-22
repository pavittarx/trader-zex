# Research Archive

Strategies and research artifacts that have been analyzed, tested, and archived.

## hmm_confluence/

**Status:** backtest (not advanced to live)  
**Finding:** HMM regime + S/R structure confluence signal showed strong IC on 15m bars but degraded with realistic fills. Strategy archived after [OHLCV-sweep verdict](../STRATEGY_GUIDELINES.md).

**Use case:** Reference implementation for:
- NautilusTrader strategy pattern (multi-timeframe signal compute, position sizing)
- `core.signals.hmm_model` and `core.signals.structure` (still in use, production-ready)
- Daily backtest engine integration

The strategy code is frozen; the signal infrastructure (`core/signals/`) remains active and reused by new strategies.

---

## Lessons

See [STRATEGY_GUIDELINES.md](../STRATEGY_GUIDELINES.md) §10 for the sweep conclusion:
> Six signal families tested (HMM-confluence, momentum, reversal, gap-fade, gap-continuation, compression-breakout) — none tradable on simple OHLCV. The retail-accessible edge, if it exists, is likely in **event-driven signals or regime + structure combos, not pure price/volume technicals.**

PEAD (earnings drift) proved the event thesis; momentum is testing cross-sectional ranks.
