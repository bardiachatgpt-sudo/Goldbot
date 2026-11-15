"""تست‌های چرخه‌ی بازار (رنج/اسپایک/کانال/تست)، فالو کردن و پیام‌ها."""
import os
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import scanner  # noqa: E402
from bot.cycle import CHANNEL, RANGE, SPIKE, TEST, TEST_BARS, CycleEngine  # noqa: E402
from bot.messages import build_cycle_alert, cycle_block  # noqa: E402
from bot.storage import JsonState, followers, is_following  # noqa: E402
from bot.telegram_bot import Telegram, caption_fits  # noqa: E402
from tests.synthetic import candles  # noqa: E402

ALLOWED = {RANGE: {SPIKE, CHANNEL}, SPIKE: {CHANNEL, SPIKE}, CHANNEL: {TEST, RANGE, SPIKE},
           TEST: {CHANNEL, RANGE, SPIKE}}


def _bars(rows):
    idx = pd.date_range("2026-11-12 00:00", periods=len(rows), freq="5min", tz="UTC")
    return pd.DataFrame(rows, index=idx, columns=["Open", "High", "Low", "Close"])


def _flat(n, mid=100.0):
    out = []
    for i in range(n):
        o = mid + (0.3 if i % 2 else -0.3)
        c = mid - (0.3 if i % 2 else -0.3)
        out.append((o, max(o, c) + 0.2, min(o, c) - 0.2, c))
    return out


class TestHandBuilt(unittest.TestCase):
    def test_range_then_spike_then_first_pullback(self):
        rows = _flat(40) + [(100.2, 101.6, 100.1, 101.5), (101.5, 103.0, 101.4, 102.9),
                            (102.9, 104.4, 102.8, 104.3)]
        e = CycleEngine()
        e.feed(_bars(rows))
        self.assertEqual((e.state, e.side), (SPIKE, 1))
        self.assertEqual(e.segments[-1]["start"], 40)            # اسپایک از اولین کندل قوی
        snap = e.snapshot()
        self.assertAlmostEqual(snap["start_price"], 100.1)
        self.assertAlmostEqual(snap["extreme"], 104.4)
        e.feed(_bars(rows + [(104.3, 104.35, 103.6, 103.7)]))   # اولین پولبک
        self.assertEqual((e.state, e.side), (CHANNEL, 1))
        self.assertTrue(e.snapshot()["forming"])

    def test_spike_erased_becomes_range(self):
        rows = _flat(40) + [(100.2, 101.6, 100.1, 101.5), (101.5, 103.0, 101.4, 102.9),
                            (102.9, 103.0, 102.0, 102.1), (102.1, 102.2, 99.9, 100.0)]
        e = CycleEngine()
        e.feed(_bars(rows))
        self.assertEqual(e.state, RANGE)
        self.assertEqual(e.snapshot()["why"], "spike_erased")
        self.assertIn("Formed by: the spike was fully erased", cycle_block("XAUUSD", e.snapshot()))

    def test_flat_market_stays_range(self):
        e = CycleEngine()
        e.feed(_bars(_flat(200)))
        self.assertEqual(e.state, RANGE)
        self.assertEqual(len(e.segments), 1)


class TestCycleRules(unittest.TestCase):
    """روی داده‌ی ساختگی طولانی، قواعد چرخه همیشه رعایت می‌شود."""

    def test_rules_hold(self):
        seen = set()
        for seed in range(6):
            e = CycleEngine("XAUUSD", always_in=True)       # همه‌ی گذارها، از جمله Always In
            prev = (RANGE, 0)
            test_start = None
            for ts, r in candles(n=1500, seed=seed).iterrows():
                evs = e.on_bar(ts, r.Open, r.High, r.Low, r.Close)
                i = e.n - 1
                cur = (e.state, e.side)
                for ev in evs:
                    a, b = ev["from"], ev["to"]
                    if a != b:
                        self.assertIn(b[0], ALLOWED[a[0]], (a, b))
                        seen.add((a[0], b[0]))
                    if a[0] == TEST and b[0] == CHANNEL:       # ادامه‌ی کانال فقط با بسته‌شدن فراتر از سقف
                        self.assertEqual(ev["note"], "resumed")
                    cycle_block("XAUUSD", ev["snap"])
                    self.assertIn("M5 cycle", build_cycle_alert(ev))
                if e.state == TEST:
                    if prev[0] != TEST:
                        test_start = i
                    self.assertLessEqual(i - test_start, TEST_BARS + 1)
                if e.state == CHANNEL and not e.info["forming"] and "slope" in e.info:
                    self.assertGreaterEqual(e.info["slope"] * e.side, -1e-12)     # شیب در جهت کانال
                    a = e.info["anchor_i"]
                    for j in range(a, i):                                       # همه‌ی کندل‌ها سمت درست خط
                        back = e.l[j] if e.side > 0 else e.h[j]
                        self.assertGreaterEqual((back - e.line_at(j)) * e.side, -1e-9)
                prev = cur
            segs = e.segments
            self.assertEqual(segs[0]["start"], 0)
            for x, y in zip(segs, segs[1:]):
                self.assertEqual(x["end"] + 1, y["start"])                     # بخش‌ها پیوسته‌اند
        for need in [(RANGE, SPIKE), (RANGE, CHANNEL), (SPIKE, CHANNEL), (CHANNEL, TEST), (TEST, RANGE),
                     (TEST, CHANNEL)]:
            self.assertIn(need, seen)


class TestFollowRouting(unittest.TestCase):
    def test_cycle_changes_go_only_to_followers(self):
        c = candles(n=900, seed=1)
        feed = {"n": 600}
        alerts, fol = [], []

        def fake(sym, n_bars, min_bars, interval=None):
            return c.iloc[:feed["n"]]

        photos = []

        def send(t, photo=None):
            alerts.append(t)
            photos.append(photo)

        def send_fol(s, t, photo=None):
            fol.append((s, t))
            photos.append(photo)

        with mock.patch.object(scanner, "get_closed_candles", fake), \
             mock.patch.object(scanner, "SYMBOLS", {"XAUUSD": []}), \
             mock.patch.object(scanner, "ALERT_SETUPS", {"H2", "L2", "PIN"}):
            sc = scanner.Scanner(send, send_fol)
            sc.scan_once()
            self.assertEqual((alerts, fol), ([], []))
            while feed["n"] < len(c):
                feed["n"] += 1
                sc.scan_once()
        self.assertTrue(fol)
        self.assertTrue(alerts)
        self.assertTrue(all(p and p[:4] == b"\x89PNG" for p in photos))       # هر هشدار یک عکس دارد
        self.assertTrue(all(s == "XAUUSD" and "M5 cycle" in t for s, t in fol))
        self.assertFalse(any("M5 cycle" in t for t in alerts))
        # موتور زنده با موتوری که کل داده را یک‌جا خوانده یکی است
        e = CycleEngine()
        e.feed(c)
        self.assertEqual([(x["state"], x["side"], x["start"]) for x in e.segments],
                         [(x["state"], x["side"], x["start"]) for x in sc.engine("XAUUSD").segments])


class TestFollowStorage(unittest.TestCase):
    def test_follow_persists_and_keyboard_marks_it(self):
        path = os.path.join(tempfile.mkdtemp(), "state.json")
        st = JsonState(path)
        st.add_user(1)
        st.set_follow(1, "XAUUSD", True)
        st.set_follow(2, "EURUSD", True)
        st.set_follow(2, "EURUSD", False)
        st2 = JsonState(path)
        self.assertEqual(followers(st2, "XAUUSD"), [1])
        self.assertEqual(followers(st2, "EURUSD"), [])
        self.assertTrue(is_following(st2, 1, "XAUUSD"))

        tg = Telegram(None, st2)
        names = [b.text for row in tg.pairs_keyboard(1).keyboard for b in row]
        self.assertIn("⭐ 🥇🇺🇸 XAUUSD", names)
        btns = [b.callback_data for row in tg.pair_keyboard(1, "XAUUSD").keyboard for b in row]
        self.assertEqual(btns, ["uf:XAUUSD", "st:XAUUSD", "home"])
        btns = [b.callback_data for row in tg.pair_keyboard(1, "EURUSD").keyboard for b in row]
        self.assertEqual(btns[0], "fo:EURUSD")


class TestTelegramPhotos(unittest.TestCase):
    def _tg(self):
        st = JsonState(os.path.join(tempfile.mkdtemp(), "s.json"))
        for u in (1, 2, 3):
            st.add_user(u)
        tg = Telegram(None, st)
        tg.bot = mock.MagicMock()
        photo_msg = mock.MagicMock()
        photo_msg.photo = [mock.MagicMock(file_id="small"), mock.MagicMock(file_id="FILE123")]
        tg.bot.send_photo.return_value = photo_msg
        return tg

    def test_photo_uploaded_once_then_reused_as_caption(self):
        tg = self._tg()
        tg.broadcast("<b>H2</b> short alert", b"\x89PNGdata")
        calls = tg.bot.send_photo.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].args[1], b"\x89PNGdata")                   # اولی آپلود
        self.assertEqual([c.args[1] for c in calls[1:]], ["FILE123", "FILE123"])   # بقیه file_id
        self.assertEqual(calls[0].kwargs["caption"], "<b>H2</b> short alert")
        tg.bot.send_message.assert_not_called()

    def test_long_text_goes_after_photo(self):
        tg = self._tg()
        long = "<b>x</b>" + "y" * 1100
        self.assertFalse(caption_fits(long))
        self.assertTrue(caption_fits("<b>" + "y" * 1000 + "</b>"))
        tg.notify_followers("XAUUSD", long, b"png")       # کسی فالو نکرده
        tg.bot.send_photo.assert_not_called()
        tg.state.set_follow(2, "XAUUSD", True)
        tg.notify_followers("XAUUSD", long, b"png")
        self.assertNotIn("caption", tg.bot.send_photo.call_args.kwargs)
        tg.bot.send_message.assert_called_once_with(2, long, parse_mode="HTML")

    def test_alert_charts_mark_the_signal_bar(self):
        from bot.alert_chart import _m5_focus
        from bot.strategy import analyze, new_events
        from bot.alert_chart import m5_alert_chart
        c = candles(n=600, seed=1)
        res = analyze(c)
        evs = new_events("XAUUSD", res, c.index[-100])
        pin = [e for e in evs if e["kind"] == "PIN"][-1]
        f = _m5_focus("XAUUSD", pin)
        self.assertEqual((f["text"], f["time"]), ("PIN BAR", pin["time"]))
        self.assertEqual(m5_alert_chart("XAUUSD", res, pin)[:4], b"\x89PNG")


if __name__ == "__main__":
    unittest.main()
