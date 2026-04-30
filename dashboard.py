"""
dashboard.py — Streamlit UI for the HMM Market Regime Screener.

Run:
    uv run streamlit run dashboard.py
"""

import json
from datetime import datetime

import pandas as pd
import streamlit as st

import auth
import config
from fyers_client import FyersClient
from screener import Screener
from universe import get_cached_symbols

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



_REGIME_CLASS = {
    "▲ Bullish":  "bullish",
    "▼ Bearish":  "bearish",
    "— Sideways": "sideways",
    "✕ Error":    "error",
}
_SIGNAL_CLASS = {
    "★ STRONG BUY":  "strong-buy",
    "↑ WEAK BUY":    "weak-buy",
    "★ STRONG SELL": "strong-sell",
    "✕ AVOID":       "avoid",
    "⊙ TAKE PROFIT": "take-profit",
    "◎ WATCH":       "watch",
    "⏸ WAIT":        "wait",
    "· NEUTRAL":     "neutral",
}
_LOCATION_CLASS = {
    "At Support":    "at-support",
    "At Resistance": "at-resistance",
}

_TABLE_CSS = """
<style>
.sct { border-collapse: collapse; width: 100%; font-size: 13px;
       font-family: 'SF Mono','Fira Code','Consolas',monospace; }
.sct th, .sct td {
  border: 1px solid #252525; padding: 7px 14px;
  text-align: center; white-space: nowrap; }
.sct thead th {
  background: #181818; color: #777; font-weight: 600;
  font-size: 11px; letter-spacing: .6px; text-transform: uppercase; }
.sct thead tr:last-child th { color: #404040; font-size: 10px; }

/* Merged cells (Symbol, Price, Chg%, Support, Resistance, Dist) */
.sct .mrg { background: #111; color: #bbb; vertical-align: middle; }
.sct .alt  { background: #0a0a0a !important; }

/* Symbol cell */
.sct .sym { text-align: left; font-weight: 700; color: #fff;
            font-size: 13px; background: #111 !important; }
.sct .sym.alt { background: #0a0a0a !important; }

/* Location cell — separate class so location colors aren't beaten by .mrg */
.sct .loc { vertical-align: middle; font-weight: 500; }

/* Thick border separating each symbol group */
.sct tr.grp > td { border-top: 2px solid #333 !important; }

/* Regime */
.sct .bullish  { background:#1a3d28; color:#4fc870; font-weight:600; }
.sct .bearish  { background:#3d1a1a; color:#f05555; font-weight:600; }
.sct .sideways { background:#362800; color:#d98e00; font-weight:600; }
.sct .error    { color:#555; }

/* Signals */
.sct .strong-buy  { background:#143322; color:#00e676; font-weight:700; }
.sct .weak-buy    { background:#1a3324; color:#5ed898; }
.sct .strong-sell { background:#331416; color:#ff4455; font-weight:700; }
.sct .avoid       { background:#2b1315; color:#e06060; }
.sct .take-profit { background:#2b2700; color:#ffe040; }
.sct .watch       { background:#132534; color:#3db8f5; }
.sct .wait        { background:#16163a; color:#a090d0; }
.sct .neutral     { color:#505050; }

/* Location — explicit !important beats .alt on odd rows */
.sct .at-support    { background:#1a3d28 !important; color:#4fc870 !important;
                      font-weight:600; }
.sct .at-resistance { background:#3d1a1a !important; color:#f05555 !important;
                      font-weight:600; }

/* Chg% */
.sct .chg-up { color:#4fc870; font-weight:600; }
.sct .chg-dn { color:#f05555; font-weight:600; }

/* Last-fetched age */
.sct .age-fresh { color:#4fc870; font-size:11px; }
.sct .age-stale { color:#d98e00; font-size:11px; }
.sct .age-old   { color:#f05555; font-size:11px; }
.sct .age-none  { color:#404040; font-size:11px; }
</style>
"""


def _fmt_age(dt: datetime) -> tuple[str, str]:
    elapsed = (datetime.now() - dt).total_seconds()
    if elapsed < 90:
        return "just now", "age-fresh"
    if elapsed < 300:
        return f"{int(elapsed / 60)}m ago", "age-fresh"
    if elapsed < 3600:
        return f"{int(elapsed / 60)}m ago", "age-stale"
    return f"{int(elapsed / 3600)}h ago", "age-old"


def _render_table_html(
    regimes: pd.DataFrame,
    signals: pd.DataFrame,
    levels: pd.DataFrame,
    timeframes: list[str],
    symbol_times: dict[str, datetime] | None = None,
) -> str:
    # Header: two sub-rows — timeframe name, then "signal" label
    tf_th   = "".join(f"<th>{tf}</th>" for tf in timeframes)
    tf_sig  = "".join(f"<th>sig</th>" for _ in timeframes)
    header = f"""
      <tr>
        <th rowspan="2">Symbol</th>
        <th rowspan="2">Price</th>
        <th rowspan="2">Chg%</th>
        {tf_th}
        <th rowspan="2">Support</th>
        <th rowspan="2">Dist S%</th>
        <th rowspan="2">Resistance</th>
        <th rowspan="2">Dist R%</th>
        <th rowspan="2">Location</th>
        <th rowspan="2">Fetched</th>
      </tr>
      <tr>{tf_sig}</tr>
    """

    has_price = "Price" in regimes.columns
    has_chg   = "Chg%"  in regimes.columns
    reg_cols  = [tf for tf in timeframes if tf in regimes.columns]
    sig_cols  = [tf for tf in timeframes if tf in signals.columns]
    lv_cols   = levels.columns.tolist() if not levels.empty else []

    _CHG_CLASS = {"▲": "chg-up", "▼": "chg-dn"}

    def lv(sym: str, col: str) -> str:
        return str(levels.at[sym, col]) if sym in levels.index and col in lv_cols else "—"

    rows = []
    for i, sym in enumerate(regimes.index):
        alt     = "alt" if i % 2 else ""
        label   = sym.replace("NSE:", "").replace("-EQ", "")
        price   = str(regimes.at[sym, "Price"]) if has_price else "—"
        chg     = str(regimes.at[sym, "Chg%"])  if has_chg  else "—"
        chg_cls = _CHG_CLASS.get(chg[0], "") if chg else ""

        reg_cells = "".join(
            f'<td class="{_REGIME_CLASS.get(str(regimes.at[sym, tf]).strip(), "error")}">'
            f'{regimes.at[sym, tf]}</td>'
            for tf in reg_cols
        )
        sig_cells = "".join(
            f'<td class="{_SIGNAL_CLASS.get(str(signals.at[sym, tf]).strip(), "neutral")}">'
            f'{signals.at[sym, tf]}</td>'
            for tf in sig_cols
        )
        loc     = lv(sym, "Location")
        loc_cls = _LOCATION_CLASS.get(loc.strip(), "")

        dt = symbol_times.get(sym) if symbol_times else None
        if dt:
            age_txt, age_cls = _fmt_age(dt)
        else:
            age_txt, age_cls = "—", "age-none"

        rows.append(f"""
          <tr class="grp">
            <td rowspan="2" class="sym {alt}">{label}</td>
            <td rowspan="2" class="mrg {alt}">{price}</td>
            <td rowspan="2" class="mrg {alt} {chg_cls}">{chg}</td>
            {reg_cells}
            <td rowspan="2" class="mrg {alt}">{lv(sym, "Support")}</td>
            <td rowspan="2" class="mrg {alt}">{lv(sym, "Dist_S%")}</td>
            <td rowspan="2" class="mrg {alt}">{lv(sym, "Resistance")}</td>
            <td rowspan="2" class="mrg {alt}">{lv(sym, "Dist_R%")}</td>
            <td rowspan="2" class="loc {alt} {loc_cls}">{loc}</td>
            <td rowspan="2" class="mrg {alt} {age_cls}">{age_txt}</td>
          </tr>
          <tr>{sig_cells}</tr>
        """)

    return f"""
      {_TABLE_CSS}
      <div style="overflow-x:auto">
        <table class="sct">
          <thead>{header}</thead>
          <tbody>{"".join(rows)}</tbody>
        </table>
      </div>
    """


# ---------------------------------------------------------------------------
# Watchlist helpers
# ---------------------------------------------------------------------------

def _load_watchlist() -> list[str]:
    try:
        return json.loads(config.WATCHLIST_FILE.read_text())
    except Exception:
        return config.DEFAULT_SYMBOLS


def _save_watchlist(symbols: list[str]) -> None:
    config.WATCHLIST_FILE.write_text(json.dumps(symbols))


def _symbol_options() -> list[str]:
    symbols = get_cached_symbols()
    return sorted(symbols) if symbols else config.ALL_SYMBOLS


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
# Results display (shared by streaming loop and static re-render)
# ---------------------------------------------------------------------------

def _show_tables(
    regimes: pd.DataFrame,
    signals: pd.DataFrame,
    levels: pd.DataFrame,
    timeframes: list[str],
    method: str,
    *,
    status_line: str = "",
    allow_remove: bool = False,
    symbol_times: dict[str, datetime] | None = None,
) -> tuple[str, str] | None:
    """Render the combined table.

    Returns ``("remove", sym)`` or ``("add", sym)`` when the user clicks a
    remove/add button, otherwise ``None``.
    """
    if status_line:
        st.caption(status_line)
    st.html(_render_table_html(regimes, signals, levels, timeframes, symbol_times))
    st.caption(
        f"Row 1: HMM Regime · Row 2: Confluence Signal · "
        f"Levels ref: {timeframes[-1]} ({method.upper()})"
    )

    if not allow_remove:
        return None

    syms   = list(regimes.index)
    labels = [s.replace("NSE:", "").replace("-EQ", "") for s in syms]

    st.markdown("**Remove from watchlist:**")
    n_cols = min(10, len(syms))
    cols = st.columns(n_cols)
    for i, (sym, lbl) in enumerate(zip(syms, labels)):
        if cols[i % n_cols].button(f"✕ {lbl}", key=f"rm_{sym}", use_container_width=True):
            return ("remove", sym)

    # Add symbol — show only symbols not already in the watchlist
    available = [s for s in _symbol_options() if s not in set(syms)]
    if available:
        st.markdown("**Add symbol to watchlist:**")
        add_cols = st.columns([3, 1])
        chosen = add_cols[0].selectbox(
            "Search symbol",
            options=[None] + available,
            format_func=lambda s: "— select —" if s is None else s.replace("NSE:", "").replace("-EQ", ""),
            key="add_sym_select",
            label_visibility="collapsed",
        )
        if add_cols[1].button("＋ Add", key="add_sym_btn", use_container_width=True, disabled=chosen is None):
            return ("add", chosen)

    return None


# ---------------------------------------------------------------------------
# Results fragment
# ---------------------------------------------------------------------------

def _make_results_fragment(refresh_every: int | None):
    @st.fragment(run_every=refresh_every)
    def _results_fragment():
        trigger = st.session_state.pop("trigger_run", False)
        is_auto = st.session_state.get("auto_refresh", False)
        should_run = trigger or is_auto

        if "symbol_times" not in st.session_state:
            st.session_state.symbol_times = {}

        result_ph = st.empty()

        if not should_run:
            res = st.session_state.get("results")
            if not res:
                result_ph.info("Click **▶ Run Screener** or enable **Auto-refresh** to fetch data.")
                return
            with result_ph.container():
                action = _show_tables(
                    res["regimes"], res["signals"], res["levels"],
                    res["timeframes"], res["method"],
                    status_line=(
                        f"Last updated: **{res['updated_at']}**"
                        + ("  |  🔄 Auto-refreshing" if is_auto else "")
                    ),
                    allow_remove=True,
                    symbol_times=st.session_state.symbol_times,
                )
            if action:
                kind, sym = action
                syms = list(res["regimes"].index)
                if kind == "remove":
                    remaining = [s for s in syms if s != sym]
                    if not remaining:
                        st.warning("Cannot remove the last symbol.")
                        st.rerun()
                        return
                    st.session_state.symbol_times.pop(sym, None)
                    new_syms = remaining
                else:  # "add"
                    new_syms = syms + [sym]
                _save_watchlist(new_syms)
                st.session_state.run_settings["symbols"] = new_syms
                st.session_state.trigger_run = True
                st.rerun()
            return

        settings = st.session_state.get("run_settings")
        if not settings:
            result_ph.info("Configure settings in the sidebar first.")
            return

        syms = settings["symbols"]
        tfs = settings["timeframes"]
        method = settings["method"]

        try:
            client = FyersClient(access_token=st.session_state.access_token)
            screener = Screener(client)

            last: tuple | None = None
            seen: set[str] = set()
            for i, total, regimes, signals, levels in screener.stream(syms, tfs):
                last = (regimes, signals, levels)
                # Record fetch time for each newly appeared symbol
                for sym in regimes.index:
                    if sym not in seen:
                        st.session_state.symbol_times[sym] = datetime.now()
                        seen.add(sym)
                with result_ph.container():
                    _show_tables(
                        regimes, signals, levels, tfs, method,
                        status_line=f"⏳ Analysing **{i} / {total}** …",
                        symbol_times=st.session_state.symbol_times,
                    )

            if last:
                regimes, signals, levels = last
                updated_at = datetime.now().strftime("%d %b %Y  %H:%M:%S")
                st.session_state.results = {
                    "regimes": regimes, "signals": signals, "levels": levels,
                    "updated_at": updated_at, "timeframes": tfs, "method": method,
                }
                with result_ph.container():
                    _show_tables(
                        regimes, signals, levels, tfs, method,
                        status_line=(
                            f"Last updated: **{updated_at}**"
                            + ("  |  🔄 Auto-refreshing" if is_auto else "")
                        ),
                        allow_remove=True,
                        symbol_times=st.session_state.symbol_times,
                    )

        except Exception as exc:
            result_ph.error(f"Screener error: {exc}")

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

        # Symbol picker
        options = _symbol_options()
        watchlist = st.session_state.get("run_settings", {}).get("symbols") or _load_watchlist()
        # Ensure saved symbols appear in options even if universe changed
        all_options = sorted(set(options) | set(watchlist))
        default = [s for s in watchlist if s in all_options]

        symbols = st.multiselect(
            "Symbols",
            options=all_options,
            default=default,
            key=f"sym_ms_{','.join(sorted(default))}",
        )
        col1, col2 = st.columns([3, 2])
        col1.caption(f"{len(symbols)} symbol{'s' if len(symbols) != 1 else ''} selected")
        if col2.button("💾 Save list", use_container_width=True, disabled=not symbols):
            _save_watchlist(symbols)
            st.toast("Watchlist saved!", icon="💾")

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

        run_btn = st.button("▶  Run Screener", type="primary", use_container_width=True)

        st.subheader("Auto-refresh")
        interval_options = {"1 min": 60, "3 min": 3 * 60, "5 min": 5 * 60, "10 min": 10 * 60}
        interval_label = st.selectbox(
            "Interval",
            options=list(interval_options.keys()),
            index=2,
            disabled=auto_refresh,
        )
        interval_sec = interval_options[interval_label]

        if auto_refresh:
            if st.button("⏹  Stop Auto-refresh", use_container_width=True):
                st.session_state.auto_refresh = False
                st.rerun()
            st.success(f"Refreshing every {interval_label}")
            last = st.session_state.get("results", {}).get("updated_at", "—")
            st.caption(f"Last run: {last}")
        else:
            if st.button("🔄  Start Auto-refresh", use_container_width=True):
                if not symbols or not timeframes:
                    st.error("Select symbols and timeframes first.")
                else:
                    _save_settings(symbols, timeframes, method, proximity)
                    st.session_state.auto_refresh = True
                    st.session_state.refresh_interval_sec = interval_sec
                    st.rerun()

        st.divider()
        if st.button("🔒 Re-authenticate", use_container_width=True):
            for key in ("access_token", "results", "auto_refresh", "run_settings"):
                st.session_state.pop(key, None)
            st.rerun()

    # --- Validate ---
    if not symbols or not timeframes:
        st.info("Select at least one symbol and one timeframe.")
        return

    # --- Manual run ---
    if run_btn:
        _save_settings(symbols, timeframes, method, proximity)
        st.session_state.trigger_run = True
        st.rerun()

    # --- Results (fragment reruns on interval when auto-refresh is on) ---
    refresh_every = st.session_state.get("refresh_interval_sec") if auto_refresh else None
    _make_results_fragment(refresh_every)()


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
