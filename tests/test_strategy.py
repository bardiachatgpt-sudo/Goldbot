"""تست‌های تشخیص، اسکنر و پیام‌ها با داده‌ی ساختگی (بدون اینترنت)."""
import os
import sys
import unittest
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import scanner  # noqa: E402
from bot.chart import render_chart  # noqa: E402
from bot.messages import build_alert, build_report  # noqa: E402
from bot.strategy import analyze, new_events  # noqa: E402
from tests.synthetic import candles  # noqa: E402


class TestStrategy(unittest.TestCase):
    def setUp(self):
        self.c = candles()
        self.res = analyze(self.c)

    def test_pullback_counts_only_in_matching_context(self):
        df = self.res["df"]
        self.assertTrue((df.loc[df.h_setup > 0, "close"] > df.loc[df.h_setup > 0, "ema20"]).all())
        self.assertTrue((df.loc[df.l_setup > 0, "close"] < df.loc[df.l_setup > 0, "ema20"]).all())
        self.assertGreater((df.h_setup > 0).sum(), 0)
        self.assertGreater((df.l_setup > 0).sum(), 0)

    def test_wedges_are_three_pushes(self):
        self.assertTrue(self.res["all_wedges"])
        for w in self.res["all_wedges"]:
            p = [x["price"] for x in w["points"]]
            self.assertTrue(p[0] > p[1] > p[2] if w["side"] > 0 else p[0] < p[1] < p[2])

    def test_report_and_chart(self):
        txt = build_report("XAUUSD", self.res)
        self.assertIn("Market cycle", txt)
        png = render_chart("XAUUSD", self.res)
        self.assertEqual(png[:4], b"\x89PNG")

    def test_live_scan_matches_batch(self):
        """اسکن کندل‌به‌کندل باید دقیقاً همان هشدارهای تحلیل یک‌جا را بدهد، بدون تکرار."""
        n0 = 400
        live = []
        feed = {"n": n0}

        def fake(sym, n_bars, min_bars, interval=None):
            return self.c.iloc[max(0, feed["n"] - n_bars):feed["n"]]

        with mock.patch.object(scanner, "get_closed_candles", fake), \
             mock.patch.object(scanner, "BARS", 10_000), \
             mock.patch.object(scanner, "SYMBOLS", {"XAUUSD": []}), \
             mock.patch.object(scanner, "ALERT_SETUPS", {"H1", "H2", "L1", "L2", "WEDGE"}), \
             mock.patch.object(scanner, "build_alert", lambda ev: ev):
            seen = {}
            scanner.scan_once(seen, live.append)          # اولین اجرا: بی‌صدا
            self.assertEqual(live, [])
            scanner.scan_once(seen, live.append)          # کندل جدیدی نیامده
            self.assertEqual(live, [])
            while feed["n"] < len(self.c):
                feed["n"] += 1
                scanner.scan_once(seen, live.append)

        allowed = {"H1", "H2", "L1", "L2", "WEDGE"}
        batch = [e for e in new_events("XAUUSD", analyze(self.c), self.c.index[n0 - 1])
                 if e["setup"] in allowed]
        key = lambda e: (e["time"], e["setup"])
        self.assertEqual(sorted(map(key, live)), sorted(map(key, batch)))
        self.assertEqual(len(set(map(key, live))), len(live))
        self.assertTrue(any(e["kind"] == "WEDGE" for e in live))
        for ev in live[:5]:
            self.assertIn("XAUUSD", build_alert(ev))


if __name__ == "__main__":
    unittest.main()


class TestSymbols(unittest.TestCase):
    def test_all_symbols_scanned_independently(self):
        """هر نماد داده‌ی خودش را می‌گیرد و هشدارهایش با نام همان نماد ارسال می‌شود."""
        from bot.config import SYMBOLS
        data = {s: candles(seed=i, p0=1.1 if s != "BTCUSD" else 68000.0) for i, s in enumerate(SYMBOLS)}
        feed = {"n": 400}
        out = []

        def fake(sym, n_bars, min_bars, interval=None):
            return data[sym].iloc[:feed["n"]]

        with mock.patch.object(scanner, "get_closed_candles", fake), \
             mock.patch.object(scanner, "build_alert", lambda ev: ev):
            seen = {}
            scanner.scan_once(seen, out.append)
            self.assertEqual(set(seen), set(SYMBOLS))
            for _ in range(150):
                feed["n"] += 1
                scanner.scan_once(seen, out.append)
        self.assertEqual({e["sym"] for e in out}, set(SYMBOLS))
        for e in out[:20]:
            self.assertIn(e["sym"], build_alert(e))
