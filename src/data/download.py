"""Télécharge les M1 HistData puis construit les timeframes (et le DXY synthétique).

Exemples :
    python -m src.data.download                                  # tout, 2015-01-01 → hier
    python -m src.data.download --start 2024-01-01 --end 2024-03-31
    python -m src.data.download --skip-download                  # reconstruit seulement les timeframes

Sortie :
    data/raw/histdata/{SYMBOL}/*.zip        fichiers HistData d'origine
    data/m1/{SYMBOL}/{YYYY-MM}.parquet      bougies M1 (UTC)
    data/bars/{SYMBOL}_{TF}.parquet         M5 … MN1, index d'ouverture en heure de New York
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.data.histdata import download_symbol
from src.data.store import load_m1
from src.data.dxy import COMPONENTS, compute_dxy
from src.data.resample import TIMEFRAMES, resample_all

TRADED = ["EURUSD", "GBPUSD"]
EXTRA = ["EURGBP"]  # force relative (docs/strategy.md, section 4)
ALL_SYMBOLS = list(dict.fromkeys(TRADED + EXTRA + COMPONENTS))
BAR_SYMBOLS = TRADED + EXTRA + ["DXY"]

log = logging.getLogger("download")


def build_bars(root: Path, start: str | None, end: str | None) -> None:
    out_dir = root / "bars"
    out_dir.mkdir(parents=True, exist_ok=True)

    m1 = {s: load_m1(s, root, start, end) for s in ALL_SYMBOLS}
    m1["DXY"] = compute_dxy(m1)

    for symbol in BAR_SYMBOLS:
        for tf, bars in resample_all(m1[symbol], TIMEFRAMES).items():
            bars.to_parquet(out_dir / f"{symbol}_{tf}.parquet")
        log.info("%s : %d M1 → %s", symbol, len(m1[symbol]), ", ".join(TIMEFRAMES))
    report(m1)


def report(m1: dict[str, pd.DataFrame]) -> None:
    """Contrôle qualité, par jour de trading forex (17:00 → 17:00 New York) :
    - jours incomplets (< 20 h de données : trous, ou jours fériés comme Noël / 1er janvier) ;
    - heure d'ouverture du dimanche par année : doit être 17h New York, hiver comme été
      (sinon, problème de fuseau horaire dans la source)."""
    print("\nContrôle qualité des M1")
    print(f"{'symbole':8} {'bougies':>10}  {'début (UTC)':16}  {'fin (UTC)':16}  {'jours<20h':>9}  ouvertures du dimanche hors 17h NY")
    for s, df in m1.items():
        ny = df.index.tz_convert("America/New_York")
        trading_day = (ny.tz_localize(None) + pd.Timedelta(hours=7)).floor("D")
        per_day = pd.Series(1, index=trading_day).groupby(level=0).sum()
        thin = int((per_day < 20 * 60).sum())
        gap = (ny[1:] - ny[:-1]) > pd.Timedelta(hours=24)
        opens = pd.Series(ny[1:][gap])
        bad = opens[opens.dt.hour != 17]
        bad_txt = "aucune" if bad.empty else " ".join(f"{y}:{n}" for y, n in bad.dt.year.value_counts().sort_index().items())
        print(f"{s:8} {len(df):>10}  {str(df.index[0])[:16]}  {str(df.index[-1])[:16]}  {thin:>9}  {bad_txt}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--end", default=str(date.today() - timedelta(days=1)))
    p.add_argument("--root", type=Path, default=Path("data"))
    p.add_argument("--skip-download", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if not args.skip_download:
        start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
        for symbol in ALL_SYMBOLS:
            log.info("téléchargement %s %s → %s", symbol, start, end)
            download_symbol(symbol, start, end, args.root)
    build_bars(args.root, args.start, args.end)


if __name__ == "__main__":
    main()
