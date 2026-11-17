"""ربات تلگرام: فقط ساختار بازار.

جفت (طلا، ماژورها، داوجونز) ← تایم‌فریم ← دو عکس: آخرین ۵۰۰ کندل با ساختار، و بزرگ‌نمایی دو ساختار آخر.
"""
import time

import telebot
from telebot import types

from .config import MIN_BARS, PERIODS, STRUCTURE_BARS, STRUCTURE_SYMBOLS, TIMEFRAMES, label
from .data import get_closed_candles

VERSION = "structure · gold + majors + Dow Jones · M1 to D1 · M1 + M5 with the gap setup · gap backtest M1/M5/M15"
MENU_STRUCTURE = "📐 Structure"
MENU_BACKTEST = "🧪 Gap backtest"
MENU_ALL = "🌍 All pairs"
HELP = ("📐 This bot only draws market structure (spike / channel / trading range) on the last "
        f"{STRUCTURE_BARS} candles, plus a zoom on the last two structures.\n"
        "Pick a pair, then a timeframe.\n\n"
        "🔬 M1 + M5: M1 candles; each M5 structure is a light-blue box (range flat, channel slanted) with its "
        "top and bottom price, and the M1 gap setup on it (gap, entry, stop, 1:1 target, result).\n\n"
        "🧪 Gap backtest: pick a pair and M1, M5 or M15; the gap setup runs on all available candles.\n\n"
        "/structure · /structure XAUUSD 5  (timeframes: " + ", ".join(
            f"{k}={v}" for k, v in TIMEFRAMES.items()) + ") · /structure XAUUSD mtf")


class Telegram:
    LOSER_BATCH = 5                     # عکس باخت‌ها ۵تا ۵تا

    def __init__(self, token):
        self.losers = {}                # چت → آخرین بک‌تست M1: نماد، کندل‌ها، M5، باخت‌ها، بردها، رقم اعشار
        self.bot = telebot.TeleBot(token, parse_mode=None) if token else None
        if self.bot:
            self._register_handlers()

    # ------------------------------------------------------------ دکمه‌ها
    def menu(self):
        """دکمه‌ی ثابت پایین چت."""
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
        kb.add(types.KeyboardButton(MENU_STRUCTURE), types.KeyboardButton(MENU_BACKTEST),
               types.KeyboardButton(MENU_ALL))
        return kb

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
        bot = self.bot

        @bot.message_handler(commands=["start", "help"])
        def on_start(m):
            bot.send_message(m.chat.id, f"{HELP}\n\n🆕 Version: {VERSION}", reply_markup=self.menu())
            self.ask_structure(m.chat.id)

        @bot.message_handler(commands=["structure", "sx"])
        def on_structure(m):
            parts = m.text.split()
            sym = parts[1].upper() if len(parts) > 1 else None
            if sym is None:
                self.ask_structure(m.chat.id)
            elif sym not in STRUCTURE_SYMBOLS:
                bot.send_message(m.chat.id, f"Unknown pair. Available: {', '.join(STRUCTURE_SYMBOLS)}")
            elif len(parts) > 2 and parts[2].lower() in ("mtf", "1+5", "m1m5"):  # /structure XAUUSD mtf
                self.send_mtf(m.chat.id, sym)
            elif len(parts) > 2 and parts[2].upper() in TIMEFRAMES:          # /structure EURUSD 5
                self.send_structure(m.chat.id, sym, parts[2].upper())
            else:
                self.ask_structure_tf(m.chat.id, sym)

        @bot.message_handler(commands=["backtest", "bt"])
        def on_backtest(m):
            from .gap_backtest import BT_TIMEFRAMES
            parts = m.text.split()
            sym = parts[1].upper() if len(parts) > 1 else None
            if sym is not None and sym not in STRUCTURE_SYMBOLS:
                bot.send_message(m.chat.id, f"Unknown pair. Available: {', '.join(STRUCTURE_SYMBOLS)}")
            elif sym and len(parts) > 3 and parts[2] in BT_TIMEFRAMES and parts[3].upper() in PERIODS:
                self.send_gap_backtest(m.chat.id, sym, parts[2], parts[3].upper())   # /backtest XAUUSD 1 L
            elif sym and len(parts) > 2 and parts[2] in BT_TIMEFRAMES:          # /backtest XAUUSD 5 → بازه؟
                self.ask_period(m.chat.id, sym, parts[2])
            else:
                self.ask_backtest(m.chat.id, sym)

        @bot.message_handler(func=lambda m: True)
        def on_text(m):                                          # دکمه‌های پایین چت یا هر پیام دیگر
            if (m.text or "").strip() == MENU_BACKTEST:
                self.ask_backtest(m.chat.id)
                return
            if (m.text or "").strip() == MENU_ALL:
                self.ask_all_pairs(m.chat.id)
                return
            self.ask_structure(m.chat.id)

        @bot.callback_query_handler(func=lambda c: bool(c.data))
        def on_button(c):
            chat_id = c.message.chat.id
            action, _, rest = c.data.partition(":")
            sym, _, tf = rest.partition(":")
            if action == "sxa":                                 # همه‌ی جفت‌ها: انتخاب بازه
                bot.answer_callback_query(c.id)
                self.ask_all_pairs(chat_id)
                return
            if action == "sxap":                                # همه‌ی جفت‌ها: اجرا
                bot.answer_callback_query(c.id, "Running all pairs…")
                self.send_all_pairs(chat_id, sym)
                return
            if action == "sxr" and sym in STRUCTURE_SYMBOLS:    # بک‌تست یک جفت: تایم‌فریم و بازه انتخاب شده
                tf, _, code = tf.partition(":")
                bot.answer_callback_query(c.id, f"Backtesting {sym}…")
                self.send_gap_backtest(chat_id, sym, tf, code)
                return
            if action == "sxwl":                                # فهرست بردها + ۵ عکس اول
                bot.answer_callback_query(c.id)
                self.send_winners(chat_id)
                return
            if action in ("sxl", "sxw"):                        # ۵ عکس باخت / برد بعدی
                bot.answer_callback_query(c.id)
                self.send_loser_batch(chat_id, int(sym) if sym.isdigit() else 0, "loss" if action == "sxl" else "win")
            elif action == "sxb" and sym in STRUCTURE_SYMBOLS and tf:   # تایم‌فریم انتخاب شد → از کی؟
                bot.answer_callback_query(c.id)
                self.ask_period(chat_id, sym, tf)
            elif action in ("sxb", "sxbp"):                     # انتخاب جفت / تایم‌فریم بک‌تست
                bot.answer_callback_query(c.id)
                self.ask_backtest(chat_id, sym if sym in STRUCTURE_SYMBOLS else None)
            elif action == "sxm" and sym in STRUCTURE_SYMBOLS:
                bot.answer_callback_query(c.id, f"Drawing {sym} M1 + M5…")
                self.send_mtf(chat_id, sym)
            elif action == "sxt" and sym in STRUCTURE_SYMBOLS and tf in TIMEFRAMES:
                bot.answer_callback_query(c.id, f"Drawing {sym} {TIMEFRAMES[tf]}…")
                self.send_structure(chat_id, sym, tf)
            elif action in ("sxp", "sxt") and sym in STRUCTURE_SYMBOLS:
                bot.answer_callback_query(c.id)
                self.ask_structure_tf(chat_id, sym)
            else:                                                # sx و دکمه‌های قدیمی (وضعیت، بک‌تست، فالو…)
                bot.answer_callback_query(c.id)
                self.ask_structure(chat_id)

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
                                      types.BotCommand("structure", "📐 Market structure"),
                                      types.BotCommand("backtest", "🧪 Gap setup backtest (M1 / M5 / M15)")])
        except Exception as e:
            print("set_my_commands error:", e)
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
