"""
trader_zex.py — Reflex UI for the HMM Market Regime Screener.

Run:
    reflex run
"""

import reflex as rx

from trader_zex.state import AppState

# ---------------------------------------------------------------------------
# Results table helpers
# ---------------------------------------------------------------------------

def _regime_badge(regime: rx.Var, cls: rx.Var) -> rx.Component:
    return rx.badge(
        regime,
        color_scheme=rx.match(
            cls,
            ("bullish",  "green"),
            ("bearish",  "red"),
            ("sideways", "yellow"),
            "gray",
        ),
        size="1",
        style={"font_size": "11px", "white_space": "nowrap"},
    )


def _signal_badge(signal: rx.Var, cls: rx.Var) -> rx.Component:
    return rx.badge(
        signal,
        color_scheme=rx.match(
            cls,
            ("strong-buy",  "jade"),
            ("weak-buy",    "teal"),
            ("strong-sell", "red"),
            ("avoid",       "crimson"),
            ("take-profit", "yellow"),
            ("watch",       "blue"),
            ("wait",        "violet"),
            "gray",
        ),
        variant="soft",
        size="1",
        style={"font_size": "11px", "white_space": "nowrap"},
    )


def _tf_header_cell(i: int) -> rx.Component:
    """Renders the i-th TF column header, or nothing if fewer TFs were selected."""
    return rx.cond(
        AppState.n_result_tfs > i,
        rx.table.column_header_cell(
            AppState.tf_labels_padded[i],
            white_space="nowrap",
            text_align="center",
        ),
        rx.fragment(),
    )


def _tf_data_cell(row: rx.Var, i: int) -> rx.Component:
    """Renders regime + signal badges stacked in the i-th TF cell."""
    rk, rck, sk, sck = f"r{i}", f"rc{i}", f"s{i}", f"sc{i}"
    return rx.cond(
        AppState.n_result_tfs > i,
        rx.table.cell(
            rx.vstack(
                _regime_badge(row[rk], row[rck]),
                _signal_badge(row[sk], row[sck]),
                spacing="1",
                align="center",
            ),
            text_align="center",
            padding="6px 8px",
        ),
        rx.fragment(),
    )


def _result_row(row: rx.Var) -> rx.Component:
    return rx.table.row(
        rx.table.cell(row["label"], font_weight="700", white_space="nowrap"),
        rx.table.cell(row["price"], white_space="nowrap"),
        rx.table.cell(
            row["chg"],
            color=rx.cond(row["chg_up"] == "true", "var(--green-10)", "var(--red-10)"),
            font_weight="600",
            white_space="nowrap",
        ),
        _tf_data_cell(row, 0),
        _tf_data_cell(row, 1),
        _tf_data_cell(row, 2),
        _tf_data_cell(row, 3),
        _tf_data_cell(row, 4),
        rx.table.cell(row["support"], white_space="nowrap"),
        rx.table.cell(row["dist_s"],  white_space="nowrap"),
        rx.table.cell(row["resistance"], white_space="nowrap"),
        rx.table.cell(row["dist_r"],  white_space="nowrap"),
        rx.table.cell(
            row["location"],
            color=rx.match(
                row["loc_cls"],
                ("at-support",    "var(--green-10)"),
                ("at-resistance", "var(--red-10)"),
                "inherit",
            ),
            font_weight=rx.match(
                row["loc_cls"],
                ("at-support",    "600"),
                ("at-resistance", "600"),
                "400",
            ),
            white_space="nowrap",
        ),
        rx.table.cell(
            row["fetched"],
            font_size="11px",
            color=rx.match(
                row["fetched_cls"],
                ("age-fresh", "var(--green-10)"),
                ("age-stale", "var(--yellow-10)"),
                ("age-old",   "var(--red-10)"),
                "var(--gray-8)",
            ),
            white_space="nowrap",
        ),
        rx.table.cell(
            rx.icon_button(
                rx.icon("x", size=12),
                on_click=AppState.remove_symbol(row["sym"]),
                size="1",
                variant="ghost",
                color_scheme="red",
            ),
            padding="2px 6px",
        ),
    )


def _results_table() -> rx.Component:
    return rx.scroll_area(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Symbol"),
                    rx.table.column_header_cell("Price"),
                    rx.table.column_header_cell("Chg%"),
                    _tf_header_cell(0),
                    _tf_header_cell(1),
                    _tf_header_cell(2),
                    _tf_header_cell(3),
                    _tf_header_cell(4),
                    rx.table.column_header_cell("Support"),
                    rx.table.column_header_cell("Dist S%"),
                    rx.table.column_header_cell("Resistance"),
                    rx.table.column_header_cell("Dist R%"),
                    rx.table.column_header_cell("Location"),
                    rx.table.column_header_cell("Fetched"),
                    rx.table.column_header_cell(""),
                ),
            ),
            rx.table.body(
                rx.foreach(AppState.result_rows, _result_row),
            ),
            variant="surface",
            size="1",
            style={
                "font_family": "'SF Mono','Fira Code','Consolas',monospace",
                "font_size":   "12px",
            },
            width="100%",
        ),
        type="always",
        scrollbars="horizontal",
        width="100%",
    )

# ---------------------------------------------------------------------------
# Auth page
# ---------------------------------------------------------------------------

def auth_page() -> rx.Component:
    return rx.center(
        rx.card(
            rx.vstack(
                rx.heading("Trader-Zex", size="7"),
                rx.text("Authentication Required", color_scheme="gray", size="2"),
                rx.divider(),
                rx.text(
                    "Step 1 — Open this URL in your browser and log in:",
                    weight="medium",
                ),
                rx.box(
                    rx.text(
                        AppState.auth_url,
                        font_family="'SF Mono','Fira Code','Consolas',monospace",
                        font_size="11px",
                        word_break="break-all",
                    ),
                    background="#111",
                    border="1px solid #333",
                    border_radius="6px",
                    padding="0.75em",
                    width="100%",
                ),
                rx.text(
                    "Step 2 — Paste the auth_code from the redirect URL:",
                    weight="medium",
                ),
                rx.input(
                    placeholder="Paste auth_code here…",
                    value=AppState.auth_code,
                    on_change=AppState.set_auth_code,
                    width="100%",
                ),
                rx.button(
                    "Authenticate",
                    on_click=AppState.authenticate,
                    width="100%",
                    color_scheme="jade",
                ),
                rx.cond(
                    AppState.auth_error != "",
                    rx.callout(
                        AppState.auth_error,
                        color_scheme="red",
                        icon="circle_alert",
                        width="100%",
                    ),
                ),
                spacing="4",
                width="100%",
            ),
            width="480px",
            padding="2em",
        ),
        width="100%",
        min_height="100vh",
    )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _symbol_tags() -> rx.Component:
    return rx.flex(
        rx.foreach(
            AppState.symbol_entries,
            lambda entry: rx.badge(
                entry["label"],
                rx.icon(
                    "x",
                    size=12,
                    cursor="pointer",
                    on_click=AppState.remove_symbol(entry["sym"]),
                    style={"margin_left": "4px"},
                ),
                variant="soft",
                color_scheme="gray",
                style={"cursor": "default"},
            ),
        ),
        wrap="wrap",
        gap="1",
    )


def _add_symbol_popover() -> rx.Component:
    return rx.popover.root(
        rx.popover.trigger(
            rx.button(
                rx.icon("plus", size=14),
                " Add Symbols",
                variant="soft",
                color_scheme="jade",
                size="2",
                width="100%",
            ),
        ),
        rx.popover.content(
            rx.vstack(
                rx.input(
                    placeholder="Search symbols…",
                    value=AppState.symbol_search,
                    on_change=AppState.set_symbol_search,
                    width="100%",
                ),
                rx.scroll_area(
                    rx.vstack(
                        rx.foreach(
                            AppState.filtered_available,
                            lambda item: rx.button(
                                rx.hstack(
                                    rx.cond(
                                        item["checked"] == "true",
                                        rx.text("✓", color_scheme="jade", weight="bold"),
                                        rx.text("○", color_scheme="gray"),
                                    ),
                                    rx.text(item["label"], size="2"),
                                    spacing="2",
                                    align="center",
                                ),
                                on_click=AppState.toggle_symbol_selection(item["sym"]),
                                variant="ghost",
                                color_scheme=rx.cond(
                                    item["checked"] == "true", "jade", "gray"
                                ),
                                size="2",
                                width="100%",
                                justify="start",
                            ),
                        ),
                        spacing="0",
                        width="100%",
                        align="start",
                    ),
                    height="260px",
                    width="100%",
                ),
                rx.hstack(
                    rx.text(AppState.add_count_label, size="1", color_scheme="gray"),
                    rx.hstack(
                        rx.popover.close(
                            rx.button(
                                "Cancel",
                                variant="ghost",
                                color_scheme="gray",
                                size="2",
                                on_click=AppState.clear_symbol_selection,
                            ),
                        ),
                        rx.popover.close(
                            rx.button(
                                "Add Selected",
                                color_scheme="jade",
                                size="2",
                                disabled=~AppState.has_pending_add,
                                on_click=AppState.add_selected_symbols,
                            ),
                        ),
                        spacing="2",
                    ),
                    justify="between",
                    width="100%",
                    align="center",
                ),
                spacing="3",
                width="260px",
            ),
            padding="1em",
        ),
    )


def _timeframe_checkboxes() -> rx.Component:
    return rx.flex(
        rx.checkbox(
            "5min",
            checked=AppState.tf_5_checked,
            on_change=AppState.toggle_tf_5,
        ),
        rx.checkbox(
            "15min",
            checked=AppState.tf_15_checked,
            on_change=AppState.toggle_tf_15,
        ),
        rx.checkbox(
            "60min",
            checked=AppState.tf_60_checked,
            on_change=AppState.toggle_tf_60,
        ),
        rx.checkbox(
            "Daily",
            checked=AppState.tf_d_checked,
            on_change=AppState.toggle_tf_d,
        ),
        rx.checkbox(
            "Weekly",
            checked=AppState.tf_w_checked,
            on_change=AppState.toggle_tf_w,
        ),
        direction="row",
        wrap="wrap",
        gap="3",
    )


def sidebar() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.heading("Trader-Zex", size="5"),
            rx.text("HMM Regime Screener", size="1", color_scheme="gray"),

            rx.divider(),

            # ---- Symbols ----
            rx.text("Watchlist", weight="bold", size="2"),
            _symbol_tags(),
            _add_symbol_popover(),
            rx.button(
                rx.icon("save", size=14),
                " Save list",
                on_click=AppState.save_watchlist,
                size="1",
                variant="soft",
                color_scheme="gray",
            ),

            rx.divider(),

            # ---- Timeframes ----
            rx.text("Timeframes", weight="bold", size="2"),
            _timeframe_checkboxes(),

            rx.divider(),

            # ---- Structure ----
            rx.text("Structure Detector", weight="bold", size="2"),
            rx.text("Method", size="1", color_scheme="gray"),
            rx.radio_group.root(
                rx.hstack(
                    rx.radio_group.item("ATR", value="atr"),
                    rx.text("ATR", size="2"),
                    rx.radio_group.item("Pivot", value="pivot"),
                    rx.text("Pivot", size="2"),
                    spacing="2",
                    align="center",
                ),
                value=AppState.method,
                on_change=AppState.set_method,
            ),
            rx.vstack(
                rx.hstack(
                    rx.text("Proximity %", size="2"),
                    rx.badge(AppState.proximity_str, size="1"),
                    justify="between",
                    width="100%",
                ),
                rx.slider(
                    min=0.5,
                    max=5.0,
                    step=0.5,
                    value=[AppState.proximity],
                    on_value_commit=AppState.set_proximity,
                    width="100%",
                ),
                width="100%",
                spacing="2",
            ),

            rx.divider(),

            # ---- Run ----
            rx.button(
                rx.cond(
                    AppState.is_running,
                    rx.hstack(rx.spinner(size="2"), rx.text("Running…"), spacing="2"),
                    rx.text("▶  Run Screener"),
                ),
                on_click=AppState.run_screener,
                width="100%",
                color_scheme="jade",
                disabled=AppState.is_running,
            ),

            rx.divider(),

            # ---- Auto-refresh ----
            rx.text("Auto-refresh", weight="bold", size="2"),
            rx.select.root(
                rx.select.trigger(width="100%"),
                rx.select.content(
                    rx.select.item("1 min",  value="1 min"),
                    rx.select.item("3 min",  value="3 min"),
                    rx.select.item("5 min",  value="5 min"),
                    rx.select.item("10 min", value="10 min"),
                ),
                value=AppState.refresh_interval_label,
                on_change=AppState.set_refresh_interval,
                disabled=AppState.auto_refresh,
                width="100%",
            ),
            rx.button(
                rx.cond(
                    AppState.auto_refresh,
                    "⏹  Stop Auto-refresh",
                    "🔄  Start Auto-refresh",
                ),
                on_click=AppState.toggle_auto_refresh,
                width="100%",
                color_scheme=rx.cond(AppState.auto_refresh, "red", "blue"),
                variant="soft",
            ),
            rx.cond(
                AppState.auto_refresh,
                rx.callout(
                    rx.hstack(
                        rx.text(f"Refreshing every ", size="1"),
                        rx.text(AppState.refresh_interval_label, size="1", weight="bold"),
                        spacing="1",
                    ),
                    color_scheme="jade",
                    size="1",
                    width="100%",
                ),
            ),

            rx.divider(),

            # ---- Auth ----
            rx.button(
                "🔒 Re-authenticate",
                on_click=AppState.logout,
                width="100%",
                variant="ghost",
                color_scheme="gray",
                size="2",
            ),

            spacing="3",
            width="100%",
            align="start",
        ),
        width="280px",
        min_width="280px",
        padding="1.25em",
        border_right="1px solid #252525",
        min_height="100vh",
        overflow_y="auto",
        background="#0d0d0d",
        flex_shrink="0",
    )


# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

def results_section() -> rx.Component:
    return rx.box(
        rx.vstack(
            # Status bar
            rx.hstack(
                rx.cond(
                    AppState.is_running,
                    rx.hstack(
                        rx.spinner(size="2"),
                        rx.text(AppState.status_text, size="2", color_scheme="gray"),
                        spacing="2",
                    ),
                    rx.text(AppState.status_text, size="2", color_scheme="gray"),
                ),
                width="100%",
            ),

            # Table (or placeholder)
            rx.cond(
                AppState.has_results,
                rx.vstack(
                    _results_table(),
                    rx.text(
                        "Regime + Signal per timeframe · ✕ to remove from watchlist",
                        size="1",
                        color_scheme="gray",
                    ),
                    width="100%",
                    align="start",
                    spacing="2",
                ),
                rx.center(
                    rx.text(
                        "Click ▶ Run Screener in the sidebar to fetch data.",
                        size="3",
                        color_scheme="gray",
                    ),
                    width="100%",
                    padding="4em",
                ),
            ),

            width="100%",
            align="start",
            spacing="4",
        ),
        flex="1",
        padding="1.25em",
        overflow="auto",
        min_height="100vh",
    )


# ---------------------------------------------------------------------------
# Root page
# ---------------------------------------------------------------------------

def index() -> rx.Component:
    return rx.cond(
        AppState.is_authenticated,
        rx.hstack(
            sidebar(),
            results_section(),
            width="100%",
            min_height="100vh",
            align="start",
            spacing="0",
        ),
        auth_page(),
    )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = rx.App(
    theme=rx.theme(
        appearance="dark",
        accent_color="jade",
        gray_color="slate",
    ),
    stylesheets=[],
)
app.add_page(index, route="/", title="Trader-Zex | Regime Screener", on_load=AppState.on_load)
