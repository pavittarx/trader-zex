"""screener.in scraper — deep quarterly EPS history (for PEAD fundamental surprise).

nse_past_results gives only ~5 quarters; screener gives ~13, enough to compute a
YoY (seasonal) earnings surprise. We scrape the 'Quarterly Results' table's
'EPS in Rs' row. screener does NOT expose clean per-quarter announcement dates,
so the event study dates the reaction separately (quarter-end + reporting lag,
snapped to the volume spike).

Be polite: cache to disk, sleep between requests, low volume.
"""
from __future__ import annotations

import html as H
import json
import re
import time
import urllib.request as u
from pathlib import Path

import pandas as pd

_CACHE = Path("~/.trader_zex_screener_cache").expanduser()
_CACHE.mkdir(parents=True, exist_ok=True)
_UA = {"User-Agent": "Mozilla/5.0 (research; quarterly-eps)"}
_MON = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _quarter_end(label: str) -> pd.Timestamp | None:
    # "Mar 2024" -> period-end date (last day of that month)
    m = re.match(r"([A-Za-z]{3})\s+(\d{4})", label.strip())
    if not m or m.group(1) not in _MON:
        return None
    return pd.Timestamp(year=int(m.group(2)), month=_MON[m.group(1)], day=1) + pd.offsets.MonthEnd(0)


def _fetch(url: str) -> str | None:
    try:
        return u.urlopen(u.Request(url, headers=_UA), timeout=25).read().decode("utf-8", "ignore")
    except Exception:
        return None


def get_quarterly_eps(symbol_plain: str, use_cache: bool = True) -> pd.Series:
    """Return EPS-in-Rs indexed by quarter-end Timestamp (empty Series on failure)."""
    cache = _CACHE / f"{symbol_plain}.json"
    if use_cache and cache.exists():
        try:
            d = json.loads(cache.read_text())
            return pd.Series(d, dtype=float).set_axis(pd.to_datetime(list(d.keys()))).sort_index()
        except Exception:
            pass

    html_ = None
    for path in ("consolidated/", ""):
        html_ = _fetch(f"https://www.screener.in/company/{symbol_plain}/{path}")
        if html_ and "Quarterly Results" in html_:
            break
    if not html_ or "Quarterly Results" not in html_:
        return pd.Series(dtype=float)

    tbl = re.search(r"Quarterly Results.*?</table>", html_, re.S)
    if not tbl:
        return pd.Series(dtype=float)
    tbl = tbl.group(0)

    def cells(row):
        return [H.unescape(re.sub("<.*?>", "", c)).strip()
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S)
    headers = cells(rows[0]) if rows else []
    qdates = [_quarter_end(h) for h in headers]
    eps_row = next((cells(r) for r in rows if cells(r) and "EPS" in cells(r)[0]), None)
    if not eps_row:
        return pd.Series(dtype=float)

    out = {}
    for qd, val in zip(qdates[1:], eps_row[1:]):
        if qd is None:
            continue
        try:
            out[qd] = float(val.replace(",", ""))
        except ValueError:
            continue
    s = pd.Series(out).sort_index()
    if use_cache and not s.empty:
        cache.write_text(json.dumps({d.isoformat(): v for d, v in s.items()}))
    return s


if __name__ == "__main__":
    import sys
    syms = sys.argv[1:] or ["RELIANCE", "TCS", "INFY", "SAIL", "PNB"]
    for sym in syms:
        s = get_quarterly_eps(sym, use_cache=False)
        if s.empty:
            print(f"{sym:<10} FAILED")
        else:
            print(f"{sym:<10} {len(s)} quarters  {s.index[0].date()}..{s.index[-1].date()}  "
                  f"last EPS={s.iloc[-1]}")
        time.sleep(1.5)
