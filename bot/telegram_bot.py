"""ربات تلگرام.

- هر جفت‌ارز یک دکمه دارد: وضعیت چرخه‌ی M5 (رنج/اسپایک/کانال/تست) + گزارش + نمودار
- فالو کردن یک جفت: علاوه بر هشدارهای معمولی، هر تغییر چرخه‌ی آن جفت هم فرستاده می‌شود
- هشدارهای ستاپ و بریک‌اوت برای همه‌ی کاربران و کانال
"""
import time

import telebot
from telebot import types

from .chart import render_chart
from .config import ALERT_SETUPS, BARS, CHANNEL_ID, MIN_BARS, SYMBOLS, label, tf_label
from .data import get_closed_candles
from .messages import build_report
from .storage import followers, is_following
from .strategy import analyze

HELP = ("Tap a pair to see its Al Brooks market cycle on M5 (range / spike / channel / under test) "
        "with levels and chart.\n"
        "⭐ Follow a pair to also get every cycle change for it.\n\n"
        "/status XAUUSD · /follow XAUUSD · /unfollow XAUUSD · /following")


class Telegram:
    def __init__(self, token, state, scanner=None):
        self.state = state
        self.scanner = scanner
        self.bot = telebot.TeleBot(token) if token else None
        if self.bot:
            self._register_handlers()

    # ------------------------------------------------------------ ارسال
    def _send(self, chat_id, text):
        try:
            self.bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception as e:
            print("telegram send error:", chat_id, e)

    def broadcast(self, text):
        """هشدارهای ستاپ و بریک‌اوت: همه‌ی کاربران + کانال."""
        if not self.bot:
            print(text)
            return
        targets = list(self.state.users) + ([CHANNEL_ID] if CHANNEL_ID else [])
        for chat_id in targets:
            self._send(chat_id, text)

    def notify_followers(self, sym, text):
        """تغییرات چرخه: فقط کسانی که این نماد را فالو کرده‌اند."""
        if not self.bot:
            print(f"[followers of {sym}]\n{text}")
            return
        for chat_id in followers(self.state, sym):
            self._send(chat_id, text)

    # ------------------------------------------------------------ دکمه‌ها
    def pairs_keyboard(self, chat_id):
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(*[types.InlineKeyboardButton(("⭐ " if is_following(self.state, chat_id, n) else "") + label(n),
                                            callback_data="st:" + n) for n in SYMBOLS])
        return kb

    def pair_keyboard(self, chat_id, sym):
        kb = types.InlineKeyboardMarkup(row_width=3)
        if is_following(self.state, chat_id, sym):
            follow = types.InlineKeyboardButton("🔕 Unfollow", callback_data="uf:" + sym)
        else:
            follow = types.InlineKeyboardButton("⭐ Follow", callback_data="fo:" + sym)
        kb.add(follow, types.InlineKeyboardButton("🔄 Refresh", callback_data="st:" + sym),
               types.InlineKeyboardButton("📋 All pairs", callback_data="home"))
        return kb

    # ------------------------------------------------------------ وضعیت
    def send_status(self, chat_id, sym):
        df = get_closed_candles(sym, BARS, MIN_BARS)
        if df is None:
            self.bot.send_message(chat_id, f"⚠️ {sym}: could not fetch candles, try again in a minute.",
                                  reply_markup=self.pair_keyboard(chat_id, sym))
            return
        lock = self.scanner.lock if self.scanner else None
        if lock:
            lock.acquire()
        try:
            res = analyze(df, engine=self.scanner.engine(sym) if self.scanner else None)
            text = build_report(sym, res)
            try:
                png = render_chart(sym, res, n=160)
            except Exception as e:
                print("chart error:", e)
                png = None
        finally:
            if lock:
                lock.release()
        if png:
            try:
                self.bot.send_photo(chat_id, png)
            except Exception as e:
                print("photo error:", e)
        self.bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=self.pair_keyboard(chat_id, sym))

    def set_follow(self, chat_id, sym, on):
        self.state.add_user(chat_id)
        self.state.set_follow(chat_id, sym, on)

    def following_text(self, chat_id):
        syms = sorted(self.state.follows.get(chat_id, ()))
        if not syms:
            return "You are not following any pair yet. Tap a pair and press ⭐ Follow."
        return "⭐ Following: " + ", ".join(label(s) for s in syms)

    # ------------------------------------------------------------ دستورها
    def _register_handlers(self):
        bot = self.bot

        def pick(m):
            parts = m.text.split()
            sym = parts[1].upper() if len(parts) > 1 else None
            if sym and sym not in SYMBOLS:
                bot.send_message(m.chat.id, f"Unknown pair. Available: {', '.join(SYMBOLS)}")
                return False
            return sym

        @bot.message_handler(commands=["start", "help"])
        def on_start(m):
            self.state.add_user(m.chat.id)
            bot.send_message(m.chat.id,
                             f"✅ Registered. You will receive Al Brooks {tf_label()} alerts for all pairs "
                             f"({', '.join(sorted(ALERT_SETUPS))}).\n\n{HELP}",
                             reply_markup=self.pairs_keyboard(m.chat.id))

        @bot.message_handler(commands=["status", "analyze", "pa"])
        def on_status(m):
            self.state.add_user(m.chat.id)
            sym = pick(m)
            if sym is False:
                return
            if sym is None:
                bot.send_message(m.chat.id, "Choose a pair:", reply_markup=self.pairs_keyboard(m.chat.id))
                return
            self.send_status(m.chat.id, sym)

        @bot.message_handler(commands=["follow", "unfollow"])
        def on_follow(m):
            sym = pick(m)
            if not sym:
                if sym is None:
                    bot.send_message(m.chat.id, "Usage: /follow XAUUSD", reply_markup=self.pairs_keyboard(m.chat.id))
                return
            on = m.text.lstrip("/").lower().startswith("follow")
            self.set_follow(m.chat.id, sym, on)
            bot.send_message(m.chat.id, ("⭐ Following " if on else "🔕 Unfollowed ") + label(sym) + "\n"
                             + self.following_text(m.chat.id))

        @bot.message_handler(commands=["following"])
        def on_following(m):
            bot.send_message(m.chat.id, self.following_text(m.chat.id),
                             reply_markup=self.pairs_keyboard(m.chat.id))

        @bot.callback_query_handler(func=lambda c: bool(c.data))
        def on_button(c):
            chat_id = c.message.chat.id
            action, _, sym = c.data.partition(":")
            if action == "home":
                bot.answer_callback_query(c.id)
                bot.send_message(chat_id, self.following_text(chat_id), reply_markup=self.pairs_keyboard(chat_id))
                return
            if sym not in SYMBOLS:
                bot.answer_callback_query(c.id)
                return
            if action == "st":
                bot.answer_callback_query(c.id, f"Reading {sym}…")
                self.state.add_user(chat_id)
                self.send_status(chat_id, sym)
            elif action in ("fo", "uf"):
                on = action == "fo"
                self.set_follow(chat_id, sym, on)
                bot.answer_callback_query(c.id, ("⭐ Following " if on else "🔕 Unfollowed ") + sym)
                try:
                    bot.edit_message_reply_markup(chat_id, c.message.message_id,
                                                  reply_markup=self.pair_keyboard(chat_id, sym))
                except Exception as e:
                    print("edit markup error:", e)

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
