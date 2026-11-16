"""قاعده‌ی رنج کاربر: پین‌بار در لبه‌ی رنج + Key bar، حد ضرر نصف عرض رنج، حد سود لبه‌ی مقابل."""
import os
import sys
import unittest
from unittest import mock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot import backtest, range_trades  # noqa: E402


def frame(rows):
    idx = pd.date_range("2026-11-10", periods=len(rows), freq="5min", tz="UTC")
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)


def market(after):
    """۶۰ کندل آرام دور ۱۰۰، پین‌بار صعودی در کف، Key bar صعودی، بعد کندل‌های after."""
    rng = np.random.default_rng(3)
    rows = []
    for _ in range(60):
        m = 100 + rng.normal(0, 0.2)
        rows.append((m, m + 0.5, m - 0.5, m + rng.normal(0, 0.1)))
    rows.append((100.0, 100.4, 97.0, 100.2))       # پین‌بار: سایه‌ی پایین بلند، کف تازه
    rows.append((100.2, 102.1, 100.1, 102.0))      # Key bar صعودی قوی
    return frame(rows + after)


class TestRangeTrades(unittest.TestCase):
    RANGE = (106.0, 96.0, 50)                      # سقف، کف، طول رنج

    def run_with(self, after, stop_from="entry", confirm="key"):
        with mock.patch.object(range_trades, "range_at", lambda c, t, window=500: self.RANGE), \
                mock.patch.object(range_trades, "spread", lambda s: 0.1):
            return range_trades.run("XAUUSD", market(after), stop_from=stop_from, confirm=confirm)

    def test_default_enters_on_the_candle_after_the_pin(self):
        ev = self.run_with([(102.0, 104.5, 101.5, 104.2), (104.2, 106.5, 104, 106.2)], confirm="none")
        op = next(e for e in ev if e["kind"] == "TRADE_OPEN")
        self.assertEqual(op["side"], 1)
        self.assertAlmostEqual(op["entry"], 100.2 + 0.1)             # باز کندل بعد از پین‌بار + اسپرد
        self.assertAlmostEqual(op["sl"], 100.3 - 5 - 0.1)
        cl = next(e for e in ev if e["kind"] == "TRADE_CLOSED")
        self.assertEqual(cl["result"], "TP")
        self.assertAlmostEqual(cl["r"], round((106.0 - 100.3) / 5.1, 2))

    def test_buy_at_bottom_hits_other_edge(self):
        ev = self.run_with([(102.0, 103, 101.5, 102.8), (102.8, 104.5, 102.5, 104.2), (104.2, 106.5, 104, 106.2)])
        op = next(e for e in ev if e["kind"] == "TRADE_OPEN")
        self.assertEqual(op["side"], 1)
        self.assertAlmostEqual(op["entry"], 102.1)                   # باز کندل بعد از Key bar + اسپرد
        self.assertAlmostEqual(op["sl"], 102.1 - 5 - 0.1)            # نصف عرض رنج (۱۰/۲) از ورود
        self.assertAlmostEqual(op["tp"], 106.0)                      # لبه‌ی مقابل
        cl = next(e for e in ev if e["kind"] == "TRADE_CLOSED")
        self.assertEqual(cl["result"], "TP")
        self.assertAlmostEqual(cl["r"], round((106.0 - 102.1) / 5.1, 2))

    def test_stop_half_range_beyond_edge(self):
        ev = self.run_with([(102.0, 103, 101.5, 102.8)], stop_from="edge")
        op = next(e for e in ev if e["kind"] == "TRADE_OPEN")
        self.assertAlmostEqual(op["sl"], 96.0 - 5 - 0.1)

    def test_loss_is_minus_one_r(self):
        ev = self.run_with([(102.0, 102.2, 98, 98.5), (98.5, 98.6, 96.5, 96.8)])
        cl = next(e for e in ev if e["kind"] == "TRADE_CLOSED")
        self.assertEqual(cl["result"], "SL")
        self.assertAlmostEqual(cl["r"], -1.0)

    def test_no_range_no_trade(self):
        with mock.patch.object(range_trades, "range_at", lambda c, t, window=500: None):
            ev = range_trades.run("XAUUSD", market([(102.0, 103, 101.5, 102.8)]))
        self.assertEqual(ev, [])

    def test_backtest_button_runs_range_rules(self):
        self.assertIn(backtest.RANGE_TF, backtest.TF_PRESETS)
        rng = np.random.default_rng(5)
        mid = 100 + np.cumsum(rng.normal(0, 0.3, 3500))
        o = np.r_[mid[0], mid[:-1]]
        df = pd.DataFrame({"Open": o, "High": np.maximum(o, mid) + 0.3, "Low": np.minimum(o, mid) - 0.3,
                           "Close": mid}, index=pd.date_range("2026-11-02", periods=3500, freq="5min", tz="UTC"))
        res, err = backtest.run_days("XAUUSD", 5, m1=df, m5=df, tf=backtest.RANGE_TF)
        self.assertIsNone(err)
        self.assertEqual(res["strategy"], "range3")
        self.assertGreaterEqual((df.index < res["start"]).sum(), 500)      # ۵۰۰ کندل گرم شدن
        txt = backtest.report_text(res)
        self.assertIn("Range edges", txt)
        self.assertIn("Risk 2% per trade", txt)
        self.assertEqual([c["strategy"] for c in res["compare"]], ["range3_edge", "range3_key"])


if __name__ == "__main__":
    unittest.main()
