import io
import zipfile
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.data.dxy import CONSTANT, COMPONENTS, compute_dxy
from src.data.histdata import parse_zip, periods
from src.data.resample import resample


def _zip(lines):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("DAT_ASCII_EURUSD_M1_2024.csv", "\n".join(lines))
        z.writestr("DAT_ASCII_EURUSD_M1_2024.txt", "report")
    return buf.getvalue()


def test_parse_histdata_london_minus_5h():
    df = parse_zip(
        _zip(
            [
                "20240305 120000;1.08540;1.08541;1.08531;1.08535;0",  # hiver
                "20240705 083000;1.0854;1.0855;1.0853;1.0854;0",  # été (NFP 08:30 New York)
                "20240315 155900;1.0854;1.0855;1.0853;1.0854;0",  # USA à l'heure d'été, pas encore l'Europe
                "20180316 165900;1.0854;1.0855;1.0853;1.0854;0",  # avant 2019 : heure de New York
            ]
        )
    )
    times = set(df.index)
    assert pd.Timestamp("2024-03-05 17:00", tz="UTC") in times  # hiver : UTC-5
    assert pd.Timestamp("2024-07-05 12:30", tz="UTC") in times  # été : UTC-4
    assert pd.Timestamp("2024-03-15 20:59", tz="UTC") in times  # = 16:59 New York, clôture du vendredi
    assert pd.Timestamp("2018-03-16 20:59", tz="UTC") in times  # = 16:59 New York, clôture du vendredi
    assert len(df) == 4
    row = df.loc[pd.Timestamp("2024-03-05 17:00", tz="UTC")]
    assert (row.open, row.high, row.low, row.close) == (1.0854, 1.08541, 1.08531, 1.08535)
    assert df.index.is_monotonic_increasing


def test_periods_years_then_current_year_months():
    assert periods(date(2024, 1, 1), date(2026, 3, 31), today=date(2026, 11, 17)) == ["2024", "2025", "2026/1", "2026/2", "2026/3"]


def _m1(start_utc, end_utc, price=1.0):
    idx = pd.date_range(start_utc, end_utc, freq="1min", tz="UTC", inclusive="left")
    close = price + np.arange(len(idx)) * 1e-5
    return pd.DataFrame(
        {"open": close, "high": close + 1e-5, "low": close - 1e-5, "close": close, "volume": 1.0}, index=idx
    )


def test_daily_opens_at_17h_new_york_winter_and_summer():
    # hiver (EST, UTC-5) : 17:00 NY = 22:00 UTC ; été (EDT, UTC-4) : 17:00 NY = 21:00 UTC
    for start, open_utc in [("2024-01-07 22:00", "2024-01-07 22:00"), ("2024-07-07 21:00", "2024-07-07 21:00")]:
        m1 = _m1(start, pd.Timestamp(start) + pd.Timedelta(days=2))
        d1 = resample(m1, "D1")
        assert len(d1) == 2
        assert d1.index[0] == pd.Timestamp(open_utc, tz="UTC")
        assert d1.index[0].hour == 17 and d1.index[0].weekday() == 6  # dimanche 17:00 NY
        first_day = m1.iloc[: 24 * 60]
        assert d1.iloc[0].open == first_day.open.iloc[0]
        assert d1.iloc[0].close == first_day.close.iloc[-1]
        assert d1.iloc[0].high == first_day.high.max()


def test_h4_boundaries():
    m1 = _m1("2024-01-07 22:00", "2024-01-08 22:00")
    hours = sorted({t.hour for t in resample(m1, "H4").index})
    assert hours == [1, 5, 9, 13, 17, 21]


def test_weekly_opens_sunday_17h():
    m1 = _m1("2024-01-07 22:00", "2024-01-19 22:00")  # 2 semaines forex complètes
    w1 = resample(m1, "W1")
    assert len(w1) == 2
    assert all(t.weekday() == 6 and t.hour == 17 for t in w1.index)


def test_h1_matches_utc_hours():
    m1 = _m1("2024-01-08 10:00", "2024-01-08 12:00")
    h1 = resample(m1, "H1")
    assert len(h1) == 2 and h1.iloc[0].volume == 60


def test_dxy_constant_when_all_pairs_equal_one():
    m1 = {s: _m1("2024-01-08 10:00", "2024-01-08 10:05", price=1.0).assign(open=1.0, close=1.0) for s in COMPONENTS}
    dxy = compute_dxy(m1)
    assert len(dxy) == 5
    assert dxy.close.iloc[0] == pytest.approx(CONSTANT, abs=1e-4)


def test_dxy_rises_when_euro_falls():
    up = {s: _m1("2024-01-08 10:00", "2024-01-08 10:02").assign(open=1.0, close=1.0) for s in COMPONENTS}
    up["EURUSD"] = up["EURUSD"].assign(close=[1.0, 0.9])
    dxy = compute_dxy(up)
    assert dxy.close.iloc[1] > dxy.close.iloc[0]
