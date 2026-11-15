"""بک‌تست مرحله‌به‌مرحله در تلگرام: جفت‌ارز ← تایم‌فریم ← بازه ← پیام انتظار ← نتیجه."""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import backtest  # noqa: E402
from bot.storage import JsonState  # noqa: E402
from bot.telegram_bot import Telegram  # noqa: E402
from tests.synthetic import candles  # noqa: E402


def buttons(markup):
    return [(b.text, b.callback_data) for row in markup.keyboard for b in row]


class FakeCall:
    def __init__(self, data, chat_id=7, mid=100):
        self.id = "cb"
        self.data = data
        self.message = mock.MagicMock()
        self.message.chat.id = chat_id
        self.message.message_id = mid


class TestBacktestFlow(unittest.TestCase):
    def setUp(self):
        st = JsonState(os.path.join(tempfile.mkdtemp(), "s.json"))
        self.tg = Telegram(None, st)
        self.tg.bot = mock.MagicMock()
        self.tg.bot.send_photo.return_value = mock.MagicMock(photo=[mock.MagicMock(file_id="F")])
        self.flow = self.tg.backtests

    def last_markup(self):
        call = self.tg.bot.edit_message_text.call_args
        return call.kwargs.get("reply_markup")

    def test_steps_suggest_pair_timeframe_and_period(self):
        self.flow.start(7)
        kb = self.tg.bot.send_message.call_args.kwargs["reply_markup"]
        self.assertEqual(buttons(kb)[0], ("🥇🇺🇸 XAUUSD · recommended", "btp:XAUUSD"))   # پیشنهاد: طلا
        self.assertEqual(len(buttons(kb)), 9)

        self.flow.on_callback(FakeCall("btp:EURUSD"))
        tf = buttons(self.last_markup())
        self.assertIn(("M5 → M1  ✅ recommended (your live setup)", "btt:EURUSD:5-1"), tf)
        self.assertIn(("H1 → M5", "btt:EURUSD:60-5"), tf)
        self.assertEqual(tf[-1], ("⬅️ Back", "bt"))

        self.flow.on_callback(FakeCall("btt:EURUSD:5-1"))
        days = buttons(self.last_markup())
        self.assertEqual([d for _, d in days[:-1]],
                         ["btd:EURUSD:5-1:1", "btd:EURUSD:5-1:3", "btd:EURUSD:5-1:5", "btd:EURUSD:5-1:10"])
        self.assertIn(("5 days ✅", "btd:EURUSD:5-1:5"), days)

    def test_run_shows_waiting_then_results(self):
        m1 = candles(n=7600, vol=0.0005, freq="1min", seed=5)
        real = backtest.run_days

        def fake_run_days(sym, days, tf="5-1", progress=None, **kw):
            for stage in ("fetch_trig", "fetch_ctx"):
                progress(stage)
                time.sleep(0.05)
            return real(sym, days, m1=m1, m5=backtest.to_m5(m1), tf=tf, progress=progress)

        with mock.patch.object(backtest, "run_days", fake_run_days):
            self.flow.on_callback(FakeCall("btd:XAUUSD:5-1:5"))
            for _ in range(200):                        # در پس‌زمینه اجرا می‌شود
                if 7 not in self.flow.running:
                    break
                time.sleep(0.05)
        self.assertNotIn(7, self.flow.running)
        texts = [c.args[0] for c in self.tg.bot.edit_message_text.call_args_list]
        self.assertTrue(any("⏳" in t and "Downloading trigger" in t for t in texts))     # پیام انتظار
        self.assertTrue(any("Replaying" in t for t in texts))
        self.assertTrue(any("Backtest finished" in t for t in texts))
        photo = self.tg.bot.send_photo.call_args
        self.assertEqual(photo.args[1][:4], b"\x89PNG")                                  # نمودار موجودی
        sent = [c.args[1] for c in self.tg.bot.send_message.call_args_list]
        sent.append(photo.kwargs.get("caption", ""))                      # کوتاه: زیر عکس
        self.assertTrue(any("BACKTEST" in t and "Risk 1% per trade" in t for t in sent))

    def test_one_backtest_at_a_time(self):
        self.flow.running.add(7)
        self.flow.run(7, "XAUUSD", "5-1", 5)
        self.assertIn("already running", self.tg.bot.send_message.call_args.args[1])

    def test_pairs_menu_has_backtest_button(self):
        self.assertIn(("🧪 Backtest", "bt"), buttons(self.tg.pairs_keyboard(7)))


if __name__ == "__main__":
    unittest.main()
