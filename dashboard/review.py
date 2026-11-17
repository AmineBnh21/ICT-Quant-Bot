"""Revue visuelle des trades du backtest.

Lancement (depuis la racine du projet) :
    .venv\\Scripts\\streamlit run dashboard/review.py

Pour chaque trade : graphique avec la bougie de la veille (PDH, PDL, EQ), la DOL, les killzones,
le CISD (début de la série, extrême, niveau), l'entrée, le stop, la cible et la sortie.
Ton avis sur chaque trade est enregistré dans data/results/review_notes.csv.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.store import load_bars  # noqa: E402

RESULTS = ROOT / "data" / "results"
NOTES = RESULTS / "review_notes.csv"
TZ = "America/New_York"
KILLZONES = {"Londres": ("02:00", "05:00"), "New York": ("07:00", "10:00")}
COLORS = {"entry": "#2563eb", "stop": "#dc2626", "target": "#16a34a", "dol": "#9333ea", "day": "#6b7280"}

st.set_page_config(page_title="Revue des trades", layout="wide")


@st.cache_data(show_spinner=False)
def bars(symbol: str, tf: str) -> pd.DataFrame:
    return load_bars(symbol, tf, ROOT / "data")


@st.cache_data(show_spinner=False)
def trades(path: str) -> pd.DataFrame:
    t = pd.read_csv(path)
    for c in ["day", "signal_time", "entry_time", "exit_time", "cisd_run_start", "cisd_extreme_time"]:
        if c in t:
            t[c] = pd.to_datetime(t[c], utc=True).dt.tz_convert(TZ) if c != "day" else pd.to_datetime(t[c])
    t["trade_id"] = t.symbol + " " + t.entry_time.dt.strftime("%Y-%m-%d %H:%M")
    return t.sort_values("entry_time").reset_index(drop=True)


def load_notes() -> pd.DataFrame:
    if NOTES.exists():
        return pd.read_csv(NOTES)
    return pd.DataFrame(columns=["fichier", "trade_id", "verdict", "commentaire"])


def save_note(fichier: str, trade_id: str, verdict: str, commentaire: str) -> None:
    notes = load_notes()
    notes = notes[~((notes.fichier == fichier) & (notes.trade_id == trade_id))]
    row = pd.DataFrame([dict(fichier=fichier, trade_id=trade_id, verdict=verdict, commentaire=commentaire)])
    pd.concat([notes, row], ignore_index=True).to_csv(NOTES, index=False)


def chart(tr: pd.Series, tf: str) -> go.Figure:
    day = tr.day.strftime("%Y-%m-%d")
    day_open = pd.Timestamp(f"{day} 00:00", tz=TZ) - pd.Timedelta(hours=7)  # 17:00 la veille
    # on montre aussi la bougie daily de la veille (la vraie : le vendredi pour un lundi)
    d1 = bars(tr.symbol, "D1")
    before = d1.index[d1.index < day_open - pd.Timedelta(hours=1)]
    start = before[-1] if len(before) else day_open - pd.Timedelta(hours=24)
    end = max(tr.exit_time, pd.Timestamp(f"{day} 12:00", tz=TZ)) + pd.Timedelta(hours=2)
    b = bars(tr.symbol, tf).loc[start:end]
    # masquer les heures sans cotation (week-end, jours fériés) pour garder un graphique continu
    step = b.index.to_series().diff().min()
    gaps = [dict(bounds=[t0 + step, t1]) for t0, t1 in zip(b.index[:-1], b.index[1:]) if t1 - t0 > pd.Timedelta(hours=2)]

    fig = go.Figure(
        go.Candlestick(
            x=b.index, open=b.open, high=b.high, low=b.low, close=b.close, name=tf,
            increasing_line_color="#16a34a", decreasing_line_color="#111827", showlegend=False,
        )
    )
    # jour de la veille et jour du trade
    fig.add_vrect(x0=start, x1=day_open, fillcolor="#f3f4f6", opacity=0.5, line_width=0,
                  annotation_text="veille", annotation_position="top left")
    for name, (a, z) in KILLZONES.items():
        fig.add_vrect(x0=pd.Timestamp(f"{day} {a}", tz=TZ), x1=pd.Timestamp(f"{day} {z}", tz=TZ),
                      fillcolor="#fde68a", opacity=0.25, line_width=0,
                      annotation_text=name, annotation_position="top left")
    eq = (tr.pdh + tr.pdl) / 2

    def hline(y, x0, x1, color, text, dash="solid", yshift=0):
        fig.add_shape(type="line", x0=x0, x1=x1, y0=y, y1=y, line=dict(color=color, width=1.5, dash=dash))
        fig.add_annotation(x=x1, y=y, text=text, showarrow=False, xanchor="left", yshift=yshift,
                           font=dict(color=color, size=11))

    hline(tr.pdh, start, end, COLORS["day"], "PDH", "dot", yshift=-8 if tr.side == 1 else 0)
    hline(tr.pdl, start, end, COLORS["day"], "PDL", "dot", yshift=8 if tr.side == -1 else 0)
    hline(eq, day_open, end, COLORS["day"], "EQ veille", "dash")
    hline(tr.dol, day_open, end, COLORS["dol"], "DOL (cible du biais)", yshift=8 if tr.side == 1 else -8)
    hline(tr.entry, tr.signal_time, tr.exit_time, COLORS["entry"], "entrée")
    hline(tr.stop, tr.signal_time, tr.exit_time, COLORS["stop"], "stop")
    hline(tr.target, tr.signal_time, tr.exit_time, COLORS["target"], "cible 2R")

    if "cisd_run_start" in tr and pd.notna(tr.cisd_run_start):
        fig.add_shape(type="line", x0=tr.cisd_run_start, x1=tr.signal_time, y0=tr.entry, y1=tr.entry,
                      line=dict(color=COLORS["entry"], width=1, dash="dot"))
        fig.add_trace(go.Scatter(x=[tr.cisd_extreme_time], y=[tr.cisd_extreme], mode="markers+text",
                                 text=["extrême CISD"], textposition="bottom center" if tr.side == 1 else "top center",
                                 marker=dict(symbol="x", size=10, color=COLORS["stop"]), showlegend=False))
    fig.add_trace(go.Scatter(x=[tr.signal_time], y=[tr.entry], mode="markers+text", text=["CISD"],
                             textposition="top center", marker=dict(symbol="diamond", size=10, color="#f59e0b"),
                             showlegend=False))
    fig.add_trace(go.Scatter(x=[tr.entry_time, tr.exit_time], y=[tr.entry, tr.exit_price], mode="markers+lines",
                             marker=dict(size=11, symbol=["triangle-up" if tr.side == 1 else "triangle-down", "square"],
                                         color=[COLORS["entry"], COLORS["target"] if tr.r > 0 else COLORS["stop"]]),
                             line=dict(color="#94a3b8", dash="dot"), showlegend=False))
    fig.update_layout(height=640, margin=dict(l=80, r=130, t=30, b=10), xaxis_rangeslider_visible=False,
                      plot_bgcolor="white", hovermode="x unified")
    fig.update_xaxes(rangebreaks=gaps, showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#f1f5f9", tickformat=".5f")
    return fig


# ---------------------------------------------------------------- interface
files = sorted(RESULTS.glob("trades_*.csv"))
if not files:
    st.error("Aucun journal de trades. Lance d'abord : python -m src.backtest.run --compare")
    st.stop()

with st.sidebar:
    st.header("Journal")
    default = next((i for i, f in enumerate(files) if f.name == "trades_M15_A_discount.csv"), 0)
    path = st.selectbox("Fichier de trades", files, index=default, format_func=lambda f: f.name)
    t = trades(str(path))
    st.header("Filtres")
    pairs = st.multiselect("Paire", sorted(t.symbol.unique()), default=sorted(t.symbol.unique()))
    outcome = st.multiselect("Résultat", ["target", "stop", "time"], default=["target", "stop", "time"])
    kinds = st.multiselect("Biais (bougie de la veille)", sorted(t.bias_kind.unique()), default=sorted(t.bias_kind.unique()))
    sessions = st.multiselect("Session", sorted(t.session.unique()), default=sorted(t.session.unique()))
    years = st.slider("Années", int(t.day.dt.year.min()), int(t.day.dt.year.max()),
                      (int(t.day.dt.year.min()), int(t.day.dt.year.max())))
    only_unreviewed = st.checkbox("Seulement les trades pas encore revus")
    tf = st.radio("Timeframe du graphique", ["M5", "M15", "H1"], index=1, horizontal=True)

f = t[t.symbol.isin(pairs) & t.outcome.isin(outcome) & t.bias_kind.isin(kinds) & t.session.isin(sessions)
      & t.day.dt.year.between(*years)].reset_index(drop=True)
notes = load_notes()
reviewed = set(notes[notes.fichier == path.name].trade_id)
if only_unreviewed:
    f = f[~f.trade_id.isin(reviewed)].reset_index(drop=True)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Trades (filtre)", len(f))
c2.metric("Gagnants", f"{100 * (f.r > 0).mean():.1f} %" if len(f) else "–")
c3.metric("Espérance", f"{f.r.mean():+.3f} R" if len(f) else "–")
c4.metric("Total", f"{f.r.sum():+.1f} R" if len(f) else "–")
c5.metric("Revus", f"{len(reviewed)}")

if f.empty:
    st.info("Aucun trade avec ces filtres.")
    st.stop()

if "i" not in st.session_state:
    st.session_state.i = 0
st.session_state.i = min(st.session_state.i, len(f) - 1)
n1, n2, n3, n4 = st.columns([1, 1, 1, 4])
if n1.button("◀ Précédent"):
    st.session_state.i = max(0, st.session_state.i - 1)
if n2.button("Suivant ▶"):
    st.session_state.i = min(len(f) - 1, st.session_state.i + 1)
if n3.button("🎲 Au hasard"):
    st.session_state.i = int(pd.Series(range(len(f))).sample(1).iloc[0])
st.session_state.i = n4.number_input("Trade n°", 0, len(f) - 1, st.session_state.i)

tr = f.iloc[st.session_state.i]
sens = "LONG" if tr.side == 1 else "SHORT"
res = {"target": "✅ cible 2R", "stop": "❌ stop", "time": "⏱ sortie 16:55"}[tr.outcome]
st.subheader(f"{tr.trade_id} · {sens} · biais {tr.bias_kind} · session {tr.session} · {res} ({tr.r:+.2f} R)")
st.caption(
    f"Entrée {tr.entry:.5f} · stop {tr.stop:.5f} ({tr.stop_pips:.1f} pips) · cible {tr.target:.5f} · DOL {tr.dol:.5f} · "
    f"MAE {tr.mae_r:+.2f} R · MFE {tr.mfe_r:+.2f} R · sortie {tr.exit_time:%H:%M} à {tr.exit_price:.5f}"
)
st.plotly_chart(chart(tr, tf), width="stretch")

st.markdown("#### Ton avis sur ce trade")
prev = notes[(notes.fichier == path.name) & (notes.trade_id == tr.trade_id)]
options = ["Je l'aurais pris comme ça", "Je l'aurais pris, mais autrement", "Je ne l'aurais pas pris"]
v0 = options.index(prev.verdict.iloc[0]) if len(prev) and prev.verdict.iloc[0] in options else 0
with st.form(key=f"note-{path.name}-{tr.trade_id}"):
    verdict = st.radio("Verdict", options, index=v0, horizontal=True)
    comment = st.text_area("Pourquoi ? (biais, DOL, PD Array, entrée, stop…)",
                           value=prev.commentaire.iloc[0] if len(prev) and pd.notna(prev.commentaire.iloc[0]) else "")
    if st.form_submit_button("Enregistrer"):
        save_note(path.name, tr.trade_id, verdict, comment)
        st.success("Enregistré dans data/results/review_notes.csv")
