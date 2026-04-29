"""
dashboard.py — Streamlit UI for the HMM Market Regime Screener.

Run:
    uv run streamlit run dashboard.py
"""

from datetime import datetime

import pandas as pd
import streamlit as st

import auth
import config
from fyers_client import FyersClient
from screener import Screener

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Trader-Zex | Regime Screener",
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Styling helpers
# ---------------------------------------------------------------------------

_REGIME_CSS: dict[str, str] = {
    "▲ Bullish":  "background-color:#1e4d2b; color:#4caf50; font-weight:600",
    "▼ Bearish":  "background-color:#4d1e1e; color:#f44336; font-weight:600",
    "— Sideways": "background-color:#3d3000; color:#ff9800; font-weight:600",
    "✕ Error":    "color:#9e9e9e",
}

_SIGNAL_CSS: dict[str, str] = {
    "★ STRONG BUY":  "background-color:#1a3a1a; color:#00e676; font-weight:700",
    "↑ WEAK BUY":    "background-color:#1e3d1e; color:#69f0ae",
    "★ STRONG SELL": "background-color:#3a1a1a; color:#ff1744; font-weight:700",
    "✕ AVOID":       "background-color:#2d1a1a; color:#ef9a9a",
    "⊙ TAKE PROFIT": "background-color:#2d2d00; color:#ffee58",
    "◎ WATCH":       "background-color:#1a2d3a; color:#4fc3f7",
    "⏸ WAIT":        "background-color:#1a1a2d; color:#b39ddb",
    "· NEUTRAL":     "color:#9e9e9e",
}

_LOCATION_CSS: dict[str, str] = {
    "At Support":    "background-color:#1e4d2b; color:#4caf50",
    "At Resistance": "background-color:#4d1e1e; color:#f44336",
    "In Middle":     "color:#9e9e9e",
}


def _style_map(css_map: dict[str, str]):
    def _apply(val: str) -> str:
        return css_map.get(str(val).strip(), "")
    return _apply


def _style_regime(df: pd.DataFrame):
    tf_cols = [c for c in df.columns if c not in ("Price", "Chg%")]
    return (
        df.style
        .map(_style_map(_REGIME_CSS), subset=tf_cols)
        .map(
            lambda v: "color:#4caf50" if "▲" in str(v) else ("color:#f44336" if "▼" in str(v) else ""),
            subset=["Chg%"],
        )
    )


def _style_signals(df: pd.DataFrame):
    return df.style.map(_style_map(_SIGNAL_CSS))


def _style_levels(df: pd.DataFrame):
    return df.style.map(_style_map(_LOCATION_CSS), subset=["Location"])


# ---------------------------------------------------------------------------
# Auth flow
# ---------------------------------------------------------------------------

def _auth_section() -> str | None:
    st.warning("No valid Fyers token found for today. Complete authentication below.")

    url = auth.build_auth_url()
    st.markdown("**Step 1 — Open this URL in your browser and log in:**")
    st.code(url, language=None)

    st.markdown("**Step 2 — Paste the `auth_code` from the redirect URL:**")
    auth_code = st.text_input("auth_code", placeholder="xxxxxxxxxxxxxxxx")

    if st.button("Authenticate", type="primary"):
        if not auth_code.strip():
            st.error("Please paste the auth_code first.")
            return None
        with st.spinner("Exchanging auth code for token …"):
            try:
                token = auth.generate_token(auth_code.strip())
                st.success("Authentication successful!")
                return token
            except Exception as exc:
                st.error(f"Authentication failed: {exc}")
    return None


# ---------------------------------------------------------------------------
# Screener runner (shared by manual run and auto-refresh)
# ---------------------------------------------------------------------------

def _run_screener() -> None:
    settings = st.session_state.get("run_settings")
    if not settings:
        return
    with st.spinner(f"Analysing {len(settings['symbols'])} symbol(s) …"):
        try:
            client = FyersClient(access_token=st.session_state.access_token)
            regimes, signals, levels = Screener(client).run(
                symbols=settings["symbols"],
                timeframes=settings["timeframes"],
            )
            st.session_state.results = {
                "regimes": regimes,
                "signals": signals,
                "levels": levels,
                "updated_at": datetime.now().strftime("%d %b %Y  %H:%M:%S"),
                "timeframes": settings["timeframes"],
                "method": settings["method"],
            }
        except Exception as exc:
            st.error(f"Screener failed: {exc}")


# ---------------------------------------------------------------------------
# Results fragment — only this pane reruns on auto-refresh
# ---------------------------------------------------------------------------

def _make_results_fragment(run_every: int | None):
    @st.fragment(run_every=run_every)
    def _results_fragment():
        # On each auto-rerun, re-fetch data with the saved settings
        if st.session_state.get("auto_refresh"):
            _run_screener()

        if "results" not in st.session_state:
            st.info("Click **▶ Run Screener** or enable **Auto-refresh** to fetch data.")
            return

        res = st.session_state.results
        st.caption(
            f"Last updated: **{res['updated_at']}**  |  "
            f"Structure: **{res['method'].upper()}**"
            + ("  |  🔄 Auto-refreshing" if st.session_state.get("auto_refresh") else "")
        )

        st.subheader("HMM Regime")
        st.dataframe(_style_regime(res["regimes"]), width="stretch")
        st.caption("▲ Bullish  |  — Sideways  |  ▼ Bearish  |  ✕ Error")

        st.divider()

        st.subheader("Confluence Signals")
        st.dataframe(_style_signals(res["signals"]), width="stretch")
        st.caption(
            "★ STRONG BUY/SELL  |  ↑ WEAK BUY  |  ⊙ TAKE PROFIT  |  "
            "◎ WATCH  |  · NEUTRAL  |  ⏸ WAIT  |  ✕ AVOID"
        )

        st.divider()

        ref_tf = res["timeframes"][-1]
        st.subheader(f"Price Levels  (ref: {ref_tf} timeframe)")
        st.dataframe(_style_levels(res["levels"]), width="stretch")

    return _results_fragment


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("📊 HMM Market Regime Screener")

    # --- Auth ---
    if "access_token" not in st.session_state:
        token = auth.load_token()
        if token:
            st.session_state.access_token = token
        else:
            new_token = _auth_section()
            if new_token:
                st.session_state.access_token = new_token
                st.rerun()
            return

    auto_refresh: bool = st.session_state.get("auto_refresh", False)

    # --- Sidebar ---
    with st.sidebar:
        st.header("Settings")

        symbols = st.multiselect(
            "Symbols",
            options=config.ALL_SYMBOLS,
            default=st.session_state.get("run_settings", {}).get("symbols", config.DEFAULT_SYMBOLS),
        )
        tf_options = ["5", "15", "60", "D", "W"]
        timeframes = st.multiselect(
            "Timeframes",
            options=tf_options,
            default=st.session_state.get("run_settings", {}).get("timeframes", config.DEFAULT_TIMEFRAMES),
        )

        st.divider()
        st.subheader("Structure Detector")
        saved = st.session_state.get("run_settings", {})
        method = st.radio(
            "Method",
            options=["atr", "pivot"],
            index=0 if saved.get("method", config.STRUCTURE_METHOD) == "atr" else 1,
            horizontal=True,
        )
        proximity = st.slider(
            "Proximity %",
            min_value=0.5, max_value=5.0,
            value=float(saved.get("proximity", config.STRUCTURE_PROXIMITY_PCT)),
            step=0.5,
        )

        st.divider()

        # --- Manual run ---
        run_btn = st.button("▶  Run Screener", type="primary", width="stretch")

        # --- Auto-refresh ---
        st.subheader("Auto-refresh")
        interval_options = {"3 min": 3 * 60, "5 min": 5 * 60, "10 min": 10 * 60}
        interval_label = st.selectbox(
            "Interval",
            options=list(interval_options.keys()),
            index=1,
            disabled=auto_refresh,
        )
        interval_sec = interval_options[interval_label]

        if auto_refresh:
            if st.button("⏹  Stop Auto-refresh", width="stretch"):
                st.session_state.auto_refresh = False
                st.rerun()
            st.success(f"Refreshing every {interval_label}")
            last = st.session_state.get("results", {}).get("updated_at", "—")
            st.caption(f"Last run: {last}")
        else:
            if st.button("🔄  Start Auto-refresh", width="stretch"):
                if not symbols or not timeframes:
                    st.error("Select symbols and timeframes first.")
                else:
                    _save_settings(symbols, timeframes, method, proximity)
                    st.session_state.auto_refresh = True
                    st.session_state.refresh_interval_sec = interval_sec
                    st.rerun()

        st.divider()
        if st.button("🔒 Re-authenticate", width="stretch"):
            for key in ("access_token", "results", "auto_refresh", "run_settings"):
                st.session_state.pop(key, None)
            st.rerun()

    # --- Validate ---
    if not symbols or not timeframes:
        st.info("Select at least one symbol and one timeframe.")
        return

    # --- Manual run handler ---
    if run_btn:
        _save_settings(symbols, timeframes, method, proximity)
        _run_screener()

    # --- Results (fragment reruns on interval when auto-refresh is on) ---
    refresh_every = st.session_state.get("refresh_interval_sec") if auto_refresh else None
    results_fragment = _make_results_fragment(refresh_every)
    results_fragment()


def _save_settings(symbols, timeframes, method, proximity) -> None:
    config.STRUCTURE_METHOD = method
    config.STRUCTURE_PROXIMITY_PCT = proximity
    st.session_state.run_settings = {
        "symbols": symbols,
        "timeframes": timeframes,
        "method": method,
        "proximity": proximity,
    }


if __name__ == "__main__":
    main()
