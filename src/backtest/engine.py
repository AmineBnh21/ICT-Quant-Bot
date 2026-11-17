"""Exécution d'un trade sur les bougies M1, avec BID et ASK.

Les données sont en BID. ASK = BID + spread. Règles d'exécution :
- long  : entrée buy limit remplie quand l'ASK descend au prix (bid_low + spread <= entry) ;
          stop vendu sur le BID (bid_low <= stop) ; cible vendue sur le BID (bid_high >= target).
- short : entrée sell limit remplie quand le BID monte au prix (bid_high >= entry) ;
          stop racheté sur l'ASK (bid_high + spread >= stop) ; cible rachetée sur l'ASK (bid_low + spread <= target).
- Les stops subissent un slippage défavorable ; les ordres limit n'en ont pas.
- Hypothèses PRUDENTES quand une seule bougie M1 ne permet pas de savoir l'ordre des événements :
  * la bougie qui remplit l'entrée ne peut que toucher le stop, jamais la cible ;
  * si stop et cible sont touchés dans la même minute → stop.
- Sortie forcée à ``exit_time`` (ouverture de la première minute à cette heure ou après).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class M1:
    """Colonnes M1 en tableaux numpy (accès rapide). ``t`` en int64 (ns UTC)."""

    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray

    @classmethod
    def from_frame(cls, df) -> "M1":
        return cls(
            df.index.as_unit("ns").asi8, df["open"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy()
        )


@dataclass
class Fill:
    filled: bool
    entry_time: int = 0
    exit_time: int = 0
    exit_price: float = np.nan
    outcome: str = "unfilled"  # unfilled | stop | target | time
    r: float = 0.0
    mae_r: float = 0.0  # pire excursion contre le trade, en R
    mfe_r: float = 0.0  # meilleure excursion en faveur, en R


def simulate(
    m1: M1,
    side: int,
    entry: float,
    stop: float,
    target: float,
    start: int,
    fill_deadline: int,
    exit_time: int,
    spread: float,
    slippage: float,
) -> Fill:
    """Simule un ordre limit placé à ``start`` (ns), valable jusqu'à ``fill_deadline``."""
    risk = abs(entry - stop)
    i = int(np.searchsorted(m1.t, start, side="left"))
    end_fill = int(np.searchsorted(m1.t, fill_deadline, side="left"))
    end_trade = int(np.searchsorted(m1.t, exit_time, side="left"))

    # 1) attente du remplissage
    fill_i = -1
    for j in range(i, min(end_fill, end_trade)):
        if (side == 1 and m1.l[j] + spread <= entry) or (side == -1 and m1.h[j] >= entry):
            fill_i = j
            break
    if fill_i < 0:
        return Fill(False)

    def stop_hit(j: int) -> bool:
        return m1.l[j] <= stop if side == 1 else m1.h[j] + spread >= stop

    def target_hit(j: int) -> bool:
        return m1.h[j] >= target if side == 1 else m1.l[j] + spread <= target

    worst = best = 0.0

    def excursions(j: int) -> None:
        nonlocal worst, best
        if side == 1:
            worst = min(worst, (m1.l[j] - entry) / risk)
            best = max(best, (m1.h[j] - entry) / risk)
        else:
            worst = min(worst, (entry - (m1.h[j] + spread)) / risk)
            best = max(best, (entry - (m1.l[j] + spread)) / risk)

    def result(j: int, price: float, outcome: str) -> Fill:
        r = (price - entry) / risk if side == 1 else (entry - price) / risk
        return Fill(True, int(m1.t[fill_i]), int(m1.t[j]), price, outcome, r, worst, best)

    stop_exit = stop - slippage if side == 1 else stop + slippage

    # 2) la minute du remplissage : seul le stop peut être touché (prudence)
    excursions(fill_i)
    if stop_hit(fill_i):
        return result(fill_i, stop_exit, "stop")

    # 3) gestion du trade
    for j in range(fill_i + 1, len(m1.t)):
        if j >= end_trade:
            price = m1.o[j] if side == 1 else m1.o[j] + spread
            return result(j, price, "time")
        excursions(j)
        if stop_hit(j):
            return result(j, stop_exit, "stop")
        if target_hit(j):
            return result(j, target, "target")
    j = len(m1.t) - 1
    return result(j, m1.o[j] if side == 1 else m1.o[j] + spread, "time")
