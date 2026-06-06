"""NSE event sources for event studies (earnings result dates, ...)."""
from __future__ import annotations

import pandas as pd


def result_dates(sym_plain: str) -> list[pd.Timestamp]:
    """Past earnings-announcement dates for a plain NSE ticker (no NSE:/-EQ).

    Source: nsepython.nse_past_results re_create_dt. Announcements typically
    land after-hours — pair with event_study.reaction_events, which takes the
    first session strictly after.
    """
    import nsepython as n
    try:
        raw = n.nse_past_results(sym_plain)
    except Exception:
        return []
    rows = (raw.get("resCmpData") or []) if isinstance(raw, dict) else []
    out = []
    for r in rows:
        dt = r.get("re_create_dt")
        if dt:
            try:
                out.append(pd.to_datetime(dt, format="%d-%b-%Y"))
            except Exception:
                pass
    return sorted(set(out))
