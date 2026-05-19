import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # loads .env from cwd (or any parent) into os.environ

# --- Fyers API Credentials ---
# Set these in .env; the defaults below are only fallback placeholders.
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "YOUR_CLIENT_ID-100")
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "YOUR_SECRET_KEY")
FYERS_REDIRECT_URI = os.getenv(
    "FYERS_REDIRECT_URI",
    "https://trade.fyers.in/api-login/redirect-uri/index.html",
)

# --- Token Persistence ---
TOKEN_FILE = Path("~/.fyers_token.json").expanduser()

# --- HMM Configuration ---
HMM_N_STATES = 3
HMM_N_ITER = 1000
HMM_RANDOM_STATE = 42
# Minimum bars required to fit the model reliably
HMM_MIN_SAMPLES = 100

# --- Screener Defaults ---
ALL_SYMBOLS = [
    "NSE:RELIANCE-EQ",
    "NSE:TCS-EQ",
    "NSE:INFY-EQ",
    "NSE:HDFCBANK-EQ",
    "NSE:ICICIBANK-EQ",
    "NSE:HINDUNILVR-EQ",
    "NSE:SBIN-EQ",
    "NSE:BHARTIARTL-EQ",
    "NSE:KOTAKBANK-EQ",
    "NSE:ITC-EQ",
    "NSE:LT-EQ",
    "NSE:AXISBANK-EQ",
    "NSE:BAJFINANCE-EQ",
    "NSE:ASIANPAINT-EQ",
    "NSE:MARUTI-EQ",
    "NSE:WIPRO-EQ",
    "NSE:HCLTECH-EQ",
    "NSE:SUNPHARMA-EQ",
    "NSE:TITAN-EQ",
    "NSE:ULTRACEMCO-EQ",
    "NSE:TATAMOTORS-EQ",
    "NSE:TATASTEEL-EQ",
    "NSE:JSWSTEEL-EQ",
    "NSE:ADANIENT-EQ",
    "NSE:ADANIPORTS-EQ",    
    "NSE:NTPC-EQ",
    "NSE:POWERGRID-EQ",
    "NSE:ONGC-EQ",
    "NSE:TECHM-EQ",
    "NSE:BAJAJFINSV-EQ",
]

DEFAULT_SYMBOLS = [
    # Large-cap / Nifty 50
    "NSE:RELIANCE-EQ",
    # "NSE:TCS-EQ",
    # "NSE:INFY-EQ",
    # "NSE:HDFCBANK-EQ",
    # "NSE:ICICIBANK-EQ",
    # "NSE:HINDUNILVR-EQ",
    # "NSE:SBIN-EQ",
    # "NSE:BHARTIARTL-EQ",
    # "NSE:KOTAKBANK-EQ",
    # "NSE:ITC-EQ",
    # "NSE:LT-EQ",
    # "NSE:AXISBANK-EQ",
    # "NSE:BAJFINANCE-EQ",
    # "NSE:ASIANPAINT-EQ",
    # "NSE:MARUTI-EQ",
    # "NSE:WIPRO-EQ",
    # "NSE:HCLTECH-EQ",
    # "NSE:SUNPHARMA-EQ",
    # "NSE:TITAN-EQ",
    # "NSE:ULTRACEMCO-EQ",
    # Mid-cap / sector picks
    # "NSE:TATAMOTORS-EQ",
    # "NSE:TATASTEEL-EQ",
    # "NSE:JSWSTEEL-EQ",
    # "NSE:ADANIENT-EQ",
    # "NSE:ADANIPORTS-EQ",
    # "NSE:NTPC-EQ",
    # "NSE:POWERGRID-EQ",
    # "NSE:ONGC-EQ",
    # "NSE:TECHM-EQ",
    # "NSE:BAJAJFINSV-EQ",
]

DEFAULT_TIMEFRAMES = ["5", "15", "60", "D"]

# --- API Rate Limiting ---
# Pause between successive history API calls to avoid rate-limit errors.
API_SLEEP_SECONDS = 0.5

# --- Historical Data Lookback (calendar days per timeframe) ---
# Chosen to yield ~200-500 bars per request while staying inside Fyers limits.
LOOKBACK_DAYS: dict[str, int] = {
    # Fyers hard limit: intraday resolutions (1–240 min) → max 100 calendar days
    "1": 30,
    "2": 40,
    "3": 50,
    "5": 60,
    "10": 80,
    "15": 90,
    "20": 90,
    "30": 95,
    "60": 95,
    "120": 95,
    "240": 95,
    # Fyers hard limit: D / W / M → max 366 calendar days
    "D": 365,
    "W": 365,
    "M": 365,
}

# --- Tradable Universe (nsepython) ---
UNIVERSE_MAX_PRICE: float = 500.0       # upper LTP bound (₹)
UNIVERSE_MIN_VOLUME: int = 500_000      # minimum daily traded volume
UNIVERSE_CACHE_FILE = Path("~/.trader_zex_universe.json").expanduser()
WATCHLIST_FILE = Path("~/.trader_zex_watchlist.json").expanduser()

# --- Structure Detector Configuration ---
STRUCTURE_METHOD = "atr"  # "atr" (Keltner bands) or "pivot" (swing highs/lows)
STRUCTURE_ATR_PERIOD = 14  # ATR lookback period
STRUCTURE_EMA_PERIOD = 20  # EMA period for band midline
STRUCTURE_ATR_MULT = 2.0  # band width = EMA ± multiplier × ATR
STRUCTURE_PROXIMITY_PCT = 2.0  # % distance to consider "at" a level
STRUCTURE_PIVOT_DISTANCE = 5  # min bars between pivots (scipy find_peaks)

# --- Stock Ranker Configuration ---
RANKER_TOP_N: int = 25                   # top-N long and top-N short candidates
RANKER_CACHE_FILE = Path("~/.trader_zex_rankings.json").expanduser()
RANKER_WEIGHT_SIGNAL: float = 0.40       # confluence signal strength
RANKER_WEIGHT_STRUCTURE: float = 0.30   # proximity to support/resistance
RANKER_WEIGHT_MOMENTUM: float = 0.20    # price momentum (5d + 20d returns)
RANKER_WEIGHT_VOLUME: float = 0.10      # volume surge vs. 20-day average
RANKER_MOMENTUM_DAYS: tuple[int, int] = (5, 20)   # short and long windows

# --- Backtester Configuration ---
BACKTEST_INITIAL_CAPITAL: float = 1_000_000.0   # ₹10 lakh starting balance
BACKTEST_RISK_PCT: float = 0.02                 # 2% of equity risked per trade
BACKTEST_STOP_BUFFER: float = 0.005             # 0.5% buffer past S/R for stop
BACKTEST_COMMISSION: float = 0.00065            # 0.065% per leg (brokerage + STT + exchange + SEBI + stamp)
BACKTEST_EOD_EXIT_HOUR_IST: int = 15            # flatten all positions at 15:15 IST
BACKTEST_EOD_EXIT_MINUTE_IST: int = 15
BACKTEST_SIGNAL_WARMUP: int = HMM_MIN_SAMPLES   # bars needed before first signal
BACKTEST_ALLOW_SHORTS: bool = False             # long-only by default (Indian equity spot)
BACKTEST_REGIME_STABILITY_BARS: int = 2         # require N consecutive signals agreeing before entry
