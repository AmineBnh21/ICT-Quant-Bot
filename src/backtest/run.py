"""Lance le backtest v1 sur EURUSD et GBPUSD et affiche les résultats.

    python -m src.backtest.run                 # M5 et M15
    python -m src.backtest.run --tf M15

Les trades sont enregistrés dans data/results/trades_v1_{TF}.csv (journal).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from src.backtest.metrics import equity_curve, prop_firm, summary
from src.backtest.strategy_v1 import Params, generate_trades
from src.data.store import load_bars, load_m1
from src.features.cisd import cisds

ROOT = Path("data")
PAIRS = ["EURUSD", "GBPUSD"]


def load_plan() -> dict:
    return yaml.safe_load(Path("config/trading_plan.yaml").read_text(encoding="utf-8"))


def params_from_plan(plan: dict, tf: str) -> Params:
    c = plan["costs"]
    kz = {k: (v["start"], v["end"]) for k, v in plan["time"]["killzones"].items()}
    return Params(
        entry_tf=tf,
        killzones=kz,
        target_r=plan["risk"]["target_r"],
        spread=c["spread_points"] * c["point_size"],
        slippage=c["slippage_pips"] * 0.0001,
    )


def one_per_day(t: pd.DataFrame, max_per_day: int) -> pd.DataFrame:
    """Règle du plan : au plus ``max_per_day`` trades par jour, toutes paires confondues (les premiers remplis)."""
    t = t.sort_values("entry_time")
    return t.groupby("day", group_keys=False).head(max_per_day)


def fmt(s: dict) -> str:
    if not s.get("trades"):
        return "aucun trade"
    lo, hi = s["win_ci"]
    return (
        f"{s['trades']:>5} trades | gagnants {100 * s['win_rate']:4.1f} % [{100 * lo:.0f}–{100 * hi:.0f}] "
        f"| espérance {s['expectancy_r']:+.3f} R | total {s['total_r']:+7.1f} R | PF {s['profit_factor']:.2f} "
        f"| DD max {s['max_dd_r']:.1f} R | pire série {s['worst_streak']}"
    )


def report(tf: str, trades: pd.DataFrame, plan: dict) -> None:
    rules = plan["risk"]["risk_per_trade"]
    print(f"\n{'=' * 100}\nSTRATÉGIE v1, entrée {tf} — EURUSD + GBPUSD, 1 trade par jour max\n{'=' * 100}")
    print("Seuil de rentabilité à RR 1:2 : 33,3 % de gagnants\n")
    for label, mask in [
        ("2015-2020", trades.day.dt.year <= 2020),
        ("2021-2026", trades.day.dt.year >= 2021),
        ("TOUT", trades.day.notna()),
    ]:
        print(f"{label:10} {fmt(summary(trades[mask]))}")

    print("\nPar catégorie (toute la période) :")
    for col, title in [("symbol", "paire"), ("session", "session"), ("bias_kind", "bougie de biais"), ("side", "sens")]:
        for k, g in trades.groupby(col):
            name = {1: "long", -1: "short"}.get(k, k) if col == "side" else k
            print(f"  {title:15} {str(name):8} {fmt(summary(g))}")

    print("\nPar année :")
    for y, g in trades.groupby(trades.day.dt.year):
        print(f"  {y}  {fmt(summary(g))}")

    eq = equity_curve(trades, rules)
    peak = eq.equity.cummax()
    print(
        f"\nCompte de 100 000 $ avec risque 1 % (en positif) / 0,5 % (sinon) : "
        f"final {eq.equity.iloc[-1]:,.0f} $ | drawdown max {100 * ((peak - eq.equity) / peak).max():.1f} %"
    )
    pf = prop_firm(trades, rules, plan["prop_firm"])
    print(
        f"\nAlpha Capital Pro 6 % — {pf['challenges']} challenges simulés (un départ par mois) :\n"
        f"  phase 1 réussie : {100 * pf['pass_phase1']:.0f} % | les deux phases : {100 * pf['pass_both']:.0f} % "
        f"| échec perte max 6 % : {100 * pf['fail_max_loss']:.0f} % | échec perte jour 3 % : {100 * pf['fail_daily']:.0f} %"
        f"\n  durée médiane pour réussir les deux phases : {pf['median_days_to_pass']:.0f} jours"
    )


VARIANTS = {
    "base": {},
    "A discount": {"require_discount": True},
    "A + S1 H1": {"require_discount": True, "stop_mode": "h1_swing"},
    "A + S2 jour": {"require_discount": True, "stop_mode": "day_extreme"},
}
# Règles écartées : "B FVG H1" = {"require_htf_fvg": True} (dégrade les deux périodes),
# "C CISD H1" = {"h1_cisd": "all" | "C2"} (améliore une période, dégrade l'autre).


def compare(tfs: list[str], plan: dict, data: dict, out: Path) -> None:
    """Teste les règles de contexte une par une, puis ensemble, avec les mêmes signaux CISD."""
    rules = plan["risk"]["risk_per_trade"]
    for tf in tfs:
        signals = {s: cisds(load_bars(s, tf)) for s in PAIRS}
        print(f"\n{'=' * 118}\nCOMPARAISON DES RÈGLES DE CONTEXTE, entrée {tf} (seuil de rentabilité : 33,3 % de gagnants)\n{'=' * 118}")
        print(f"{'variante':12} {'période':10} {'trades':>6} {'gagnants':>9} {'IC95':>9} {'espérance':>10} {'total':>8} {'PF':>5} {'DD':>6} {'stop':>6}   prop 2015-2026 : P1 / 2 phases")
        for name, overrides in VARIANTS.items():
            p = params_from_plan(plan, tf)
            for k, v in overrides.items():
                setattr(p, k, v)
            all_t = pd.concat(
                [generate_trades(s, data[s][0], load_bars(s, tf), data[s][1], p, data[s][2], signals[s]) for s in PAIRS],
                ignore_index=True,
            )
            trades = one_per_day(all_t, plan["risk"]["max_trades_per_day"])
            trades.to_csv(out / f"trades_{tf}_{name.replace(' ', '_').replace('+', 'plus')}.csv", index=False)
            pf = prop_firm(trades, rules, plan["prop_firm"]) if len(trades) else None
            for label, mask in [("2015-2020", trades.day.dt.year <= 2020), ("2021-2026", trades.day.dt.year >= 2021)]:
                s = summary(trades[mask])
                if not s.get("trades"):
                    print(f"{name:12} {label:10} aucun trade")
                    continue
                lo, hi = s["win_ci"]
                prop = f"{100 * pf['pass_phase1']:3.0f} % / {100 * pf['pass_both']:3.0f} %" if label == "2015-2020" and pf else ""
                print(
                    f"{name:12} {label:10} {s['trades']:>6} {100 * s['win_rate']:8.1f}% {f'[{100 * lo:.0f}–{100 * hi:.0f}]':>9} "
                    f"{s['expectancy_r']:+9.3f}R {s['total_r']:+7.1f}R {s['profit_factor']:5.2f} {s['max_dd_r']:5.1f}R "
                    f"{trades[mask].stop_pips.median():5.1f}p   {prop}"
                )


CRT_VARIANTS = {
    "4H": {"model": "4H"},
    "4H + HTF": {"model": "4H", "htf_filter": True},
    "Daily": {"model": "Daily"},
    "Daily + HTF": {"model": "Daily", "htf_filter": True},
}


def print_row(name: str, label: str, t: pd.DataFrame, prop: str = "") -> None:
    s = summary(t)
    if not s.get("trades"):
        print(f"{name:14} {label:10} aucun trade")
        return
    lo, hi = s["win_ci"]
    print(
        f"{name:14} {label:10} {s['trades']:>6} {100 * s['win_rate']:8.1f}% {f'[{100 * lo:.0f}–{100 * hi:.0f}]':>9} "
        f"{s['expectancy_r']:+9.3f}R {s['total_r']:+7.1f}R {s['profit_factor']:5.2f} {s['max_dd_r']:5.1f}R "
        f"{t.stop_pips.median():5.1f}p   {prop}"
    )


def compare_crt(plan: dict, out: Path) -> None:
    """Les deux modèles CRT de l'utilisateur (4H : H4/H1/M15 ; Daily : D1/H4/H1), avec et sans filtre HTF."""
    from src.backtest.strategy_crt import CRTParams
    from src.backtest.strategy_crt import generate_trades as crt_trades

    rules = plan["risk"]["risk_per_trade"]
    c = plan["costs"]
    tfs = ["MN1", "W1", "D1", "H4", "H1", "M15"]
    bars = {s: {tf: load_bars(s, tf) for tf in tfs} for s in PAIRS}
    m1 = {s: load_m1(s, ROOT) for s in PAIRS}
    sigs = {s: {tf: cisds(bars[s][tf]) for tf in ["H4", "H1", "M15"]} for s in PAIRS}
    print(f"\n{'=' * 120}\nMODÈLES CRT HAUTE PROBABILITÉ (seuil de rentabilité : 33,3 % de gagnants)\n{'=' * 120}")
    print(f"{'variante':14} {'période':10} {'trades':>6} {'gagnants':>9} {'IC95':>9} {'espérance':>10} {'total':>8} {'PF':>5} {'DD':>6} {'stop':>6}   prop 2015-2026 : P1 / 2 phases")
    all_models = {}
    for name, overrides in CRT_VARIANTS.items():
        p = CRTParams(spread=c["spread_points"] * c["point_size"], slippage=c["slippage_pips"] * 0.0001,
                      killzones={k: (v["start"], v["end"]) for k, v in plan["time"]["killzones"].items()}, **overrides)
        t = pd.concat([crt_trades(s, bars[s], m1[s], p, sigs[s]) for s in PAIRS], ignore_index=True)
        if t.empty:
            print(f"{name:14} aucun trade")
            continue
        t = one_per_day(t, plan["risk"]["max_trades_per_day"])
        all_models[name] = t
        t.to_csv(out / f"trades_CRT_{name.replace(' ', '_').replace('+', 'plus')}.csv", index=False)
        pf = prop_firm(t, rules, plan["prop_firm"])
        prop = f"{100 * pf['pass_phase1']:3.0f} % / {100 * pf['pass_both']:3.0f} %"
        print_row(name, "2015-2020", t[t.day.dt.year <= 2020], prop)
        print_row(name, "2021-2026", t[t.day.dt.year >= 2021])
    print("\nDétail par setup (C2 = on trade pendant la formation du C2, C3 = après un C2 terminé) :")
    for name, t in all_models.items():
        for setup, g in t.groupby("bias_kind"):
            print_row(f"{name} {setup}", "2015-2020", g[g.day.dt.year <= 2020])
            print_row(f"{name} {setup}", "2021-2026", g[g.day.dt.year >= 2021])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", nargs="+", default=["M15"])
    ap.add_argument("--compare", action="store_true", help="compare les règles de contexte de la v1")
    ap.add_argument("--crt", action="store_true", help="les deux modèles CRT (4H et Daily)")
    args = ap.parse_args()
    plan = load_plan()
    out = ROOT / "results"
    out.mkdir(parents=True, exist_ok=True)
    if args.crt:
        compare_crt(plan, out)
        return
    data = {s: (load_bars(s, "D1"), load_m1(s, ROOT), load_bars(s, "H1")) for s in PAIRS}
    if args.compare:
        compare(args.tf, plan, data, out)
        return
    for tf in args.tf:
        p = params_from_plan(plan, tf)
        all_t = pd.concat(
            [generate_trades(s, data[s][0], load_bars(s, tf), data[s][1], p, data[s][2]) for s in PAIRS],
            ignore_index=True,
        )
        trades = one_per_day(all_t, plan["risk"]["max_trades_per_day"])
        trades.to_csv(out / f"trades_v1_{tf}.csv", index=False)
        report(tf, trades, plan)


if __name__ == "__main__":
    main()
