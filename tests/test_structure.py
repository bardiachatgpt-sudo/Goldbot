"""ساختار بازار (نسخه‌ی ۳) و ربات تلگرامِ فقط-ساختار."""
import os
import sys
import unittest
from unittest import mock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import config, structure3, telegram_bot  # noqa: E402

def fake_market(seed):
    """رنج ← اسپایک ← کانال صعودی ← رنج ← کانال نزولی (بدون اسپایک) ← رنج ← اسپایک ← کانال (۵۰۰ کندل M5)."""
    rnd = np.random.default_rng(seed)

    def seg(n, drift, amp, period):
        t = np.arange(n)
        ph = rnd.uniform(0, 2 * np.pi)
        return drift * t + amp * np.sin(2 * np.pi * t / period + ph) + rnd.normal(0, 0.6, n).cumsum() * 0.3

    plan = [("range", 90, 0.0), ("spike", 6, None), ("channel", 110, rnd.uniform(0.3, 0.5)), ("range", 80, 0.0),
            ("channel", 110, -rnd.uniform(0.3, 0.5)), ("range", 60, 0.0), ("spike", 5, None), ("channel", 40, 0.4)]
    mid, level = [], 4000.0
    for kind, n, drift in plan:
        if kind == "spike":
            part = level + rnd.uniform(5, 8, n).cumsum()
            rnd.random()                              # همان دنباله‌ی تصادفی تصاویر (fake_market.py)
        else:
            s = seg(n, drift, rnd.uniform(5, 8), rnd.uniform(16, 24))
            part = level + s - s[0]
        mid.extend(part)
        level = part[-1]
    mid = np.array(mid)[:500]
    n = len(mid)
    o = np.r_[mid[0], mid[:-1]] + rnd.normal(0, 0.4, n)
    c = mid + rnd.normal(0, 0.4, n)
    h = np.maximum(o, c) + np.abs(rnd.normal(0, 1.3, n))
    l = np.minimum(o, c) - np.abs(rnd.normal(0, 1.3, n))
    idx = pd.date_range("2026-11-12 00:00", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=idx)



class TestStructure3(unittest.TestCase):
    """نسخه‌ی ۳: قاعده‌هایی که از خط‌های کاربر روی ۶ نمودار M5 درآمد."""

    @staticmethod
    def walk(parts, seed=1, noise=0.02):
        rng = np.random.default_rng(seed)
        c = np.concatenate([np.linspace(a, b, n) for a, b, n in parts])
        return c + rng.normal(0, noise, len(c))

    def test_phases_cover_the_chart(self):
        c = fake_market(57730)["Close"].values
        ph, _ = structure3.segment(c)
        self.assertEqual(ph[0]["start"], 0)
        self.assertEqual(ph[-1]["end"], len(c) - 1)
        for x, y in zip(ph, ph[1:]):
            self.assertEqual(x["end"], y["start"])
            self.assertFalse(x["type"] == y["type"] == "RANGE")

    def test_v_that_comes_back_is_one_range(self):
        # رنج، ریزش تند تا پایین، برگشت کامل، رنج (مثل USDCAD): یک رنج
        parts = []
        for k in range(6):
            parts.append((10, 11, 15)); parts.append((11, 10, 15))
        parts += [(10, 4, 6), (4, 10.5, 12)]
        for k in range(6):
            parts.append((10.5, 9.8, 15)); parts.append((9.8, 10.5, 15))
        ph, _ = structure3.segment(self.walk(parts))
        self.assertEqual([p["type"] for p in ph], ["RANGE"])

    def test_held_breakout_is_spike_then_new_range(self):
        # رنج، اسپایک پایین که برنمی‌گردد، رنج پایین‌تر (پله‌ای، مثل AUDUSD)
        parts = []
        for k in range(5):
            parts.append((10, 11, 15)); parts.append((11, 10, 15))
        parts.append((10, 5, 5))
        for k in range(5):
            parts.append((5, 6, 15)); parts.append((6, 5, 15))
        ph, _ = structure3.segment(self.walk(parts))
        self.assertEqual([(p["type"], p["side"]) for p in ph], [("RANGE", 0), ("SPIKE", -1), ("RANGE", 0)])

    def test_lower_highs_and_lows_is_bear_channel(self):
        parts = []
        top = 20.0
        for k in range(6):
            parts.append((top, top - 3, 20)); parts.append((top - 3, top - 1.5, 20)); top -= 1.5
        ph, _ = structure3.segment(self.walk(parts))
        self.assertIn(("CHANNEL", -1), [(p["type"], p["side"]) for p in ph])
        self.assertGreater(sum(p["end"] - p["start"] for p in ph if p["type"] == "CHANNEL"), 150)

    def test_triangle_range_lines(self):
        parts = []
        hi, lo = 12.0, 8.0
        for k in range(6):
            parts.append((lo, hi, 15)); parts.append((hi, lo, 15)); hi -= 0.3; lo += 0.3
        c = self.walk(parts, noise=0.01)
        ph, piv = structure3.segment(c)
        self.assertEqual([p["type"] for p in ph], ["RANGE"])
        (_, t0, _, t1, _), (_, b0, _, b1, _) = structure3.lines(ph[0], c, piv)
        self.assertLess(t1, t0)                                         # سقف پایین می‌آید
        self.assertGreater(b1, b0)                                      # کف بالا می‌رود

    def test_swing_labels(self):
        piv = [[1, "L", 5.0], [5, "H", 8.0], [9, "L", 6.0], [14, "H", 9.0], [20, "L", 4.0], [25, "H", 7.0]]
        self.assertEqual([t for *_, t in structure3.swing_labels(piv)], ["L", "H", "HL", "HH", "LL", "LH"])
        self.assertEqual(structure3.render_line("XAUUSD", fake_market(57730))[:4], b"\x89PNG")

    def test_zoom_shows_last_two_structures(self):
        df = fake_market(57730)
        png, ph, _ = structure3.render("XAUUSD", df, zoom=2)
        full, ph2, _ = structure3.render("XAUUSD", df)
        self.assertEqual(png[:4], b"\x89PNG")
        self.assertEqual(ph, ph2)                                        # همان ساختار، فقط بزرگ‌تر

    def test_render_png(self):
        png, ph, now = structure3.render("XAUUSD", fake_market(57730))
        self.assertEqual(png[:4], b"\x89PNG")
        self.assertTrue(ph and now)


def make_bot():
    tg = telegram_bot.Telegram(None)
    tg.bot = mock.MagicMock()
    return tg


class TestStructureBot(unittest.TestCase):
    def test_pairs_are_gold_majors_and_dow(self):
        tg = make_bot()
        tg.ask_structure(7)
        kb = tg.bot.send_message.call_args.kwargs["reply_markup"]
        self.assertEqual([b.callback_data for row in kb.keyboard for b in row],
                         ["sxp:XAUUSD", "sxp:EURUSD", "sxp:GBPUSD", "sxp:USDJPY", "sxp:USDCHF",
                          "sxp:USDCAD", "sxp:AUDUSD", "sxp:NZDUSD", "sxp:US30"])
        self.assertEqual([b["text"] for row in tg.menu().keyboard for b in row], ["📐 Structure"])

    def test_every_timeframe_can_be_chosen(self):
        tfs = [b.callback_data for row in make_bot().structure_tf_keyboard("US30").keyboard for b in row]
        self.assertEqual(tfs, [f"sxt:US30:{tf}" for tf in config.TIMEFRAMES])
        self.assertEqual(list(config.TIMEFRAMES.values()), ["M1", "M5", "M15", "M30", "H1", "H4", "D1"])

    def test_sends_500_candles_and_zoom_on_chosen_timeframe(self):
        tg = make_bot()
        df = fake_market(57730)
        extra = pd.concat([df, df.tail(100).set_index(df.index[-100:] + pd.Timedelta(hours=10))])
        calls = []

        def fake(sym, n, m, interval=None):
            calls.append((sym, n, interval))
            return extra

        with mock.patch.object(telegram_bot, "get_closed_candles", fake):
            tg.send_structure(7, "EURUSD", "60")
        self.assertEqual(calls, [("EURUSD", 501, "60")])
        photos = tg.bot.send_photo.call_args_list
        self.assertEqual(len(photos), 2)                                 # کل ۵۰۰ کندل + بزرگ‌نمایی
        for call in photos:
            self.assertEqual(call.args[1][:4], b"\x89PNG")
        self.assertIn("H1 structure", photos[0].kwargs["caption"])
        self.assertIn("last 500 candles", photos[0].kwargs["caption"])
        self.assertIn("last two structures", photos[1].kwargs["caption"])
        btns = [b.callback_data for row in photos[1].kwargs["reply_markup"].keyboard for b in row]
        self.assertEqual(btns, ["sxt:EURUSD:60", "sxp:EURUSD", "sx"])  # تازه کردن، تایم‌فریم، جفت دیگر

    def test_fetch_failure_says_so(self):
        tg = make_bot()
        with mock.patch.object(telegram_bot, "get_closed_candles", lambda *a, **k: None):
            tg.send_structure(7, "US30", "5")
        self.assertIn("could not fetch", tg.bot.send_message.call_args.args[1])
        tg.bot.send_photo.assert_not_called()


class TestPollingSurvivesConflict(unittest.TestCase):
    def test_409_during_deploy_does_not_stop_the_bot(self):
        tg = make_bot()
        tg.bot.infinity_polling.side_effect = [Exception("Error code: 409. Conflict"), SystemExit]
        with mock.patch.object(telegram_bot.time, "sleep"), self.assertRaises(SystemExit):
            tg.run()
        self.assertEqual(tg.bot.infinity_polling.call_count, 2)            # بعد از 409 دوباره وصل شد


if __name__ == "__main__":
    unittest.main()
