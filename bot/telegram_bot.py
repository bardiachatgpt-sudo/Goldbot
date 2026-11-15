"""ربات تلگرام: ثبت کاربر، دستور /analyze (گزارش + نمودار) و ارسال هشدارها به کاربران و کانال."""
import time

import telebot
from telebot import types

from .chart import render_chart
from .config import ALERT_SETUPS, BARS, CHANNEL_ID, MIN_BARS, SYMBOLS, label, tf_label
from .data import get_closed_candles
from .messages import build_report
from .strategy import analyze


class Telegram:
    def __init__(self, token, state):
        self.state = state
        self.bot = telebot.TeleBot(token) if token else None
        if self.bot:
            self._register_handlers()

    def _targets(self):
        t = list(self.state.users)
        if CHANNEL_ID:
            t.append(CHANNEL_ID)
        return t

    def broadcast(self, text):
        if not self.bot:
            print(text)
            return
        for chat_id in self._targets():
            try:
                self.bot.send_message(chat_id, text, parse_mode="HTML")
            except Exception as e:
                print("telegram send error:", chat_id, e)

    def keyboard(self):
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(*[types.InlineKeyboardButton(f"📊 {label(n)}", callback_data="pa:" + n) for n in SYMBOLS])
        return kb

    def send_analysis(self, chat_id, sym):
        df = get_closed_candles(sym, BARS, MIN_BARS)
        if df is None:
            self.bot.send_message(chat_id, f"⚠️ {sym}: could not fetch candles, try again in a minute.")
            return
        res = analyze(df)
        text = build_report(sym, res)
        try:
            self.bot.send_photo(chat_id, render_chart(sym, res))
        except Exception as e:
            print("chart error:", e)
        self.bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=self.keyboard())

    def _register_handlers(self):
        bot = self.bot

        @bot.message_handler(commands=["start"])
        def on_start(m):
            self.state.add_user(m.chat.id)
            bot.send_message(m.chat.id,
                             f"✅ Registered. You will receive Al Brooks {tf_label()} alerts "
                             f"({', '.join(sorted(ALERT_SETUPS))}).\n"
                             "Tap a symbol or send /analyze for the current market structure:",
                             reply_markup=self.keyboard())

        @bot.message_handler(commands=["analyze", "pa"])
        def on_analyze(m):
            self.state.add_user(m.chat.id)
            parts = m.text.split()
            sym = parts[1].upper() if len(parts) > 1 else next(iter(SYMBOLS))
            if sym not in SYMBOLS:
                bot.send_message(m.chat.id, f"Unknown symbol. Available: {', '.join(SYMBOLS)}")
                return
            self.send_analysis(m.chat.id, sym)

        @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("pa:"))
        def on_button(c):
            sym = c.data.split(":", 1)[1]
            bot.answer_callback_query(c.id, "Analyzing…")
            if sym in SYMBOLS:
                self.send_analysis(c.message.chat.id, sym)

    def run(self):
        """حلقه‌ی اصلی (مسدودکننده)."""
        if not self.bot:
            while True:
                time.sleep(60)
        # نسخه‌ی قبلی این ربات webhook داشت؛ تا webhook فعال باشد polling کار نمی‌کند
        try:
            self.bot.remove_webhook()
        except Exception as e:
            print("remove_webhook error:", e)
        self.bot.infinity_polling(skip_pending=True)
