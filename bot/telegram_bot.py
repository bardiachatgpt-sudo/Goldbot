"""ربات تلگرام.

- هر جفت‌ارز یک دکمه دارد: وضعیت چرخه‌ی M5 (رنج/اسپایک/کانال/تست) + گزارش + نمودار
- فالو کردن یک جفت: علاوه بر هشدارهای معمولی، هر تغییر چرخه‌ی آن جفت هم فرستاده می‌شود
- هشدارهای ستاپ و بریک‌اوت برای همه‌ی کاربران و کانال
"""
import time

import telebot
from telebot import types

from .backtest_ui import BacktestFlow
from .chart import render_chart
from .config import ALERT_SETUPS, BARS, CHANNEL_ID, MIN_BARS, SYMBOLS, label, tf_label
from .data import get_closed_candles
from .messages import build_report
from .storage import followers, is_following
from .strategy import analyze

HELP = ("Tap a pair to see its Al Brooks market cycle on M5 (range / spike / channel / under test) "
        "with levels and chart.\n"
        "⭐ Follow a pair to also get every cycle change for it.\n"
        "📐 Structure: the last 500 M5 candles with only the structure (spike / channel / range).\n"
        "🧪 Backtest: the range rules on M5 (buy the bottom / sell the top) over recent days "
        "on a $1,000 account.\n\n"
        "/status XAUUSD · /structure XAUUSD · /follow XAUUSD · /unfollow XAUUSD · /following · /backtest")
BACKTEST_MAX_DAYS = 10
VERSION = "16 Nov · gold only · structure v3 (2 pictures) · range backtest"
MENU_STATUS, MENU_STRUCTURE, MENU_BACKTEST = "🥇 Gold", "📐 Structure", "🧪 Backtest"
STRUCTURE_BARS = 500


CAPTION_LIMIT = 1024


def caption_fits(text):
    """تلگرام کپشن عکس را به ۱۰۲۴ کاراکتر (بدون تگ‌های HTML) محدود می‌کند."""
    import re
    plain = re.sub(r"<[^>]+>", "", text).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return len(plain) <= CAPTION_LIMIT


class Telegram:
    def __init__(self, token, state, scanner=None):
        self.state = state
        self.scanner = scanner
        self.bot = telebot.TeleBot(token) if token else None
        self.backtests = BacktestFlow(self)
        if self.bot:
            self._register_handlers()

    # ------------------------------------------------------------ ارسال
    def _send(self, chat_id, text, photo=None):
        """متن، یا عکس + متن. عکس فقط یک بار آپلود می‌شود و برای بقیه از file_id استفاده می‌شود.
        برمی‌گرداند: file_id عکس (برای گیرنده‌ی بعدی) یا همان photo."""
        try:
            if photo is None:
                self.bot.send_message(chat_id, text, parse_mode="HTML")
                return None
            if caption_fits(text):
                msg = self.bot.send_photo(chat_id, photo, caption=text, parse_mode="HTML")
            else:
                msg = self.bot.send_photo(chat_id, photo)
                self.bot.send_message(chat_id, text, parse_mode="HTML")
            return msg.photo[-1].file_id if getattr(msg, "photo", None) else photo
        except Exception as e:
            print("telegram send error:", chat_id, e)
            return photo

    def _send_all(self, targets, text, photo=None):
        for chat_id in targets:
            photo = self._send(chat_id, text, photo)

    def broadcast(self, text, photo=None):
        """هشدارهای ستاپ و بریک‌اوت: همه‌ی کاربران + کانال."""
        if not self.bot:
            print(text + ("\n[+ chart]" if photo else ""))
            return
        self._send_all(list(self.state.users) + ([CHANNEL_ID] if CHANNEL_ID else []), text, photo)

    def notify_followers(self, sym, text, photo=None):
        """تغییرات چرخه: فقط کسانی که این نماد را فالو کرده‌اند."""
        if not self.bot:
            print(f"[followers of {sym}]\n{text}" + ("\n[+ chart]" if photo else ""))
            return
        self._send_all(followers(self.state, sym), text, photo)

    # ------------------------------------------------------------ دکمه‌ها
    def pairs_keyboard(self, chat_id):
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(*[types.InlineKeyboardButton(("⭐ " if is_following(self.state, chat_id, n) else "") + label(n),
                                            callback_data="st:" + n) for n in SYMBOLS])
        kb.row(types.InlineKeyboardButton("📐 Structure", callback_data="sx"),
               types.InlineKeyboardButton("🧪 Backtest", callback_data="bt"))
        return kb

    def pair_keyboard(self, chat_id, sym):
        kb = types.InlineKeyboardMarkup(row_width=3)
        if is_following(self.state, chat_id, sym):
            follow = types.InlineKeyboardButton("🔕 Unfollow", callback_data="uf:" + sym)
        else:
            follow = types.InlineKeyboardButton("⭐ Follow", callback_data="fo:" + sym)
        kb.add(follow, types.InlineKeyboardButton("🔄 Refresh", callback_data="st:" + sym),
               types.InlineKeyboardButton("📋 All pairs", callback_data="home"))
        kb.row(types.InlineKeyboardButton("📐 Structure", callback_data="sxp:" + sym))
        return kb

    def menu(self):
        """دکمه‌های ثابت پایین چت."""
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
        kb.add(types.KeyboardButton(MENU_STATUS), types.KeyboardButton(MENU_STRUCTURE),
               types.KeyboardButton(MENU_BACKTEST))
        return kb

    def ask_structure(self, chat_id):
        """فقط یک جفت (طلا): مستقیم عکس‌ها؛ وگرنه انتخاب جفت."""
        if len(SYMBOLS) == 1:
            self.send_structure(chat_id, next(iter(SYMBOLS)))
        else:
            self.bot.send_message(chat_id, "📐 Structure · which pair?", reply_markup=self.structure_pairs())

    # ------------------------------------------------------------ ساختار (فقط نمایش)
    def structure_pairs(self):
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(*[types.InlineKeyboardButton(label(n), callback_data="sxp:" + n) for n in SYMBOLS])
        return kb

    def send_structure(self, chat_id, sym):
        """یک عکس: آخرین STRUCTURE_BARS کندل M5 با ساختار نسخه‌ی ۳ (اسپایک / کانال / رنج، روی بسته‌شدن‌ها)."""
        from .structure3 import NAMES, render
        try:
            self.bot.send_chat_action(chat_id, "upload_photo")
        except Exception:
            pass
        df = get_closed_candles(sym, STRUCTURE_BARS + 1, MIN_BARS, "5")
        if df is None:
            self.bot.send_message(chat_id, f"⚠️ {sym}: could not fetch candles, try again in a minute.")
            return
        df = df.tail(STRUCTURE_BARS)
        png, phases, now = render(sym, df, tf="M5")
        icons = {"SPIKE": "🚀", "RANGE": "📦", ("CHANNEL", 1): "📈", ("CHANNEL", -1): "📉"}
        recent = " → ".join(f"{icons.get(p['type']) or icons[('CHANNEL', p['side'])]} {NAMES[(p['type'], p['side'])].title()}"
                            for p in phases[-6:]) or "-"
        cap = (f"📐 <b>{label(sym)} · M5 structure</b> · last {len(df)} candles\n"
               f"Now: <b>{now}</b>\n"
               f"Phases: {recent}\n"
               f"<i>Closes only (like a line chart). A range lasts until a breakout that doesn't come back; "
               f"anything that isn't a spike or a channel is a range.</i>")
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="sxp:" + sym),
               types.InlineKeyboardButton("📐 Other pair", callback_data="sx"))
        kb.row(types.InlineKeyboardButton("🧪 Backtest range rules · last 5 days",   # پین‌بار در لبه‌ی رنج
                                          callback_data=f"btd:{sym}:5r:5"))
        self.bot.send_photo(chat_id, png, caption=cap, parse_mode="HTML")
        try:                                     # بزرگ‌نمایی دو ساختار آخر
            png2, _, _ = render(sym, df, tf="M5", zoom=2)
            self.bot.send_photo(chat_id, png2, caption=f"🔍 {label(sym)} · M5 · zoom on the last two structures",
                                reply_markup=kb)
        except Exception as e:
            print("structure zoom error:", e)
            self.bot.send_message(chat_id, "📐", reply_markup=kb)

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
            pairs = "gold" if list(SYMBOLS) == ["XAUUSD"] else "all pairs"
            bot.send_message(m.chat.id,
                             f"✅ Registered. You will receive Al Brooks {tf_label()} alerts for {pairs} "
                             f"({', '.join(sorted(ALERT_SETUPS))}).\n\n{HELP}\n\n🆕 Version: {VERSION}",
                             reply_markup=self.menu())
            bot.send_message(m.chat.id, "👇", reply_markup=self.pairs_keyboard(m.chat.id))

        @bot.message_handler(func=lambda m: (m.text or "").strip() in (MENU_STATUS, MENU_STRUCTURE, MENU_BACKTEST))
        def on_menu(m):
            self.state.add_user(m.chat.id)
            txt = m.text.strip()
            if txt == MENU_STRUCTURE:
                self.ask_structure(m.chat.id)
            elif txt == MENU_BACKTEST:
                self.backtests.start(m.chat.id)
            else:
                self.send_status(m.chat.id, next(iter(SYMBOLS)))

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

        @bot.message_handler(commands=["backtest", "bt"])
        def on_backtest(m):
            self.state.add_user(m.chat.id)
            parts = m.text.split()[1:]
            if not parts:                                   # مرحله‌به‌مرحله با دکمه
                self.backtests.start(m.chat.id)
                return
            sym, days = "XAUUSD", 5                          # میان‌بر: /backtest XAUUSD 5
            for a in parts:
                if a.isdigit():
                    days = max(1, min(int(a), BACKTEST_MAX_DAYS))
                elif a.upper() in SYMBOLS:
                    sym = a.upper()
                else:
                    bot.send_message(m.chat.id, f"Usage: /backtest  (step by step)  or  /backtest XAUUSD 5\n"
                                                f"Pairs: {', '.join(SYMBOLS)} · days 1–{BACKTEST_MAX_DAYS}")
                    return
            self.backtests.run(m.chat.id, sym, "5r", days)

        @bot.message_handler(commands=["structure", "sx"])
        def on_structure(m):
            sym = pick(m)
            if sym is False:
                return
            if sym is None:
                self.ask_structure(m.chat.id)
                return
            self.send_structure(m.chat.id, sym)

        @bot.message_handler(commands=["following"])
        def on_following(m):
            bot.send_message(m.chat.id, self.following_text(m.chat.id),
                             reply_markup=self.pairs_keyboard(m.chat.id))

        @bot.callback_query_handler(func=lambda c: bool(c.data))
        def on_button(c):
            chat_id = c.message.chat.id
            action, _, sym = c.data.partition(":")
            if action in ("bt", "btp", "btt", "btd"):          # بک‌تست مرحله‌به‌مرحله
                self.backtests.on_callback(c)
                return
            if action == "sx":                                  # ساختار: انتخاب جفت (یا مستقیم طلا)
                bot.answer_callback_query(c.id)
                self.ask_structure(chat_id)
                return
            if action in ("sxp", "sxt"):                        # ساختار M5 (sxt: دکمه‌های قدیمی)
                sym = sym.partition(":")[0]
                if sym in SYMBOLS:
                    bot.answer_callback_query(c.id, f"Drawing {sym} M5…")
                    self.send_structure(chat_id, sym)
                else:
                    bot.answer_callback_query(c.id)
                return
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
        try:                                     # منوی دستورها در تلگرام
            self.bot.set_my_commands([
                types.BotCommand("start", "Menu and buttons"),
                types.BotCommand("structure", "📐 Gold M5 structure"),
                types.BotCommand("backtest", "🧪 Backtest"),
                types.BotCommand("status", "🥇 Gold status")])
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
                skip = False                     # پیام‌هایی که در این فاصله آمده‌اند از دست نروند
