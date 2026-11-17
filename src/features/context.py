"""Zones de contexte HTF (docs/strategy.md, sections 1.4 à 1.6 ; Arjo, Context / FLOD).

Une FVG HTF (H1 par défaut) est une zone de contexte valide pour un trade dans son sens tant qu'aucune
bougie HTF n'a CLÔTURÉ de l'autre côté (disrespect). Les mèches à travers la zone sont permises (2CR).

``fvg_zones`` ajoute à chaque FVG :
- ``known_at`` : clôture de la 3e bougie (la FVG n'existe pas avant) ;
- ``invalid_at`` : clôture de la première bougie qui la traverse (NaT si jamais dans l'horizon).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.fvg import fvgs


def fvg_zones(bars: pd.DataFrame, tf: pd.Timedelta, max_age_bars: int = 120, min_size_atr: float = 0.1) -> pd.DataFrame:
    z = fvgs(bars, min_size_atr=min_size_atr)
    pos = bars.index.get_indexer(z.index)
    close = bars["close"].to_numpy()
    times = bars.index
    invalid = []
    for k, i in enumerate(pos):
        seg = close[i + 1 : i + 1 + max_age_bars]
        side = z["side"].iat[k]
        broken = seg < z["bottom"].iat[k] if side == 1 else seg > z["top"].iat[k]
        j = int(np.argmax(broken)) if broken.any() else -1
        invalid.append(times[i + 1 + j] + tf if j >= 0 else pd.NaT)
    z = z.assign(known_at=z.index + tf, invalid_at=pd.DatetimeIndex(invalid, tz=bars.index.tz))
    z["expires_at"] = z.known_at + max_age_bars * tf
    return z


def touched_valid_zone(zones: pd.DataFrame, side: int, extreme: float, extreme_time, known_at) -> bool:
    """Le mouvement qui a formé le CISD (son extrême) a-t-il touché une FVG HTF valide de ce sens ?
    - la FVG existait au moment de l'extrême ;
    - elle n'était ni périmée ni invalidée au moment du signal ;
    - l'extrême est entré dans la zone, une mèche au-delà étant tolérée jusqu'à une hauteur de zone
      (ce qui compte pour le disrespect, ce sont les clôtures, déjà gérées par ``invalid_at``)."""
    z = zones[zones["side"] == side]
    z = z[(z.known_at <= extreme_time) & (z.expires_at > known_at)]
    z = z[z.invalid_at.isna() | (z.invalid_at > known_at)]
    height = z.top - z.bottom
    if side == 1:
        tapped = (extreme <= z.top) & (extreme >= z.bottom - height)
    else:
        tapped = (extreme >= z.bottom) & (extreme <= z.top + height)
    return bool(tapped.any())
