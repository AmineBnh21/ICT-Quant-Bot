"""Construction des timeframes supérieurs à partir des M1, à l'heure de New York.

Convention forex (voir docs/strategy.md) :
- la bougie daily ouvre à 17:00 New York (la bougie qui ouvre le dimanche 17:00 est celle du lundi) ;
- les bougies H4 ouvrent à 17:00, 21:00, 01:00, 05:00, 09:00, 13:00 New York ;
- la semaine ouvre le dimanche 17:00 New York.

Méthode : on passe en heure murale New York, on décale de +7 h (17:00 devient minuit),
on regroupe, puis on retire les 7 h. Ça gère automatiquement l'heure d'été / d'hiver.
M5 / M15 / H1 sont regroupés directement en UTC (le décalage New York est en heures entières).

Index de sortie : heure d'OUVERTURE de la bougie, en America/New_York.
"""

from __future__ import annotations

import pandas as pd

NY = "America/New_York"
SHIFT = pd.Timedelta(hours=7)  # 17:00 NY + 7 h = 00:00
TIMEFRAMES = ["M5", "M15", "H1", "H4", "D1", "W1", "MN1"]
AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def resample(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Regroupe des bougies M1 (index UTC) en ``tf``. Retourne un index d'ouverture en heure de New York."""
    if m1.empty:
        raise ValueError("pas de données M1")
    if m1.index.tz is None:
        raise ValueError("l'index M1 doit être en UTC (tz-aware)")

    if tf in ("M5", "M15", "H1"):
        freq = {"M5": "5min", "M15": "15min", "H1": "1h"}[tf]
        keys = m1.index.tz_convert("UTC").floor(freq)
        out = m1.groupby(keys).agg(AGG)
        out.index = out.index.tz_convert(NY)
    else:
        shifted = m1.index.tz_convert(NY).tz_localize(None) + SHIFT
        if tf == "H4":
            keys = shifted.floor("4h")
        elif tf == "D1":
            keys = shifted.floor("D")
        elif tf == "W1":
            day = shifted.floor("D")
            keys = day - pd.to_timedelta(day.day_of_week, unit="D")  # lundi (décalé) = dimanche 17:00 NY
        elif tf == "MN1":
            keys = shifted.to_period("M").to_timestamp()
        else:
            raise ValueError(f"timeframe inconnu : {tf} (attendu : {TIMEFRAMES})")
        out = m1.groupby(keys).agg(AGG)
        # 17:00, 21:00, 01:00, 05:00... : jamais dans le trou de l'heure d'été ; en cas d'heure ambiguë
        # (passage à l'heure d'hiver, 01:00) on garde la première occurrence.
        out.index = (out.index - SHIFT).tz_localize(NY, ambiguous=True, nonexistent="shift_forward")

    out.index.name = "time"
    return out.dropna(subset=["open"])


def resample_all(m1: pd.DataFrame, timeframes: list[str] | None = None) -> dict[str, pd.DataFrame]:
    return {tf: resample(m1, tf) for tf in (timeframes or TIMEFRAMES)}
