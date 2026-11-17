"""Stratégie CRT haute probabilité, deux modèles (règles de l'utilisateur, docs/strategy.md section 7 ter).

    Modèle 4H    : CRT en H4, confirmation en H1, entrée en M15
    Modèle Daily : CRT en D1, confirmation en H4, entrée en H1
Le M15 est le plus petit timeframe ; le M1 ne sert qu'au moteur d'exécution (ordre stop / cible).

Même logique fractale pour les deux. Pour un LONG (tout est inversé pour un short), avec X = timeframe CRT,
Y = timeframe de confirmation, Z = timeframe d'entrée, au moment d'un signal d'entrée :
1. CRT sur X (bougies C1-C2-C3) :
   - setup C3 : la dernière bougie X terminée est un C2 haussier (elle a balayé le bas de la bougie d'avant (C1)
     et clôturé dans son range) → on trade la bougie X en cours (C3). Cible = haut de C1 (CRT High).
   - setup C2 : la bougie X en cours a déjà balayé le bas de la bougie X précédente (C1), sans prendre son haut.
     Cible = haut de C1 (CRT High).
2. Confirmation sur Y, après le balayage : CISD Y haussier OU #01 First Opposing Candle (première bougie Y
   haussière qui clôture, à partir de la bougie Y du balayage).
3. Entrée sur Z : CISD Z haussier connu après la confirmation, dans une killzone. Limit au niveau du CISD,
   stop sous l'extrême Z, cible 2R fixe.
Filtres : la cible CRT doit être au-delà de 2R et pas encore prise ; entrée dans la moitié discount du range de
C1 (sous son 0,5) ; stop >= 3 pips ; un trade par jour et par paire ; sortie forcée 16:55 New York.
Option top-down : biais Weekly et Monthly (src/features/htf_bias.py) pas dans le sens opposé.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.backtest.engine import M1, simulate
from src.features.cisd import cisds
from src.features.daily_bias import day_key
from src.features.htf_bias import known_at as htf_known_at
from src.features.htf_bias import tf_bias

TZ = "America/New_York"
TF = {"M15": pd.Timedelta(minutes=15), "H1": pd.Timedelta(hours=1), "H4": pd.Timedelta(hours=4), "D1": pd.Timedelta(days=1)}
MODELS = {"4H": ("H4", "H1", "M15"), "Daily": ("D1", "H4", "H1")}


@dataclass
class CRTParams:
    model: str = "4H"
    killzones: dict = field(default_factory=lambda: {"london": ("02:00", "05:00"), "newyork": ("07:00", "10:00")})
    setups: tuple = ("C2", "C3")
    confirm: tuple = ("cisd", "first_opposing")  # l'une OU l'autre
    require_discount: bool = True
    htf_filter: bool = False
    target_r: float = 2.0
    pip: float = 0.0001
    spread: float = 0.00004
    slippage: float = 0.00002
    stop_buffer: float = 0.00005
    min_stop_pips: float = 3.0
    exit_hhmm: str = "16:55"


def _ns(ts: pd.Timestamp) -> int:
    return ts.tz_convert("UTC").as_unit("ns").value


class Frame:
    """Bougies d'un timeframe en tableaux numpy, avec recherche rapide par heure."""

    def __init__(self, df: pd.DataFrame, tf: str):
        self.df, self.dur = df, TF[tf]
        self.t = df.index
        self.o, self.h, self.l, self.c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))

    def containing(self, ts: pd.Timestamp) -> int:
        """Index de la bougie en cours à l'instant ``ts`` (ouverte avant ts)."""
        return int(self.t.searchsorted(ts, side="left")) - 1

    def between(self, a: pd.Timestamp, b: pd.Timestamp) -> tuple[int, int]:
        """Bougies qui OUVRENT dans [a, b) et sont TERMINÉES à b."""
        i0 = int(self.t.searchsorted(a, side="left"))
        i1 = int(self.t.searchsorted(b - self.dur, side="right"))
        return i0, max(i0, i1)


def first_sweep(y: Frame, a: pd.Timestamp, b: pd.Timestamp, side: int, level: float) -> int:
    """Première bougie Y terminée dans [a, b) qui balaie ``level`` (long : bas < level)."""
    i0, i1 = y.between(a, b)
    hit = (y.l[i0:i1] < level) if side == 1 else (y.h[i0:i1] > level)
    return i0 + int(np.argmax(hit)) if hit.any() else -1


def generate_trades(symbol: str, bars: dict[str, pd.DataFrame], m1_df: pd.DataFrame, p: CRTParams,
                    signals: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    x_tf, y_tf, z_tf = MODELS[p.model]
    X, Y = Frame(bars[x_tf], x_tf), Frame(bars[y_tf], y_tf)
    signals = signals or {}
    z_sig = (signals.get(z_tf) if z_tf in signals else cisds(bars[z_tf])).copy()
    y_sig = signals.get(y_tf) if y_tf in signals else cisds(bars[y_tf])
    y_cisd_known = {s: y_sig.index[y_sig.side == s] + Y.dur for s in (1, -1)}
    z_sig["known"] = z_sig.index + TF[z_tf]
    z_sig["day"] = day_key(pd.DatetimeIndex(z_sig.known - pd.Timedelta(minutes=1)))
    m1 = M1.from_frame(m1_df)
    m1_high, m1_low = m1_df["high"], m1_df["low"]

    htf = None
    if p.htf_filter:
        days = pd.DatetimeIndex(sorted(z_sig.day.unique()))
        opens = pd.DatetimeIndex([pd.Timestamp(d.strftime("%Y-%m-%d"), tz=TZ) - pd.Timedelta(hours=7) for d in days])
        htf = pd.DataFrame({"w": htf_known_at(tf_bias(bars["W1"]), opens).direction.to_numpy(),
                            "m": htf_known_at(tf_bias(bars["MN1"]), opens).direction.to_numpy()}, index=days)

    rows = []
    for day, sigs in z_sig.groupby("day"):
        date = day.strftime("%Y-%m-%d")
        exit_time = pd.Timestamp(f"{date} {p.exit_hhmm}", tz=TZ)
        done = False
        for kz_name, (kz_a, kz_z) in p.killzones.items():
            kz_s, kz_e = pd.Timestamp(f"{date} {kz_a}", tz=TZ), pd.Timestamp(f"{date} {kz_z}", tz=TZ)
            for t, s in sigs.iterrows():
                known = s.known
                if not (kz_s < known <= kz_e):
                    continue
                side = int(s.side)
                if htf is not None and (htf.at[day, "w"] == -side or htf.at[day, "m"] == -side):
                    continue
                j = X.containing(known)  # bougie X en cours
                if j < 2:
                    continue

                # 1) CRT sur X
                setup, c1, sweep_y = None, -1, -1
                k1, k2 = j - 1, j - 2  # dernière bougie X terminée, et celle d'avant
                c2_bull = X.l[k1] < X.l[k2] and X.h[k1] <= X.h[k2] and X.l[k2] < X.c[k1] < X.h[k2]
                c2_bear = X.h[k1] > X.h[k2] and X.l[k1] >= X.l[k2] and X.l[k2] < X.c[k1] < X.h[k2]
                if "C3" in p.setups and ((side == 1 and c2_bull) or (side == -1 and c2_bear)):
                    level = X.l[k2] if side == 1 else X.h[k2]
                    sweep_y = first_sweep(Y, X.t[k1], X.t[j], side, level)
                    setup, c1 = "C3", k2
                if setup is None and "C2" in p.setups:
                    level = X.l[k1] if side == 1 else X.h[k1]
                    sweep_y = first_sweep(Y, X.t[j], known, side, level)
                    if sweep_y >= 0:
                        win = slice(X.t[j].tz_convert("UTC"), known.tz_convert("UTC") - pd.Timedelta(minutes=1))
                        other_taken = m1_high.loc[win].max() > X.h[k1] if side == 1 else m1_low.loc[win].min() < X.l[k1]
                        if not other_taken:
                            setup, c1 = "C2", k1
                if setup is None or sweep_y < 0:
                    continue
                target_crt = X.h[c1] if side == 1 else X.l[c1]
                win = slice(X.t[j].tz_convert("UTC"), known.tz_convert("UTC") - pd.Timedelta(minutes=1))
                if (side == 1 and m1_high.loc[win].max() >= target_crt) or (side == -1 and m1_low.loc[win].min() <= target_crt):
                    continue  # CRT High / Low déjà pris

                # 2) Confirmation sur Y après le balayage
                sweep_t = Y.t[sweep_y]
                confirm = None
                if "cisd" in p.confirm:
                    k = y_cisd_known[side]
                    k = k[(k > sweep_t) & (k <= known)]
                    if len(k):
                        confirm = k[0]
                if "first_opposing" in p.confirm:
                    i1 = int(Y.t.searchsorted(known - Y.dur, side="right"))
                    seg = (Y.c[sweep_y:i1] > Y.o[sweep_y:i1]) if side == 1 else (Y.c[sweep_y:i1] < Y.o[sweep_y:i1])
                    if seg.any():
                        fo = Y.t[sweep_y + int(np.argmax(seg))] + Y.dur
                        confirm = fo if confirm is None else min(confirm, fo)
                if confirm is None or t < confirm:
                    continue  # la bougie qui valide le CISD d'entrée doit s'ouvrir après la confirmation

                # 3) Entrée sur Z
                entry = s.level
                stop = s.extreme - p.stop_buffer if side == 1 else s.extreme + p.stop_buffer + p.spread
                risk = abs(entry - stop)
                if risk < p.min_stop_pips * p.pip:
                    continue
                target = entry + side * p.target_r * risk
                if (side == 1 and target_crt < target) or (side == -1 and target_crt > target):
                    continue
                if p.require_discount:
                    eq = (X.h[c1] + X.l[c1]) / 2
                    if (side == 1 and entry > eq) or (side == -1 and entry < eq):
                        continue
                f = simulate(m1, side, entry, stop, target, _ns(known), _ns(kz_e), _ns(exit_time), p.spread, p.slippage)
                if not f.filled:
                    continue
                rows.append(dict(
                    symbol=symbol, day=day, model=p.model, session=kz_name, side=side, bias_kind=setup,
                    signal_time=known, entry_time=pd.Timestamp(f.entry_time, tz="UTC").tz_convert(TZ),
                    exit_time=pd.Timestamp(f.exit_time, tz="UTC").tz_convert(TZ),
                    entry=entry, stop=stop, target=target, dol=target_crt, exit_price=f.exit_price,
                    stop_pips=risk / p.pip, outcome=f.outcome, r=f.r, mae_r=f.mae_r, mfe_r=f.mfe_r,
                    pdh=X.h[c1], pdl=X.l[c1], cisd_run_start=s.run_start, cisd_extreme=s.extreme,
                    cisd_extreme_time=s.extreme_time, entry_tf=z_tf, sweep_time=sweep_t, confirm_time=confirm,
                ))
                done = True
                break
            if done:
                break
    return pd.DataFrame(rows)
