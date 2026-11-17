"""DXY synthétique à partir des 6 paires de sa formule officielle (ICE).

DXY = 50.14348112 × EURUSD^-0.576 × USDJPY^0.136 × GBPUSD^-0.119
                  × USDCAD^0.091 × USDSEK^0.042 × USDCHF^0.036

Limite connue : open et close sont exacts, mais high et low ne peuvent pas être recalculés à partir
des extrêmes de chaque paire (ils n'ont pas lieu au même instant). On prend high = max(open, close)
et low = min(open, close) en M1 : l'erreur se limite aux mèches d'une minute et devient négligeable
dès le M5. C'est suffisant pour le SMT sur des swings M5 et au-dessus.
"""

from __future__ import annotations

import pandas as pd

CONSTANT = 50.14348112
WEIGHTS = {
    "EURUSD": -0.576,
    "USDJPY": 0.136,
    "GBPUSD": -0.119,
    "USDCAD": 0.091,
    "USDSEK": 0.042,
    "USDCHF": 0.036,
}
COMPONENTS = list(WEIGHTS)
MAX_FILL_MINUTES = 5  # une paire peut manquer quelques minutes ; au-delà, la minute est supprimée


def compute_dxy(m1: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """``m1`` : {symbole: DataFrame M1 indexé en UTC}. Retourne le DXY M1 (open, high, low, close)."""
    missing = [s for s in COMPONENTS if s not in m1]
    if missing:
        raise ValueError(f"paires manquantes pour le DXY : {missing}")

    base = m1["EURUSD"].index
    union = base
    for s in COMPONENTS:
        union = union.union(m1[s].index)

    result = {}
    for field in ("open", "close"):
        value = pd.Series(CONSTANT, index=union)
        for s, w in WEIGHTS.items():
            px = m1[s][field].reindex(union).ffill(limit=MAX_FILL_MINUTES)
            value = value * px**w
        result[field] = value.reindex(base)

    dxy = pd.DataFrame(result).dropna()
    dxy["high"] = dxy[["open", "close"]].max(axis=1)
    dxy["low"] = dxy[["open", "close"]].min(axis=1)
    dxy["volume"] = 0.0
    dxy.index.name = "time"
    return dxy[["open", "high", "low", "close", "volume"]].round(4)
