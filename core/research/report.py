"""Uniform result printing for research scripts."""
from __future__ import annotations

import numpy as np

from core.research.stats import ann_return, sharpe, t_stat


def stats_line(daily: np.ndarray, rt_cost: float, label: str) -> None:
    """Gross vs net annualized line for a daily L/S return series.

    (Extracted from scripts/gap_fade_test.py.)
    """
    if len(daily) < 20:
        print(f"  {label:<22} (too few days: {len(daily)})")
        return
    net = daily - rt_cost  # one round trip per day
    print(f"  {label:<22} gross={ann_return(daily.mean()):+7.1f}%  "
          f"net={ann_return(net.mean()):+7.1f}%  "
          f"t={t_stat(daily):+5.2f}  net_Sharpe={sharpe(net):+5.2f}  days={len(daily)}")
