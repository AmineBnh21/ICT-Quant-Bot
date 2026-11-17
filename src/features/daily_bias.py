"""Biais daily et numérotation des bougies (docs/strategy.md, sections 2.1 et 2.2).

Pour chaque jour de trading J (bougie daily forex 17:00 → 17:00 New York) :
- ``bull_cont`` : J clôture au-dessus du haut de J-1 ; ``bear_cont`` : en dessous du bas de J-1
- ``bull_c2`` : J balaie le bas de J-1 et clôture à l'intérieur de son range (CRT) ; ``bear_c2`` : l'inverse
  (une bougie qui balaie les deux côtés n'est pas un C2)
- une continuation qui suit un C2 du même sens est un **C3**, celle qui suit un C3 est un **C4**

Le biais de J+1 est le sens de J ; sa DOL est le haut de J (haussier) ou le bas de J (baissier).
Index : clé du jour de trading (date calendaire de la partie 00:00 → 17:00 New York).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SHIFT = pd.Timedelta(hours=7)


def day_key(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Heure New York → clé du jour de trading forex (17:00 = début du jour suivant)."""
    return (idx.tz_localize(None) + SHIFT).floor("D")


def label_days(d1: pd.DataFrame) -> pd.DataFrame:
    d = d1.copy()
    d.index = day_key(d.index)
    p = d.shift(1)
    bull_cont = d.close > p.high
    bear_cont = d.close < p.low
    sweep_lo, sweep_hi = d.low < p.low, d.high > p.high
    inside = (d.close < p.high) & (d.close > p.low)
    bull_c2 = sweep_lo & ~sweep_hi & inside
    bear_c2 = sweep_hi & ~sweep_lo & inside

    direction = np.select([bull_cont | bull_c2, bear_cont | bear_c2], [1, -1], 0)
    kind = np.select([bull_c2 | bear_c2, bull_cont | bear_cont], ["C2", "cont"], "none").astype(object)
    # C3 / C4 : continuation qui suit un C2 / C3 du même sens
    for i in range(1, len(d)):
        if kind[i] == "cont" and direction[i] == direction[i - 1]:
            if kind[i - 1] == "C2":
                kind[i] = "C3"
            elif kind[i - 1] == "C3":
                kind[i] = "C4"
    return pd.DataFrame(
        {"direction": direction, "kind": kind, "high": d.high, "low": d.low, "close": d.close}, index=d.index
    )


def bias_for_next_day(d1: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par jour de trading D : le biais et la DOL viennent de la bougie de la veille."""
    lab = label_days(d1)
    prev = lab.shift(1)
    return pd.DataFrame(
        {
            "bias": prev.direction.fillna(0).astype(int),
            "bias_kind": prev.kind.fillna("none"),
            "pdh": prev.high,
            "pdl": prev.low,
        },
        index=lab.index,
    )
