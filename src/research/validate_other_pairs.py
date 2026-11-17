"""Validation hors échantillon : règle FIGÉE « C3 + filtre Weekly/Monthly » sur des paires jamais utilisées.

La règle a été trouvée sur EURUSD et GBPUSD (2015-2026). Ici, on ne change AUCUN paramètre :
on l'applique telle quelle à USDJPY, USDCAD, USDCHF et EURGBP. Coûts identiques (spread 4 points = 0,4 pip).

    python -m src.research.validate_other_pairs
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.backtest.metrics import summary
from src.backtest.run import load_plan, print_row
from src.backtest.strategy_crt import CRTParams, generate_trades
from src.data.resample import resample_all
from src.data.store import load_m1
from src.features.cisd import cisds

ROOT = Path("data")
PAIRS = ["USDJPY", "USDCAD", "USDCHF", "EURGBP"]
TFS = ["MN1", "W1", "D1", "H4", "H1", "M15"]


def bars_for(symbol: str, m1: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = ROOT / "bars"
    paths = {tf: out / f"{symbol}_{tf}.parquet" for tf in TFS}
    if not all(p.exists() for p in paths.values()):
        for tf, b in resample_all(m1, TFS).items():
            b.to_parquet(paths[tf])
    return {tf: pd.read_parquet(paths[tf]) for tf in TFS}


def main() -> None:
    plan = load_plan()
    kz = {k: (v["start"], v["end"]) for k, v in plan["time"]["killzones"].items()}
    results = []
    for symbol in PAIRS:
        m1 = load_m1(symbol, ROOT)
        bars = bars_for(symbol, m1)
        pip = 0.01 if symbol.endswith("JPY") else 0.0001
        sigs = {tf: cisds(bars[tf]) for tf in ["H4", "H1", "M15"]}
        for model in ["4H", "Daily"]:
            p = CRTParams(
                model=model, setups=("C3",), htf_filter=True, killzones=kz,
                pip=pip, spread=0.4 * pip, slippage=0.2 * pip, stop_buffer=0.5 * pip,
            )
            t = generate_trades(symbol, bars, m1, p, sigs)
            if not t.empty:
                t = t.sort_values("entry_time").groupby("day", group_keys=False).head(1)
            results.append(t)
            print(f"{symbol} {model}: {len(t)} trades", flush=True)

    allt = pd.concat(results, ignore_index=True)
    allt.to_csv(ROOT / "results" / "trades_validation_C3_HTF.csv", index=False)
    print(f"\n{'=' * 120}\nVALIDATION SUR PAIRES NON UTILISÉES — règle figée « C3 + Weekly/Monthly » (seuil : 33,3 % de gagnants)\n{'=' * 120}")
    print(f"{'groupe':14} {'période':10} {'trades':>6} {'gagnants':>9} {'IC95':>9} {'espérance':>10} {'total':>8} {'PF':>5} {'DD':>6} {'stop':>6}")
    for model, g in allt.groupby("model"):
        for symbol, gs in g.groupby("symbol"):
            print_row(f"{model} {symbol}", "2015-2026", gs)
        print_row(f"{model} TOUTES", "2015-2020", g[g.day.dt.year <= 2020])
        print_row(f"{model} TOUTES", "2021-2026", g[g.day.dt.year >= 2021])
        print_row(f"{model} TOUTES", "2015-2026", g)
        print()
    print_row("2 MODÈLES", "2015-2026", allt)


if __name__ == "__main__":
    main()
