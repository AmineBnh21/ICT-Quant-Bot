"""CISD : Change in State of Delivery (docs/strategy.md, section 1.7 ; TTrades, CISD).

CISD haussier : le prix baisse par une ou plusieurs séries de bougies baissières consécutives. On retient
la série qui a fait le PLUS BAS du mouvement. Le CISD est validé quand une bougie CLÔTURE au-dessus de
l'OPEN de la 1re bougie de cette série. Le niveau (cet open) sert de prix d'entrée en limit, et le plus
bas du mouvement sert de swing pour le stop.
CISD baissier : l'inverse.

Le CISD est connu à la CLÔTURE de la bougie de validation (colonne ``time`` = son ouverture).
Après un CISD, le suivi repart de zéro dans ce sens.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def cisds(bars: pd.DataFrame, max_age_bars: int = 48) -> pd.DataFrame:
    """Détecte les CISD haussiers (+1) et baissiers (-1).

    ``max_age_bars`` : un niveau plus vieux que ça (en bougies) est abandonné [À VALIDER].
    Colonnes : side, level (prix d'entrée), extreme (plus bas / plus haut du mouvement),
    extreme_time, run_start (1re bougie de la série).
    """
    t = bars.index
    o, h, l, c = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
    out = []
    for side in (1, -1):
        # side=+1 : on suit les séries BAISSIÈRES et on attend une clôture au-dessus de leur open
        against = (c < o) if side == 1 else (c > o)
        level = np.nan
        level_i = -1
        extreme = np.nan
        extreme_i = -1
        run_start = -1
        for i in range(len(bars)):
            if against[i]:
                if run_start < 0:
                    run_start = i
                lo_hi = l[i] if side == 1 else h[i]
                new_extreme = np.isnan(extreme) or (lo_hi < extreme if side == 1 else lo_hi > extreme)
                if new_extreme:
                    extreme, extreme_i = lo_hi, i
                    level, level_i = o[run_start], run_start
                continue
            run_start = -1
            if np.isnan(level):
                continue
            if i - level_i > max_age_bars:
                level = extreme = np.nan
                continue
            # une bougie non-baissière peut aussi faire un nouvel extrême (mèche) : on le suit pour le stop
            lo_hi = l[i] if side == 1 else h[i]
            if lo_hi < extreme if side == 1 else lo_hi > extreme:
                extreme, extreme_i = lo_hi, i
            if (c[i] > level) if side == 1 else (c[i] < level):
                out.append((t[i], side, level, extreme, t[extreme_i], t[level_i]))
                level = extreme = np.nan
    df = pd.DataFrame(out, columns=["time", "side", "level", "extreme", "extreme_time", "run_start"])
    return df.sort_values("time").set_index("time")
