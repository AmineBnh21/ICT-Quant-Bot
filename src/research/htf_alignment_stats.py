"""Le biais daily marche-t-il mieux quand le Weekly et le Monthly sont dans le même sens ?

Biais d'une bougie (D1, W1 ou MN1) : même règle que le Fractal Model (src/features/daily_bias.py) :
continuation (clôture au-delà du haut / bas précédent) ou C2 (balayage + clôture dans le range) → sens.
Pour le jour D, on utilise la DERNIÈRE bougie TERMINÉE de chaque timeframe (pas de futur) :
- daily : la veille ; weekly : la semaine précédente ; monthly : le mois précédent.
Résultat mesuré : le jour D atteint-il la DOL du biais daily (haut de la veille si haussier, bas si baissier) ?

    python -m src.research.htf_alignment_stats
"""

from __future__ import annotations

import pandas as pd

from src.data.store import load_bars
from src.features.daily_bias import day_key, label_days
from src.research.daily_bias_stats import wilson


def htf_bias_on_days(htf: pd.DataFrame, days: pd.DatetimeIndex) -> pd.Series:
    """Sens de la dernière bougie HTF TERMINÉE avant chaque jour de trading."""
    lab = label_days(htf)  # index = clé de jour de l'OUVERTURE de la bougie HTF
    # une bougie HTF est terminée quand la suivante ouvre : on décale le sens d'une bougie
    known = pd.Series(lab.direction.shift(1).to_numpy(), index=lab.index)
    return known.reindex(days, method="ffill")


def main() -> None:
    rows = []
    for sym in ["EURUSD", "GBPUSD"]:
        d1 = load_bars(sym, "D1")
        lab = label_days(d1)
        days = lab.index
        bias = lab.direction.shift(1)  # biais du jour D = sens de la veille
        prev_hi, prev_lo = lab.high.shift(1), lab.low.shift(1)
        hit = ((bias == 1) & (lab.high > prev_hi)) | ((bias == -1) & (lab.low < prev_lo))
        w = htf_bias_on_days(load_bars(sym, "W1"), days)
        m = htf_bias_on_days(load_bars(sym, "MN1"), days)
        rows.append(pd.DataFrame({"sym": sym, "bias": bias, "w": w, "m": m, "hit": hit}, index=days))
    df = pd.concat(rows).dropna()
    df = df[df.bias != 0]

    def rel(x):
        return x.map({1: "même sens", -1: "sens opposé", 0: "neutre"})

    df["weekly"] = rel(df.w * df.bias)
    df["monthly"] = rel(df.m * df.bias)
    print("Le jour atteint-il la DOL de son biais daily ? (EURUSD + GBPUSD, 2015-2026)\n")
    print(f"{'condition':45} {'jours':>6} {'DOL atteinte':>13} {'IC95':>10}")

    def line(name, s):
        k, n = int(s.sum()), len(s)
        lo, hi = wilson(k, n)
        print(f"{name:45} {n:>6} {100 * k / n:12.1f}% {f'[{100 * lo:.0f}–{100 * hi:.0f}]':>10}")

    line("tous les biais daily", df.hit)
    for col in ["weekly", "monthly"]:
        for v in ["même sens", "neutre", "sens opposé"]:
            line(f"  {col} {v}", df.hit[df[col] == v])
    line("  weekly ET monthly dans le même sens", df.hit[(df.weekly == "même sens") & (df.monthly == "même sens")])
    line("  weekly même sens, monthly pas opposé", df.hit[(df.weekly == "même sens") & (df.monthly != "sens opposé")])
    line("  weekly ET monthly opposés", df.hit[(df.weekly == "sens opposé") & (df.monthly == "sens opposé")])
    for period, mask in [("2015-2020", df.index.year <= 2020), ("2021-2026", df.index.year >= 2021)]:
        sub = df[mask]
        line(f"{period} : tous", sub.hit)
        line(f"{period} : weekly même sens", sub.hit[sub.weekly == "même sens"])
        line(f"{period} : weekly sens opposé", sub.hit[sub.weekly == "sens opposé"])


if __name__ == "__main__":
    main()
