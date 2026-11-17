"""Statistiques des trades, courbe d'équité avec le risque dynamique, et simulation Alpha Capital Pro 6 %."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return c - h, c + h


def worst_streak(r: pd.Series) -> int:
    best = cur = 0
    for x in r:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    return best


def summary(t: pd.DataFrame) -> dict:
    if t.empty:
        return dict(trades=0)
    r = t.r
    wins = int((r > 0).sum())
    lo, hi = wilson(wins, len(r))
    cum = r.cumsum()
    gross_loss = -r[r < 0].sum()
    return dict(
        trades=len(r),
        win_rate=wins / len(r),
        win_ci=(lo, hi),
        expectancy_r=r.mean(),
        total_r=r.sum(),
        profit_factor=r[r > 0].sum() / gross_loss if gross_loss > 0 else math.inf,
        max_dd_r=(cum.cummax().clip(lower=0) - cum).max(),
        worst_streak=worst_streak(r),
        time_exits=float((t.outcome == "time").mean()),
    )


def risk_pct(equity: float, start: float, rules: dict) -> float:
    return rules["when_in_profit_pct"] if equity > start else rules["when_flat_or_drawdown_pct"]


def equity_curve(t: pd.DataFrame, rules: dict, start: float = 100_000.0) -> pd.DataFrame:
    """Applique le risque dynamique (1 % en positif, 0,5 % sinon) dans l'ordre chronologique.
    Le risque d'un trade dépend de l'équité RÉALISÉE au moment de son entrée."""
    t = t.sort_values("entry_time").reset_index(drop=True)
    equity = start
    pending: list[tuple[pd.Timestamp, float]] = []
    pnl = np.zeros(len(t))
    for i, row in t.iterrows():
        for ex, amount in [x for x in pending if x[0] <= row.entry_time]:
            equity += amount
        pending = [x for x in pending if x[0] > row.entry_time]
        amount = equity * risk_pct(equity, start, rules) / 100 * row.r
        pnl[i] = amount
        pending.append((row.exit_time, amount))
    t["pnl"] = pnl
    t = t.sort_values("exit_time")
    t["equity"] = start + t.pnl.cumsum()
    return t


def prop_firm(t: pd.DataFrame, rules: dict, prop: dict, start: float = 100_000.0) -> dict:
    """Démarre un challenge au début de chaque mois et le joue avec les trades réels qui suivent.
    Phase 1 puis phase 2 (+6 % chacune, 3 jours minimum), perte max 6 % statique,
    perte journalière max 3 % (sur les trades clôturés de la journée)."""
    t = t.sort_values("entry_time").reset_index(drop=True)
    target = prop["phases"][0]["profit_target_pct"] / 100
    min_days = prop["phases"][0]["min_trading_days"]
    max_dd = prop["max_drawdown_pct"] / 100
    daily = prop["max_daily_drawdown_pct"] / 100

    def run_phase(i0: int) -> tuple[str, int, int]:
        """Retourne (résultat, index du trade suivant, jours calendaires écoulés)."""
        eq, days, day_start_eq, cur_day = start, set(), start, None
        for i in range(i0, len(t)):
            row = t.iloc[i]
            if row.day != cur_day:
                cur_day, day_start_eq = row.day, eq
            eq += eq * risk_pct(eq, start, rules) / 100 * row.r
            days.add(row.day)
            elapsed = (row.exit_time - t.iloc[i0].entry_time).days
            if eq <= start * (1 - max_dd):
                return "echec_perte_max", i + 1, elapsed
            if eq <= day_start_eq * (1 - daily):
                return "echec_perte_jour", i + 1, elapsed
            if eq >= start * (1 + target) and len(days) >= min_days:
                return "reussi", i + 1, elapsed
        return "inacheve", len(t), 0

    results = []
    months = pd.Series(t.entry_time).dt.tz_localize(None).dt.to_period("M").unique()
    for m in months:
        i0 = int(np.argmax(t.entry_time.dt.tz_localize(None).dt.to_period("M") >= m))
        r1, i1, d1 = run_phase(i0)
        r2, d2 = ("non_joue", 0)
        if r1 == "reussi":
            r2, _, d2 = run_phase(i1)
        results.append(dict(start=str(m), phase1=r1, phase2=r2, days=d1 + d2))
    df = pd.DataFrame(results)
    done = df[(df.phase1 != "inacheve") & ~((df.phase1 == "reussi") & (df.phase2 == "inacheve"))]
    n = len(done)
    both = done[(done.phase1 == "reussi") & (done.phase2 == "reussi")]
    return dict(
        challenges=n,
        pass_phase1=(done.phase1 == "reussi").mean() if n else math.nan,
        pass_both=len(both) / n if n else math.nan,
        fail_max_loss=((done.phase1 == "echec_perte_max") | (done.phase2 == "echec_perte_max")).mean() if n else math.nan,
        fail_daily=((done.phase1 == "echec_perte_jour") | (done.phase2 == "echec_perte_jour")).mean() if n else math.nan,
        median_days_to_pass=float(both.days.median()) if len(both) else math.nan,
        detail=df,
    )
