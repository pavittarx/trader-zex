"""
table_html.py — Pure-Python HTML table renderer for the regime screener.

No Streamlit dependency; used by both the Reflex state and (optionally) tests.
"""

from datetime import datetime

import pandas as pd

_REGIME_CLASS: dict[str, str] = {
    "▲ Bullish":  "bullish",
    "▼ Bearish":  "bearish",
    "— Sideways": "sideways",
    "✕ Error":    "error",
}
_SIGNAL_CLASS: dict[str, str] = {
    "★ STRONG BUY":  "strong-buy",
    "↑ WEAK BUY":    "weak-buy",
    "★ STRONG SELL": "strong-sell",
    "✕ AVOID":       "avoid",
    "⊙ TAKE PROFIT": "take-profit",
    "◎ WATCH":       "watch",
    "⏸ WAIT":        "wait",
    "· NEUTRAL":     "neutral",
}
_LOCATION_CLASS: dict[str, str] = {
    "At Support":    "at-support",
    "At Resistance": "at-resistance",
}

TABLE_CSS = """
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

.sct .mrg { background: #111; color: #bbb; vertical-align: middle; }
.sct .alt  { background: #0a0a0a !important; }

.sct .sym { text-align: left; font-weight: 700; color: #fff;
            font-size: 13px; background: #111 !important; }
.sct .sym.alt { background: #0a0a0a !important; }

.sct .loc { vertical-align: middle; font-weight: 500; }

.sct tr.grp > td { border-top: 2px solid #333 !important; }

.sct .bullish  { background:#1a3d28; color:#4fc870; font-weight:600; }
.sct .bearish  { background:#3d1a1a; color:#f05555; font-weight:600; }
.sct .sideways { background:#362800; color:#d98e00; font-weight:600; }
.sct .error    { color:#555; }

.sct .strong-buy  { background:#143322; color:#00e676; font-weight:700; }
.sct .weak-buy    { background:#1a3324; color:#5ed898; }
.sct .strong-sell { background:#331416; color:#ff4455; font-weight:700; }
.sct .avoid       { background:#2b1315; color:#e06060; }
.sct .take-profit { background:#2b2700; color:#ffe040; }
.sct .watch       { background:#132534; color:#3db8f5; }
.sct .wait        { background:#16163a; color:#a090d0; }
.sct .neutral     { color:#505050; }

.sct .at-support    { background:#1a3d28 !important; color:#4fc870 !important;
                      font-weight:600; }
.sct .at-resistance { background:#3d1a1a !important; color:#f05555 !important;
                      font-weight:600; }

.sct .chg-up { color:#4fc870; font-weight:600; }
.sct .chg-dn { color:#f05555; font-weight:600; }

.sct .age-fresh { color:#4fc870; font-size:11px; }
.sct .age-stale { color:#d98e00; font-size:11px; }
.sct .age-old   { color:#f05555; font-size:11px; }
.sct .age-none  { color:#404040; font-size:11px; }
</style>
"""


def fmt_age(dt: datetime) -> tuple[str, str]:
    elapsed = (datetime.now() - dt).total_seconds()
    if elapsed < 90:
        return "just now", "age-fresh"
    if elapsed < 300:
        return f"{int(elapsed / 60)}m ago", "age-fresh"
    if elapsed < 3600:
        return f"{int(elapsed / 60)}m ago", "age-stale"
    return f"{int(elapsed / 3600)}h ago", "age-old"


def render_table_html(
    regimes: pd.DataFrame,
    signals: pd.DataFrame,
    levels: pd.DataFrame,
    timeframes: list[str],
    symbol_times: dict[str, datetime] | None = None,
) -> str:
    """Return a self-contained HTML string for the regime + signal table."""
    tf_th  = "".join(f"<th>{tf}</th>" for tf in timeframes)
    tf_sig = "".join("<th>sig</th>" for _ in timeframes)
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
            age_txt, age_cls = fmt_age(dt)
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
      {TABLE_CSS}
      <div style="overflow-x:auto">
        <table class="sct">
          <thead>{header}</thead>
          <tbody>{"".join(rows)}</tbody>
        </table>
      </div>
    """
