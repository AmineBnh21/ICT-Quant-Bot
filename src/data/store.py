"""Lecture des données stockées dans ``data/``."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_m1(symbol: str, root: Path, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Charge les M1 d'un symbole (index UTC), filtrées sur [start, end] (dates ISO) si données."""
    files = sorted((root / "m1" / symbol.upper()).glob("*.parquet"))
    if start:
        files = [f for f in files if f.stem >= start[:7]]
    if end:
        files = [f for f in files if f.stem <= end[:7]]
    if not files:
        raise FileNotFoundError(f"aucune donnée M1 pour {symbol} dans {root / 'm1'}")
    df = pd.concat(pd.read_parquet(f) for f in files).sort_index()
    if start:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        df = df[df.index < pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)]
    return df


def load_bars(symbol: str, tf: str, root: Path = Path("data")) -> pd.DataFrame:
    """Charge les bougies d'un timeframe (index d'ouverture en heure de New York)."""
    return pd.read_parquet(root / "bars" / f"{symbol.upper()}_{tf}.parquet")
