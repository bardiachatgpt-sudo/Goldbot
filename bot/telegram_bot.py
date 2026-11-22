"""ربات تلگرام: فقط ساختار بازار.

جفت (طلا، ماژورها، داوجونز) ← تایم‌فریم ← دو عکس: آخرین ۵۰۰ کندل با ساختار، و بزرگ‌نمایی دو ساختار آخر.
"""
import json
import os
import threading
import time

import telebot
from telebot import types

from .config import MIN_BARS, PERIODS, STRUCTURE_BARS, STRUCTURE_SYMBOLS, TIMEFRAMES, label
from .data import get_closed_candles

VERSION = "gap alerts only · gold 1-min and 5-min gaps · bitcoin on Saturday and Sunday"
MENU_STRUCTURE = "📐 Structure"
MENU_BACKTEST = "🧪 Gap backtest"
MENU_ALL = "🌍 All pairs"
MENU_ALERTS = "🔔 Gold gap alerts"
MENU_RUNNER = "🔥 Runner alerts"
RUNNER_FILE = "runner_subs.json"        # چت‌هایی که هشدار رانر را روشن کرده‌اند (با دیپلوی تازه پاک می‌شود)
ALERT_FILE = "alert_subs.json"          # چت‌هایی که هشدار گپ طلا را روشن کرده‌اند (با دیپلوی تازه پاک می‌شود)
ALERT_POLL = 15                         # ثانیه بین هر بار گرفتن کندل‌ها
HELP = ("🔔 Gap alerts only.\n"
        "Tap 🔔 Gold gap alerts to turn them on or off.\n"
        "• Gold: every 1-min gap (with the 5-min structure) and every 5-min gap.\n"
        "• Saturday and Sunday (Tehran time): Bitcoin 1-min and 5-min gaps too.")


class Telegram:
    LOSER_BATCH = 5                     # عکس باخت‌ها ۵تا ۵تا

    def __init__(self, token):
        self.losers = {}                # چت → آخرین بک‌تست M1: نماد، کندل‌ها، M5، باخت‌ها، بردها، رقم اعشار
        self.bot = telebot.TeleBot(token, parse_mode=None) if token else None
        self.alert_chats = self._load_alert_chats()
        self.runner_chats = self._load_alert_chats(RUNNER_FILE, "RUNNER_CHAT_IDS")
        self.m5trade = {}               # نماد → M5TradeWatch (برچسب «اولین هم‌جهت / اولین خلاف جهت» در هشدار ۱ دقیقه)
        if self.bot:
            self._register_handlers()

    # ------------------------------------------------------------ دکمه‌ها
    def menu(self):
        """دکمه‌ی ثابت پایین چت."""
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        kb.add(types.KeyboardButton(MENU_ALERTS))          # فقط هشدار گپ (کاربر، ۲۲ نوامبر: «هیچ چیز دیگری نباشد»)
        return kb

    # ------------------------------------------------------------ هشدار گپ طلا
    @staticmethod
    def _load_alert_chats(path=None, env="ALERT_CHAT_IDS"):
        chats = {int(x) for x in os.environ.get(env, "").replace(" ", "").split(",") if x}
        try:
            with open(path or ALERT_FILE) as f:
                chats |= {int(x) for x in json.load(f)}
        except Exception:
            pass
        return chats

    def _save_alert_chats(self, path=None, chats=None):
        try:
            with open(path or ALERT_FILE, "w") as f:
                json.dump(sorted(self.alert_chats if chats is None else chats), f)
        except Exception as e:
            print("alert file error:", e)

    def toggle_alerts(self, chat_id, on=None):
        on = (chat_id not in self.alert_chats) if on is None else on
        (self.alert_chats.add if on else self.alert_chats.discard)(chat_id)
        self._save_alert_chats()
        self.bot.send_message(chat_id, "🔔 Gold M1 gap alerts are ON: a picture with the M5 structure each time a gap "
                                       "forms (candle 3 closed; not in the Off session). Tap again to turn off." if on else
                              "🔕 Gold gap alerts are OFF.")

    def toggle_runner(self, chat_id, on=None):
        on = (chat_id not in self.runner_chats) if on is None else on
        (self.runner_chats.add if on else self.runner_chats.discard)(chat_id)
        self._save_alert_chats(RUNNER_FILE, self.runner_chats)
        self.bot.send_message(chat_id, "🔥 Runner alerts are ON: after a gold 5-min gap, the first 1-min gap the same "
                                       "way (before the 5-min entry triggers) sends a picture labelled 'Possible "
                                       "runner'. Tap again to turn off." if on else "🔕 Runner alerts are OFF.")

    def runner_tick(self, watcher, df):
        for _, ev in watcher.poll(df):
            try:
                png = watcher.picture(ev)
            except Exception as e:
                print("runner picture error:", e)
                png = None
            for chat in list(self.runner_chats):
                try:
                    if png:
                        self.bot.send_photo(chat, png, caption=watcher.caption(ev))
                    else:
                        self.bot.send_message(chat, watcher.caption(ev))
                except Exception as e:
                    print("runner send error:", chat, e)

    def m5gap_tick(self, alerter, df, chats=None):
        """گپ‌های ۵ دقیقه: عکس جدا (کندل‌های ۵ دقیقه، زمینه‌ی سفید شیری) به همان کسانی که رانر را روشن کرده‌اند
        (یا به chats اگر داده شود — بیت‌کوین آخر هفته به مشترکان 🔔)."""
        from .gap_alerts import m5_frame
        import pandas as pd
        for _, ev in alerter.poll(m5_frame(df)):
            # گپ ۵ دقیقه‌ی تازه (نه زنجیره): از حالا اولین گپ ۱ دقیقه‌ی هم‌جهت و اولین خلاف جهت برچسب می‌گیرند
            self._watch(alerter.sym).new_gap(ev, m5_frame(df))
            try:
                png = alerter.picture(ev)
            except Exception as e:
                print("5-min gap picture error:", e)
                continue
            for chat in list(self.runner_chats if chats is None else chats):
                try:
                    self.bot.send_photo(chat, png, caption=alerter.gap_caption(ev))
                except Exception as e:
                    print("5-min gap send error:", chat, e)

    def _watch(self, sym):
        from .gap_alerts import M5TradeWatch
        if sym not in self.m5trade:
            self.m5trade[sym] = M5TradeWatch(sym)
        return self.m5trade[sym]

    def _m5_hint(self, sym, ev):
        """برچسب اولین گپ خلاف جهت / هم‌جهت بعد از گپ ۵ دقیقه (قانون در gap_alerts.M5TradeWatch)."""
        h = self._watch(sym).hint(ev)
        if h:
            ev["m5_hint"] = h

    def alert_tick(self, alerter, df, m5_source=None):
        """یک بار: رویدادهای تازه را به همه‌ی چت‌های مشترک بفرست. عکس گپ همراه ساختار M5 همان لحظه."""
        try:
            self._watch(alerter.sym).update(df)          # ورود / پایان معامله‌ی ۵ دقیقه تا همین کندل
        except Exception as e:
            print("5-min trade watch error:", e)
        for kind, ev in alerter.poll(df):
            self._m5_hint(alerter.sym, ev)
            m5 = None
            try:
                m5 = m5_source() if m5_source else None
            except Exception as e:
                print("alert M5 error:", e)
            # برچسب «با روند / خلاف روند» حذف شد (کاربر، ۲۲ نوامبر)
            try:
                png = alerter.picture(ev, m5)
            except Exception as e:
                print("alert picture error:", e)
                png = alerter.picture(ev)
            for chat in list(self.alert_chats):
                try:
                    self.bot.send_photo(chat, png, caption=alerter.gap_caption(ev))
                except Exception as e:
                    print("alert send error:", chat, e)

    def btc_tick(self, btc1, btc5, now=None):
        """آخر هفته (شنبه و یکشنبه به وقت تهران): گپ‌های ۱ و ۵ دقیقه‌ی بیت‌کوین به مشترکان 🔔 (خواست کاربر، ۲۱ نوامبر)."""
        import pandas as pd

        from .config import is_weekend_tehran
        from .gap_alerts import live_candles, m5_candles
        now = now or pd.Timestamp.now(tz="UTC")
        if not self.alert_chats or not is_weekend_tehran(now):
            btc1.last_closed = btc5.last_closed = None    # بیرون آخر هفته: از نو شروع کن
            return
        df = live_candles("BTCUSD")
        self.alert_tick(btc1, df, lambda: m5_candles("BTCUSD"))
        self.m5gap_tick(btc5, df, chats=self.alert_chats)

    def alert_loop(self):
        """فقط هشدار گپ (کاربر، ۲۲ نوامبر): گپ‌های ۱ و ۵ دقیقه‌ی طلا، و شنبه/یکشنبه بیت‌کوین، به مشترکان 🔔."""
        from .gap_alerts import GapAlerter, M5GapAlerter, live_candles, m5_candles
        alerter, m5gaps = GapAlerter(), M5GapAlerter()
        btc1, btc5 = GapAlerter("BTCUSD", sessions=False), M5GapAlerter("BTCUSD", sessions=False)
        while True:
            try:
                self.btc_tick(btc1, btc5)
            except Exception as e:
                print("btc alert error:", e)
            try:
                if self.alert_chats:
                    df = live_candles()
                    self.alert_tick(alerter, df, m5_candles)
                    self.m5gap_tick(m5gaps, df, chats=self.alert_chats)
                else:
                    alerter.last_closed = m5gaps.last_closed = None   # کسی گوش نمی‌دهد: از همان لحظه‌ی روشن شدن
            except Exception as e:
                print("alert loop error:", e)
            time.sleep(ALERT_POLL)

    def structure_pairs(self):
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(*[types.InlineKeyboardButton(label(n), callback_data="sxp:" + n) for n in STRUCTURE_SYMBOLS])
        return kb

    def structure_tf_keyboard(self, sym):
        kb = types.InlineKeyboardMarkup(row_width=4)
        kb.add(*[types.InlineKeyboardButton(f"⏱ {name}", callback_data=f"sxt:{sym}:{tf}")
                 for tf, name in TIMEFRAMES.items()])
        kb.row(types.InlineKeyboardButton("🔬 M1 candles + M5 structure + gap setup", callback_data=f"sxm:{sym}"))
        kb.row(types.InlineKeyboardButton("🧪 Backtest the gap setup (M1 / M5 / M15)", callback_data=f"sxbp:{sym}"))
        return kb

    def ask_structure(self, chat_id):
        if len(STRUCTURE_SYMBOLS) == 1:
            self.ask_structure_tf(chat_id, STRUCTURE_SYMBOLS[0])
        else:
            self.bot.send_message(chat_id, "📐 Structure · which pair?", reply_markup=self.structure_pairs())

    def ask_structure_tf(self, chat_id, sym):
        self.bot.send_message(chat_id, f"📐 {label(sym)} · last {STRUCTURE_BARS} candles on which timeframe?",
                              reply_markup=self.structure_tf_keyboard(sym))

    # ------------------------------------------------------------ ساختار
    def send_structure(self, chat_id, sym, tf="5"):
        """دو عکس: آخرین STRUCTURE_BARS کندل با ساختار نسخه‌ی ۳، و بزرگ‌نمایی دو ساختار آخر."""
        from .structure3 import NAMES, render
        tf = tf if tf in TIMEFRAMES else "5"
        tf_name = TIMEFRAMES[tf]
        try:
            self.bot.send_chat_action(chat_id, "upload_photo")
        except Exception:
            pass
        df = get_closed_candles(sym, STRUCTURE_BARS + 1, MIN_BARS, tf)
        if df is None:
            self.bot.send_message(chat_id, f"⚠️ {sym} {tf_name}: could not fetch candles, try again in a minute.")
            return
        df = df.tail(STRUCTURE_BARS)
        png, phases, now = render(sym, df, tf=tf_name)
        icons = {"SPIKE": "🚀", "RANGE": "📦", ("CHANNEL", 1): "📈", ("CHANNEL", -1): "📉"}
        recent = " → ".join(f"{icons.get(p['type']) or icons[('CHANNEL', p['side'])]} "
                            f"{NAMES[(p['type'], p['side'])].title()}" for p in phases[-6:]) or "-"
        cap = (f"📐 <b>{label(sym)} · {tf_name} structure</b> · last {len(df)} candles\n"
               f"Now: <b>{now}</b>\n"
               f"Phases: {recent}\n"
               f"<i>Closes only (like a line chart). A range lasts until a breakout that doesn't come back; "
               f"anything that isn't a spike or a channel is a range.</i>")
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(types.InlineKeyboardButton("🔄 Refresh", callback_data=f"sxt:{sym}:{tf}"),
               types.InlineKeyboardButton("⏱ Timeframe", callback_data=f"sxp:{sym}"),
               types.InlineKeyboardButton("📐 Other pair", callback_data="sx"))
        self.bot.send_photo(chat_id, png, caption=cap, parse_mode="HTML")
        try:                                     # بزرگ‌نمایی دو ساختار آخر
            png2, _, _ = render(sym, df, tf=tf_name, zoom=2)
            self.bot.send_photo(chat_id, png2, caption=f"🔍 {label(sym)} · {tf_name} · zoom on the last two structures",
                                reply_markup=kb)
        except Exception as e:
            print("structure zoom error:", e)
            self.bot.send_message(chat_id, "📐", reply_markup=kb)

    def send_mtf(self, chat_id, sym):
        """یک عکس: کندل‌های M1 با ساختار M5 (جعبه‌های آبی) و ستاپ گپ M1 (گپ، ورود، حد ضرر، حد سود ۱:۱)."""
        from .mtf import MAX_M1, render
        from .structure3 import NAMES
        try:
            self.bot.send_chat_action(chat_id, "upload_photo")
        except Exception:
            pass
        m5 = get_closed_candles(sym, 2 * STRUCTURE_BARS + 1, MIN_BARS, "5")      # ۵۰۰ برای جعبه‌ها + قبلش برای فیلتر
        m1 = get_closed_candles(sym, MAX_M1 + 1, MIN_BARS, "1") if m5 is not None else None
        if m5 is None or m1 is None:
            self.bot.send_message(chat_id, f"⚠️ {sym}: could not fetch M1/M5 candles, try again in a minute.")
            return
        png, ph5, trades, now5, now1 = render(sym, m5.tail(STRUCTURE_BARS), m1, m5_full=m5)
        chain5 = " → ".join(NAMES[(p["type"], p["side"])].title() for p in ph5[-4:]) or "-"
        waiting = [t for t in trades if t.get("entry_i") is None]
        live = [t for t in trades if t.get("entry_i") is not None and t.get("exit_i") is None]
        state = ("🟢 trade open: " + ("SELL" if live[0]["side"] < 0 else "BUY") if live else
                 "⏳ gap found, waiting for entry: " + ("SELL" if waiting[0]["side"] < 0 else "BUY") if waiting else
                 "no gap waiting")
        cap = (f"🔬 <b>{label(sym)} · M1 candles · M5 structure · gap setup</b>\n"
               f"M5: <b>{now5}</b>\n"
               f"M5 phases: {chain5}\n"
               f"Gap setup on these M1 candles: <b>{now1}</b>\n"
               f"Now: {state}\n"
               f"<i>Gap = 3 same-colour candles, candle 1 and candle 3 do not overlap and candle 2's body covers part "
               f"of the space; no trade when the 1:1 target is outside the M5 box. "
               f"Sell: enter 1 pipette above the previous candle's high; stop just beyond candle 1; target 1:1 "
               f"(buy: the mirror).</i>")
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(types.InlineKeyboardButton("🔄 Refresh", callback_data=f"sxm:{sym}"),
               types.InlineKeyboardButton("⏱ Timeframe", callback_data=f"sxp:{sym}"),
               types.InlineKeyboardButton("📐 Other pair", callback_data="sx"))
        kb.row(types.InlineKeyboardButton("🧪 Backtest the gap setup (M1 / M5 / M15)", callback_data=f"sxbp:{sym}"))
        self.bot.send_photo(chat_id, png, caption=cap, parse_mode="HTML", reply_markup=kb)

    # ------------------------------------------------------------ بک‌تست گپ
    def backtest_pairs(self):
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(*[types.InlineKeyboardButton(label(n), callback_data="sxbp:" + n) for n in STRUCTURE_SYMBOLS])
        kb.row(types.InlineKeyboardButton("🌍 All pairs · M1 (with / without M5)", callback_data="sxa"))
        return kb

    @staticmethod
    def period_keyboard(prefix):
        """از آخرین شروع توکیو / لندن / نیویورک تا الان. callback: prefix + کد بازه."""
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(*[types.InlineKeyboardButton(name, callback_data=f"{prefix}{code}") for code, (name, *_) in PERIODS.items()])
        return kb

    def ask_all_pairs(self, chat_id):
        self.bot.send_message(chat_id, "🌍 All pairs · M1 gap setup · from when?", reply_markup=self.period_keyboard("sxap:"))

    def send_all_pairs(self, chat_id, code="T"):
        """ستاپ گپ روی M1 برای همه‌ی جفت‌ها، از آخرین شروع سشن (T/L/N) تا الان؛ با و بدون فیلتر M5."""
        import threading

        import pandas as pd
        code = code if code in PERIODS else "T"
        period = PERIODS[code][1]

        def work():
            from .config import last_session_start
            from .gap_backtest import all_pairs_text, period_fetch, run
            msg = self.bot.send_message(chat_id, f"⏳ Gap setup on all {len(STRUCTURE_SYMBOLS)} pairs · M1 · {period}…")
            n, last = period_fetch(code, "1", pd.Timestamp.now(tz="UTC"))
            rows = []
            for k, sym in enumerate(STRUCTURE_SYMBOLS, 1):
                try:
                    self.bot.edit_message_text(f"⏳ Gap setup on all pairs · M1 · {period}… {k}/{len(STRUCTURE_SYMBOLS)} "
                                               f"({sym})", chat_id, msg.message_id)
                except Exception:
                    pass
                try:
                    m1 = get_closed_candles(sym, min(n + 60, 5000) + 1, MIN_BARS, "1", timeout=60)
                    m5 = get_closed_candles(sym, min(n // 5 + 560, 5000), MIN_BARS, "5", timeout=60) \
                        if m1 is not None else None
                    if m1 is None:
                        rows.append((sym, None, None, "no data"))
                        continue
                    since = last_session_start(code, m1.index[-1])
                    kw = dict(days=None, compare=False, last_bars=last, since=since, period=period)
                    rf = run(sym, m1, "1", m5=m5, **kw)
                    rn = run(sym, m1, "1", m5=None, **kw)
                    rows.append((sym, rf, rn, None))
                except Exception as e:
                    print("all pairs error:", sym, e)
                    rows.append((sym, None, None, str(e)[:50]))
            try:
                self.bot.delete_message(chat_id, msg.message_id)
            except Exception:
                pass
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🔄 Run again", callback_data=f"sxap:{code}"),
                   types.InlineKeyboardButton("🕐 Other period", callback_data="sxa"),
                   types.InlineKeyboardButton("🧪 One pair in detail", callback_data="sxbp"))
            self.bot.send_message(chat_id, all_pairs_text(rows, period=period), parse_mode="HTML", reply_markup=kb)

        threading.Thread(target=work, daemon=True).start()

    def backtest_tf_keyboard(self, sym):
        from .gap_backtest import BT_TIMEFRAMES
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(*[types.InlineKeyboardButton(f"⏱ {name}", callback_data=f"sxb:{sym}:{tf}")
                 for tf, name in BT_TIMEFRAMES.items()])
        return kb

    def ask_backtest(self, chat_id, sym=None):
        """بک‌تست گپ: اول جفت (اگر داده نشده)، بعد تایم‌فریم."""
        if sym is None and len(STRUCTURE_SYMBOLS) > 1:
            self.bot.send_message(chat_id, "🧪 Gap backtest · which pair?", reply_markup=self.backtest_pairs())
            return
        sym = sym or STRUCTURE_SYMBOLS[0]
        self.bot.send_message(chat_id, f"🧪 Gap backtest · {label(sym)} · which timeframe?",
                              reply_markup=self.backtest_tf_keyboard(sym))

    def ask_period(self, chat_id, sym, tf):
        from .gap_backtest import BT_TIMEFRAMES
        self.bot.send_message(chat_id, f"🧪 Gap backtest · {label(sym)} · {BT_TIMEFRAMES.get(tf, tf)} · from when?",
                              reply_markup=self.period_keyboard(f"sxr:{sym}:{tf}:"))

    def send_gap_backtest(self, chat_id, sym, tf="1", code="T"):
        """ستاپ گپ روی M1، M5 یا M15، از آخرین شروع سشن (T/L/N) تا الان؛ گزارش + نمودار."""
        import pandas as pd

        from .config import last_session_start
        from .gap_backtest import BT_TIMEFRAMES, equity_chart, period_fetch, report_text, run
        from .mtf import fmt_price
        tf = tf if tf in BT_TIMEFRAMES else "1"
        code = code if code in PERIODS else "T"
        tfn, period = BT_TIMEFRAMES[tf], PERIODS[code][1]
        wait = self.bot.send_message(chat_id, f"⏳ Backtesting the gap setup on {label(sym)} {tfn} · {period}…")
        try:
            self.bot.send_chat_action(chat_id, "upload_photo")
        except Exception:
            pass
        n, last = period_fetch(code, tf, pd.Timestamp.now(tz="UTC"))
        extra = 560 if tf == "5" else 60                            # M5: ۵۰۰ کندل قبل برای ساختار
        df = get_closed_candles(sym, min(n + extra, 5000) + 1, MIN_BARS, tf, timeout=90)
        if df is None:
            self.bot.send_message(chat_id, f"⚠️ {sym} {tfn}: could not fetch candles, try again in a minute.")
            return
        m5 = df if tf == "5" else (get_closed_candles(sym, min(n // 5 + 560, 5000), MIN_BARS, "5", timeout=60)
                                   if tf == "1" else None)
        since = last_session_start(code, df.index[-1])
        res = run(sym, df, tf, days=None, m5=m5, last_bars=last, since=since, period=period)   # فیلتر M5 برای M1 و M5
        dec = len(fmt_price(sym, 1.0).split(".")[1])
        text = report_text(res, dec)
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(types.InlineKeyboardButton("🔄 Run again", callback_data=f"sxr:{sym}:{tf}:{code}"),
               types.InlineKeyboardButton("🕐 Other period", callback_data=f"sxb:{sym}:{tf}"),
               types.InlineKeyboardButton("⏱ Other timeframe", callback_data=f"sxbp:{sym}"),
               types.InlineKeyboardButton("🧪 Other pair", callback_data="sxbp"))
        try:
            self.bot.delete_message(chat_id, wait.message_id)
        except Exception:
            pass
        try:
            self.bot.send_photo(chat_id, equity_chart(res))
        except Exception as e:
            print("gap backtest chart error:", e)
        self.bot.send_message(chat_id, text, parse_mode="HTML")
        from .gap_backtest import losers_text
        for part in losers_text(res, dec):              # فهرست کامل باخت‌ها با شماره‌ی عکس
            self.bot.send_message(chat_id, part, parse_mode="HTML")
        if tf == "1":
            self.send_losing_trades(chat_id, sym, res, m5, dec)
            if any(t["r"] > 0 for t in res["closed"]):
                kb.row(types.InlineKeyboardButton("🏆 Winning trades: list + pictures", callback_data="sxwl"))
        self.bot.send_message(chat_id, "🧪 More?", reply_markup=kb)

    def send_losing_trades(self, chat_id, sym, res, m5, dec=2):
        """معامله‌هایی که حد ضرر خوردند: اول ۵ عکس، بقیه با دکمه‌ی «۵تای بعدی». بردها هم برای دکمه‌ی 🏆 نگه داشته می‌شوند."""
        losers = [t for t in res["closed"] if t["r"] < 0]
        self.losers[chat_id] = {"sym": sym, "candles": res["candles"], "m5": m5, "loss": losers,
                                "win": [t for t in res["closed"] if t["r"] > 0], "res": res, "dec": dec}
        if not losers:
            return
        self.bot.send_message(chat_id, f"🛑 {len(losers)} stopped-out trades. Zoomed pictures with the M5 structure at "
                                       f"the moment of entry, {self.LOSER_BATCH} at a time:")
        self.send_loser_batch(chat_id, 0)

    def send_winners(self, chat_id):
        """فهرست کامل بردها (با شماره و تاریخ) و ۵ عکس اول."""
        from .gap_backtest import trades_text
        saved = self.losers.get(chat_id)
        if saved is None:
            self.bot.send_message(chat_id, "⚠️ This backtest is no longer in memory (the bot restarted). "
                                           "Run the backtest again.")
            return
        if not saved["win"]:
            self.bot.send_message(chat_id, "No winning trades in this backtest.")
            return
        for part in trades_text(saved["res"], "win", saved["dec"]):
            self.bot.send_message(chat_id, part, parse_mode="HTML")
        self.send_loser_batch(chat_id, 0, kind="win")

    def send_loser_batch(self, chat_id, start, kind="loss"):
        """عکس معامله‌های start تا start+5 (kind: "loss" بازنده‌ها، "win" برنده‌ها) و دکمه‌ی ۵تای بعدی."""
        from .gap_pictures import caption, trade_picture
        saved = self.losers.get(chat_id)
        if saved is None:
            self.bot.send_message(chat_id, "⚠️ This backtest is no longer in memory (the bot restarted). "
                                           "Run the backtest again.")
            return
        sym, candles, m5, losers = saved["sym"], saved["candles"], saved["m5"], saved[kind]
        batch = losers[start:start + self.LOSER_BATCH]
        media = []
        for t in batch:
            try:
                png = trade_picture(sym, candles, m5, t, t["num"])
                media.append(types.InputMediaPhoto(png, caption=caption(sym, t, t["num"])))
            except Exception as e:
                print("trade picture error:", t.get("num"), e)
        for attempt in range(3):
            try:
                if media:
                    self.bot.send_media_group(chat_id, media)
                break
            except Exception as e:                     # محدودیت تعداد پیام تلگرام (429): صبر و دوباره
                info = getattr(e, "result_json", None)
                params = info.get("parameters", {}) if isinstance(info, dict) else {}
                print("trade pictures album error:", e)
                time.sleep(min(int(params.get("retry_after", 5)) + 1, 60))
        nxt = start + len(batch)
        what, icon, cb = (("stopped-out", "🛑", "sxl") if kind == "loss" else ("winning", "🏆", "sxw"))
        if nxt < len(losers):
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton(f"📷 Next {min(self.LOSER_BATCH, len(losers) - nxt)} {what} "
                                              f"trades ({nxt} of {len(losers)} shown)", callback_data=f"{cb}:{nxt}"))
            self.bot.send_message(chat_id, f"{icon} {nxt} of {len(losers)} {what} trades shown.", reply_markup=kb)
        else:
            self.bot.send_message(chat_id, f"✅ All {len(losers)} {what} trades shown.")


    # ------------------------------------------------------------ دستورها
    def _register_handlers(self):
        """فقط هشدار گپ؛ ساختار، بک‌تست، همه‌ی جفت‌ها و رانر از ربات برداشته شدند (کاربر، ۲۲ نوامبر).
        کدشان در فایل‌ها مانده ولی هیچ دکمه یا دستوری به آن‌ها نمی‌رسد."""
        bot = self.bot

        @bot.message_handler(commands=["start", "help"])
        def on_start(m):
            bot.send_message(m.chat.id, f"{HELP}\n\n🆕 Version: {VERSION}", reply_markup=self.menu())

        @bot.message_handler(commands=["alerts"])
        def on_alerts(m):                                        # /alerts · /alerts on · /alerts off
            parts = m.text.split()
            self.toggle_alerts(m.chat.id, None if len(parts) < 2 else parts[1].lower() == "on")

        @bot.message_handler(func=lambda m: True)
        def on_text(m):                                          # دکمه‌ی پایین چت یا هر پیام دیگر
            if (m.text or "").strip() == MENU_ALERTS:
                self.toggle_alerts(m.chat.id)
                return
            bot.send_message(m.chat.id, HELP, reply_markup=self.menu())

        @bot.callback_query_handler(func=lambda c: bool(c.data))
        def on_button(c):                                        # دکمه‌های پیام‌های قدیمی: دیگر کاری نمی‌کنند
            bot.answer_callback_query(c.id, "This feature was removed. Only gap alerts now.")

    def run(self):
        """حلقه‌ی اصلی (مسدودکننده)."""
        if not self.bot:
            while True:
                time.sleep(60)
        try:
            self.bot.remove_webhook()
        except Exception as e:
            print("remove_webhook error:", e)
        try:                                     # منوی دستورها در تلگرام
            self.bot.set_my_commands([types.BotCommand("start", "Menu"),
                                      types.BotCommand("alerts", "🔔 Gap alerts on/off")])
        except Exception as e:
            print("set_my_commands error:", e)
        threading.Thread(target=self.alert_loop, daemon=True).start()     # هشدار زنده‌ی گپ طلا
        # هر خطایی (مثلاً 409 وقتی نسخه‌ی قبلی هنگام دیپلوی هنوز در حال polling است) نباید برنامه را ببندد،
        # وگرنه Render دیپلوی را Failed می‌کند. صبر کن و دوباره وصل شو.
        skip = True
        while True:
            try:
                self.bot.infinity_polling(skip_pending=skip, timeout=20, long_polling_timeout=20)
            except Exception as e:
                print("telegram polling error, retrying in 10s:", e)
                time.sleep(10)
                skip = False
