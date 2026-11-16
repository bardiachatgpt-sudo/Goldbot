"""بک‌تست مرحله‌به‌مرحله در تلگرام.

۱) جفت‌ارز (پیشنهاد: طلا)  ←  ۲) تایم‌فریم زمینه → ماشه (پیشنهاد: M5 → M1، تنظیم ربات زنده)
←  ۳) بازه‌ی زمانی  ←  ⏳ پیام انتظار با مرحله و زمان سپری‌شده  ←  نتیجه + نمودار موجودی
"""
import threading
import time

from telebot import types

from . import backtest
from .config import SYMBOLS, label

RECOMMENDED_PAIR = "XAUUSD"
RECOMMENDED_DAYS = {"5r": 5}
STAGES = {
    "start": "Preparing…",
    "fetch_trig": "Downloading M5 candles from TradingView…",
    "fetch_ctx": "Downloading M5 candles from TradingView…",
    "replay": "Replaying every candle: range, entries, stops and targets…",
    "chart": "Drawing the account chart…",
}
BAR = ["▱▱▱▱", "▰▱▱▱", "▰▰▱▱", "▰▰▰▱", "▰▰▰▰"]
STAGE_STEP = {"start": 0, "fetch_trig": 1, "fetch_ctx": 2, "replay": 3, "chart": 4}


class BacktestFlow:
    def __init__(self, tg):
        self.tg = tg
        self.running = set()                      # چت‌هایی که بک‌تستشان در جریان است
        self.lock = threading.Lock()

    @property
    def bot(self):
        return self.tg.bot

    # ------------------------------------------------------------ مرحله‌ها
    def pairs_markup(self):
        kb = types.InlineKeyboardMarkup(row_width=3)
        rec = types.InlineKeyboardButton(f"{label(RECOMMENDED_PAIR)} · recommended",
                                         callback_data=f"btp:{RECOMMENDED_PAIR}")
        kb.row(rec)
        kb.add(*[types.InlineKeyboardButton(label(s), callback_data=f"btp:{s}")
                 for s in SYMBOLS if s != RECOMMENDED_PAIR])
        return kb

    def days_markup(self, sym, tf=backtest.RANGE_TF):
        kb = types.InlineKeyboardMarkup(row_width=2)
        rec = RECOMMENDED_DAYS.get(tf)
        kb.add(*[types.InlineKeyboardButton(f"{d} day{'s' if d > 1 else ''}" + (" ✅" if d == rec else ""),
                                            callback_data=f"btd:{sym}:{tf}:{d}")
                 for d in backtest.TF_PRESETS[tf][3]])
        if len(SYMBOLS) > 1:
            kb.add(types.InlineKeyboardButton("⬅️ Back", callback_data="bt"))
        return kb

    def _days_text(self, sym):
        return (f"🧪 <b>Backtest · {label(sym)}</b>\n"
                "📦 Range rules on M5: price reaches the bottom of the range → buy, the top → sell; "
                "stop ½ range, target the other edge.\n"
                "Over which period? Counted in recent trading days (weekends have no candles).")

    def start(self, chat_id, message_id=None):
        """فقط بک‌تست قاعده‌ی رنج. یک جفت (طلا): مستقیم انتخاب بازه."""
        if len(SYMBOLS) == 1:
            sym = next(iter(SYMBOLS))
            return self._show(chat_id, message_id, self._days_text(sym), self.days_markup(sym))
        text = "🧪 <b>Backtest</b> · range rules on M5\nWhich pair?"
        self._show(chat_id, message_id, text, self.pairs_markup())

    def on_callback(self, c):
        chat_id, mid = c.message.chat.id, c.message.message_id
        parts = c.data.split(":")
        action = parts[0]
        self.bot.answer_callback_query(c.id)
        if action == "bt":
            return self.start(chat_id, mid)
        sym = parts[1] if len(parts) > 1 else None
        if sym not in SYMBOLS:
            return
        if action in ("btp", "btt"):                         # دکمه‌های قدیمی هم به انتخاب بازه می‌روند
            return self._show(chat_id, mid, self._days_text(sym), self.days_markup(sym))
        if action == "btd" and len(parts) > 3 and parts[2] == backtest.RANGE_TF:
            days = int(parts[3])
            if days in backtest.TF_PRESETS[backtest.RANGE_TF][3]:
                self.run(chat_id, sym, backtest.RANGE_TF, days, mid)

    def _show(self, chat_id, message_id, text, markup):
        if message_id:
            try:
                self.bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=markup)
                return
            except Exception:
                pass
        self.bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

    # ------------------------------------------------------------ اجرا با پیام انتظار
    def run(self, chat_id, sym, tf, days, message_id=None):
        with self.lock:
            if chat_id in self.running:
                self.bot.send_message(chat_id, "⏳ A backtest is already running for you, please wait for it.")
                return
            self.running.add(chat_id)
        threading.Thread(target=self._run, args=(chat_id, sym, tf, days, message_id), daemon=True).start()

    def _waiting_text(self, sym, tf, days, stage, elapsed):
        name = backtest.TF_PRESETS[tf][2]
        step = STAGE_STEP.get(stage, 0)
        return (f"⏳ <b>Backtesting {label(sym)}</b>\n"
                f"{name} · last {days} trading day{'s' if days > 1 else ''} · $1,000 account\n\n"
                f"{BAR[step]}  {STAGES.get(stage, '')}\n"
                f"<i>{elapsed}s elapsed · usually under a minute</i>")

    def _run(self, chat_id, sym, tf, days, message_id):
        state = {"stage": "start", "done": False}
        t0 = time.time()
        bot = self.bot

        def show():
            txt = self._waiting_text(sym, tf, days, state["stage"], int(time.time() - t0))
            try:
                if state.get("mid"):
                    bot.edit_message_text(txt, chat_id, state["mid"], parse_mode="HTML")
                else:
                    raise ValueError
            except Exception:
                if not state.get("mid"):
                    state["mid"] = bot.send_message(chat_id, txt, parse_mode="HTML").message_id

        if message_id:
            state["mid"] = message_id
        show()

        def ticker():                              # هر چند ثانیه زمان سپری‌شده را به‌روز کن
            while not state["done"]:
                time.sleep(4)
                if not state["done"]:
                    show()
                    try:
                        bot.send_chat_action(chat_id, "typing")
                    except Exception:
                        pass

        threading.Thread(target=ticker, daemon=True).start()

        def progress(stage):
            state["stage"] = stage
            show()

        try:
            res, err = backtest.run_days(sym, days, tf=tf, progress=progress)
            png = None
            if res is not None:
                progress("chart")
                try:
                    png = backtest.equity_chart(res)
                except Exception as e:
                    print("backtest chart error:", e)
        except Exception as e:
            res, err, png = None, str(e)[:200], None
        finally:
            state["done"] = True
            with self.lock:
                self.running.discard(chat_id)

        secs = int(time.time() - t0)
        again = types.InlineKeyboardMarkup()
        again.add(types.InlineKeyboardButton("🧪 New backtest", callback_data="bt"))
        if res is None:
            bot.edit_message_text(f"⚠️ <b>Backtest failed</b> after {secs}s\n{err}", chat_id, state["mid"],
                                  parse_mode="HTML", reply_markup=again)
            return
        try:
            bot.edit_message_text(f"✅ <b>Backtest finished</b> in {secs}s · results below", chat_id,
                                  state["mid"], parse_mode="HTML")
        except Exception:
            pass
        self.tg._send(chat_id, backtest.report_text(res), png)
        bot.send_message(chat_id, "Run another one?", reply_markup=again)
