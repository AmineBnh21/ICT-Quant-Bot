"""Stratégie v1 : le modèle minimal de docs/strategy.md, section 7.

Pour chaque jour de trading D :
1. Biais : bougie daily de la veille (continuation, C2, C3, C4) → sens et DOL (PDH pour un long, PDL pour un short).
2. Pendant les killzones de D (Londres 02:00–05:00, New York 07:00–10:00, heure de New York), on cherche
   un CISD sur le timeframe d'entrée (M5 ou M15), dans le sens du biais.
3. Ordre limit au niveau du CISD, stop au-delà de l'extrême du mouvement (+ marge), cible à 2R fixe.
4. Filtres : la DOL doit être au-delà de la cible 2R ; elle ne doit pas être déjà prise avant le signal ;
   stop d'au moins ``min_stop_pips``.
5. L'ordre reste valable jusqu'à la fin de la killzone. Un seul trade rempli par jour et par paire.
6. Sortie : stop, cible, ou fermeture forcée à 16:55 New York (avant le rollover).

Non inclus dans la v1 (à ajouter une règle à la fois) : zones de contexte FLOD / OD, premium / discount,
CISD 1H obligatoire, SMT / PSP, qualité des FVG, filtre news, break-even.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.backtest.engine import M1, simulate
from src.features.cisd import cisds
from src.features.daily_bias import bias_for_next_day, day_key

TF_MINUTES = {"M5": 5, "M15": 15}


@dataclass
class Params:
    entry_tf: str = "M5"
    killzones: dict = field(default_factory=lambda: {"london": ("02:00", "05:00"), "newyork": ("07:00", "10:00")})
    bias_kinds: tuple = ("cont", "C2", "C3", "C4")
    target_r: float = 2.0
    pip: float = 0.0001
    spread: float = 0.00004  # 4 points
    slippage: float = 0.00002  # 0.2 pip
    stop_buffer: float = 0.00005  # 0.5 pip au-delà de l'extrême [À VALIDER]
    min_stop_pips: float = 3.0  # [À VALIDER]
    exit_hhmm: str = "16:55"


def _ns(ts: pd.Timestamp) -> int:
    return ts.tz_convert("UTC").as_unit("ns").value


def generate_trades(symbol: str, d1: pd.DataFrame, entry_bars: pd.DataFrame, m1_df: pd.DataFrame, p: Params) -> pd.DataFrame:
    bias = bias_for_next_day(d1)
    signals = cisds(entry_bars)
    signals["day"] = day_key(signals.index)
    tf = pd.Timedelta(minutes=TF_MINUTES[p.entry_tf])
    m1 = M1.from_frame(m1_df)
    m1_ny_high = m1_df["high"]
    m1_ny_low = m1_df["low"]
    tz = "America/New_York"

    rows = []
    for day, sigs in signals.groupby("day"):
        if day not in bias.index:
            continue
        b = bias.loc[day]
        if b.bias == 0 or b.bias_kind not in p.bias_kinds or np.isnan(b.pdh):
            continue
        dol = b.pdh if b.bias == 1 else b.pdl
        date = day.strftime("%Y-%m-%d")
        day_open = pd.Timestamp(f"{date} 00:00", tz=tz) - pd.Timedelta(hours=7)  # 17:00 la veille
        exit_time = pd.Timestamp(f"{date} {p.exit_hhmm}", tz=tz)

        for kz_name, (kz_start, kz_end) in p.killzones.items():
            kz_s = pd.Timestamp(f"{date} {kz_start}", tz=tz)
            kz_e = pd.Timestamp(f"{date} {kz_end}", tz=tz)
            done = False
            for t, s in sigs[(sigs.side == b.bias)].iterrows():
                known_at = t + tf  # le CISD est connu à la clôture de sa bougie
                if not (kz_s < known_at <= kz_e):
                    continue
                entry = s.level
                stop = s.extreme - p.stop_buffer if b.bias == 1 else s.extreme + p.stop_buffer + p.spread
                risk = abs(entry - stop)
                if risk < p.min_stop_pips * p.pip:
                    continue
                target = entry + b.bias * p.target_r * risk
                if (b.bias == 1 and dol < target) or (b.bias == -1 and dol > target):
                    continue  # DOL trop proche : pas de 2R disponible
                # DOL déjà prise entre l'ouverture du jour et le signal ?
                window = slice(day_open.tz_convert("UTC"), known_at.tz_convert("UTC") - pd.Timedelta(minutes=1))
                if b.bias == 1 and m1_ny_high.loc[window].max() >= dol:
                    continue
                if b.bias == -1 and m1_ny_low.loc[window].min() <= dol:
                    continue
                f = simulate(
                    m1, int(b.bias), entry, stop, target,
                    _ns(known_at), _ns(kz_e), _ns(exit_time), p.spread, p.slippage,
                )
                if not f.filled:
                    continue
                rows.append(
                    dict(
                        symbol=symbol, day=day, session=kz_name, side=int(b.bias), bias_kind=b.bias_kind,
                        signal_time=known_at, entry_time=pd.Timestamp(f.entry_time, tz="UTC").tz_convert(tz),
                        exit_time=pd.Timestamp(f.exit_time, tz="UTC").tz_convert(tz),
                        entry=entry, stop=stop, target=target, dol=dol, exit_price=f.exit_price,
                        stop_pips=risk / p.pip, outcome=f.outcome, r=f.r, mae_r=f.mae_r, mfe_r=f.mfe_r,
                    )
                )
                done = True
                break
            if done:
                break  # un seul trade par jour et par paire
    return pd.DataFrame(rows)
