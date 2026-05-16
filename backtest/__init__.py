"""
backtest — NautilusTrader-based backtesting engine for the HMM confluence strategy.

Entry point:  python -m backtest  (see __main__.py)

Modules
-------
instruments     : NSE equity instrument definitions
data_loader     : Fyers OHLCV DataFrame → NautilusTrader Bar objects
signal_precompute : rolling HMM + confluence signals without look-ahead
strategy        : HMMConfluenceStrategy (NautilusTrader Strategy subclass)
engine          : BacktestEngine setup and single-symbol run
metrics         : post-run performance statistics
"""
