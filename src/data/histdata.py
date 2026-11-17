"""Téléchargement des bougies M1 (BID) depuis HistData.com (gratuit).

- Années terminées : un ZIP par an ; année en cours : un ZIP par mois.
- Contenu : ``DAT_ASCII_{PAIR}_M1_{periode}.csv`` avec des lignes ``YYYYMMDD HHMMSS;open;high;low;close;volume``.
- Fuseau : la doc HistData annonce « EST sans heure d'été », mais c'est FAUX, et ça a changé en 2019 :
    * **jusqu'au 31/12/2018** : heure de **New York** (avec l'heure d'été américaine) ;
    * **depuis le 01/01/2019** : heure de **Londres moins 5 h** (heure d'été européenne).
  Les deux coïncident l'été et l'hiver (NFP de 08:30 New York à 08:30 dans les fichiers). Ils ne
  diffèrent que pendant les semaines où les États-Unis ont changé d'heure et pas l'Europe (mi-mars →
  fin mars, fin octobre → début novembre). Méthode de vérification : l'ouverture du dimanche doit
  tomber à 17:00 New York toutes les semaines (voir le contrôle qualité de ``download.py``).
  Seule exception connue : USDSEK, semaine du 10/03/2019 (décalée d'une heure ; sert seulement au DXY).
  Les changements d'heure ont lieu le week-end, marché fermé : aucune heure ambiguë à gérer.
- Le volume vaut toujours 0 chez HistData : il n'est pas utilisable.

Le téléchargement imite le formulaire du site : on lit le jeton ``tk`` sur la page, puis POST sur ``/get.php``.
Les ZIP sont gardés dans ``data/raw/histdata/`` (reprise possible) et convertis en
``data/m1/{SYMBOL}/{YYYY-MM}.parquet`` (index UTC).
"""

from __future__ import annotations

import io
import logging
import re
import time
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

SITE = "https://www.histdata.com"
PAGE = SITE + "/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{pair}/{period}"
HEADERS = {"User-Agent": "Mozilla/5.0 (research backtest downloader)"}
DELAY_S = 1.0  # pause entre deux téléchargements, par politesse
TZ_SWITCH = pd.Timestamp("2019-01-01")  # changement de fuseau des fichiers HistData
LONDON_OFFSET = pd.Timedelta(hours=5)  # depuis 2019 : heure du fichier + 5 h = heure de Londres


def periods(start: date, end: date, today: date | None = None) -> list[str]:
    """Liste des fichiers à demander : 'YYYY' pour les années terminées, 'YYYY/M' pour l'année en cours."""
    today = today or date.today()
    out = []
    for year in range(start.year, end.year + 1):
        if year < today.year:
            out.append(str(year))
        else:
            first = start.month if year == start.year else 1
            last = min(end.month, today.month) if year == end.year else today.month
            out += [f"{year}/{m}" for m in range(first, last + 1)]
    return out


def fetch_zip(session: requests.Session, pair: str, period: str) -> bytes | None:
    """Télécharge le ZIP d'une période. Retourne None si HistData n'a pas ce fichier."""
    page_url = PAGE.format(pair=pair.lower(), period=period)
    page = session.get(page_url, timeout=60)
    page.raise_for_status()
    fields = dict(re.findall(r'<input type="hidden" name="(\w+)" id="\w+" value="([^"]*)"', page.text))
    if "tk" not in fields:
        return None
    r = session.post(SITE + "/get.php", data=fields, headers={"Referer": page_url}, timeout=300)
    r.raise_for_status()
    if not r.content.startswith(b"PK"):
        return None
    return r.content


def to_utc(local: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Heure des fichiers HistData → UTC (voir la note sur le fuseau en haut du module)."""
    old = local < TZ_SWITCH
    ny = local.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")
    london = (local + LONDON_OFFSET).tz_localize("Europe/London", ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")
    return pd.DatetimeIndex(ny.where(old, london), name="time")


def parse_zip(raw: bytes) -> pd.DataFrame:
    """ZIP HistData → DataFrame M1 indexé en UTC."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        text = z.read(name)
    df = pd.read_csv(
        io.BytesIO(text), sep=";", header=None, names=["time", "open", "high", "low", "close", "volume"]
    )
    local = pd.DatetimeIndex(pd.to_datetime(df.pop("time"), format="%Y%m%d %H%M%S"), name="time")
    df.index = to_utc(local)
    df = df[df.index.notna()].astype("f8")
    return df[~df.index.duplicated(keep="first")].sort_index()


def download_symbol(symbol: str, start: date, end: date, root: Path) -> None:
    raw_dir = root / "raw" / "histdata" / symbol.upper()
    raw_dir.mkdir(parents=True, exist_ok=True)
    all_periods = periods(start, end)
    with requests.Session() as session:
        session.headers.update(HEADERS)
        for period in all_periods:
            zip_path = raw_dir / f"{period.replace('/', '-')}.zip"
            is_latest = period == all_periods[-1] and "/" in period  # le mois en cours peut être incomplet
            if zip_path.exists() and not is_latest:
                raw = zip_path.read_bytes()  # cache local : pas de nouveau téléchargement
            else:
                raw = fetch_zip(session, symbol, period)
                time.sleep(DELAY_S)
                if raw is None:
                    log.warning("%s %s : pas de fichier sur HistData", symbol, period)
                    continue
                zip_path.write_bytes(raw)
            # conversion toujours refaite (rapide, idempotente) : un changement de parse_zip s'applique partout
            df = parse_zip(raw)
            write_months(df, symbol, root)
            log.info("%s %s : %d bougies M1", symbol, period, len(df))


def write_months(df: pd.DataFrame, symbol: str, root: Path) -> None:
    out_dir = root / "m1" / symbol.upper()
    out_dir.mkdir(parents=True, exist_ok=True)
    for (year, month), part in df.groupby([df.index.year, df.index.month]):
        path = out_dir / f"{year:04d}-{month:02d}.parquet"
        if path.exists():  # un mois peut être à cheval sur deux fichiers (décalage New York → UTC au 31/12)
            part = pd.concat([pd.read_parquet(path), part])
            part = part[~part.index.duplicated(keep="last")].sort_index()
        part.to_parquet(path)
