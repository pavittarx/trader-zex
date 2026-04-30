"""
state.py — Reflex AppState for the HMM Market Regime Screener.

All event handlers and the background screener task live here.
Backend modules (auth, config, screener, …) are at the project root and
are importable because Reflex is run from that directory.
"""

import asyncio
import json
import queue
import threading
from datetime import datetime

import reflex as rx

import auth as fyers_auth
import config as app_config
from fyers_client import FyersClient
from screener import Screener
from universe import get_cached_symbols
import pandas as pd
from trader_zex.table_html import _REGIME_CLASS, _SIGNAL_CLASS, _LOCATION_CLASS, fmt_age

_TF_ORDER = ["5", "15", "60", "D", "W"]
_INTERVAL_MAP = {"1 min": 60, "3 min": 180, "5 min": 300, "10 min": 600}


def _build_result_rows(
    regimes: pd.DataFrame,
    signals: pd.DataFrame,
    levels: pd.DataFrame,
    timeframes: list[str],
    symbol_times: dict[str, datetime],
) -> list[dict[str, str]]:
    """Convert screener DataFrames into a flat list[dict[str,str]] for Reflex state."""
    tfs = timeframes[:5]  # cap at 5 rendered columns
    rows: list[dict[str, str]] = []

    for sym in regimes.index:
        label = sym.replace("NSE:", "").replace("-EQ", "")
        price = str(regimes.at[sym, "Price"]) if "Price" in regimes.columns else "—"
        chg   = str(regimes.at[sym, "Chg%"])  if "Chg%"  in regimes.columns else "—"
        chg_up = "true" if chg.startswith("▲") else "false"

        def lv(col: str) -> str:
            return str(levels.at[sym, col]) if sym in levels.index and col in levels.columns else "—"

        loc     = lv("Location")
        loc_cls = _LOCATION_CLASS.get(loc.strip(), "")

        dt = symbol_times.get(sym)
        fetched, fetched_cls = fmt_age(dt) if dt else ("—", "age-none")

        row: dict[str, str] = {
            "sym": sym, "label": label,
            "price": price, "chg": chg, "chg_up": chg_up,
            "support": lv("Support"), "dist_s": lv("Dist_S%"),
            "resistance": lv("Resistance"), "dist_r": lv("Dist_R%"),
            "location": loc, "loc_cls": loc_cls,
            "fetched": fetched, "fetched_cls": fetched_cls,
        }

        for i, tf in enumerate(tfs):
            regime = str(regimes.at[sym, tf]) if tf in regimes.columns else "✕ Error"
            signal = str(signals.at[sym, tf]) if tf in signals.columns else "· NEUTRAL"
            row[f"r{i}"]  = regime
            row[f"rc{i}"] = _REGIME_CLASS.get(regime.strip(), "error")
            row[f"s{i}"]  = signal
            row[f"sc{i}"] = _SIGNAL_CLASS.get(signal.strip(), "neutral")

        rows.append(row)

    return rows


class AppState(rx.State):
    # ---- Auth ----
    access_token: str = ""
    auth_url: str = ""
    auth_code: str = ""
    auth_error: str = ""

    # ---- Watchlist / symbol options ----
    selected_symbols: list[str] = list(app_config.DEFAULT_SYMBOLS)
    all_symbol_options: list[str] = sorted(app_config.ALL_SYMBOLS)
    # Multi-add popover state
    symbol_search: str = ""
    symbols_to_add: list[str] = []

    # ---- Timeframes ----
    selected_timeframes: list[str] = list(app_config.DEFAULT_TIMEFRAMES)

    # ---- Structure settings ----
    method: str = app_config.STRUCTURE_METHOD
    proximity: float = app_config.STRUCTURE_PROXIMITY_PCT

    # ---- Auto-refresh ----
    auto_refresh: bool = False
    refresh_interval_label: str = "5 min"

    # ---- Screener runtime ----
    is_running: bool = False
    progress: int = 0
    total: int = 0
    status_text: str = ""
    updated_at: str = ""
    symbol_times: dict[str, str] = {}       # sym → ISO datetime string
    # Result rows: list of flat string dicts, one per symbol
    result_rows: list[dict[str, str]] = []
    # TF columns for the current result set (max 5)
    result_timeframes_display: list[str] = []
    n_result_tfs: int = 0

    # ------------------------------------------------------------------
    # Page load
    # ------------------------------------------------------------------

    def on_load(self) -> None:
        token = fyers_auth.load_token()
        if token:
            self.access_token = token
        else:
            self.auth_url = fyers_auth.build_auth_url()

        try:
            saved = json.loads(app_config.WATCHLIST_FILE.read_text())
            self.selected_symbols = saved
        except Exception:
            self.selected_symbols = list(app_config.DEFAULT_SYMBOLS)

        cached = get_cached_symbols()
        if cached:
            self.all_symbol_options = sorted(cached)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def set_auth_code(self, val: str) -> None:
        self.auth_code = val

    def authenticate(self) -> None:
        if not self.auth_code.strip():
            self.auth_error = "Please paste the auth_code first."
            return
        try:
            token = fyers_auth.generate_token(self.auth_code.strip())
            self.access_token = token
            self.auth_error = ""
        except Exception as exc:
            self.auth_error = f"Authentication failed: {exc}"

    def logout(self) -> None:
        self.access_token = ""
        self.auth_code = ""
        self.auth_url = fyers_auth.build_auth_url()
        self.table_html = ""
        self.symbol_times = {}
        self.is_running = False
        self.auto_refresh = False
        self.status_text = ""

    # ------------------------------------------------------------------
    # Symbol management
    # ------------------------------------------------------------------

    def set_symbol_search(self, val: str) -> None:
        self.symbol_search = val

    def toggle_symbol_selection(self, sym: str) -> None:
        if sym in self.symbols_to_add:
            self.symbols_to_add = [s for s in self.symbols_to_add if s != sym]
        else:
            self.symbols_to_add = self.symbols_to_add + [sym]

    def add_selected_symbols(self):
        current = set(self.selected_symbols)
        new_syms = [s for s in self.symbols_to_add if s not in current]
        if new_syms:
            self.selected_symbols = self.selected_symbols + new_syms
            self._persist_watchlist()
        self.symbols_to_add = []
        self.symbol_search = ""
        if new_syms:
            yield AppState.run_screener

    def clear_symbol_selection(self) -> None:
        self.symbols_to_add = []
        self.symbol_search = ""

    def remove_symbol(self, sym: str):
        remaining = [s for s in self.selected_symbols if s != sym]
        if not remaining:
            return
        self.selected_symbols = remaining
        self.result_rows = [r for r in self.result_rows if r["sym"] != sym]
        times = dict(self.symbol_times)
        times.pop(sym, None)
        self.symbol_times = times
        self._persist_watchlist()

    def save_watchlist(self) -> None:
        self._persist_watchlist()

    def _persist_watchlist(self) -> None:
        try:
            app_config.WATCHLIST_FILE.write_text(json.dumps(self.selected_symbols))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Computed vars
    # ------------------------------------------------------------------

    @rx.var
    def symbol_entries(self) -> list[dict[str, str]]:
        """Current watchlist as [{sym, label}] for UI rendering."""
        return [
            {"sym": s, "label": s.replace("NSE:", "").replace("-EQ", "")}
            for s in self.selected_symbols
        ]

    @rx.var
    def filtered_available(self) -> list[dict[str, str]]:
        """
        Searchable, capped symbol list for the multi-add popover.
        Each entry: {sym, label, checked}.  Max 50 results.
        """
        query = self.symbol_search.upper().strip()
        current = set(self.selected_symbols)
        pending = set(self.symbols_to_add)
        results: list[dict[str, str]] = []
        for s in self.all_symbol_options:
            if s in current:
                continue
            label = s.replace("NSE:", "").replace("-EQ", "")
            if query and query not in label.upper():
                continue
            results.append({
                "sym": s,
                "label": label,
                "checked": "true" if s in pending else "false",
            })
            if len(results) >= 50:
                break
        return results

    @rx.var
    def add_count_label(self) -> str:
        n = len(self.symbols_to_add)
        return f"{n} selected" if n else "None selected"

    @rx.var
    def has_pending_add(self) -> bool:
        return len(self.symbols_to_add) > 0

    @rx.var
    def tf_5_checked(self) -> bool:
        return "5" in self.selected_timeframes

    @rx.var
    def tf_15_checked(self) -> bool:
        return "15" in self.selected_timeframes

    @rx.var
    def tf_60_checked(self) -> bool:
        return "60" in self.selected_timeframes

    @rx.var
    def tf_d_checked(self) -> bool:
        return "D" in self.selected_timeframes

    @rx.var
    def tf_w_checked(self) -> bool:
        return "W" in self.selected_timeframes

    @rx.var
    def proximity_str(self) -> str:
        return f"{self.proximity:.1f}%"

    @rx.var
    def has_results(self) -> bool:
        return len(self.result_rows) > 0

    @rx.var
    def tf_labels_padded(self) -> list[str]:
        """5-element list of TF labels (padded with "" so index access is always safe)."""
        labels = list(self.result_timeframes_display)
        while len(labels) < 5:
            labels.append("")
        return labels

    @rx.var
    def is_authenticated(self) -> bool:
        return self.access_token != ""

    # ------------------------------------------------------------------
    # Timeframe toggles (one handler per TF — avoids foreach closure issues)
    # ------------------------------------------------------------------

    def _set_tf(self, tf: str, checked: bool) -> None:
        current = set(self.selected_timeframes)
        if checked:
            current.add(tf)
        else:
            current.discard(tf)
        self.selected_timeframes = [t for t in _TF_ORDER if t in current]

    def toggle_tf_5(self, checked: bool) -> None:
        self._set_tf("5", checked)

    def toggle_tf_15(self, checked: bool) -> None:
        self._set_tf("15", checked)

    def toggle_tf_60(self, checked: bool) -> None:
        self._set_tf("60", checked)

    def toggle_tf_d(self, checked: bool) -> None:
        self._set_tf("D", checked)

    def toggle_tf_w(self, checked: bool) -> None:
        self._set_tf("W", checked)

    # ------------------------------------------------------------------
    # Structure settings
    # ------------------------------------------------------------------

    def set_method(self, val: str) -> None:
        self.method = val

    def set_proximity(self, val: list[float]) -> None:
        if val:
            self.proximity = val[0]

    # ------------------------------------------------------------------
    # Auto-refresh
    # ------------------------------------------------------------------

    def set_refresh_interval(self, label: str) -> None:
        self.refresh_interval_label = label

    def toggle_auto_refresh(self):
        if self.auto_refresh:
            self.auto_refresh = False
            return
        if not self.selected_symbols or not self.selected_timeframes:
            return
        self.auto_refresh = True
        yield AppState.run_screener

    # ------------------------------------------------------------------
    # Background screener task
    # ------------------------------------------------------------------

    @rx.event(background=True)
    async def run_screener(self) -> None:
        async with self:
            if self.is_running:
                return
            self.is_running = True
            self.status_text = "Starting screener…"

        while True:
            # Snapshot settings + reset display state under lock
            async with self:
                token   = self.access_token
                syms    = list(self.selected_symbols)
                tfs     = list(self.selected_timeframes)
                method  = self.method
                prox    = self.proximity
                s_times = dict(self.symbol_times)
                self.result_rows = []
                self.result_timeframes_display = list(tfs[:5])
                self.n_result_tfs = len(tfs[:5])

            if not token or not syms or not tfs:
                async with self:
                    self.status_text = "Configure settings first."
                    self.is_running = False
                return

            try:
                client  = FyersClient(access_token=token)
                app_config.STRUCTURE_METHOD = method
                app_config.STRUCTURE_PROXIMITY_PCT = prox
                screener = Screener(client)

                result_q: queue.Queue = queue.Queue()

                def _worker() -> None:
                    try:
                        for item in screener.stream(syms, tfs):
                            result_q.put(("result", item))
                        result_q.put(("done", None))
                    except Exception as exc:
                        result_q.put(("error", exc))

                threading.Thread(target=_worker, daemon=True).start()

                seen: set[str] = set()
                new_times: dict[str, str] = dict(s_times)

                while True:
                    try:
                        kind, data = result_q.get_nowait()
                    except queue.Empty:
                        await asyncio.sleep(0.1)
                        continue

                    if kind == "error":
                        async with self:
                            self.status_text = f"Screener error: {data}"
                            self.is_running = False
                        return

                    if kind == "done":
                        now_str = datetime.now().strftime("%d %b %Y  %H:%M:%S")
                        async with self:
                            self.updated_at  = now_str
                            self.status_text = f"Last updated: {now_str}"
                        break

                    i, total, regimes, signals, levels = data
                    for sym in regimes.index:
                        if sym not in seen:
                            new_times[sym] = datetime.now().isoformat()
                            seen.add(sym)

                    dt_times = {k: datetime.fromisoformat(v) for k, v in new_times.items()}
                    rows = _build_result_rows(regimes, signals, levels, tfs, dt_times)

                    async with self:
                        self.symbol_times = dict(new_times)
                        self.progress     = i
                        self.total        = total
                        self.status_text  = f"Analysing {i} / {total}…"
                        self.result_rows  = rows

            except Exception as exc:
                async with self:
                    self.status_text = f"Unexpected error: {exc}"
                    self.is_running  = False
                return

            # Check auto-refresh
            async with self:
                keep_going    = self.auto_refresh
                interval_lbl  = self.refresh_interval_label

            if not keep_going:
                async with self:
                    self.is_running = False
                return

            wait_sec = _INTERVAL_MAP.get(interval_lbl, 300)
            # Sleep in small chunks so a toggle-off is responsive
            for _ in range(wait_sec * 10):
                await asyncio.sleep(0.1)
                async with self:
                    if not self.auto_refresh:
                        self.is_running = False
                        return
