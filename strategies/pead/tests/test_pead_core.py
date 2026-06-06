"""Tests for pead_core — the shared PEAD signal/risk logic (kill-switch +
reaction-day alignment). These are the money-path invariants; they were
previously untested across the (now-removed) duplicated implementations.
"""
import numpy as np
import pandas as pd

from strategies.pead.core import reaction_events, kill_check, tercile_bounds, in_bucket


# --- reaction_events: the t+1 alignment that was a real bug ---------------

def _close(dates, prices):
    return pd.Series(prices, index=pd.DatetimeIndex(dates))


def test_reaction_day_is_session_after_announcement():
    # announcement on the 3rd (after-hours) -> reaction is the 4th (next session)
    idx = pd.bdate_range("2024-01-01", periods=6)   # Mon..Mon
    close = _close(idx, [100, 101, 102, 108, 109, 110])
    ann = idx[2]                                     # 2024-01-03
    ev = reaction_events(close, [ann])
    react_day = idx[3].date().isoformat()
    assert list(ev.keys()) == [react_day]
    assert ev[react_day] == (108 / 102 - 1)          # close[t]/close[t-1]-1, t=reaction day


def test_announcement_on_nontrading_day_snaps_forward():
    idx = pd.bdate_range("2024-01-01", periods=6)
    close = _close(idx, [100, 101, 102, 103, 104, 105])
    ann = pd.Timestamp("2024-01-06")                 # Saturday -> next session Mon 8th
    ev = reaction_events(close, [ann])
    assert list(ev.keys()) == [idx[5].date().isoformat()]


def test_reaction_events_frm_filter():
    idx = pd.bdate_range("2024-01-01", periods=6)
    close = _close(idx, [100, 101, 102, 103, 104, 105])
    ev = reaction_events(close, [idx[1]], frm="2024-01-05")
    assert ev == {}                                  # announcement before frm is dropped


# --- kill_check: the pre-registered halt criteria -------------------------

def test_kill_none_when_empty_or_healthy():
    assert kill_check([]) is None
    assert kill_check([0.01, 0.02, 0.01]) is None    # small, positive
    assert kill_check([0.01] * 25) is None           # healthy long run


def test_kill_drawdown():
    assert "drawdown" in kill_check([0.05, -0.15])   # -15% from peak <= -8%


def test_kill_trailing_mean_nonpositive():
    r = [-0.001] * 20                                # 20 small losses, dd shallow
    assert kill_check(r) == "trailing-20 mean <= 0"


def test_kill_win_rate():
    r = [0.05] * 8 + [-0.001] * 12                   # mean>0 but 40% win
    assert kill_check(r) == "trailing-20 win% < 45"


# --- liquidity bucketing --------------------------------------------------

def test_tercile_bucketing():
    liqs = list(range(1, 10))                         # 1..9
    lo, hi = tercile_bounds(liqs)
    assert in_bucket(1, (lo, hi), "low")
    assert in_bucket(9, (lo, hi), "high")
    assert in_bucket(5, (lo, hi), "mid")
    assert in_bucket(5, (lo, hi), "all")
