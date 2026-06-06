"""runners — stage-gated entry points for the strategy pipeline.

    python -m runners.list                  # all strategies + stages
    python -m runners.backtest <strategy>   # requires stage >= backtest
    python -m runners.sandbox  <strategy>   # requires stage >= sandbox
    python -m runners.live     <strategy>   # requires stage == live + --i-am-sure
"""
