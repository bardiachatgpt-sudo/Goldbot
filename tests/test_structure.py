"""ساختار با خط‌های تریدر (فقط نمایش): رنج، اسپایک، کانال روی بازار ساختگی، و دکمه‌ی 📐 Structure."""
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import structure, structure3, telegram_bot  # noqa: E402
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
        png, phases, now = structure.render("XAUUSD", fake_market(57730))
        self.assertEqual(png[:4], b"\x89PNG")
        self.assertEqual(now, ("CHANNEL", 1))


class TestRangeDoubt(unittest.TestCase):
    """رنج تمیز (دو سقف و دو کف هم‌سطح) در برابر رنج «در شک» (نامنظم)."""

    @staticmethod
    def phase(top, bot):
        return {"type": "RANGE", "side": 0, "start": 0, "end": 40,
                "lines": {"x0": 0, "y0": bot, "slope": 0.0, "off": top - bot}}

    def test_two_touches_each_side_is_a_clean_box(self):
        ph = self.phase(10.0, 0.0)
        piv = [(5, "H", 10.0, 7), (10, "L", 0.3, 12), (18, "H", 9.6, 20), (25, "L", 0.0, 27)]
        structure._mark_doubt([ph], piv, np.ones(50))
        self.assertFalse(ph["doubt"])

    def test_uneven_touches_is_in_doubt(self):
        ph = self.phase(14.0, 0.0)
        piv = [(5, "H", 10.0, 7), (10, "L", 0.3, 12), (18, "H", 14.0, 20), (25, "L", 0.0, 27)]   # یک سقف دور
        structure._mark_doubt([ph], piv, np.ones(50))
        self.assertTrue(ph["doubt"])

    def test_clean_fake_ranges_are_boxes_and_random_walks_have_doubt(self):
        for seed in (57730, 1234):
            df = fake_market(seed)
            phases, _, _, _ = structure.detect(df["Open"], df["High"], df["Low"], df["Close"])
            self.assertTrue(all(not p["doubt"] for p in phases if p["type"] == "RANGE"), seed)
        doubts = 0
        for seed in range(4):
            rnd = np.random.default_rng(seed)
            mid = 4000 + rnd.normal(0, 2.2, 500).cumsum()
            o = np.r_[mid[0], mid[:-1]]
            h = np.maximum(o, mid) + np.abs(rnd.normal(0, 1.2, 500))
            l = np.minimum(o, mid) - np.abs(rnd.normal(0, 1.2, 500))
            phases, _, _, _ = structure.detect(o, h, l, mid)
            doubts += sum(1 for p in phases if p["type"] == "RANGE" and p["doubt"])
        self.assertGreater(doubts, 0)


class TestCoreLines(unittest.TestCase):
    """خط‌های رنج از جایی که بیشترین برخورد بوده؛ یک سایه/کف دور خط را نمی‌کشد."""

    def test_far_single_low_is_ignored(self):
        ph = {"type": "RANGE", "side": 0, "start": 0, "end": 200,
              "lines": {"x0": 0, "y0": 159.42, "slope": 0.0, "off": 159.99 - 159.42}}
        piv = [(5, "L", 159.42, 8), (20, "H", 159.97, 23), (35, "L", 159.86, 38), (50, "H", 159.99, 53),
               (65, "L", 159.85, 68), (80, "H", 159.96, 83), (95, "L", 159.87, 98), (110, "H", 159.95, 113)]
        top, bot = structure.core_lines(ph, piv, np.full(250, 0.03))
        self.assertAlmostEqual(bot, 159.86, places=3)
        self.assertAlmostEqual(top, 159.96, places=3)

    def test_no_cluster_keeps_outer_line(self):
        ph = {"type": "RANGE", "side": 0, "start": 0, "end": 100,
              "lines": {"x0": 0, "y0": 10.0, "slope": 0.0, "off": 10.0}}
        piv = [(5, "L", 10.0, 8), (20, "H", 20.0, 23), (35, "L", 13.0, 38), (50, "H", 16.0, 53)]
        self.assertEqual(structure.core_lines(ph, piv, np.ones(120)), (20.0, 10.0))

    def test_render_plain_png(self):
        self.assertEqual(structure.render_plain(fake_market(57730))[:4], b"\x89PNG")

    def test_render_core_png(self):
        png, phases, now = structure.render("XAUUSD", fake_market(57730), core=True)
        self.assertEqual(png[:4], b"\x89PNG")


class TestStructureV2(unittest.TestCase):
    def test_v2_runs_and_keeps_v1_unchanged(self):
        df = fake_market(57730)
        v1 = sequence(df)
        phases, state, _, _ = structure.detect(df["Open"], df["High"], df["Low"], df["Close"], v2=True)
        self.assertTrue(phases)
        self.assertEqual(sequence(df), v1)                              # نسخه‌ی ۱ دست‌نخورده
        self.assertIn(("CHANNEL", 1), [(p["type"], p["side"]) for p in phases])


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


class TestGoldMenu(unittest.TestCase):
    def test_start_shows_menu_and_version_and_structure_goes_to_gold(self):
        st = JsonState(os.path.join(tempfile.mkdtemp(), "s.json"))
        tg = telegram_bot.Telegram(None, st)
        tg.bot = mock.MagicMock()
        menu = [b["text"] for row in tg.menu().keyboard for b in row]
        self.assertEqual(menu, ["🥇 Gold", "📐 Structure", "🧪 Backtest"])
        with mock.patch.object(tg, "send_structure") as ss:
            tg.ask_structure(7)
        ss.assert_called_once_with(7, "XAUUSD")                         # فقط طلا: بدون انتخاب جفت


class TestPollingSurvivesConflict(unittest.TestCase):
    def test_409_during_deploy_does_not_stop_the_bot(self):
        st = JsonState(os.path.join(tempfile.mkdtemp(), "s.json"))
        tg = telegram_bot.Telegram(None, st)
        tg.bot = mock.MagicMock()
        tg.bot.infinity_polling.side_effect = [Exception("Error code: 409. Conflict"), SystemExit]
        with mock.patch.object(telegram_bot.time, "sleep"), self.assertRaises(SystemExit):
            tg.run()
        self.assertEqual(tg.bot.infinity_polling.call_count, 2)            # بعد از 409 دوباره وصل شد


class TestStructureButton(unittest.TestCase):
    def test_button_sends_one_m5_picture(self):
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
        self.assertEqual(calls, [("XAUUSD", 501, "5")])                # فقط M5
        photos = tg.bot.send_photo.call_args_list
        self.assertEqual(len(photos), 2)                                 # کل ۵۰۰ کندل + بزرگ‌نمایی
        for call in photos:
            self.assertEqual(call.args[1][:4], b"\x89PNG")
        cap = photos[0].kwargs["caption"]
        self.assertIn("M5 structure", cap)
        self.assertIn("last 500 candles", cap)
        self.assertIn("last two structures", photos[1].kwargs["caption"])
        btns = [b.callback_data for row in photos[1].kwargs["reply_markup"].keyboard for b in row]
        self.assertEqual(btns, ["sxp:XAUUSD", "sx", "btd:XAUUSD:5r:5"])  # تازه کردن، جفت دیگر، بک‌تست رنج
        names = [b.callback_data for row in tg.pairs_keyboard(7).keyboard for b in row]
        self.assertIn("sx", names)


if __name__ == "__main__":
    unittest.main()
