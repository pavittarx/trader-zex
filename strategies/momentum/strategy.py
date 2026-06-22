"""
Momentum Strategy — NautilusTrader implementation.

Same code path for backtest and live:
- Backtest: subscribe to historical bars, simulated fills at VWAP
- Live: subscribe to real-time bars, fills via Fyers API

Weekly rebalance logic:
  1. Compute 12-1 ranks for all symbols
  2. Generate target portfolio (top quintile)
  3. Skip rebalance if portfolio change < 1.5%
  4. Place orders for rebalance
  5. Track fills and P&L
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Optional

from nautilus_trader.core.data import BarType
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import OrderType, TimeInForce
from nautilus_trader.model.orders import Order
from nautilus_trader.model.position import Position
from nautilus_trader.trading.strategy import Strategy

log = logging.getLogger(__name__)


class MomentumStrategy(Strategy):
    """
    Cross-sectional momentum: 12-1 window, top quintile, weekly rebalance.
    
    Parameters (from manifest):
    - n_stocks: 100 (Nifty 500 constituents)
    - window_months: 12
    - exclude_months: 1
    - rebalance_frequency: "WEEKLY" (Friday)
    - turnover_pct: 1.5
    - max_position_pct: 2.0
    """
    
    def __init__(
        self,
        config: dict,
        bar_types: list[BarType],
        trading_pairs: list[str],
    ):
        """
        Initialize momentum strategy.
        
        Parameters
        ----------
        config : dict
            Strategy config from manifest (n_stocks, window_months, etc)
        bar_types : list[BarType]
            Bar subscriptions (e.g., daily bars)
        trading_pairs : list[str]
            Nifty 500 symbols (NSE:SYMBOL-EQ format)
        """
        super().__init__(config=config)
        
        self.config = config
        self.bar_types = bar_types
        self.trading_pairs = trading_pairs
        
        # Portfolio state
        self.current_portfolio: dict[str, float] = {}  # {symbol: qty}
        self.target_portfolio: set[str] = set()        # top quintile symbols
        self.last_rebalance_date: Optional[datetime] = None
        
        # Signal cache
        self._signals: dict[str, dict] = {}  # {symbol: {date: rank}}
        self._close_prices: dict[str, list] = {sym: [] for sym in trading_pairs}
        
        log.info(f"Initialized MomentumStrategy: {len(trading_pairs)} symbols, {config}")
    
    def on_start(self) -> None:
        """Called when strategy starts (backtest or live)."""
        log.info("Strategy started")
        
        # Subscribe to daily bars
        for bar_type in self.bar_types:
            self.subscribe_bars(bar_type)
        
        self.log.info("✅ Strategy ready")
    
    def on_bar(self, bar: Bar) -> None:
        """Process daily bar."""
        symbol = bar.instrument_id.symbol
        
        # Cache close price
        if symbol not in self._close_prices:
            self._close_prices[symbol] = []
        self._close_prices[symbol].append((bar.ts_event, bar.close))
        
        # Check if it's Friday (rebalance day)
        bar_date = bar.ts_event.date()
        if bar_date.weekday() == 4:  # Friday
            self._on_rebalance_day(bar_date)
    
    def _on_rebalance_day(self, rebalance_date) -> None:
        """Execute weekly rebalance logic on Friday."""
        log.info(f"Rebalance day: {rebalance_date}")
        
        # 1. Compute 12-1 ranks for all symbols (from cached closes)
        ranks = self._compute_12_1_ranks(rebalance_date)
        
        if not ranks:
            log.warning("No ranks computed")
            return
        
        # 2. Generate target portfolio (top quintile)
        self.target_portfolio = self._get_top_quintile(ranks)
        log.info(f"Target portfolio: {len(self.target_portfolio)} stocks")
        
        # 3. Compute turnover
        to_add = self.target_portfolio - set(self.current_portfolio.keys())
        to_remove = set(self.current_portfolio.keys()) - self.target_portfolio
        turnover = len(to_add | to_remove) / max(len(self.current_portfolio), 1)
        
        # 4. Check turnover gate
        if turnover < (self.config.get("turnover_pct", 1.5) / 100):
            log.info(f"Turnover {turnover*100:.2f}% < gate; skipping rebalance")
            return
        
        # 5. Place rebalance orders
        self._rebalance_portfolio(to_add, to_remove, rebalance_date)
        
        self.last_rebalance_date = rebalance_date
    
    def _compute_12_1_ranks(self, as_of_date) -> dict[str, float]:
        """
        Compute 12-1 ranks for all symbols.
        
        Uses cached close prices, expanding window (no look-ahead).
        
        Returns: {symbol: rank} where rank is 0-100 percentile
        """
        ranks = {}
        returns_12_1 = {}
        
        lookback_days = 12 * 21  # ~252 trading days
        exclude_days = 1 * 21
        
        for symbol, closes in self._close_prices.items():
            if len(closes) < lookback_days + exclude_days:
                continue
            
            # Most recent price (as_of_date)
            idx_now = len(closes) - 1
            idx_start = max(0, idx_now - lookback_days)
            idx_end = max(0, idx_now - exclude_days)
            
            if idx_start < idx_end:
                price_start = closes[idx_start][1]
                price_end = closes[idx_end][1]
                
                if price_start > 0:
                    ret_12_1 = (price_end - price_start) / price_start
                    returns_12_1[symbol] = ret_12_1
        
        if not returns_12_1:
            return {}
        
        # Rank by 12-1 return (0-100 percentile)
        sorted_rets = sorted(returns_12_1.items(), key=lambda x: x[1])
        
        for rank, (symbol, _) in enumerate(sorted_rets):
            percentile = (rank / len(sorted_rets)) * 100
            ranks[symbol] = percentile
        
        return ranks
    
    def _get_top_quintile(self, ranks: dict[str, float]) -> set[str]:
        """Get top 20% of symbols by rank."""
        sorted_by_rank = sorted(ranks.items(), key=lambda x: x[1], reverse=True)
        n_top = max(1, len(sorted_by_rank) // 5)  # Top 20%
        return {sym for sym, _ in sorted_by_rank[:n_top]}
    
    def _rebalance_portfolio(self, to_add: set[str], to_remove: set[str], rebalance_date) -> None:
        """Place orders to rebalance portfolio."""
        log.info(f"Rebalance: add {len(to_add)}, remove {len(to_remove)}")
        
        # TODO: Connect to order placement
        # For now, just log
        if to_remove:
            log.info(f"  Sell: {to_remove}")
        if to_add:
            log.info(f"  Buy: {to_add}")
        
        # Update portfolio state (simplified: equal weight all positions)
        self.current_portfolio = {sym: 1.0 for sym in self.target_portfolio}
    
    def on_order_filled(self, order: Order) -> None:
        """Called when an order fills."""
        log.info(f"Order filled: {order.client_order_id} {order.symbol} {order.quantity} @ {order.average_price}")
    
    def on_order_rejected(self, order: Order) -> None:
        """Called when an order is rejected."""
        log.warning(f"Order rejected: {order.client_order_id}")
    
    def on_stop(self) -> None:
        """Called when strategy stops."""
        log.info("Strategy stopped")
