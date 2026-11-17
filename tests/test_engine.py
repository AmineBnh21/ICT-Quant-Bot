import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import M1, simulate

SPREAD = 0.00004


def m1(rows):
    """rows : (open, high, low) en BID, une par minute à partir de 0."""
    a = np.array(rows, dtype=float)
    return M1(np.arange(len(rows), dtype=np.int64) * 60, a[:, 0], a[:, 1], a[:, 2])


def run(bars, side, entry, stop, target, exit_at=10_000):
    return simulate(bars, side, entry, stop, target, 0, 10_000, exit_at, SPREAD, 0.0)


def test_long_fills_on_ask_then_hits_target():
    bars = m1([(1.1010, 1.1012, 1.1000), (1.1001, 1.1030, 1.1001)])
    # entrée 1.1000 : l'ASK (bid_low 1.1000 + 0.4 pip) n'y descend pas → pas rempli à la minute 0
    assert not run(bars, 1, 1.1000, 1.0990, 1.1020).filled
    bars = m1([(1.1010, 1.1012, 1.0995), (1.1001, 1.1030, 1.1001)])
    f = run(bars, 1, 1.1000, 1.0990, 1.1020)
    assert f.filled and f.outcome == "target" and f.r == pytest.approx(2.0)


def test_stop_and_target_same_minute_counts_as_stop():
    bars = m1([(1.1005, 1.1005, 1.0999), (1.1000, 1.1030, 1.0980)])
    f = run(bars, 1, 1.1000, 1.0990, 1.1020)
    assert f.outcome == "stop" and f.r == pytest.approx(-1.0)


def test_short_stop_triggers_on_ask():
    # short à 1.1000, stop 1.1010 : le BID monte à 1.10097 (sous le stop), l'ASK à 1.10101 → stop
    bars = m1([(1.0995, 1.1000, 1.0995), (1.1000, 1.10097, 1.0999)])
    f = run(bars, -1, 1.1000, 1.1010, 1.0980)
    assert f.outcome == "stop"


def test_time_exit():
    bars = m1([(1.1005, 1.1005, 1.0995), (1.1002, 1.1004, 1.1001), (1.1003, 1.1004, 1.1002)])
    f = run(bars, 1, 1.1000, 1.0990, 1.1020, exit_at=120)
    assert f.outcome == "time" and f.r == pytest.approx(0.3)
