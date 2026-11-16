"""ربات تلگرام: فقط ساختار بازار.

جفت (طلا، ماژورها، داوجونز) ← تایم‌فریم ← دو عکس: آخرین ۵۰۰ کندل با ساختار، و بزرگ‌نمایی دو ساختار آخر.
"""
import time

import telebot
from telebot import types

from .config import MIN_BARS, STRUCTURE_BARS, STRUCTURE_SYMBOLS, TIMEFRAMES, label
from .data import get_closed_candles

VERSION = "structure only · gold + majors + Dow Jones · M1 to D1"
MENU_STRUCTURE = "📐 Structure"
HELP = ("📐 This bot only draws market structure (spike / channel / trading range) on the last "
        f"{STRUCTURE_BARS} candles, plus a zoom on the last two structures.\n"
        "Pick a pair, then a timeframe.\n\n"
        "/structure · /structure XAUUSD 5  (timeframes: " + ", ".join(
            f"{k}={v}" for k, v in TIMEFRAMES.items()) + ")")


class Telegram:
    def __init__(self, token):
        self.bot = telebot.TeleBot(token, parse_mode=None) if token else None
        if self.bot:
            self._register_handlers()

    # ------------------------------------------------------------ دکمه‌ها
    def menu(self):
        """دکمه‌ی ثابت پایین چت."""
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton(MENU_STRUCTURE))
        return kb

    def structure_pairs(self):
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(*[types.InlineKeyboardButton(label(n), callback_data="sxp:" + n) for n in STRUCTURE_SYMBOLS])
        return kb

    def structure_tf_keyboard(self, sym):
        kb = types.InlineKeyboardMarkup(row_width=4)
        kb.add(*[types.InlineKeyboardButton(f"⏱ {name}", callback_data=f"sxt:{sym}:{tf}")
                 for tf, name in TIMEFRAMES.items()])
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
            elif len(parts) > 2 and parts[2].upper() in TIMEFRAMES:          # /structure EURUSD 5
                self.send_structure(m.chat.id, sym, parts[2].upper())
            else:
                self.ask_structure_tf(m.chat.id, sym)

        @bot.message_handler(func=lambda m: True)
        def on_text(m):                                          # دکمه‌ی 📐 یا هر پیام دیگر
            self.ask_structure(m.chat.id)

        @bot.callback_query_handler(func=lambda c: bool(c.data))
        def on_button(c):
            chat_id = c.message.chat.id
            action, _, rest = c.data.partition(":")
            sym, _, tf = rest.partition(":")
            if action == "sxt" and sym in STRUCTURE_SYMBOLS and tf in TIMEFRAMES:
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
                                      types.BotCommand("structure", "📐 Market structure")])
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
