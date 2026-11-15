"""تست‌های ستاپ ورود: رنج (Stop روی پین‌بار) و اولین پولبک اسپایک (پین‌بار + Key bar)، ۱:۲،
ترتیب رسیدن به سطح‌ها (قیمت زنده یا شکل کندل)."""
import os
import sys
import unittest
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import scanner  # noqa: E402
from bot.alert_chart import trade_chart  # noqa: E402
from bot.config import spread  # noqa: E402
from bot.messages import build_spike_alert, build_trade_alert  # noqa: E402
from bot.strategy import analyze  # noqa: E402
from bot.trades import TradeManager, candle_path, signal_bar, walk  # noqa: E402
from tests.synthetic import candles, to_tf  # noqa: E402

SP = spread("XAUUSD")
T0 = pd.Timestamp("2026-11-12 10:00", tz="UTC")
M5 = pd.Timedelta(minutes=5)
M1 = pd.Timedelta(minutes=1)


def bar(t, o, h, l, c):
    return {"date": t, "open": o, "high": h, "low": l, "close": c}


def kinds(ev):
    return [e["kind"] for e in ev]


class Sim:
    """کندل‌های M5 (با زمینه‌ی دلخواه) و M1 را به ترتیب زمان به TradeManager می‌دهد."""

    def __init__(self, warm=6, size=1.0, base=100.0):
        self.tm = TradeManager("XAUUSD")
        self.t = T0
        self.ev = []
        for _ in range(warm):                          # گرم شدن: کندل‌های متوسط ۱ واحدی
            self.m5((base, base + size / 2, base - size / 2, base), None)

    def m5(self, ohlc, ctx):
        out = self.tm.on_m5_close(bar(self.t, *ohlc), ctx)
        self.t += M5
        self.ev += out
        return out

    def m1(self, ohlc):
        out = self.tm.on_m1(bar(self.t, *ohlc))
        self.t += M1
        self.ev += out
        return out


def chan(side=1, kind="tight", high=110.0, start=100.0, forming=False, **kw):
    return {"state": "CHANNEL", "side": side, "kind": kind, "high": high, "start_price": start,
            "start_time": T0, "since": T0, "forming": forming, **kw}


RANGE_CTX = {"state": "RANGE", "hi": 110.0, "lo": 100.0, "valid": True, "tight": False,
             "bottom_tests": [100.2, 100.4], "top_tests": [109.8], "since": T0}


class TestWalk(unittest.TestCase):
    def test_candle_path(self):
        self.assertEqual(candle_path(1, 3, 0, 2), [1, 0, 3, 2])      # صعودی: اول کف
        self.assertEqual(candle_path(2, 3, 0, 1), [2, 3, 0, 1])      # نزولی: اول سقف

    def test_first_level_on_path(self):
        self.assertEqual(walk([1, 0, 3, 2], {"A": (2.5, 1), "B": (0.5, -1)})[0], "B")
        self.assertEqual(walk([2, 3, 0, 1], {"A": (2.5, 1), "B": (0.5, -1)})[0], "A")
        self.assertEqual(walk([3, 4], {"A": (2.5, 1)})[:2], ("A", 3))             # گپ: اجرا با قیمت باز
        self.assertIsNone(walk([1, 2], {"A": (2.5, 1)}))


class TestSignalBar(unittest.TestCase):
    def test_signal_bar(self):
        self.assertTrue(signal_bar(1, 100, 101, 99, 100.8))        # صعودی، بسته‌شدن بالا
        self.assertTrue(signal_bar(1, 100.5, 101, 99, 100.6))      # سایه‌ی پایین بلند
        self.assertFalse(signal_bar(1, 100.8, 101, 99, 99.2))      # نزولی، بسته‌شدن پایین
        self.assertTrue(signal_bar(-1, 100.8, 101, 99, 99.2))


class TestTrendTrades(unittest.TestCase):
    """در جهت روند: H1 در کانال تنگ، H2 در کانال باز (جزوه فصل ۰۴)."""

    def setup(self, kind="tight"):
        sim = Sim()
        ctx = chan(kind=kind)
        sim.m5((109.0, 110.0, 108.8, 109.9), ctx)              # سقف کانال
        return sim, ctx

    def test_h1_in_tight_channel_then_take_profit(self):
        sim, ctx = self.setup()
        ev = sim.m5((109.6, 109.8, 108.9, 109.6), ctx)         # کندل پولبک با بسته‌شدن قوی
        self.assertEqual(kinds(ev), ["TRADE_PENDING"])
        p = ev[0]
        self.assertEqual((p["mode"], p["n_h"], p["planned_entry"]), ("TREND", 1, 109.8))
        self.assertAlmostEqual(p["sl"], 108.9 - SP)
        sim.m1((109.6, 109.9, 109.5, 109.85))                   # ورود روی سقف کندل سیگنال
        sim.m1((109.85, 112.5, 109.8, 112.4))                   # حد سود
        self.assertEqual(kinds(sim.ev)[1:], ["TRADE_OPEN", "TRADE_CLOSED"])
        self.assertEqual(sim.ev[1]["entry"], 109.8)
        self.assertEqual((sim.ev[2]["result"], sim.ev[2]["r"]), ("TP", 2.0))

    def test_broad_channel_needs_h2(self):
        sim, ctx = self.setup("broad")
        self.assertEqual(sim.m5((109.6, 109.8, 108.9, 109.6), ctx), [])     # H1: صبر
        sim.m5((109.6, 109.95, 109.4, 109.5), ctx)              # تلاشی که سقف تازه نساخت
        ev = sim.m5((109.5, 109.7, 108.7, 109.5), ctx)          # پولبک دوم
        self.assertEqual(kinds(ev), ["TRADE_PENDING"])
        self.assertEqual(ev[0]["n_h"], 2)

    def test_deep_pullback_is_not_a_trend_trade(self):
        sim, ctx = self.setup()
        self.assertEqual(sim.m5((104.0, 104.5, 103.0, 104.4), ctx), [])     # بیش از ۶۲٪ پس داده

    def test_weak_signal_bar_is_skipped(self):
        sim, ctx = self.setup()
        self.assertEqual(sim.m5((109.6, 109.8, 108.9, 109.0), ctx), [])

    def test_bear_channel_sells(self):
        sim = Sim()
        ctx = chan(side=-1, high=90.0, start=100.0)
        sim.m5((91.0, 91.2, 90.0, 90.1), ctx)
        ev = sim.m5((90.4, 91.1, 90.2, 90.4), ctx)
        self.assertEqual((ev[0]["side"], ev[0]["planned_entry"]), (-1, 90.2))
        self.assertAlmostEqual(ev[0]["sl"], 91.1 + SP)

    def test_no_trades_when_channel_under_test(self):
        sim, ctx = self.setup()
        self.assertEqual(sim.m5((109.6, 109.8, 108.9, 109.6), {**ctx, "state": "TEST"}), [])


class TestSpikeTrades(unittest.TestCase):
    def ctx(self, **kw):
        return chan(forming=True, pullback=True, broken=104.0, spike_id=T0, high=110.0, start=104.5, **kw)

    def test_first_pullback_h1_above_broken_level_once_per_spike(self):
        sim = Sim()
        ctx = self.ctx()
        sim.m5((109.0, 110.0, 108.8, 109.9), ctx)
        ev = sim.m5((109.4, 109.7, 107.0, 109.5), ctx)
        self.assertEqual((ev[0]["mode"], ev[0]["n_h"], ev[0]["level"]), ("SPIKE", 1, 104.0))
        sim.m1((109.4, 109.5, 106.5, 106.6))                    # سر دیگر کندل سیگنال شکست: لغو
        self.assertEqual(kinds(sim.ev)[-1], "TRADE_CANCELLED")
        self.assertEqual(sim.m5((108.0, 108.5, 107.2, 108.4), ctx), [])     # فقط یک ستاپ برای هر اسپایک

    def test_no_trade_when_pullback_lost_the_level(self):
        sim = Sim()
        ctx = self.ctx()
        sim.m5((109.0, 110.0, 108.8, 109.9), ctx)
        self.assertEqual(sim.m5((109.4, 109.7, 107.0, 109.5), {**ctx, "pullback": False}), [])


class TestRangeTrades(unittest.TestCase):
    BULL = (100.6, 101.2, 100.3, 101.1)                     # کندل سیگنال صعودی در کف رنج

    def test_second_test_of_bottom_buys_above_signal_bar(self):
        sim = Sim()
        ev = sim.m5(self.BULL, RANGE_CTX)
        self.assertEqual((ev[0]["mode"], ev[0]["side"], ev[0]["planned_entry"]), ("RANGE", 1, 101.2))
        self.assertAlmostEqual(ev[0]["sl"], 100.3 - SP)
        self.assertIn("second entry", build_trade_alert(ev[0]))

    def test_first_test_only_is_skipped(self):
        self.assertEqual(Sim().m5(self.BULL, {**RANGE_CTX, "bottom_tests": [100.4]}), [])

    def test_second_test_breaking_the_first_is_skipped(self):
        self.assertEqual(Sim().m5(self.BULL, {**RANGE_CTX, "bottom_tests": [102.0, 100.3]}), [])

    def test_not_a_real_range_or_barbwire(self):
        self.assertEqual(Sim().m5(self.BULL, {**RANGE_CTX, "valid": False}), [])
        self.assertEqual(Sim().m5(self.BULL, {**RANGE_CTX, "tight": True}), [])

    def test_middle_of_range_is_skipped(self):
        self.assertEqual(Sim().m5((104.6, 105.2, 104.3, 105.1), RANGE_CTX), [])


class TestOrders(unittest.TestCase):
    def pending(self):
        sim = Sim()
        sim.m5(TestRangeTrades.BULL, RANGE_CTX)
        return sim

    def test_expires_after_three_m5_bars(self):
        sim = self.pending()
        for _ in range(15):
            sim.m1((100.9, 101.0, 100.8, 100.9))
        self.assertEqual(kinds(sim.ev), ["TRADE_PENDING"])
        sim.m1((100.9, 101.0, 100.8, 100.9))
        self.assertEqual(sim.ev[-1]["reason"], "expired")

    def test_newer_signal_bar_moves_the_order(self):
        sim = self.pending()
        ev = sim.m5((100.5, 101.0, 100.35, 100.9), RANGE_CTX)
        self.assertTrue(ev[0]["moved"])
        self.assertEqual(sim.tm.pending["planned_entry"], 101.0)
        self.assertIn("ORDER MOVED", build_trade_alert(ev[0]))

    def test_outside_bar_order_follows_candle_shape(self):
        sim = self.pending()
        sim.m1((100.8, 101.5, 99.0, 99.2))                       # نزولی: اول سقف (ورود) بعد کف (حد ضرر)
        self.assertEqual(kinds(sim.ev)[1:], ["TRADE_OPEN", "TRADE_CLOSED"])
        sim = self.pending()
        sim.m1((100.8, 101.5, 99.0, 101.4))                      # صعودی: اول کف ← لغو، بدون معامله
        self.assertEqual(kinds(sim.ev)[1:], ["TRADE_CANCELLED"])

    def test_live_ticks_decide_and_bars_do_not_repeat(self):
        sim = self.pending()
        sim.tm.live_started(sim.t)
        ev = sim.tm.on_price(101.25, sim.t + pd.Timedelta(seconds=5))           # ورود
        tp = sim.tm.open["tp"]
        ev += sim.tm.on_price(tp + 0.01, sim.t + pd.Timedelta(seconds=40))      # حد سود
        self.assertEqual(kinds(ev), ["TRADE_OPEN", "TRADE_CLOSED"])
        self.assertTrue(ev[1]["live"])
        self.assertEqual(sim.m1((101.0, tp + 1, 98.0, 99.0)), [])               # همان دقیقه: تکرار نمی‌شود

    def test_two_losses_brake_that_direction_until_context_changes(self):
        sim = Sim()
        for _ in range(2):
            sim.m5(TestRangeTrades.BULL, RANGE_CTX)
            sim.m1((100.9, 101.3, 99.0, 99.1))                   # ورود و حد ضرر
        self.assertEqual([e.get("result") for e in sim.ev if e["kind"] == "TRADE_CLOSED"], ["SL", "SL"])
        self.assertEqual(sim.m5(TestRangeTrades.BULL, RANGE_CTX), [])           # ترمز
        new_ctx = {**RANGE_CTX, "since": T0 + pd.Timedelta(hours=3)}
        self.assertEqual(kinds(sim.m5(TestRangeTrades.BULL, new_ctx)), ["TRADE_PENDING"])   # زمینه‌ی تازه: ترمز باز


class TestTradeOutput(unittest.TestCase):
    def test_messages_and_chart_for_every_mode(self):
        c = candles(n=600, seed=2)
        res = analyze(c)
        d = res["df"]
        row = d.iloc[-3]
        sig = {"time": row["date"], "high": row["high"], "low": row["low"], "close": row["close"]}
        base = {"sym": "XAUUSD", "side": 1, "signal": sig, "pin": sig, "spread": SP,
                "time": d["date"].iloc[-1] + M5, "price": 1.0, "planned_entry": row["high"], "entry": row["high"],
                "sl": row["low"] - SP, "tp": row["high"] + 3, "risk": 1.5, "range_high": row["high"] + 5,
                "range_low": row["low"] - 1, "first_test": row["low"], "level": row["low"] + 0.1, "n_h": 2,
                "channel_kind": "broad", "result": "TP", "r": 2.0, "exit": row["high"] + 3, "bars": 4,
                "reason": "expired"}
        for mode in ("RANGE", "SPIKE", "TREND"):
            for k in ("TRADE_PENDING", "TRADE_OPEN", "TRADE_CLOSED", "TRADE_CANCELLED"):
                ev = {**base, "mode": mode, "kind": k}
                self.assertIn("XAUUSD", build_trade_alert(ev))
                self.assertEqual(trade_chart("XAUUSD", res, ev)[:4], b"\x89PNG")

    def test_spike_alert_text(self):
        ev = {"sym": "XAUUSD", "price": 2662.0, "time": T0,
              "snap": {"side": 1, "broken": 2650.0, "start_price": 2649.0, "extreme": 2662.5, "size": 2.6}}
        self.assertIn("M5 SPIKE", build_spike_alert(ev))


class TestScannerWiring(unittest.TestCase):
    def test_spike_alert_and_trades_run_end_to_end(self):
        m1 = candles(n=3300, vol=0.0005, freq="1min", seed=5)
        feed = {"n": 2800}
        alerts, fol = [], []

        def fake(sym, n_bars, min_bars, interval=None):
            part = m1.iloc[:feed["n"]]
            return part.tail(300) if interval == "1" else to_tf(part).tail(500)

        live_ev = []
        with mock.patch.object(scanner, "get_closed_candles", fake), \
             mock.patch.object(scanner, "SYMBOLS", {"XAUUSD": []}), \
             mock.patch.object(scanner, "ALERT_CHARTS", False), \
             mock.patch.object(scanner, "build_trade_alert", lambda ev: live_ev.append(ev) or "trade"):
            sc = scanner.Scanner(lambda t, photo=None: alerts.append(t), lambda s, t, photo=None: fol.append(t))
            sc.trades = {"XAUUSD": TradeManager("XAUUSD")}
            sc.scan_once()
            while feed["n"] < len(m1):
                feed["n"] += 1
                sc.scan_once()
        self.assertTrue(fol)                                            # تغییرات چرخه برای فالوکننده‌ها
        self.assertTrue(all("M5 cycle" not in a for a in alerts))       # و نه برای همه
        self.assertTrue(any("M5 SPIKE" in a for a in alerts) or any("SPIKE" in f for f in fol))
        # بک‌تست روی همان داده دقیقاً همان معامله‌ها را می‌دهد
        from bot import backtest
        start = m1.index[2800]
        bt, _ = backtest.run("XAUUSD", m1, backtest.to_m5(m1), start)
        key = lambda e: (e["kind"], e["mode"], e["time"], round(e.get("entry", e["planned_entry"]), 4))
        self.assertTrue(live_ev)                                        # معامله‌ای واقعاً ساخته شد
        self.assertEqual([key(e) for e in live_ev],
                         [key(e) for e in bt if e["time"] > start + pd.Timedelta(minutes=1)])


class TestBacktest(unittest.TestCase):
    def test_account_math_and_report(self):
        from bot import backtest
        T = pd.Timestamp("2026-11-12", tz="UTC")
        ev = [{"kind": "TRADE_OPEN", "opened": T}, {"kind": "TRADE_CLOSED", "opened": T, "r": 2.0, "time": T},
              {"kind": "TRADE_OPEN", "opened": T + pd.Timedelta(hours=1)},
              {"kind": "TRADE_CLOSED", "opened": T + pd.Timedelta(hours=1), "r": -1.0, "time": T}]
        final, dd, curve = backtest.account(ev, 1000, 1.0)
        self.assertAlmostEqual(final, 1000 * 1.02 * 0.99)               # +2% بعد −1% (مرکب)
        self.assertAlmostEqual(dd, 1.0)
        m1 = candles(n=7600, vol=0.0005, freq="1min", seed=5)
        res, err = backtest.run_days("XAUUSD", 5, m1=m1, m5=backtest.to_m5(m1))
        self.assertIsNone(err)
        self.assertEqual(res["trades"], res["wins"] + res["losses"])
        txt = backtest.report_text(res)
        self.assertIn("BACKTEST", txt)
        self.assertIn("Risk 1% per trade", txt)
        self.assertEqual(backtest.equity_chart(res)[:4], b"\x89PNG")


class TestLiveParse(unittest.TestCase):
    def test_parse_quote_messages_and_heartbeat(self):
        from bot.live import frame as tv_frame, parse
        hb, prices = parse("~m~4~m~~h~12")
        self.assertEqual((hb, prices), ("~m~4~m~~h~12", []))
        msg = ('{"m":"qsd","p":["qs_x",{"n":"OANDA:XAUUSD","s":"ok","v":{"lp":2650.4,"bid":2650.31}}]}')
        raw = f"~m~{len(msg)}~m~{msg}" + tv_frame("quote_completed", ["qs_x", "OANDA:XAUUSD"])
        self.assertEqual(parse(raw), (None, [("OANDA:XAUUSD", 2650.31)]))       # Bid، مثل نمودار
        msg2 = '{"m":"qsd","p":["qs_x",{"n":"FX:EURUSD","v":{"lp":1.08512}}]}'
        self.assertEqual(parse(f"~m~{len(msg2)}~m~{msg2}")[1], [("FX:EURUSD", 1.08512)])


if __name__ == "__main__":
    unittest.main()
