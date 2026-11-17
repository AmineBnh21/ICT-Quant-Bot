"""Étude statistique du biais daily (docs/strategy.md, sections 2.2 et 8).

Pour chaque jour de trading J (bougie daily forex 17:00 → 17:00 New York), on classe J :
- continuation haussière : J clôture au-dessus du haut de J-1 (PDH)
- continuation baissière : J clôture en dessous du bas de J-1 (PDL)
- retournement haussier (C2 / CRT) : J balaie le bas de J-1 puis clôture à l'intérieur de son range
- retournement baissier (C2 / CRT) : J balaie le haut de J-1 puis clôture à l'intérieur de son range
(les jours qui balaient les deux côtés sont exclus des retournements)

Puis on regarde le lendemain J+1, dont la DOL attendue est le haut de J (biais haussier) ou le bas de J :
- « DOL atteinte » : J+1 dépasse cette DOL ;
- « DOL avant l'invalidation » : J+1 atteint la DOL AVANT l'extrême opposé de J (mesuré en H1).
Chaque chiffre est comparé à la base : la même mesure sur TOUS les jours.

Lancement : python -m src.research.daily_bias_stats
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src.data.store import load_bars

SHIFT = pd.Timedelta(hours=7)  # 17:00 New York + 7 h = minuit : clé du jour de trading


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalle de confiance à 95 % d'une proportion."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return c - h, c + h


def day_key(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return (idx.tz_localize(None) + SHIFT).floor("D")


def first_touch(h1: pd.DataFrame, days: pd.DataFrame) -> pd.DataFrame:
    """Pour chaque jour J+1 : heure de la 1re bougie H1 qui dépasse le haut de J, et qui casse le bas de J."""
    h1 = h1.assign(day=day_key(h1.index))
    lv = days[["prev_high", "prev_low"]]
    m = h1.join(lv, on="day", how="inner")
    up = m[m.high > m.prev_high].groupby("day").apply(lambda g: g.index[0], include_groups=False)
    dn = m[m.low < m.prev_low].groupby("day").apply(lambda g: g.index[0], include_groups=False)
    return pd.DataFrame({"t_up": up, "t_dn": dn})


def analyse(symbol: str) -> pd.DataFrame:
    d = load_bars(symbol, "D1")
    d.index = day_key(d.index)
    p = d.shift(1)
    sig = pd.DataFrame(index=d.index)
    sig["bull_cont"] = d.close > p.high
    sig["bear_cont"] = d.close < p.low
    sweep_lo, sweep_hi = d.low < p.low, d.high > p.high
    inside = (d.close < p.high) & (d.close > p.low)
    sig["bull_rev"] = sweep_lo & ~sweep_hi & inside
    sig["bear_rev"] = sweep_hi & ~sweep_lo & inside

    # résultat du lendemain : on décale J+1 sur la ligne de J
    nxt = pd.DataFrame({"prev_high": d.high, "prev_low": d.low}).shift(0)
    nxt.index = d.index
    lend = pd.DataFrame(index=d.index)
    lend["next_high"] = d.high.shift(-1)
    lend["next_low"] = d.low.shift(-1)
    # premières touches en H1, indexées par le jour J+1 → ramenées sur J
    levels = pd.DataFrame({"prev_high": d.high.values, "prev_low": d.low.values}, index=d.index).shift(1)
    ft = first_touch(load_bars(symbol, "H1"), levels.dropna())
    ft = ft.reindex(d.index).shift(-1)
    lend["up_first"] = (ft.t_up.notna()) & ((ft.t_dn.isna()) | (ft.t_up < ft.t_dn))
    lend["dn_first"] = (ft.t_dn.notna()) & ((ft.t_up.isna()) | (ft.t_dn < ft.t_up))
    lend["hit_up"] = lend.next_high > d.high
    lend["hit_dn"] = lend.next_low < d.low
    valid = lend.next_high.notna() & p.high.notna()

    rows = []
    for name, bull in [("bull_cont", True), ("bear_cont", False), ("bull_rev", True), ("bear_rev", False)]:
        hit, first = ("hit_up", "up_first") if bull else ("hit_dn", "dn_first")
        for period, mask_p in [("2015-2020", d.index.year <= 2020), ("2021-2026", d.index.year >= 2021), ("tout", np.ones(len(d), bool))]:
            base = valid & mask_p
            sel = base & sig[name]
            n, k1, k2 = int(sel.sum()), int(lend.loc[sel, hit].sum()), int(lend.loc[sel, first].sum())
            b1, b2 = lend.loc[base, hit].mean(), lend.loc[base, first].mean()
            rows.append(
                dict(paire=symbol, signal=name, periode=period, n=n,
                     dol_atteinte=k1 / n, base_atteinte=b1, ic95=wilson(k1, n),
                     dol_avant_invalidation=k2 / n, base_avant=b2, ic95_avant=wilson(k2, n))
            )
    return pd.DataFrame(rows)


LABELS = {
    "bull_cont": "Continuation haussière (clôture > PDH)",
    "bear_cont": "Continuation baissière (clôture < PDL)",
    "bull_rev": "Retournement haussier (C2 : sweep PDL, clôture dedans)",
    "bear_rev": "Retournement baissier (C2 : sweep PDH, clôture dedans)",
}


def main() -> None:
    res = pd.concat([analyse(s) for s in ["EURUSD", "GBPUSD"]])
    pct = lambda x: f"{100 * x:5.1f} %"
    ic = lambda t: f"[{100 * t[0]:.0f}–{100 * t[1]:.0f}]"
    for sym, g in res.groupby("paire", sort=False):
        print(f"\n=== {sym} ===")
        for sig, gs in g.groupby("signal", sort=False):
            print(f"\n{LABELS[sig]}")
            print(f"  {'période':10} {'n':>5}   {'DOL atteinte J+1':>16} {'IC95':>9} {'(base)':>9}   {'DOL avant invalidation':>22} {'IC95':>9} {'(base)':>9}")
            for _, r in gs.iterrows():
                print(f"  {r.periode:10} {r.n:>5}   {pct(r.dol_atteinte):>16} {ic(r.ic95):>9} {pct(r.base_atteinte):>9}   {pct(r.dol_avant_invalidation):>22} {ic(r.ic95_avant):>9} {pct(r.base_avant):>9}")


if __name__ == "__main__":
    main()
