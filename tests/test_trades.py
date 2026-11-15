"""تست‌های ستاپ ورود: رنج (Stop روی پین‌بار) و بریک‌اوت (پین‌بار + Key bar)، حد ضرر/سود ۱:۲."""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.alert_chart import trade_chart  # noqa: E402
from bot.config import spread  # noqa: E402
from bot.messages import build_trade_alert  # noqa: E402
from bot.strategy import analyze  # noqa: E402
from bot.trades import TradeManager  # noqa: E402
from tests.synthetic import candles  # noqa: E402

SP = spread("XAUUSD")
RANGE_CTX = {"state": "RANGE", "hi": 110.0, "lo": 100.0}


def frame(rows, start="2026-11-12 10:00"):
    """rows: (open, high, low, close, pin_bar, key_bar[, pin_pullback])"""
    idx = pd.date_range(start, periods=len(rows), freq="1min", tz="UTC")
    data = []
    for t, r in zip(idx, rows):
        o, h, l, c, pin, key = r[:6]
        data.append({"date": t, "open": o, "high": h, "low": l, "close": c, "pin_bar": pin,
                     "key_bar": key, "pin_pullback": r[6] if len(r) > 6 else 0})
    return pd.DataFrame(data)


FLAT = (105.0, 105.5, 104.5, 105.0, 0, 0)


def run(rows, ctx=RANGE_CTX, mtf=(), mtf_at=None):
    """کندل‌ها را یکی‌یکی به TradeManager می‌دهد (مثل اسکنر زنده)."""
    tm = TradeManager("XAUUSD")
    d = frame([FLAT] + rows)
    tm.process(d.iloc[:1], ctx)
    out = []
    for n in range(2, len(d) + 1):
        ev = list(mtf) if mtf_at == n else []
        out += tm.process(d.iloc[:n], ctx, ev)
    return out


PIN_LOW = (101.0, 101.5, 100.0, 101.3, 1, 0)        # پین‌بار صعودی در کف رنج: سقف 101.5، کف 100.0


class TestRangeTrades(unittest.TestCase):
    def test_buy_stop_fills_then_take_profit(self):
        ev = run([PIN_LOW, (101.3, 101.8, 101.2, 101.7, 0, 0), (101.7, 105.5, 101.6, 105.4, 0, 0)])
        self.assertEqual([e["kind"] for e in ev], ["TRADE_PENDING", "TRADE_OPEN", "TRADE_CLOSED"])
        o = ev[1]
        self.assertEqual(o["entry"], 101.5)                            # روی سقف پین‌بار
        self.assertAlmostEqual(o["sl"], 100.0 - SP)                    # کف پین‌بار − اسپرد
        self.assertAlmostEqual(o["tp"], 101.5 + 2 * (101.5 - (100.0 - SP)))
        self.assertEqual((ev[2]["result"], ev[2]["r"]), ("TP", 2.0))

    def test_cancelled_when_tail_breaks_first(self):
        ev = run([PIN_LOW, (101.0, 101.2, 99.8, 99.9, 0, 0)])
        self.assertEqual([e["kind"] for e in ev], ["TRADE_PENDING", "TRADE_CANCELLED"])
        self.assertEqual(ev[1]["reason"], "tail")

    def test_expires_after_three_bars(self):
        quiet = (101.2, 101.4, 100.8, 101.1, 0, 0)
        ev = run([PIN_LOW, quiet, quiet, quiet, (101.1, 101.9, 101.0, 101.8, 0, 0)])
        self.assertEqual([e["kind"] for e in ev], ["TRADE_PENDING", "TRADE_CANCELLED"])
        self.assertEqual(ev[1]["reason"], "expired")

    def test_fill_and_stop_in_same_bar_counts_as_loss(self):
        ev = run([PIN_LOW, (101.0, 102.0, 99.0, 99.5, 0, 0)])
        self.assertEqual([e["kind"] for e in ev], ["TRADE_PENDING", "TRADE_OPEN", "TRADE_CLOSED"])
        self.assertEqual(ev[2]["result"], "SL")

    def test_sl_and_tp_same_bar_is_stop_loss(self):
        ev = run([PIN_LOW, (101.3, 101.8, 101.2, 101.7, 0, 0), (101.7, 110.0, 99.0, 105.0, 0, 0)])
        self.assertEqual((ev[-1]["result"], ev[-1]["r"]), ("SL", -1.0))

    def test_sell_pin_at_range_top(self):
        pin = (109.0, 110.0, 108.5, 108.7, -1, 0)
        ev = run([pin, (108.7, 108.8, 108.0, 108.1, 0, 0)])
        o = ev[1]
        self.assertEqual((o["kind"], o["entry"]), ("TRADE_OPEN", 108.5))
        self.assertAlmostEqual(o["sl"], 110.0 + SP)

    def test_pin_in_middle_of_range_is_ignored(self):
        mid = (105.0, 105.5, 104.0, 105.4, 1, 0)
        self.assertEqual(run([mid, (105.4, 106.0, 105.3, 105.9, 0, 0)]), [])

    def test_no_range_trades_outside_a_range(self):
        ctx = {"state": "CHANNEL", "side": 1}
        self.assertEqual(run([PIN_LOW, (101.3, 101.8, 101.2, 101.7, 0, 0)], ctx=ctx), [])

    def test_tp_beyond_range_top_gets_warning(self):
        ctx = {"state": "RANGE", "hi": 102.0, "lo": 100.0}
        ev = run([PIN_LOW, (101.3, 101.8, 101.2, 101.7, 0, 0)], ctx=ctx)
        self.assertTrue(ev[1]["tp_beyond_range"])
        self.assertIn("beyond the range top", build_trade_alert(ev[1]))


class TestBreakoutTrades(unittest.TestCase):
    BO = {"kind": "BO_CONFIRMED", "side": 1, "level": 104.0, "ctx": "RANGE",
          "time": pd.Timestamp("2026-11-12 10:00", tz="UTC")}

    def test_pin_then_key_bar_enters_at_key_close(self):
        pin = (105.5, 105.8, 104.4, 105.6, 0, 0, 1)                  # پین‌بار پولبک بالای سطح 104
        key = (105.6, 107.0, 105.5, 106.9, 0, 1)
        ev = run([pin, key], ctx=None, mtf=[self.BO], mtf_at=2)
        self.assertEqual([e["kind"] for e in ev], ["TRADE_PENDING", "TRADE_OPEN"])
        o = ev[1]
        self.assertEqual(o["mode"], "BREAKOUT")
        self.assertEqual(o["entry"], 106.9)                            # شروع کندل بعد از Key bar
        self.assertAlmostEqual(o["sl"], 104.4 - SP)
        self.assertAlmostEqual(o["tp"], 106.9 + 2 * (106.9 - (104.4 - SP)))

    def test_no_key_bar_within_three_bars_cancels(self):
        pin = (105.5, 105.8, 104.4, 105.6, 0, 0, 1)
        quiet = (105.6, 105.9, 105.0, 105.7, 0, 0)
        ev = run([pin, quiet, quiet, quiet], ctx=None, mtf=[self.BO], mtf_at=2)
        self.assertEqual([e["kind"] for e in ev], ["TRADE_PENDING", "TRADE_CANCELLED"])

    def test_pin_closing_back_below_level_is_ignored(self):
        pin = (104.5, 104.8, 103.0, 103.8, 0, 0, 1)                  # زیر سطح بسته شد
        self.assertEqual(run([pin], ctx=None, mtf=[self.BO], mtf_at=2), [])

    def test_without_confirmation_nothing_happens(self):
        pin = (105.5, 105.8, 104.4, 105.6, 0, 0, 1)
        key = (105.6, 107.0, 105.5, 106.9, 0, 1)
        self.assertEqual(run([pin, key], ctx=None), [])


class TestTradeOutput(unittest.TestCase):
    def test_messages_and_chart(self):
        c = candles(n=400, vol=0.0005, freq="1min", seed=2)
        res = analyze(c, cycle=False)
        d = res["df"]
        row = d.iloc[-5]
        pin = {"time": row["date"], "high": row["high"], "low": row["low"], "close": row["close"]}
        base = {"sym": "XAUUSD", "side": 1, "mode": "RANGE", "pin": pin, "spread": SP, "time": d["date"].iloc[-1],
                "price": 1.0, "planned_entry": row["high"], "entry": row["high"], "sl": row["low"] - SP,
                "tp": row["high"] + 3, "risk": 1.5, "range_high": row["high"] + 5, "range_low": row["low"] - 1,
                "result": "TP", "r": 2.0, "exit": row["high"] + 3, "bars": 4, "reason": "expired"}
        for k in ("TRADE_PENDING", "TRADE_OPEN", "TRADE_CLOSED", "TRADE_CANCELLED"):
            ev = {**base, "kind": k}
            self.assertIn("XAUUSD", build_trade_alert(ev))
            self.assertEqual(trade_chart("XAUUSD", res, ev)[:4], b"\x89PNG")


if __name__ == "__main__":
    unittest.main()
