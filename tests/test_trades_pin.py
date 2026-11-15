"""نسخه‌ی اول (STRATEGY=pin): تست‌های ستاپ ورود: رنج (Stop روی پین‌بار) و اولین پولبک اسپایک (پین‌بار + Key bar)، ۱:۲،
ترتیب رسیدن به سطح‌ها (قیمت زنده یا شکل کندل)."""
import os
import sys
import unittest
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import scanner  # noqa: E402
from bot.config import spread  # noqa: E402
from bot.messages import build_spike_alert, build_trade_alert  # noqa: E402
from bot.strategy import analyze  # noqa: E402
from bot.trades_pin import TradeManager, candle_path, walk  # noqa: E402
from tests.synthetic import candles, to_tf  # noqa: E402

SP = spread("XAUUSD")
SEED = 12                       # داده‌ی ساختگی که در پنجره‌ی تست معامله دارد
T0 = pd.Timestamp("2026-11-12 10:00", tz="UTC")
RANGE_CTX = {"state": "RANGE", "hi": 110.0, "lo": 100.0}
SPIKE_ID = pd.Timestamp("2026-11-12 09:30", tz="UTC")
SPIKE_CTX = {"state": "CHANNEL", "side": 1, "pullback": True, "broken": 104.0, "spike_id": SPIKE_ID, "high": 109.0}


def frame(rows, start=T0):
    """rows: (open, high, low, close, pin_bar, key_bar[, pin_pullback])"""
    idx = pd.date_range(start, periods=len(rows), freq="1min")
    data = []
    for t, r in zip(idx, rows):
        o, h, l, c, pin, key = r[:6]
        data.append({"date": t, "open": o, "high": h, "low": l, "close": c, "pin_bar": pin,
                     "key_bar": key, "pin_pullback": r[6] if len(r) > 6 else 0})
    return pd.DataFrame(data)


FLAT = (105.0, 105.5, 104.5, 105.0, 0, 0)
PIN_LOW = (101.0, 101.5, 100.0, 101.3, 1, 0)        # پین‌بار رنج صعودی: سقف 101.5، کف 100.0
UP = (101.3, 101.8, 101.2, 101.7, 0, 0)             # از سقف پین‌بار رد می‌شود


def run(rows, ctx=RANGE_CTX, tm=None, start=T0):
    """کندل‌ها را یکی‌یکی به TradeManager می‌دهد (مثل اسکنر زنده)."""
    tm = tm or TradeManager("XAUUSD")
    d = frame([FLAT] + rows, start)
    tm.process(d.iloc[:1], ctx)
    out = []
    for n in range(2, len(d) + 1):
        out += tm.process(d.iloc[:n], ctx)
    return out


def kinds(ev):
    return [e["kind"] for e in ev]


class TestWalk(unittest.TestCase):
    def test_candle_path(self):
        self.assertEqual(candle_path(1, 3, 0, 2), [1, 0, 3, 2])      # صعودی: اول کف
        self.assertEqual(candle_path(2, 3, 0, 1), [2, 3, 0, 1])      # نزولی: اول سقف

    def test_first_level_on_path(self):
        self.assertEqual(walk([1, 0, 3, 2], {"A": (2.5, 1), "B": (0.5, -1)})[0], "B")
        self.assertEqual(walk([2, 3, 0, 1], {"A": (2.5, 1), "B": (0.5, -1)})[0], "A")
        self.assertEqual(walk([3, 4], {"A": (2.5, 1)})[:2], ("A", 3))             # گپ: اجرا با قیمت باز
        self.assertIsNone(walk([1, 2], {"A": (2.5, 1)}))


class TestRangeTrades(unittest.TestCase):
    def test_buy_stop_fills_then_take_profit(self):
        ev = run([PIN_LOW, UP, (101.7, 105.5, 101.6, 105.4, 0, 0)])
        self.assertEqual(kinds(ev), ["TRADE_PENDING", "TRADE_OPEN", "TRADE_CLOSED"])
        o = ev[1]
        self.assertEqual(o["entry"], 101.5)                            # روی سقف پین‌بار
        self.assertAlmostEqual(o["sl"], 100.0 - SP)                    # کف پین‌بار − اسپرد
        self.assertAlmostEqual(o["tp"], 101.5 + 2 * (101.5 - (100.0 - SP)))
        self.assertEqual((ev[2]["result"], ev[2]["r"]), ("TP", 2.0))
        self.assertEqual(ev[1]["time"], T0 + pd.Timedelta(minutes=3))  # بسته‌شدن کندل ورود

    def test_cancelled_when_tail_breaks_first(self):
        ev = run([PIN_LOW, (101.0, 101.2, 99.8, 99.9, 0, 0)])
        self.assertEqual(kinds(ev), ["TRADE_PENDING", "TRADE_CANCELLED"])
        self.assertEqual(ev[1]["reason"], "tail")

    def test_expires_after_three_bars(self):
        quiet = (101.2, 101.4, 100.8, 101.1, 0, 0)
        ev = run([PIN_LOW, quiet, quiet, quiet, (101.1, 101.9, 101.0, 101.8, 0, 0)])
        self.assertEqual(kinds(ev), ["TRADE_PENDING", "TRADE_CANCELLED"])
        self.assertEqual(ev[1]["reason"], "expired")

    def test_outside_bar_bearish_fills_then_stops(self):
        # نزولی: باز ← سقف (ورود) ← کف (حد ضرر)
        ev = run([PIN_LOW, (101.0, 102.0, 99.0, 99.5, 0, 0)])
        self.assertEqual(kinds(ev), ["TRADE_PENDING", "TRADE_OPEN", "TRADE_CLOSED"])
        self.assertEqual(ev[2]["result"], "SL")

    def test_outside_bar_bullish_breaks_tail_first(self):
        # صعودی: باز ← کف (سایه شکست، قبل از ورود) ← سقف
        ev = run([PIN_LOW, (101.0, 102.0, 99.0, 101.8, 0, 0)])
        self.assertEqual(kinds(ev), ["TRADE_PENDING", "TRADE_CANCELLED"])

    def test_sl_and_tp_same_bar_follow_candle_shape(self):
        bull = run([PIN_LOW, UP, (101.7, 110.0, 99.0, 105.0, 0, 0)])        # اول کف ← حد ضرر
        self.assertEqual(bull[-1]["result"], "SL")
        bear = run([PIN_LOW, UP, (101.7, 110.0, 99.0, 100.0, 0, 0)])        # اول سقف ← حد سود
        self.assertEqual(bear[-1]["result"], "TP")

    def test_gap_above_trigger_fills_at_open(self):
        ev = run([PIN_LOW, (102.0, 102.3, 101.9, 102.2, 0, 0)])
        self.assertEqual(ev[1]["entry"], 102.0)

    def test_sell_pin_at_range_top(self):
        ev = run([(109.0, 110.0, 108.5, 108.7, -1, 0), (108.7, 108.8, 108.0, 108.1, 0, 0)])
        self.assertEqual((ev[1]["kind"], ev[1]["entry"]), ("TRADE_OPEN", 108.5))
        self.assertAlmostEqual(ev[1]["sl"], 110.0 + SP)

    def test_pin_in_middle_of_range_is_ignored(self):
        self.assertEqual(run([(105.0, 105.5, 104.0, 105.4, 1, 0), (105.4, 106.0, 105.3, 105.9, 0, 0)]), [])

    def test_no_range_trades_outside_a_range(self):
        self.assertEqual(run([PIN_LOW, UP], ctx={"state": "CHANNEL", "side": 1}), [])

    def test_tp_beyond_range_top_gets_warning(self):
        ev = run([PIN_LOW, UP], ctx={"state": "RANGE", "hi": 102.0, "lo": 100.0})
        self.assertTrue(ev[1]["tp_beyond_range"])
        self.assertIn("beyond the range top", build_trade_alert(ev[1]))


PB_PIN = (105.5, 105.8, 104.4, 105.6, 0, 0, 1)      # پین‌بار پولبک بالای سطح شکسته‌شده 104
KEY = (105.6, 107.0, 105.5, 106.9, 0, 1)


class TestSpikeTrades(unittest.TestCase):
    def test_pin_then_key_bar_enters_at_key_close(self):
        ev = run([PB_PIN, KEY], ctx=SPIKE_CTX)
        self.assertEqual(kinds(ev), ["TRADE_PENDING", "TRADE_OPEN"])
        o = ev[1]
        self.assertEqual(o["mode"], "SPIKE")
        self.assertEqual(o["entry"], 106.9)                            # شروع کندل بعد از Key bar
        self.assertAlmostEqual(o["sl"], 104.4 - SP)
        self.assertAlmostEqual(o["tp"], 106.9 + 2 * (106.9 - (104.4 - SP)))
        self.assertIn("first pullback", build_trade_alert(ev[0]))

    def test_no_key_bar_within_three_bars_cancels(self):
        quiet = (105.6, 105.9, 105.0, 105.7, 0, 0)
        ev = run([PB_PIN, quiet, quiet, quiet], ctx=SPIKE_CTX)
        self.assertEqual(kinds(ev), ["TRADE_PENDING", "TRADE_CANCELLED"])

    def test_tail_break_before_key_bar_cancels(self):
        ev = run([PB_PIN, (105.6, 105.7, 104.2, 104.5, 0, 0), KEY], ctx=SPIKE_CTX)
        self.assertEqual(kinds(ev), ["TRADE_PENDING", "TRADE_CANCELLED"])

    def test_only_one_entry_per_spike(self):
        quiet = (105.6, 105.9, 105.0, 105.7, 0, 0)
        ev = run([PB_PIN, quiet, quiet, quiet, PB_PIN, KEY], ctx=SPIKE_CTX)
        self.assertEqual(kinds(ev), ["TRADE_PENDING", "TRADE_CANCELLED"])
        new_spike = {**SPIKE_CTX, "spike_id": SPIKE_ID + pd.Timedelta(hours=1)}
        tm = TradeManager("XAUUSD")
        run([PB_PIN, quiet, quiet, quiet], ctx=SPIKE_CTX, tm=tm)
        later = T0 + pd.Timedelta(hours=1)
        self.assertEqual(kinds(run([PB_PIN, KEY], ctx=new_spike, tm=tm, start=later)),
                         ["TRADE_PENDING", "TRADE_OPEN"])

    def test_pin_closing_below_broken_level_is_ignored(self):
        self.assertEqual(run([(104.5, 104.8, 103.0, 103.8, 0, 0, 1), KEY], ctx=SPIKE_CTX), [])

    def test_no_trade_when_pullback_not_valid(self):
        self.assertEqual(run([PB_PIN, KEY], ctx={**SPIKE_CTX, "pullback": False}), [])


class TestLivePrices(unittest.TestCase):
    def test_live_ticks_decide_order_and_bars_do_not_repeat(self):
        tm = TradeManager("XAUUSD")
        d = frame([FLAT, PIN_LOW, (101.3, 105.5, 99.0, 105.4, 0, 0)])
        tm.process(d.iloc[:1], RANGE_CTX)
        self.assertEqual(kinds(tm.process(d.iloc[:2], RANGE_CTX)), ["TRADE_PENDING"])
        t = T0 + pd.Timedelta(minutes=2)
        tm.live_started(t)                                # زنده از شروع کندل بعد
        self.assertTrue(tm.needs_live())
        ev = tm.on_price(101.4, t + pd.Timedelta(seconds=5))
        ev += tm.on_price(101.6, t + pd.Timedelta(seconds=10))      # ورود (اولین قیمت بالای 101.5)
        ev += tm.on_price(105.5, t + pd.Timedelta(seconds=40))      # حد سود (کف 99 بعداً آمد)
        self.assertEqual(kinds(ev), ["TRADE_OPEN", "TRADE_CLOSED"])
        self.assertEqual(ev[0]["entry"], 101.6)                     # مثل سفارش Stop واقعی
        self.assertEqual(ev[1]["result"], "TP")
        self.assertTrue(ev[1]["live"])
        self.assertIn("Live price", build_trade_alert(ev[1]))
        # همان کندل بعداً بسته می‌شود (با کف 99): چیزی تکرار نمی‌شود
        self.assertEqual(tm.process(d, RANGE_CTX), [])

    def test_without_live_same_bar_uses_candle_shape(self):
        ev = run([PIN_LOW, (101.3, 105.5, 99.0, 105.4, 0, 0)])           # صعودی: اول کف ← سایه شکست
        self.assertEqual(kinds(ev), ["TRADE_PENDING", "TRADE_CANCELLED"])


class TestPinScannerMatchesBacktest(unittest.TestCase):
    def test_live_scanner_equals_backtest(self):
        m1 = candles(n=4200, vol=0.0005, freq="1min", seed=SEED)
        feed = {"n": 3600}
        live_ev = []

        def fake(sym, n_bars, min_bars, interval=None):
            part = m1.iloc[:feed["n"]]
            return part.tail(300) if interval == "1" else to_tf(part).tail(500)

        with mock.patch.object(scanner, "get_closed_candles", fake),              mock.patch.object(scanner, "SYMBOLS", {"XAUUSD": []}),              mock.patch.object(scanner, "ALERT_CHARTS", False),              mock.patch.object(scanner, "build_trade_alert", lambda ev: live_ev.append(ev) or "trade"):
            sc = scanner.Scanner(lambda t, photo=None: None)
            sc.strategy = "pin"
            sc.trades = {"XAUUSD": TradeManager("XAUUSD")}
            sc.scan_once()
            while feed["n"] < len(m1):
                feed["n"] += 1
                sc.scan_once()
        from bot import backtest
        start = m1.index[3600]
        bt, _ = backtest.run("XAUUSD", m1, backtest.to_m5(m1), start, strategy="pin")
        key = lambda e: (e["kind"], e["mode"], e["time"], round(e.get("entry", e["planned_entry"]), 4))
        self.assertTrue(live_ev)
        self.assertEqual([key(e) for e in live_ev], [key(e) for e in bt if e["time"] > start + pd.Timedelta(minutes=1)])
        self.assertTrue(all(e["strategy"] == "pin" for e in live_ev))


if __name__ == "__main__":
    unittest.main()
