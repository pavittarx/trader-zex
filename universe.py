"""
universe.py — Tradable stock universe from Nifty 500.

Uses a single NSE bulk endpoint that returns all 500 constituents with
lastPrice and totalTradedVolume in one request — no per-symbol loop.

Results are cached to UNIVERSE_CACHE_FILE (config.py) and reused for
the rest of the calendar day; a fresh fetch runs once per day.
"""

import json
import logging
from datetime import date

import config

log = logging.getLogger(__name__)

_NIFTY500_URL = (
    "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"
)


def _to_fyers(symbol: str) -> str:
    return f"NSE:{symbol}-EQ"


def _load_cache() -> list[str] | None:
    """Return cached symbols if written today, else None."""
    try:
        data = json.loads(config.UNIVERSE_CACHE_FILE.read_text())
        if data.get("date") == date.today().isoformat():
            return data["symbols"]
    except Exception as exc:
        log.debug("Cache read failed: %s", exc)
    return None


def get_cached_symbols() -> list[str]:
    """Return any cached universe (any date), used for populating UI option lists."""
    try:
        data = json.loads(config.UNIVERSE_CACHE_FILE.read_text())
        return data.get("symbols", [])
    except Exception:
        return []


def _save_cache(symbols: list[str]) -> None:
    path = config.UNIVERSE_CACHE_FILE
    try:
        path.write_text(json.dumps({"date": date.today().isoformat(), "symbols": symbols}))
        log.debug("Universe cached to %s", path)
    except Exception as exc:
        log.warning("Could not write universe cache: %s", exc)


def get_tradable_universe() -> list[str]:
    """
    Return Fyers-formatted Nifty 500 symbols that pass the price and
    volume filters configured in config.py.

    A single bulk NSE API call fetches all constituents at once; results
    are cached for the current calendar day.
    """
    cached = _load_cache()
    if cached is not None:
        log.info("Universe: loaded %d symbols from today's cache", len(cached))
        return cached

    try:
        from nsepython.rahu import nsefetch
    except ImportError as exc:
        raise ImportError(
            "nsepython is required for universe filtering. "
            "Install it with: uv add nsepython"
        ) from exc

    max_price = config.UNIVERSE_MAX_PRICE
    min_volume = config.UNIVERSE_MIN_VOLUME

    log.info("Fetching Nifty 500 constituents from NSE …")
    payload = nsefetch(_NIFTY500_URL)
    rows = payload.get("data", [])

    # First record is the index itself — skip it
    stocks = [r for r in rows if r.get("identifier") != "NIFTY 500"]
    total = len(stocks)
    log.info("Received %d Nifty 500 stocks; applying filters …", total)

    universe: list[str] = []
    skipped = 0
    for row in stocks:
        symbol = row.get("symbol", "")
        price = row.get("lastPrice", 0) or 0
        volume = row.get("totalTradedVolume", 0) or 0

        if not symbol:
            skipped += 1
            continue

        passed = price <= max_price and volume >= min_volume
        status = "✓" if passed else "✗"
        log.debug(
            "  %-14s  ₹%-8.2f  vol %-12s  %s",
            symbol, price, f"{int(volume):,}", status,
        )
        if passed:
            universe.append(_to_fyers(symbol))
        else:
            skipped += 1

    log.info(
        "Universe: %d / %d passed  (price ≤ ₹%.0f, volume ≥ %s)  |  filtered out: %d",
        len(universe), total, max_price, f"{min_volume:,}", skipped,
    )

    _save_cache(universe)

    # Warn if any backtestable symbol is excluded by the price/volume filters
    all_syms_set = set(config.ALL_SYMBOLS)
    filtered_set = set(universe)
    excluded = all_syms_set - filtered_set
    if excluded:
        log.warning(
            "Universe filter excludes %d symbols from ALL_SYMBOLS: %s. "
            "Consider raising UNIVERSE_MAX_PRICE (currently ₹%.0f).",
            len(excluded), sorted(excluded)[:5], config.UNIVERSE_MAX_PRICE,
        )

    return universe
