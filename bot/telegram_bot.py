"""ربات تلگرام: فقط ساختار بازار.

جفت (طلا، ماژورها، داوجونز) ← تایم‌فریم ← دو عکس: آخرین ۵۰۰ کندل با ساختار، و بزرگ‌نمایی دو ساختار آخر.
"""
import time

import telebot
from telebot import types

from .config import MIN_BARS, STRUCTURE_BARS, STRUCTURE_SYMBOLS, TIMEFRAMES, label
from .data import get_closed_candles

VERSION = "structure · gold + majors + Dow Jones · M1 to D1 · M1 + M5 with the gap setup · gap backtest M1/M5/M15"
MENU_STRUCTURE = "📐 Structure"
MENU_BACKTEST = "🧪 Gap backtest"
HELP = ("📐 This bot only draws market structure (spike / channel / trading range) on the last "
        f"{STRUCTURE_BARS} candles, plus a zoom on the last two structures.\n"
        "Pick a pair, then a timeframe.\n\n"
        "🔬 M1 + M5: M1 candles; each M5 structure is a light-blue box (range flat, channel slanted) with its "
        "top and bottom price, and the M1 gap setup on it (gap, entry, stop, 1:1 target, result).\n\n"
        "🧪 Gap backtest: pick a pair and M1, M5 or M15; the gap setup runs on all available candles.\n\n"
        "/structure · /structure XAUUSD 5  (timeframes: " + ", ".join(
            f"{k}={v}" for k, v in TIMEFRAMES.items()) + ") · /structure XAUUSD mtf")


class Telegram:
    def __init__(self, token):
        self.bot = telebot.TeleBot(token, parse_mode=None) if token else None
        if self.bot:
            self._register_handlers()

    # ------------------------------------------------------------ دکمه‌ها
    def menu(self):
        """دکمه‌ی ثابت پایین چت."""
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        kb.add(types.KeyboardButton(MENU_STRUCTURE), types.KeyboardButton(MENU_BACKTEST))
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
        m5 = get_closed_candles(sym, STRUCTURE_BARS + 1, MIN_BARS, "5")
        m1 = get_closed_candles(sym, MAX_M1 + 1, MIN_BARS, "1") if m5 is not None else None
        if m5 is None or m1 is None:
            self.bot.send_message(chat_id, f"⚠️ {sym}: could not fetch M1/M5 candles, try again in a minute.")
            return
        png, ph5, trades, now5, now1 = render(sym, m5.tail(STRUCTURE_BARS), m1)
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
               f"<i>Gap = candle 1 and candle 3 do not overlap and candle 2's body covers part of the space. "
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
        return kb

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

    def send_gap_backtest(self, chat_id, sym, tf="1"):
        """همه‌ی کندل‌هایی که TradingView می‌دهد (تا M1_BARS) روی M1، M5 یا M15 با قاعده‌ی گپ؛ گزارش + نمودار."""
        from .gap_backtest import BT_TIMEFRAMES, M1_BARS, equity_chart, report_text, run
        from .mtf import fmt_price
        tf = tf if tf in BT_TIMEFRAMES else "1"
        tfn = BT_TIMEFRAMES[tf]
        wait = self.bot.send_message(chat_id, f"⏳ Backtesting the gap setup on {label(sym)} {tfn} "
                                              f"(up to {M1_BARS} candles)…")
        try:
            self.bot.send_chat_action(chat_id, "upload_photo")
        except Exception:
            pass
        need = {"1": M1_BARS, "5": 1200, "15": 600}[tf]           # ۳ روز اخیر + کمی بیشتر
        df = get_closed_candles(sym, need + 1, MIN_BARS, tf, timeout=90)
        if df is None:
            self.bot.send_message(chat_id, f"⚠️ {sym} {tfn}: could not fetch candles, try again in a minute.")
            return
        res = run(sym, df, tf)
        m5 = get_closed_candles(sym, 1700, MIN_BARS, "5", timeout=60) if tf == "1" else None   # ساختار M5
        dec = len(fmt_price(sym, 1.0).split(".")[1])
        text = report_text(res, dec)
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(types.InlineKeyboardButton("🔄 Run again", callback_data=f"sxb:{sym}:{tf}"),
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
        if tf == "1":
            self.send_losing_trades(chat_id, sym, res, m5)
        self.bot.send_message(chat_id, "🧪 More?", reply_markup=kb)

    def send_losing_trades(self, chat_id, sym, res, m5):
        """عکس بزرگ‌نمایی‌شده‌ی هر معامله‌ای که حد ضرر خورد، با ساختار M5 همان لحظه، در آلبوم‌های ۱۰تایی."""
        from .gap_pictures import caption, trade_picture
        losers = [t for t in res["closed"] if t["r"] < 0]
        if not losers:
            return
        self.bot.send_message(chat_id, f"🛑 {len(losers)} stopped-out trades: a zoomed picture of each one, "
                                       f"with the M5 structure at the moment of entry (light-blue boxes).")
        media = []
        for t in losers:
            try:
                png = trade_picture(sym, res["candles"], m5, t, t["num"])
                media.append(types.InputMediaPhoto(png, caption=caption(sym, t, t["num"])))
            except Exception as e:
                print("loser picture error:", t.get("num"), e)
        for j in range(0, len(media), 10):
            for attempt in range(3):
                try:
                    self.bot.send_media_group(chat_id, media[j:j + 10])
                    break
                except Exception as e:                 # محدودیت تعداد پیام تلگرام (429): صبر و دوباره
                    info = getattr(e, "result_json", None)
                    params = info.get("parameters", {}) if isinstance(info, dict) else {}
                    print("losing trades album error:", e)
                    time.sleep(min(int(params.get("retry_after", 5)) + 1, 60))
            time.sleep(2)


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
            elif sym and len(parts) > 2 and parts[2] in BT_TIMEFRAMES:          # /backtest XAUUSD 5
                self.send_gap_backtest(m.chat.id, sym, parts[2])
            else:
                self.ask_backtest(m.chat.id, sym)

        @bot.message_handler(func=lambda m: True)
        def on_text(m):                                          # دکمه‌های پایین چت یا هر پیام دیگر
            if (m.text or "").strip() == MENU_BACKTEST:
                self.ask_backtest(m.chat.id)
                return
            self.ask_structure(m.chat.id)

        @bot.callback_query_handler(func=lambda c: bool(c.data))
        def on_button(c):
            chat_id = c.message.chat.id
            action, _, rest = c.data.partition(":")
            sym, _, tf = rest.partition(":")
            if action == "sxb" and sym in STRUCTURE_SYMBOLS and tf:
                bot.answer_callback_query(c.id, f"Backtesting {sym}…")
                self.send_gap_backtest(chat_id, sym, tf)
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
