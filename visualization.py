"""
Visualization — plot price history with HMM regime regions as background shading.

Background shading (axvspan / add_vrect) makes regime boundaries immediately
obvious — far clearer than individual scatter dots.

Two backends:
  - matplotlib : static chart, good for saving to disk.
  - plotly     : interactive chart, good for exploration in a browser.
"""

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config
from hmm_model import HMMResult


# ------------------------------------------------------------------
# Shared helper
# ------------------------------------------------------------------

def _regime_spans(states: pd.Series) -> list[tuple]:
    """
    Collapse a per-bar regime Series into a list of (start, end, regime) tuples
    for each consecutive run of the same regime.
    """
    if states.empty:
        return []
    spans = []
    start = states.index[0]
    current = states.iloc[0]
    for ts, regime in states.items():
        if regime != current:
            spans.append((start, ts, current))
            current = regime
            start = ts
    spans.append((start, states.index[-1], current))
    return spans


def _regime_stats(states: pd.Series) -> dict[str, float]:
    """Return % time spent in each regime (for legend labels)."""
    counts = states.value_counts()
    total = len(states)
    return {r: counts.get(r, 0) / total * 100 for r in ("Bullish", "Sideways", "Bearish")}


# ------------------------------------------------------------------
# Matplotlib
# ------------------------------------------------------------------

def plot_matplotlib(
    data: pd.DataFrame,
    result: HMMResult,
    *,
    symbol: str = "",
    timeframe: str = "",
    figsize: tuple[int, int] = (16, 7),
) -> plt.Figure:
    """
    Static chart:
      - Row 1: candlestick price + regime background shading
      - Row 2: volume bars coloured by regime
    """
    aligned = data.loc[result.states.index]
    spans = _regime_spans(result.states)
    stats = _regime_stats(result.states)

    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1, figsize=figsize, sharex=True,
        gridspec_kw={"height_ratios": [4, 1]},
    )
    fig.patch.set_facecolor("#131722")
    for ax in (ax_price, ax_vol):
        ax.set_facecolor("#131722")
        ax.tick_params(colors="#9598a1")
        for spine in ax.spines.values():
            spine.set_color("#2a2e39")

    # --- Regime background shading ---
    added_labels: set[str] = set()
    for start, end, regime in spans:
        color = config.REGIME_COLORS.get(regime, "#9e9e9e")
        label = f"{regime} ({stats[regime]:.0f}%)" if regime not in added_labels else None
        ax_price.axvspan(start, end, alpha=0.18, color=color, label=label, zorder=1)
        ax_vol.axvspan(start, end, alpha=0.18, color=color, zorder=1)
        added_labels.add(regime)

    # --- Candlestick bars ---
    width = _bar_width(aligned.index)
    for ts, row in aligned.iterrows():
        is_up = row["close"] >= row["open"]
        body_color = "#26a69a" if is_up else "#ef5350"
        # Wick
        ax_price.plot([ts, ts], [row["low"], row["high"]], color=body_color, linewidth=0.6, zorder=2)
        # Body
        ax_price.bar(ts, abs(row["close"] - row["open"]),
                     bottom=min(row["open"], row["close"]),
                     color=body_color, width=width, zorder=2)

    # --- Volume bars ---
    vol_colors = result.states.map(
        lambda r: config.REGIME_COLORS.get(r, config.REGIME_COLORS["Unknown"])
    )
    ax_vol.bar(aligned.index, aligned["volume"],
               color=vol_colors.values, width=width, alpha=0.8, zorder=2)
    ax_vol.set_ylabel("Volume", color="#9598a1", fontsize=8)

    # --- Legend ---
    ax_price.legend(
        loc="upper left",
        facecolor="#1e222d", edgecolor="#2a2e39",
        labelcolor="#d1d4dc", fontsize=9,
        framealpha=0.9,
    )

    title = f"{symbol}  [{timeframe}]  —  HMM Market Regimes"
    ax_price.set_title(title, color="#d1d4dc", fontsize=13, pad=10)
    ax_price.set_ylabel("Price", color="#9598a1")
    ax_vol.set_xlabel("Date", color="#9598a1")

    # Current regime annotation
    current = result.current_regime
    color = config.REGIME_COLORS.get(current, "#ffffff")
    ax_price.annotate(
        f"Current: {current}",
        xy=(1, 1), xycoords="axes fraction",
        xytext=(-8, -8), textcoords="offset points",
        ha="right", va="top",
        fontsize=10, color=color, weight="bold",
        bbox=dict(boxstyle="round,pad=0.3", fc="#1e222d", ec=color, lw=1),
    )

    fig.tight_layout()
    return fig


def _bar_width(index: pd.Index):
    """Estimate a sensible candle body width from the index spacing."""
    if len(index) < 2:
        return 0.8
    delta = (index[1] - index[0])
    try:
        seconds = delta.total_seconds()
        return pd.Timedelta(seconds=seconds * 0.6)
    except AttributeError:
        return delta * 0.6


# ------------------------------------------------------------------
# Plotly
# ------------------------------------------------------------------

def plot_plotly(
    data: pd.DataFrame,
    result: HMMResult,
    *,
    symbol: str = "",
    timeframe: str = "",
) -> go.Figure:
    """
    Interactive Plotly chart:
      - Row 1: candlestick + regime background shading via vrect
      - Row 2: volume bars coloured by regime
    """
    aligned = data.loc[result.states.index]
    spans = _regime_spans(result.states)
    stats = _regime_stats(result.states)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.78, 0.22],
        vertical_spacing=0.02,
    )

    # --- Candlestick ---
    fig.add_trace(
        go.Candlestick(
            x=aligned.index,
            open=aligned["open"],
            high=aligned["high"],
            low=aligned["low"],
            close=aligned["close"],
            name="OHLC",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            showlegend=False,
        ),
        row=1, col=1,
    )

    # --- Volume bars coloured by regime ---
    vol_colors = result.states.map(
        lambda r: config.REGIME_COLORS.get(r, config.REGIME_COLORS["Unknown"])
    )
    fig.add_trace(
        go.Bar(
            x=aligned.index,
            y=aligned["volume"],
            marker_color=vol_colors.values,
            name="Volume",
            opacity=0.7,
            showlegend=False,
        ),
        row=2, col=1,
    )

    # --- Regime background shading (vrect) ---
    added_labels: set[str] = set()
    for start, end, regime in spans:
        color = config.REGIME_COLORS.get(regime, "#9e9e9e")
        show_legend = regime not in added_labels
        label = f"{regime} ({stats[regime]:.0f}%)"

        # Invisible scatter trace just to get a legend entry
        if show_legend:
            fig.add_trace(
                go.Scatter(
                    x=[None], y=[None],
                    mode="markers",
                    marker=dict(color=color, size=10, symbol="square"),
                    name=label,
                    showlegend=True,
                ),
                row=1, col=1,
            )
            added_labels.add(regime)

        fig.add_vrect(
            x0=start, x1=end,
            fillcolor=color, opacity=0.15,
            layer="below", line_width=0,
            row=1, col=1,
        )

    # --- Current regime annotation ---
    current = result.current_regime
    current_color = config.REGIME_COLORS.get(current, "#ffffff")
    fig.add_annotation(
        text=f"<b>Current regime: {current}</b>",
        xref="paper", yref="paper",
        x=0.99, y=0.99,
        showarrow=False,
        font=dict(size=12, color=current_color),
        bgcolor="#1e222d",
        bordercolor=current_color,
        borderwidth=1,
        borderpad=6,
        align="right",
    )

    fig.update_layout(
        title=dict(
            text=f"{symbol}  [{timeframe}]  —  HMM Market Regimes",
            font=dict(size=14, color="#d1d4dc"),
        ),
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.06, x=0, font=dict(size=10)),
        margin=dict(l=60, r=40, t=80, b=40),
        plot_bgcolor="#131722",
        paper_bgcolor="#131722",
    )
    fig.update_yaxes(title_text="Price", row=1, col=1, gridcolor="#2a2e39")
    fig.update_yaxes(title_text="Volume", row=2, col=1, gridcolor="#2a2e39")
    fig.update_xaxes(gridcolor="#2a2e39", showgrid=True)

    return fig
