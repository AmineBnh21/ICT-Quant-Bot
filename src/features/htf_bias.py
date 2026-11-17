"""Biais HTF top-down (docs/strategy.md, section 7 bis).

Pour un timeframe (MN1, W1, D1), à la clôture de chaque bougie :
- ``pd_dir`` : sens donné par la dernière réaction à un PD Array (FVG, swing) : respect / disrespect ;
- ``candle_dir`` : sens de la bougie (continuation ou C2) ;
- ``direction`` : les deux combinés (d'accord ou un neutre → ce sens ; opposés → 0) ;
- ``eq`` : 0,5 du range de la bougie (pour le filtre premium / discount).
L'index est l'ouverture de la bougie ; tout est connu à sa CLÔTURE, c'est-à-dire à l'ouverture de la suivante.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.fvg import fvgs
from src.features.swings import swings

MAX_AGE = 24  # un PD Array est oublié après 24 bougies de son timeframe [À VALIDER]


def candle_dir(bars: pd.DataFrame) -> pd.Series:
    """+1 / -1 / 0 : continuation (clôture au-delà du haut / bas précédent) ou C2 (balayage + clôture dedans)."""
    p = bars.shift(1)
    sweep_lo, sweep_hi = bars.low < p.low, bars.high > p.high
    inside = (bars.close < p.high) & (bars.close > p.low)
    bull = (bars.close > p.high) | (sweep_lo & ~sweep_hi & inside)
    bear = (bars.close < p.low) | (sweep_hi & ~sweep_lo & inside)
    return pd.Series(np.select([bull, bear], [1, -1], 0), index=bars.index)


def pd_array_dir(bars: pd.DataFrame, max_age: int = MAX_AGE) -> pd.Series:
    """Sens donné par la dernière réaction à un PD Array (Arjo : respect / disrespect)."""
    o, h, l, c = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
    n = len(bars)
    pos = {t: i for i, t in enumerate(bars.index)}
    # PD Arrays : (actif à partir de l'index, côté +1 discount / -1 premium, bas, haut)
    arrays: list[list] = []
    f = fvgs(bars, min_size_atr=0.0)
    for t, row in f.iterrows():
        # FVG haussière = discount array (on attend un rebond) ; baissière = premium array
        arrays.append([pos[t] + 1, int(row.side), row.bottom, row.top, True])
    sw = swings(bars)
    for i in np.flatnonzero(sw.swing_low.to_numpy()):
        arrays.append([i + 2, 1, l[i], l[i], True])  # connu après la bougie de confirmation
    for i in np.flatnonzero(sw.swing_high.to_numpy()):
        arrays.append([i + 2, -1, h[i], h[i], True])
    arrays.sort(key=lambda a: a[0])

    out = np.zeros(n, dtype=int)
    current = 0
    k = 0
    active: list[list] = []
    for i in range(n):
        while k < len(arrays) and arrays[k][0] <= i:
            active.append(arrays[k])
            k += 1
        events = []
        keep = []
        for a in active:
            start, side, bottom, top, _ = a
            if i - start > max_age:
                continue
            if side == 1 and l[i] <= top:  # discount array touché
                events.append(-1 if c[i] < bottom else 1)
                continue  # réagi : retiré (respecté = liquidité/FVG utilisée ; disrespecté = cassé)
            if side == -1 and h[i] >= bottom:  # premium array touché
                events.append(1 if c[i] > top else -1)
                continue
            keep.append(a)
        active = keep
        if events:
            s = int(np.sign(sum(events)))
            current = s if s != 0 else current
        out[i] = current
    return pd.Series(out, index=bars.index)


def tf_bias(bars: pd.DataFrame) -> pd.DataFrame:
    cd = candle_dir(bars)
    pdd = pd_array_dir(bars)
    combined = np.where(cd == 0, pdd, np.where((pdd == 0) | (pdd == cd), cd, 0))
    return pd.DataFrame(
        {"candle_dir": cd, "pd_dir": pdd, "direction": combined, "eq": (bars.high + bars.low) / 2},
        index=bars.index,
    )


def known_at(bias: pd.DataFrame, times: pd.DatetimeIndex) -> pd.DataFrame:
    """Pour chaque instant de ``times``, l'état de la dernière bougie TERMINÉE (ouverture de la suivante <= t)."""
    b = bias.copy()
    b["known"] = b.index.to_series().shift(-1)  # terminée à l'ouverture de la bougie suivante
    b = b.dropna(subset=["known"]).set_index("known").sort_index()
    pos = b.index.searchsorted(times, side="right") - 1
    res = b.iloc[np.clip(pos, 0, None)].copy()
    res.index = times
    res[pos < 0] = np.nan
    return res
