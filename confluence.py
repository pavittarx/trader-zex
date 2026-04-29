"""
SignalEngine — combines HMM regime with structural price location
to produce a single confluence signal.

Signal table
------------
HMM state   │ Price location  │ Signal
────────────┼─────────────────┼────────────────────
Bullish     │ At Support      │ STRONG BUY    ← momentum turning at a floor
Bullish     │ In Middle       │ WEAK BUY      ← good momentum, no structural edge
Bullish     │ At Resistance   │ TAKE PROFIT   ← momentum up but price at a ceiling
Sideways    │ At Support      │ WATCH         ← structure good, wait for momentum
Sideways    │ In Middle       │ NEUTRAL
Sideways    │ At Resistance   │ WATCH         ← could reject at ceiling
Bearish     │ At Support      │ WAIT          ← at floor but don't catch a falling knife
Bearish     │ In Middle       │ AVOID
Bearish     │ At Resistance   │ STRONG SELL   ← momentum dropping at a ceiling
"""

_SIGNAL_TABLE: dict[tuple[str, str], str] = {
    ("Bullish",  "At Support"):    "STRONG BUY",
    ("Bullish",  "In Middle"):     "WEAK BUY",
    ("Bullish",  "At Resistance"): "TAKE PROFIT",
    ("Sideways", "At Support"):    "WATCH",
    ("Sideways", "In Middle"):     "NEUTRAL",
    ("Sideways", "At Resistance"): "WATCH",
    ("Bearish",  "At Support"):    "WAIT",
    ("Bearish",  "In Middle"):     "AVOID",
    ("Bearish",  "At Resistance"): "STRONG SELL",
}

_SIGNAL_ICONS: dict[str, str] = {
    "STRONG BUY":  "★ STRONG BUY",
    "WEAK BUY":    "↑ WEAK BUY",
    "TAKE PROFIT": "⊙ TAKE PROFIT",
    "WATCH":       "◎ WATCH",
    "NEUTRAL":     "· NEUTRAL",
    "WAIT":        "⏸ WAIT",
    "AVOID":       "✕ AVOID",
    "STRONG SELL": "★ STRONG SELL",
}


def generate_signal(hmm_regime: str, price_location: str) -> str:
    """Return the raw signal label for a given HMM regime + price location."""
    return _SIGNAL_TABLE.get((hmm_regime, price_location), "NEUTRAL")


def format_signal(signal: str) -> str:
    """Return the icon-prefixed display string for a signal label."""
    return _SIGNAL_ICONS.get(signal, signal)
