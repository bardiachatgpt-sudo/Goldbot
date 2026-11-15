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
             mock.patch.object(scanner, "ALERT_CHARTS", False), \
             mock.patch.object(scanner, "BARS", 10_000), \
             mock.patch.object(scanner, "SYMBOLS", {"XAUUSD": []}), \
             mock.patch.object(scanner, "ALERT_SETUPS", {"H1", "H2", "L1", "L2", "WEDGE", "WEDGE_BO", "RANGE_BO", "PIN"}), \
             mock.patch.object(scanner, "build_alert", lambda ev: ev):
            sc = scanner.Scanner(lambda t, photo=None: live.append(t))
            sc.scan_once()                                # اولین اجرا: بی‌صدا
            self.assertEqual(live, [])
            sc.scan_once()                                # کندل جدیدی نیامده
            self.assertEqual(live, [])
            while feed["n"] < len(self.c):
                feed["n"] += 1
                sc.scan_once()

        allowed = {"H1", "H2", "L1", "L2", "WEDGE", "WEDGE_BO", "RANGE_BO", "PIN"}
        batch = [e for e in new_events("XAUUSD", analyze(self.c), self.c.index[n0 - 1])
                 if e["setup"] in allowed]
        key = lambda e: (e["time"], e["setup"])
        self.assertEqual(sorted(map(key, live)), sorted(map(key, batch)))
        self.assertEqual(len(set(map(key, live))), len(live))
        for kind in ("WEDGE", "WEDGE_BO", "RANGE_BO", "PIN"):
            self.assertTrue(any(e["kind"] == kind for e in live), kind)
        for ev in live[:5]:
            self.assertIn("XAUUSD", build_alert(ev))


def _bars(rows, start="2026-11-12 00:00", freq="5min"):
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, index=idx, columns=["Open", "High", "Low", "Close"])


def _range_rows(n=60, mid=100.0):
    """بازار خنثی: کندل‌های کوچک که دور یک قیمت بالا و پایین می‌روند."""
    rows = []
    for i in range(n):
        o = mid + (0.3 if i % 2 else -0.3)
        c = mid - (0.3 if i % 2 else -0.3)
        rows.append((o, max(o, c) + 0.2, min(o, c) - 0.2, c))
    return rows


class TestBreakouts(unittest.TestCase):
    def test_range_breakout_up_on_key_bar(self):
        rows = _range_rows() + [(100.0, 102.6, 99.9, 102.5)]      # کندل بزرگ صعودی بیرون رنج
        res = analyze(_bars(rows))
        last = res["df"].iloc[-1]
        self.assertEqual(last["range_bo"], 1)
        self.assertEqual(last["key_bar"], 1)
        self.assertAlmostEqual(last["range_hi"], 100.5)
        ev = [e for e in new_events("XAUUSD", res, res["df"]["date"].iloc[-2]) if e["kind"] == "RANGE_BO"]
        self.assertEqual(len(ev), 1)
        self.assertIn("RANGE BREAKOUT", build_alert(ev[0]))

    def test_range_breakout_down(self):
        rows = _range_rows() + [(100.0, 100.1, 97.4, 97.5)]
        self.assertEqual(analyze(_bars(rows))["df"].iloc[-1]["range_bo"], -1)

    def test_weak_bar_outside_range_is_not_breakout(self):
        rows = _range_rows() + [(100.2, 100.9, 100.1, 100.6)]     # کندل کوچک کمی بالاتر
        self.assertEqual(analyze(_bars(rows))["df"].iloc[-1]["range_bo"], 0)

    def test_pin_bar_rejects_new_low(self):
        rows = _range_rows() + [(100.2, 100.4, 98.0, 100.3)]       # سایه‌ی پایین بلند روی کف تازه
        res = analyze(_bars(rows))
        self.assertEqual(res["df"].iloc[-1]["pin_bar"], 1)
        ev = [e for e in new_events("XAUUSD", res, res["df"]["date"].iloc[-2]) if e["kind"] == "PIN"]
        self.assertIn("PIN BAR", build_alert(ev[0]))

    def test_pin_bar_rejects_new_high(self):
        rows = _range_rows() + [(99.8, 102.0, 99.7, 99.75)]
        self.assertEqual(analyze(_bars(rows))["df"].iloc[-1]["pin_bar"], -1)

    def test_wedge_breakouts_close_beyond_level(self):
        found = 0
        for seed in range(5):
            res = analyze(candles(seed=seed))
            df = res["df"]
            for bo in res["wedge_breakouts"]:
                found += 1
                c = df.at[bo["index"], "close"]
                self.assertTrue(c > bo["level"] if bo["side"] > 0 else c < bo["level"])
                self.assertEqual(bo["side"], bo["wedge"]["side"])
                self.assertGreaterEqual(bo["index"], bo["wedge"]["trigger_index"] + 3)
        self.assertGreater(found, 0)


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
             mock.patch.object(scanner, "ALERT_CHARTS", False), \
             mock.patch.object(scanner, "ALERT_SETUPS", {"H2", "L2", "WEDGE", "PIN"}), \
             mock.patch.object(scanner, "build_alert", lambda ev: ev):
            sc = scanner.Scanner(lambda t, photo=None: out.append(t))
            sc.scan_once()
            self.assertEqual(set(sc.seen), set(SYMBOLS))
            for _ in range(150):
                feed["n"] += 1
                sc.scan_once()
        self.assertEqual({e["sym"] for e in out}, set(SYMBOLS))
        for e in out[:20]:
            self.assertIn(e["sym"], build_alert(e))


if __name__ == "__main__":
    unittest.main()
