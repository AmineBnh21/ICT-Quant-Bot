"""CRT 4H : entrer seulement pendant les bougies H4 de 1am, 5am et 9am (New York).

Testé en même temps sur les paires de travail (EURUSD, GBPUSD) et sur les paires de validation
(USDJPY, USDCAD, USDCHF, EURGBP) : une règle n'est crédible que si elle tient sur les deux groupes.

    python -m src.research.crt4h_key_candles
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.backtest.metrics import prop_firm
from src.backtest.run import load_plan, print_row
from src.backtest.strategy_crt import CRTParams, generate_trades
from src.data.store import load_m1
from src.features.cisd import cisds
from src.research.validate_other_pairs import bars_for

ROOT = Path("data")
WORK = ["EURUSD", "GBPUSD"]
VALID = ["USDJPY", "USDCAD", "USDCHF", "EURGBP"]
WHOLE_CANDLE = {"bougie": ("00:00", "16:55")}
VARIANTS = {
    "KZ": dict(htf_filter=False, kz=None),
    "KZ + HTF": dict(htf_filter=True, kz=None),
    "sans KZ": dict(htf_filter=False, kz=WHOLE_CANDLE),
    "sans KZ + HTF": dict(htf_filter=True, kz=WHOLE_CANDLE),
}


def main() -> None:
    plan = load_plan()
    plan_kz = {k: (v["start"], v["end"]) for k, v in plan["time"]["killzones"].items()}
    data = {}
    for s in WORK + VALID:
        m1 = load_m1(s, ROOT)
        bars = bars_for(s, m1)
        data[s] = (bars, m1, {tf: cisds(bars[tf]) for tf in ["H4", "H1", "M15"]})
        print(f"{s} chargé", flush=True)

    rows = []
    for name, v in VARIANTS.items():
        for s in WORK + VALID:
            bars, m1, sigs = data[s]
            pip = 0.01 if s.endswith("JPY") else 0.0001
            p = CRTParams(model="4H", x_hours=(1, 5, 9), htf_filter=v["htf_filter"], killzones=v["kz"] or plan_kz,
                          pip=pip, spread=0.4 * pip, slippage=0.2 * pip, stop_buffer=0.5 * pip)
            t = generate_trades(s, bars, m1, p, sigs)
            if not t.empty:
                t = t.sort_values("entry_time").groupby("day", group_keys=False).head(1)
                t["variant"] = name
                rows.append(t)
    allt = pd.concat(rows, ignore_index=True)
    allt["groupe"] = allt.symbol.map(lambda s: "travail" if s in WORK else "validation")
    allt["heure"] = pd.to_datetime(allt.x_candle, utc=True).dt.tz_convert("America/New_York").dt.hour
    allt.to_csv(ROOT / "results" / "trades_CRT_4H_1-5-9.csv", index=False)

    print(f"\n{'=' * 120}\nCRT 4H, bougies 1am / 5am / 9am seulement (seuil : 33,3 % de gagnants)\n{'=' * 120}")
    print(f"{'variante':24} {'période':10} {'trades':>6} {'gagnants':>9} {'IC95':>9} {'espérance':>10} {'total':>8} {'PF':>5} {'DD':>6} {'stop':>6}")
    for name in VARIANTS:
        g = allt[allt.variant == name]
        for grp in ["travail", "validation"]:
            gg = g[g.groupe == grp]
            print_row(f"{name} [{grp[:5]}]", "2015-2020", gg[gg.day.dt.year <= 2020])
            print_row(f"{name} [{grp[:5]}]", "2021-2026", gg[gg.day.dt.year >= 2021])
        print()
    print("Détail (toutes paires, 2015-2026) par bougie et par setup :")
    for name in VARIANTS:
        g = allt[allt.variant == name]
        for h, gh in g.groupby("heure"):
            print_row(f"{name} {h}h", "2015-2026", gh)
        for setup, gs in g.groupby("bias_kind"):
            print_row(f"{name} {setup}", "2015-2026", gs)
        print()
    rules = plan["risk"]["risk_per_trade"]
    for name in VARIANTS:
        g = allt[(allt.variant == name) & (allt.groupe == "travail")].sort_values("entry_time")
        g = g.groupby("day", group_keys=False).head(1)
        pf = prop_firm(g, rules, plan["prop_firm"])
        print(f"Alpha Capital (EURUSD+GBPUSD, 1 trade/jour) {name:16}: phase 1 {100 * pf['pass_phase1']:.0f} % | 2 phases {100 * pf['pass_both']:.0f} %")


if __name__ == "__main__":
    main()
