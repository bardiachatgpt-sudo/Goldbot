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
        self.assertEqual([b["text"] for row in tg.menu().keyboard for b in row], ["📐 Structure", "🧪 Gap backtest"])

    def test_every_timeframe_can_be_chosen(self):
        tfs = [b.callback_data for row in make_bot().structure_tf_keyboard("US30").keyboard for b in row]
        self.assertEqual(tfs, [f"sxt:US30:{tf}" for tf in config.TIMEFRAMES] + ["sxm:US30", "sxbp:US30"])
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


def m1_market(seed=3):
    """M1 با رنج و کانال‌ها (۲۶۰۰ کندل) و M5 ساخته‌شده از همان."""
    rnd = np.random.default_rng(seed)
    plan = [(500, 0), (350, -0.06), (450, 0), (300, 0.07), (400, 0), (300, -0.05), (300, 0)]
    mid, lvl = [], 4000.0
    for m, dr in plan:
        t = np.arange(m)
        s = dr * t + rnd.uniform(2, 5) * np.sin(2 * np.pi * t / rnd.uniform(40, 100)) + \
            rnd.normal(0, 0.25, m).cumsum() * 0.25
        part = lvl + s - s[0]
        mid.extend(part)
        lvl = part[-1]
    mid = np.array(mid)
    o = np.r_[mid[0], mid[:-1]]
    h, l = np.maximum(o, mid) + 0.3, np.minimum(o, mid) - 0.3
    m1 = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": mid},
                      index=pd.date_range("2026-11-16", periods=len(mid), freq="1min", tz="UTC"))
    m5 = m1.resample("5min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    return m1, m5


class TestM1WithM5Structure(unittest.TestCase):
    def test_render_uses_the_same_m5_structure(self):
        from bot import mtf
        m1, m5 = m1_market()
        png, ph5, ph1, now5, now1 = mtf.render("XAUUSD", m5, m1, layer="micro")
        self.assertEqual(png[:4], b"\x89PNG")
        self.assertEqual(ph5, structure3.segment(m5["Close"].values)[0])        # همان ساختار دکمه‌ی M5
        self.assertTrue(ph1 and now5 and now1)
        from bot import structure                                              # M1: تشخیص ریز نسخه‌ی ۱
        w1 = mtf.m1_window(m5, m1)
        self.assertEqual(ph1, structure.detect(*(w1[k].values for k in ("Open", "High", "Low", "Close")))[0])
        w = mtf.m1_window(m5, m1)
        self.assertTrue(mtf.MIN_M1 <= len(w) <= mtf.MAX_M1)
        self.assertEqual(w.index[-1], m1.index[-1])                             # تا آخرین کندل M1

    def test_button_sends_one_picture(self):
        tg = make_bot()
        m1, m5 = m1_market()
        calls = []

        def fake(sym, n, m, interval=None):
            calls.append((sym, interval))
            return m1 if interval == "1" else m5

        with mock.patch.object(telegram_bot, "get_closed_candles", fake):
            tg.send_mtf(7, "XAUUSD")
        self.assertEqual(calls, [("XAUUSD", "5"), ("XAUUSD", "1")])
        call = tg.bot.send_photo.call_args
        self.assertEqual(call.args[1][:4], b"\x89PNG")
        self.assertIn("gap setup", call.kwargs["caption"])
        btns = [b.callback_data for row in call.kwargs["reply_markup"].keyboard for b in row]
        self.assertEqual(btns, ["sxm:XAUUSD", "sxp:XAUUSD", "sx", "sxbp:XAUUSD"])


def candles(rows):
    a = np.array(rows, float)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


class TestGapSetup(unittest.TestCase):
    # ردیف‌ها: (open, high, low, close)
    SELL = [(110, 111, 108, 108.5),       # کندل ۱: کف 108
            (108.5, 108.6, 101, 101.5),   # کندل ۲: بدنه‌ی قرمز بزرگ
            (101.5, 105, 100, 100.5),     # کندل ۳: سقف 105 < کف کندل ۱ → گپ 105..108
            (100.5, 102, 99, 99.5),       # سقف پایین‌تر: هنوز ورود نیست
            (99.5, 102.5, 99.4, 102.2),   # سقف 102.5 > سقف قبلی 102 → فروش روی 102.01
            (102.2, 102.3, 92, 92.5)]     # حد سود

    def test_bearish_gap_is_found(self):
        from bot import gap
        o, h, l, c = candles(self.SELL)
        self.assertEqual(gap.find_gap(o, h, l, c, 2), (-1, (108, 105)))
        o2 = o.copy(); c2 = c.copy()
        o2[1], c2[1] = 108.5, 108.4                                    # بدنه‌ی کندل ۲ بیرون گپ
        self.assertEqual(gap.find_gap(o2, h, l, c2, 2)[0], 0)

    def test_sell_one_pipette_above_previous_high_stop_behind_candle_1_target_1_to_1(self):
        from bot import gap
        t = gap.trades(*candles(self.SELL), sym="XAUUSD")[0]
        self.assertEqual((t["side"], t["entry_i"]), (-1, 4))
        self.assertAlmostEqual(t["entry"], 102.01)                     # سقف قبلی + ۱ پیپت
        self.assertAlmostEqual(t["sl"], 111.01)                        # پشت کندل ۱
        self.assertAlmostEqual(t["tp"], 102.01 - (111.01 - 102.01))    # ۱:۱
        self.assertEqual((t["result"], t["r"]), ("TP", 1.0))

    def test_touching_the_previous_high_is_not_an_entry(self):
        from bot import gap
        rows = self.SELL[:4] + [(99.5, 102.0, 99.4, 101.0)]           # فقط به 102 رسید، رد نکرد
        t = gap.trades(*candles(rows), sym="XAUUSD")[-1]
        self.assertIsNone(t["entry_i"])

    def test_buy_is_the_mirror(self):
        from bot import gap
        rows = [(2 * 105 - o, 2 * 105 - lo, 2 * 105 - hi, 2 * 105 - cl) for o, hi, lo, cl in self.SELL]
        t = gap.trades(*candles(rows), sym="XAUUSD")[0]
        self.assertEqual(t["side"], 1)
        self.assertAlmostEqual(t["entry"], 107.99)
        self.assertAlmostEqual(t["sl"], 98.99)


def gappy_m1(n=3000, seed=11):
    rnd = np.random.default_rng(seed)
    r = rnd.normal(0, 0.35, n) + np.where(rnd.random(n) < 0.03, rnd.choice([-1, 1], n) * 2.5, 0)
    c = 4000 + np.cumsum(r)
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"Open": o, "High": np.maximum(o, c) + 0.2, "Low": np.minimum(o, c) - 0.2, "Close": c},
                        index=pd.date_range("2026-11-16", periods=n, freq="1min", tz="UTC"))


class TestGapBacktest(unittest.TestCase):
    def test_report_and_account(self):
        from bot import gap_backtest
        res = gap_backtest.run("XAUUSD", gappy_m1())
        self.assertGreater(res["trades"], 10)
        self.assertEqual(res["trades"], res["wins"] + res["losses"])
        self.assertAlmostEqual(res["net_r"], res["wins"] - res["losses"])          # ۱:۱
        a2 = res["accounts"][2.0]
        bal = 1000.0
        for t in res["closed"]:
            bal *= 1 + 0.02 * t["r"]
        self.assertAlmostEqual(a2["final"], bal, places=6)                           # ریسک ۲٪ مرکب
        txt = gap_backtest.report_text(res)
        self.assertLess(len(txt), 4096)                                              # یک پیام تلگرام
        self.assertIn("GAP BACKTEST", txt)
        self.assertIn("Risk 2% per trade", txt)
        self.assertEqual(gap_backtest.equity_chart(res)[:4], b"\x89PNG")

    def test_one_tap_in_the_bot_sends_losing_trade_pictures(self):
        tg = make_bot()
        calls = []
        m1 = gappy_m1(6000)
        m5 = m1.resample("5min", label="left", closed="left").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()

        def fake(sym, n, m, interval=None, timeout=20):
            calls.append((sym, n, interval))
            return m1 if interval == "1" else m5

        with mock.patch.object(telegram_bot, "get_closed_candles", fake), \
                mock.patch.object(telegram_bot.time, "sleep"):
            tg.send_gap_backtest(7, "XAUUSD")
        self.assertEqual(calls, [("XAUUSD", 5001, "1"), ("XAUUSD", 1700, "5")])
        texts = [c.args[1] for c in tg.bot.send_message.call_args_list]
        report = next(t for t in texts if "GAP BACKTEST" in t)
        self.assertIn("(3 days)", report)                                           # فقط ۳ روز اخیر
        albums = [len(c.args[1]) for c in tg.bot.send_media_group.call_args_list]
        losses = int(report.split("❌ ")[1].split(" ")[0])
        self.assertEqual(sum(albums), losses)                                       # یک عکس برای هر باخت
        self.assertTrue(all(a <= 10 for a in albums))

    def test_trade_picture(self):
        from bot import gap_backtest
        from bot.gap_pictures import caption, trade_picture
        m1 = gappy_m1(3000)
        m5 = m1.resample("5min", label="left", closed="left").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
        res = gap_backtest.run("XAUUSD", m1, "1", days=None)
        t = next(t for t in res["closed"] if t["r"] < 0)
        self.assertEqual(trade_picture("XAUUSD", res["candles"], m5, t, t["num"])[:4], b"\x89PNG")
        self.assertIn(f"#{t['num']}", caption("XAUUSD", t, t["num"]))


class TestGapBacktestTimeframesAndPairs(unittest.TestCase):
    def test_menu_asks_pair_then_m1_m5_m15(self):
        tg = make_bot()
        tg.ask_backtest(7)
        pairs = [b.callback_data for row in tg.bot.send_message.call_args.kwargs["reply_markup"].keyboard for b in row]
        self.assertEqual(pairs, [f"sxbp:{s}" for s in config.STRUCTURE_SYMBOLS])
        tg.ask_backtest(7, "EURUSD")
        tfs = [b.callback_data for row in tg.bot.send_message.call_args.kwargs["reply_markup"].keyboard for b in row]
        self.assertEqual(tfs, ["sxb:EURUSD:1", "sxb:EURUSD:5", "sxb:EURUSD:15"])

    def test_m15_on_a_major(self):
        tg = make_bot()
        calls = []
        df = gappy_m1().copy()
        df.index = pd.date_range("2026-10-01", periods=len(df), freq="15min", tz="UTC")

        def fake(sym, n, m, interval=None, timeout=20):
            calls.append((sym, interval))
            return df

        with mock.patch.object(telegram_bot, "get_closed_candles", fake):
            tg.send_gap_backtest(7, "EURUSD", "15")
        self.assertEqual(calls, [("EURUSD", "15")])                               # M15: بدون M5
        texts = [c.args[1] for c in tg.bot.send_message.call_args_list]
        txt = next(t for t in texts if "GAP BACKTEST" in t)
        self.assertIn("EURUSD · M15", txt)
        tg.bot.send_media_group.assert_not_called()                                 # عکس باخت‌ها فقط برای M1
        btns = [b.callback_data for row in tg.bot.send_message.call_args.kwargs["reply_markup"].keyboard for b in row]
        self.assertEqual(btns, ["sxb:EURUSD:15", "sxbp:EURUSD", "sxbp"])


class TestLastLegAgainstTheChannel(unittest.TestCase):
    def test_fall_after_a_bull_channel_is_not_called_bull(self):
        rng = np.random.default_rng(2)
        up = []
        x = 100.0
        for k in range(5):                                           # کانال صعودی با پولبک
            up += list(np.linspace(x, x + 6, 20)) + list(np.linspace(x + 6, x + 3, 10))
            x += 3
        fall = list(np.linspace(up[-1], up[-1] - 10, 30))              # ریزش زیر آخرین کف، بدون پولبک
        c = np.array(up + fall) + rng.normal(0, 0.05, len(up) + len(fall))
        ph, _ = structure3.segment(c)
        self.assertEqual(ph[-1]["side"], -1)                            # پایه‌ی آخر نزولی است، نه «کانال صعودی»


class TestPollingSurvivesConflict(unittest.TestCase):
    def test_409_during_deploy_does_not_stop_the_bot(self):
        tg = make_bot()
        tg.bot.infinity_polling.side_effect = [Exception("Error code: 409. Conflict"), SystemExit]
        with mock.patch.object(telegram_bot.time, "sleep"), self.assertRaises(SystemExit):
            tg.run()
        self.assertEqual(tg.bot.infinity_polling.call_count, 2)            # بعد از 409 دوباره وصل شد


if __name__ == "__main__":
    unittest.main()
