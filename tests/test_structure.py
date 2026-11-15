"""ساختار با خط‌های تریدر (فقط نمایش): رنج، اسپایک، کانال روی بازار ساختگی، و دکمه‌ی 📐 Structure."""
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import structure, telegram_bot  # noqa: E402
from bot.storage import JsonState  # noqa: E402


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


def sequence(df):
    phases, _, _, _ = structure.detect(df["Open"], df["High"], df["Low"], df["Close"])
    return [(p["type"], p["side"]) for p in phases]


class TestStructure(unittest.TestCase):
    def test_reads_the_cycle_like_it_was_built(self):
        expected = [("RANGE", 0), ("SPIKE", 1), ("CHANNEL", 1), ("RANGE", 0), ("SPIKE", -1), ("CHANNEL", -1),
                    ("RANGE", 0), ("SPIKE", 1), ("CHANNEL", 1)]
        self.assertEqual(sequence(fake_market(57730)), expected)

    def test_main_phases_found_on_other_markets(self):
        for seed in (1234, 777):
            seq = sequence(fake_market(seed))
            self.assertEqual(seq[:3], [("RANGE", 0), ("SPIKE", 1), ("CHANNEL", 1)], seed)
            self.assertIn(("CHANNEL", -1), seq, seed)

    def test_flat_market_is_a_range_and_no_spikes(self):
        rnd = np.random.default_rng(1)
        t = np.arange(400)
        mid = 100 + 3 * np.sin(2 * np.pi * t / 20) + rnd.normal(0, 0.2, 400)
        df = pd.DataFrame({"Open": np.r_[mid[0], mid[:-1]], "Close": mid,
                           "High": np.maximum(np.r_[mid[0], mid[:-1]], mid) + 0.4,
                           "Low": np.minimum(np.r_[mid[0], mid[:-1]], mid) - 0.4},
                          index=pd.date_range("2026-11-12", periods=400, freq="5min", tz="UTC"))
        seq = sequence(df)
        self.assertEqual(set(seq), {("RANGE", 0)})

    def test_swings_are_confirmed_only_from_the_past(self):
        df = fake_market(57730)
        piv = structure.zigzag(df["High"].values, df["Low"].values,
                               structure._avg(df["High"].values, df["Low"].values))
        self.assertTrue(all(conf > j for j, _, _, conf in piv))
        self.assertTrue(all(a[1] != b[1] for a, b in zip(piv, piv[1:])))   # سقف و کف یک‌درمیان

    def test_render_png(self):
        png, phases, now = structure.render("XAUUSD", fake_market(57730))
        self.assertEqual(png[:4], b"\x89PNG")
        self.assertEqual(now, ("CHANNEL", 1))


class TestStructureV2(unittest.TestCase):
    def test_v2_runs_and_keeps_v1_unchanged(self):
        df = fake_market(57730)
        v1 = sequence(df)
        phases, state, _, _ = structure.detect(df["Open"], df["High"], df["Low"], df["Close"], v2=True)
        self.assertTrue(phases)
        self.assertEqual(sequence(df), v1)                              # نسخه‌ی ۱ دست‌نخورده
        self.assertIn(("CHANNEL", 1), [(p["type"], p["side"]) for p in phases])


class TestStructureButton(unittest.TestCase):
    def test_button_sends_last_500_candles_with_caption(self):
        st = JsonState(os.path.join(tempfile.mkdtemp(), "s.json"))
        tg = telegram_bot.Telegram(None, st)
        tg.bot = mock.MagicMock()
        df = fake_market(57730)
        extra = pd.concat([df, df.tail(100).set_index(df.index[-100:] + pd.Timedelta(hours=10))])
        calls = []

        def fake(sym, n, m, interval=None):
            calls.append((sym, n, interval))
            return extra

        with mock.patch.object(telegram_bot, "get_closed_candles", fake):
            tg.send_structure(7, "XAUUSD")
        self.assertEqual(calls, [("XAUUSD", 501, "5")])            # پیش‌فرض: M5
        photos = tg.bot.send_photo.call_args_list
        self.assertEqual(len(photos), 1)                                 # فقط نسخه‌ی ۱
        self.assertEqual(photos[0].args[1][:4], b"\x89PNG")
        self.assertIn("last 500 candles", photos[0].kwargs["caption"])
        self.assertNotIn("v2", photos[0].kwargs["caption"])
        names = [b.callback_data for row in tg.pairs_keyboard(7).keyboard for b in row]
        self.assertIn("sx", names)

    def test_choose_one_or_five_minutes(self):
        st = JsonState(os.path.join(tempfile.mkdtemp(), "s.json"))
        tg = telegram_bot.Telegram(None, st)
        tg.bot = mock.MagicMock()
        tf_buttons = [b.callback_data for row in tg.structure_tf_keyboard("XAUUSD").keyboard for b in row]
        self.assertEqual(tf_buttons, ["sxt:XAUUSD:1", "sxt:XAUUSD:5"])
        calls = []
        df = fake_market(1234)

        def fake(sym, n, m, interval=None):
            calls.append(interval)
            return df

        with mock.patch.object(telegram_bot, "get_closed_candles", fake):
            tg.send_structure(7, "XAUUSD", "1")
        self.assertEqual(calls, ["1"])
        kw = tg.bot.send_photo.call_args.kwargs
        self.assertIn("M1 structure", kw["caption"])
        btns = [b.callback_data for row in kw["reply_markup"].keyboard for b in row]
        self.assertEqual(btns, ["sxt:XAUUSD:1", "sxt:XAUUSD:5", "sx"])      # تازه کردن، تایم‌فریم دیگر، جفت دیگر


if __name__ == "__main__":
    unittest.main()
