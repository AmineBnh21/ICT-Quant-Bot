"""Fair Value Gaps (docs/strategy.md, section 1.1).

Sur 3 bougies c1, c2, c3 (c3 = bougie ``i``) :
- FVG haussière : low(c3) > high(c1) → zone [high(c1), low(c3)]
- FVG baissière : high(c3) < low(c1) → zone [high(c3), low(c1)]
La FVG est connue à la CLÔTURE de c3 (index de la ligne).

Type selon la 3e bougie (Arjo, module 6). Seuils [À VALIDER] :
- RFVG (rejet) : mèche opposée >= 50 % du range de c3 (pour une FVG haussière : mèche haute)
- BAG (expansion) : c3 dans le sens de la FVG avec un corps >= 50 % du corps de c2
- PFVG (consolidation) : les autres cas → la meilleure FVG d'après Arjo
"""

from __future__ import annotations

import numpy as np
import pandas as pd

REJECTION_WICK = 0.5
EXPANSION_BODY = 0.5


def atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = bars["close"].shift(1)
    tr = pd.concat(
        [bars["high"] - bars["low"], (bars["high"] - prev_close).abs(), (bars["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(period).mean()


def fvgs(bars: pd.DataFrame, min_size_atr: float = 0.1, atr_period: int = 14) -> pd.DataFrame:
    o, h, l, c = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
    h1, l1 = np.roll(h, 2), np.roll(l, 2)
    o2, c2 = np.roll(o, 1), np.roll(c, 1)
    bull = l > h1
    bear = h < l1
    bull[:2] = bear[:2] = False

    top = np.where(bull, l, np.where(bear, l1, np.nan))
    bottom = np.where(bull, h1, np.where(bear, h, np.nan))
    size = top - bottom
    big_enough = size >= min_size_atr * atr(bars, atr_period).to_numpy()

    rng = np.maximum(h - l, 1e-12)
    upper_wick = h - np.maximum(o, c)
    lower_wick = np.minimum(o, c) - l
    body3, body2 = np.abs(c - o), np.abs(c2 - o2)
    rejection = np.where(bull, upper_wick, lower_wick) >= REJECTION_WICK * rng
    with_trend = np.where(bull, c > o, c < o)
    expansion = with_trend & (body3 >= EXPANSION_BODY * body2)
    kind = np.where(rejection, "RFVG", np.where(expansion, "BAG", "PFVG"))

    keep = (bull | bear) & big_enough
    out = pd.DataFrame(
        {
            "side": np.where(bull, 1, -1)[keep],
            "top": top[keep],
            "bottom": bottom[keep],
            "kind": kind[keep],
        },
        index=bars.index[keep],
    )
    out.index.name = "time"
    return out
