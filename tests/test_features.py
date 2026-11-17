import numpy as np
import pandas as pd

from src.features.cisd import cisds
from src.features.daily_bias import label_days
from src.features.fvg import fvgs
from src.features.swings import swings


def bars(rows, start="2024-01-08 02:00", freq="5min"):
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="America/New_York")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_swing_high_and_low_with_confirmation_time():
    b = bars([(1, 2, 0.5, 1.5), (1.5, 3, 1, 2), (2, 2.5, 0.2, 1), (1, 1.5, 0.8, 1.2)])
    s = swings(b)
    assert s.swing_high.tolist() == [False, True, False, False]
    assert s.swing_low.tolist() == [False, False, True, False]
    assert s.confirmed_at.iloc[1] == b.index[2]  # connu seulement à la bougie suivante


def test_bullish_fvg_and_kind():
    # c1 haut 1.0 ; c2 grosse bougie haussière ; c3 bas 1.2 > 1.0 → FVG [1.0, 1.2]
    rows = [(0.9, 1.0, 0.8, 0.95)] * 14 + [(0.9, 1.0, 0.8, 0.95), (0.95, 1.5, 0.95, 1.45), (1.45, 1.5, 1.2, 1.48)]
    f = fvgs(bars(rows), min_size_atr=0.0)
    assert len(f) == 1
    row = f.iloc[0]
    assert (row.side, row.bottom, row.top) == (1, 1.0, 1.2)
    assert row.kind == "PFVG"  # 3e bougie : petit corps, pas de grosse mèche haute


def test_bearish_fvg_rejection_kind():
    rows = [(1.5, 1.6, 1.4, 1.45), (1.45, 1.45, 1.0, 1.05), (1.25, 1.3, 1.0, 1.27)]
    f = fvgs(bars(rows), min_size_atr=0.0, atr_period=1)
    row = f.iloc[0]
    assert (row.side, row.top, row.bottom) == (-1, 1.4, 1.3)
    assert row.kind == "RFVG"  # mèche basse (opposée) >= 50 % du range


def test_bullish_cisd_level_is_open_of_bearish_run_that_made_the_low():
    rows = [
        (1.10, 1.11, 1.09, 1.105),  # haussière
        (1.105, 1.106, 1.095, 1.097),  # série baissière : open 1.105
        (1.097, 1.098, 1.090, 1.091),  # plus bas 1.090
        (1.091, 1.100, 1.090, 1.099),  # haussière, clôture 1.099 < 1.105 : pas encore
        (1.099, 1.110, 1.098, 1.108),  # clôture 1.108 > 1.105 → CISD
    ]
    b = bars(rows)
    c = cisds(b)
    bull = c[c.side == 1]
    assert len(bull) == 1
    assert bull.index[0] == b.index[4]
    assert bull.iloc[0].level == 1.105
    assert bull.iloc[0].extreme == 1.090


def test_daily_labels_c2_then_c3():
    idx = pd.date_range("2024-01-07 17:00", periods=4, freq="D", tz="America/New_York")
    d1 = pd.DataFrame(
        {
            "open": [1.10, 1.10, 1.095, 1.105],
            "high": [1.11, 1.105, 1.115, 1.12],
            "low": [1.09, 1.085, 1.094, 1.10],  # jour 2 balaie le bas du jour 1
            "close": [1.10, 1.095, 1.112, 1.118],  # jour 2 clôture dedans ; jour 3 clôture > haut du jour 2
            "volume": 0.0,
        },
        index=idx,
    )
    lab = label_days(d1)
    assert lab.kind.tolist() == ["none", "C2", "C3", "C4"]
    assert lab.direction.tolist() == [0, 1, 1, 1]


def test_htf_fvg_zone_valid_until_close_through():
    from src.features.context import fvg_zones, touched_valid_zone

    rows = [(1.00, 1.01, 0.99, 1.005)] * 15 + [
        (1.00, 1.01, 0.99, 1.005),  # c1 : haut 1.01
        (1.005, 1.05, 1.005, 1.045),  # c2 : expansion
        (1.045, 1.05, 1.02, 1.048),  # c3 : bas 1.02 → FVG haussière [1.01, 1.02]
        (1.048, 1.049, 1.015, 1.03),  # mèche dans la zone, clôture au-dessus : respect
        (1.03, 1.031, 1.00, 1.005),  # clôture sous 1.01 : FVG invalidée
    ]
    b = bars(rows, freq="1h")
    z = fvg_zones(b, pd.Timedelta(hours=1), min_size_atr=0.0)
    z = z[z.side == 1]
    assert len(z) == 1 and z.iloc[0].bottom == 1.01 and z.iloc[0].top == 1.02
    t_touch, t_after = b.index[18], b.index[19] + pd.Timedelta(hours=1)
    assert touched_valid_zone(z, 1, 1.015, t_touch, t_touch + pd.Timedelta(hours=1))
    assert not touched_valid_zone(z, 1, 1.015, t_touch, t_after)  # signal après l'invalidation
    assert not touched_valid_zone(z, 1, 1.03, t_touch, t_touch + pd.Timedelta(hours=1))  # pas descendu dans la zone


def test_pd_array_respect_and_disrespect():
    from src.features.htf_bias import pd_array_dir

    rows = [
        (1.10, 1.12, 1.09, 1.11),
        (1.11, 1.11, 1.05, 1.06),  # swing low 1.05 (i=1)
        (1.06, 1.13, 1.06, 1.12),
        (1.12, 1.14, 1.10, 1.13),  # swing low connu à partir d'ici
        (1.13, 1.13, 1.04, 1.07),  # mèche sous 1.05, clôture au-dessus → respect → +1
        (1.07, 1.12, 1.07, 1.11),
    ]
    d = pd_array_dir(bars(rows, freq="D"))
    assert d.iloc[4] == 1 and d.iloc[5] == 1

    rows2 = rows[:4] + [(1.13, 1.13, 1.03, 1.04)]  # clôture sous 1.05 → disrespect → -1
    assert pd_array_dir(bars(rows2, freq="D")).iloc[4] == -1


def test_known_at_uses_only_finished_candles():
    from src.features.htf_bias import known_at

    idx = pd.date_range("2024-01-07 17:00", periods=3, freq="7D", tz="America/New_York")
    b = pd.DataFrame({"direction": [1, -1, 1]}, index=idx)
    t = pd.DatetimeIndex([idx[0] + pd.Timedelta(days=1), idx[1] + pd.Timedelta(days=1)])
    res = known_at(b, t)
    assert np.isnan(res.direction.iloc[0])  # la 1re semaine n'est pas finie
    assert res.direction.iloc[1] == 1  # pendant la 2e semaine, on connaît la 1re
