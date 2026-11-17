"""Swing points (docs/strategy.md, section 1.2).

Swing high : bougie dont le haut est strictement plus haut que les ``n`` bougies avant ET après
(fractale de ``2n + 1`` bougies ; ``length=3`` → n = 1). Swing low : l'inverse.

Attention au futur : un swing en ``i`` n'est connu qu'à la CLÔTURE de la bougie ``i + n``.
La colonne ``confirmed_at`` donne cette bougie ; un backtest ne doit utiliser le swing qu'après elle.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def swings(bars: pd.DataFrame, length: int = 3) -> pd.DataFrame:
    if length < 3 or length % 2 == 0:
        raise ValueError("length doit être impair et >= 3")
    n = length // 2
    high, low = bars["high"].to_numpy(), bars["low"].to_numpy()
    size = len(bars)
    is_high = np.zeros(size, bool)
    is_low = np.zeros(size, bool)
    for i in range(n, size - n):
        neighbours = np.r_[i - n : i, i + 1 : i + n + 1]
        is_high[i] = high[i] > high[neighbours].max()
        is_low[i] = low[i] < low[neighbours].min()
    confirmed = pd.Series(bars.index, index=bars.index).shift(-n)
    return pd.DataFrame(
        {"swing_high": is_high, "swing_low": is_low, "confirmed_at": confirmed}, index=bars.index
    )
