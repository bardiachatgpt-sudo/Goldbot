import os
import re
import json
import html
import time
import random
import string
import threading
from datetime import datetime
import pytz
import requests
import websocket
from flask import Flask, request
import telebot
import pandas as pd
import numpy as np

# ۱. وب‌سرور + درگاه Webhook مستقیم برای تریدینگ‌ویو شخصی شما
app = Flask(__name__)
last_source_name = "در حال اتصال به TradingView..."

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

STATE_FILE = "bot_state.json"
subscribed_users = set()
active_trade = None
stats = {"wins": 0, "losses": 0, "cancelled": 0}
last_pre_alert_time = None
last_signal_time = None

def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"users": list(subscribed_users), "stats": stats}, f)
    except Exception:
        pass

def load_state():
    global subscribed_users, stats
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                subscribed_users = set(data.get("users", []))
                stats = data.get("stats", {"wins": 0, "losses": 0, "cancelled": 0})
    except Exception:
        pass

load_state()

def broadcast(text):
    if not bot:
        return
    for chat_id in list(subscribed_users):
        try:
            bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception as e:
            print(f"Telegram send error: {e}")

@app.route('/')
def home():
    return f"TradingView Al Brooks M5 Gold Bot is LIVE! Source: {last_source_name}"

# درگاه Webhook: اگر از داخل اپلیکیشن تریدینگ‌ویو خودتان هم آلارم تنظیم کنید، اینجا دریافت و به تلگرام ارسال می‌شود
@app.route('/webhook', methods=['POST'])
def tv_webhook():
    try:
        data = request.get_data(as_text=True)
        broadcast(f"🔔 <b>آلارم مستقیم از اکانت TradingView شما:</b>\n\n<code>{html.escape(data)}</code>")
        return "OK", 200
    except Exception as e:
        return str(e), 400

def run_web():
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port)

# ۲. موتور اتصال مستقیم به وب‌سوکت زنده تریدینگ‌ویو (TradingView Live Feed)
def _tv_send(ws, func, params):
    payload = json.dumps({"m": func, "p": params}, separators=(",", ":"))
    frame = f"~m~{len(payload)}~m~{payload}"
    ws.send(frame)

def fetch_tradingview_candles(symbol="OANDA:XAUUSD", interval="5", n_bars=220):
    """
    دریافت مستقیم کندل‌های ۵ دقیقه طلا از سرور اصلی تریدینگ‌ویو
    """
    ws = None
    try:
        ws = websocket.create_connection(
            "wss://data.tradingview.com/socket.io/websocket?from=chart%2F",
            headers={
                "Origin": "https://www.tradingview.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            timeout=12
        )

        chart_session = "cs_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
        _tv_send(ws, "set_auth_token", ["unauthorized_user_token"])
        _tv_send(ws, "chart_create_session", [chart_session, ""])

        sym_json = json.dumps({"symbol": symbol, "adjustment": "splits"}, separators=(",", ":"))
        _tv_send(ws, "resolve_symbol", [chart_session, "sds_sym_1", f"={sym_json}"])
        _tv_send(ws, "create_series", [chart_session, "sds_1", "s1", "sds_sym_1", str(interval), n_bars, ""])

        bars = []
        start_t = time.time()
        while time.time() - start_t < 10:
            raw = ws.recv()
            if not raw:
                break

            # پاسخ به پینگ تریدینگ‌ویو
            if raw.startswith("~m~") and "~h~" in raw:
                ws.send(raw)
                continue

            parts = re.split(r"~m~\d+~m~", raw)
            for part in parts:
                if not part.strip():
                    continue
                try:
                    msg = json.loads(part)
                except Exception:
                    continue

                m_type = msg.get("m")
                if m_type in ("timescale_update", "du"):
                    p_data = msg.get("p", [])
                    if len(p_data) >= 2 and isinstance(p_data[1], dict):
                        sds = p_data[1].get("sds_1", {})
                        s_list = sds.get("s", [])
                        for item in s_list:
                            v = item.get("v", [])
                            if len(v) >= 5:
                                bars.append({
                                    "Time": int(v[0]),
                                    "Open": float(v[1]),
                                    "High": float(v[2]),
                                    "Low": float(v[3]),
                                    "Close": float(v[4])
                                })
                elif m_type == "series_completed":
                    break

            if len(bars) >= 50:
                break

        ws.close()

        if len(bars) < 50:
            return None, f"TradingView({symbol}) bars={len(bars)}"

        df = pd.DataFrame(bars)
        df["Time"] = pd.to_datetime(df["Time"], unit="s", utc=True)
        df.set_index("Time", inplace=True)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df, None

    except Exception as e:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        return None, f"TV({symbol}): {str(e)[:70]}"

def get_al_brooks_data():
    global last_source_name
    errors = []

    # لیست چارت‌های طلا در تریدینگ‌ویو به ترتیب اولویت
    tv_sources = [
        ("TradingView (OANDA:XAUUSD)", "OANDA:XAUUSD"),
        ("TradingView (FOREXCOM:XAUUSD)", "FOREXCOM:XAUUSD"),
        ("TradingView (FX_IDC:XAUUSD)", "FX_IDC:XAUUSD"),
        ("TradingView 24/7 Gold (BINANCE:PAXGUSDT)", "BINANCE:PAXGUSDT")
    ]

    df = None
    chosen_source = None

    for label, tv_sym in tv_sources:
        res_df, err = fetch_tradingview_candles(tv_sym, "5", 220)
        if res_df is not None and len(res_df) >= 50:
            df = res_df
            chosen_source = label
            break
        elif err:
            errors.append(err)

    if df is None:
        return None, None, " | ".join(errors)

    # محاسبه EMA 20 (تنها اندیکاتور ال بروکس)
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()

    # محاسبه ATR 14 برای سنجش اندازه استاندارد کندل‌های طلا
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    true_range = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1)
    df["ATR"] = true_range.rolling(14).mean()

    last_source_name = chosen_source
    return df, chosen_source, None

# ۳. رادار تشخیص «سیم خاردار» (Barb Wire) ال بروکس
def is_barb_wire(df_slice):
    last5 = df_slice.iloc[-5:]
    doji_count = 0
    ema_crosses = 0

    for _, row in last5.iterrows():
        rng = float(row["High"] - row["Low"])
        body = abs(float(row["Close"] - row["Open"]))
        ema = float(row["EMA20"])

        if rng > 0 and (body / rng) < 0.30:
            doji_count += 1
        if float(row["Low"]) <= ema <= float(row["High"]):
            ema_crosses += 1

    return ema_crosses >= 4 and doji_count >= 2

# ۴. تشخیص چرخه بازار ال بروکس: Always In Long / Short
def get_market_cycle(df_slice):
    if is_barb_wire(df_slice):
        return "BARB_WIRE"

    last15 = df_slice.iloc[-15:]
    above_ema = int((last15["Close"] > last15["EMA20"]).sum())
    below_ema = int((last15["Close"] < last15["EMA20"]).sum())

    ema_now = float(last15["EMA20"].iloc[-1])
    ema_prev = float(last15["EMA20"].iloc[-6])
    atr_now = float(last15["ATR"].iloc[-1])
    ema_slope = ema_now - ema_prev
    slope_thresh = max(atr_now * 0.25, 0.3)

    if above_ema >= 11 and ema_slope > slope_thresh:
        return "ALWAYS_IN_LONG"
    elif below_ema >= 11 and ema_slope < -slope_thresh:
        return "ALWAYS_IN_SHORT"
    else:
        return "TRADING_RANGE"

# ۵. شمارش لگ‌ها (H1/H2 و L1/L2) + بررسی کندل سیگنال
def analyze_al_brooks_setup(df_closed):
    if len(df_closed) < 20:
        return None

    cycle = get_market_cycle(df_closed)
    sb = df_closed.iloc[-1]
    prev1 = df_closed.iloc[-2]
    prev2 = df_closed.iloc[-3]
    prev3 = df_closed.iloc[-4]

    sb_high = float(sb["High"])
    sb_low = float(sb["Low"])
    sb_open = float(sb["Open"])
    sb_close = float(sb["Close"])
    sb_ema = float(sb["EMA20"])
    sb_atr = float(sb["ATR"])

    if pd.isna(sb_atr) or sb_atr <= 0:
        return None

    sb_range = sb_high - sb_low
    if sb_range < (sb_atr * 0.4) or sb_range > (sb_atr * 2.8):
        return None

    close_position = (sb_close - sb_low) / sb_range

    if cycle == "ALWAYS_IN_LONG":
        touched_ema = (sb_low <= sb_ema + (sb_atr * 0.25)) or (float(prev1["Low"]) <= float(prev1["EMA20"]) + (sb_atr * 0.2))
        is_pullback = (sb_low < float(prev2["Low"])) or (float(prev1["Low"]) < float(prev3["Low"]))
        valid_bull_sb = (sb_close > sb_ema) and (close_position >= 0.65) and (sb_close >= sb_open)

        if touched_ema and is_pullback and valid_bull_sb:
            leg_type = "H1 (اولین پولبک به EMA20)"
            if float(prev2["High"]) > float(prev3["High"]) and float(prev1["Low"]) < float(prev2["Low"]):
                leg_type = "H2 (ستاپ طلایی دو لِگه - High 2 Bull Flag) ⭐"

            entry_stop = sb_high + 0.20
            swing_low = min(sb_low, float(prev1["Low"])) - 0.20
            risk = max(entry_stop - swing_low, max(sb_atr * 1.2, 2.0))
            sl = entry_stop - risk
            tp = entry_stop + (risk * 2.0)

            return {
                "type": "BUY_STOP",
                "setup_name": leg_type,
                "signal_bar_high": sb_high,
                "signal_bar_low": sb_low,
                "entry": entry_stop,
                "sl": sl,
                "tp": tp,
                "risk": risk,
                "reward": risk * 2.0,
            }

    elif cycle == "ALWAYS_IN_SHORT":
        touched_ema = (sb_high >= sb_ema - (sb_atr * 0.25)) or (float(prev1["High"]) >= float(prev1["EMA20"]) - (sb_atr * 0.2))
        is_pullback = (sb_high > float(prev2["High"])) or (float(prev1["High"]) > float(prev3["High"]))
        valid_bear_sb = (sb_close < sb_ema) and (close_position <= 0.35) and (sb_close <= sb_open)

        if touched_ema and is_pullback and valid_bear_sb:
            leg_type = "L1 (اولین پولبک به EMA20)"
            if float(prev2["Low"]) < float(prev3["Low"]) and float(prev1["High"]) > float(prev2["High"]):
                leg_type = "L2 (ستاپ طلایی دو لِگه - Low 2 Bear Flag) ⭐"

            entry_stop = sb_low - 0.20
            swing_high = max(sb_high, float(prev1["High"])) + 0.20
            risk = max(swing_high - entry_stop, max(sb_atr * 1.2, 2.0))
            sl = entry_stop + risk
            tp = entry_stop - (risk * 2.0)

            return {
                "type": "SELL_STOP",
                "setup_name": leg_type,
                "signal_bar_high": sb_high,
                "signal_bar_low": sb_low,
                "entry": entry_stop,
                "sl": sl,
                "tp": tp,
                "risk": risk,
                "reward": risk * 2.0,
            }

    return None

# ۶. حلقه اصلی اسکنر ۲۴ ساعته تریدینگ‌ویو
def al_brooks_scanner():
    global active_trade, last_pre_alert_time, last_signal_time, stats

    while True:
        try:
            if not subscribed_users:
                time.sleep(10)
                continue

            now_utc = datetime.now(pytz.utc)
            df, src_name, err = get_al_brooks_data()
            if df is None:
                time.sleep(20)
                continue

            # در تریدینگ‌ویو، ردیف آخر کندل در حال حرکت (زنده) و ردیف ماقبل آخر، آخرین کندل بسته شده است
            live_bar = df.iloc[-1]
            closed_df = df.iloc[:-1]
            live_time = df.index[-1]
            closed_time = closed_df.index[-1]

            market_is_live = (now_utc - live_time) <= pd.Timedelta(minutes=10)
            live_high = float(live_bar["High"])
            live_low = float(live_bar["Low"])

            # مدیریت معاملات و سفارش‌های شرطی
            if active_trade:
                status = active_trade["type"]
                sig_time = active_trade.get("signal_time")

                if status == "BUY_STOP":
                    if live_high >= active_trade["entry"]:
                        active_trade["type"] = "BUY_ACTIVE"
                        broadcast(f"⚡ <b>سقف کندل سیگنال در تریدینگ‌ویو شکسته شد! (BUY فعال شد روی ${active_trade['entry']:.2f})</b> 🟢")
                    elif live_low < active_trade["signal_bar_low"] or (closed_time > sig_time):
                        stats["cancelled"] += 1
                        save_state()
                        broadcast("🚫 <b>سفارش Buy Stop باطل شد (قانون ال بروکس)!</b>\nکندل بعدی سقف کندل سیگنال را نشکست. 🛡️")
                        active_trade = None

                elif status == "SELL_STOP":
                    if live_low <= active_trade["entry"]:
                        active_trade["type"] = "SELL_ACTIVE"
                        broadcast(f"⚡ <b>کف کندل سیگنال در تریدینگ‌ویو شکسته شد! (SELL فعال شد روی ${active_trade['entry']:.2f})</b> 🔴")
                    elif live_high > active_trade["signal_bar_high"] or (closed_time > sig_time):
                        stats["cancelled"] += 1
                        save_state()
                        broadcast("🚫 <b>سفارش Sell Stop باطل شد (قانون ال بروکس)!</b>\nکندل بعدی کف کندل سیگنال را نشکست. 🛡️")
                        active_trade = None

                elif status == "BUY_ACTIVE":
                    if live_high >= active_trade["tp"]:
                        stats["wins"] += 1
                        save_state()
                        tot = stats["wins"] + stats["losses"]
                        wr = (stats["wins"] / tot) * 100
                        broadcast(f"🎯 <b>تارگت ۱ به ۲ طلا زده شد! (+2R سود روی ${active_trade['tp']:.2f})</b> ✅\n🏆 وین‌ریت: <b>{wr:.1f}%</b>")
                        active_trade = None
                    elif live_low <= active_trade["sl"]:
                        stats["losses"] += 1
                        save_state()
                        tot = stats["wins"] + stats["losses"]
                        wr = (stats["wins"] / tot) * 100
                        broadcast(f"🛑 <b>استاپ‌لاس فعال شد (-1R روی ${active_trade['sl']:.2f}).</b>\n🏆 وین‌ریت: <b>{wr:.1f}%</b>")
                        active_trade = None

                elif status == "SELL_ACTIVE":
                    if live_low <= active_trade["tp"]:
                        stats["wins"] += 1
                        save_state()
                        tot = stats["wins"] + stats["losses"]
                        wr = (stats["wins"] / tot) * 100
                        broadcast(f"🎯 <b>تارگت ۱ به ۲ طلا زده شد! (+2R سود روی ${active_trade['tp']:.2f})</b> ✅\n🏆 وین‌ریت: <b>{wr:.1f}%</b>")
                        active_trade = None
                    elif live_high >= active_trade["sl"]:
                        stats["losses"] += 1
                        save_state()
                        tot = stats["wins"] + stats["losses"]
                        wr = (stats["wins"] / tot) * 100
                        broadcast(f"🛑 <b>استاپ‌لاس فعال شد (-1R روی ${active_trade['sl']:.2f}).</b>\n🏆 وین‌ریت: <b>{wr:.1f}%</b>")
                        active_trade = None

            # شکار ستاپ جدید از روی کندل‌های تریدینگ‌ویو
            if active_trade is None and market_is_live:
                minute_mod = now_utc.minute % 5

                # الف) آژیر ۲ دقیقه قبل از بسته شدن کندل ۵ دقیقه
                if minute_mod in (3, 4) and last_pre_alert_time != live_time:
                    cycle = get_market_cycle(closed_df)
                    ema20 = float(live_bar["EMA20"])
                    atr = float(live_bar["ATR"])

                    if cycle == "ALWAYS_IN_LONG" and abs(live_low - ema20) <= (atr * 0.4):
                        last_pre_alert_time = live_time
                        broadcast(
                            f"⚠️ <b>آژیر ۲ دقیقه‌ای ال بروکس ({src_name})</b>\n\n"
                            f"📈 وضعیت: <b>Always In Long (روند صعودی)</b>\n"
                            f"💰 قیمت لحظه‌ای: <b>${float(live_bar['Close']):.2f}</b>\n"
                            f"🧲 قیمت در حال تست <b>EMA 20 (${ema20:.2f})</b> است!\n"
                            f"📱 آماده باشید؛ کمتر از ۲ دقیقه دیگر کندل بسته می‌شود."
                        )
                    elif cycle == "ALWAYS_IN_SHORT" and abs(live_high - ema20) <= (atr * 0.4):
                        last_pre_alert_time = live_time
                        broadcast(
                            f"⚠️ <b>آژیر ۲ دقیقه‌ای ال بروکس ({src_name})</b>\n\n"
                            f"📉 وضعیت: <b>Always In Short (روند نزولی)</b>\n"
                            f"💰 قیمت لحظه‌ای: <b>${float(live_bar['Close']):.2f}</b>\n"
                            f"🧲 قیمت در حال تست <b>EMA 20 (${ema20:.2f})</b> است!\n"
                            f"📱 آماده باشید؛ کمتر از ۲ دقیقه دیگر کندل بسته می‌شود."
                        )

                # ب) صدور سیگنال قطعی به محض بسته شدن کندل ۵ دقیقه
                if last_signal_time != closed_time and minute_mod in (0, 1):
                    setup = analyze_al_brooks_setup(closed_df)
                    last_signal_time = closed_time

                    if setup:
                        setup["signal_time"] = closed_time
                        active_trade = setup
                        risk_d = setup["risk"]
                        rew_d = setup["reward"]

                        if setup["type"] == "BUY_STOP":
                            broadcast(
                                f"🟢 <b>سیگنال خرید ال بروکس (TradingView M5)</b> 🟢\n\n"
                                f"📡 چارت: <code>{html.escape(src_name)}</code>\n"
                                f"📚 ستاپ: <code>{html.escape(setup['setup_name'])}</code>\n\n"
                                f"⚡ <b>نقطه ورود (Buy Stop):</b> <code>${setup['entry']:.2f}</code> (۲۰ سنت بالای سقف کندل سیگنال)\n"
                                f"🛑 <b>حد ضرر (SL):</b> <code>${setup['sl']:.2f}</code> (فاصله: ${risk_d:.2f})\n"
                                f"🎯 <b>حد سود ۱ به ۲ (TP):</b> <code>${setup['tp']:.2f}</code> (فاصله: ${rew_d:.2f})\n\n"
                                f"⚠️ <i>اگر کندل ۵ دقیقه جدید سقف ${setup['signal_bar_high']:.2f} را نشکست، وارد نشوید!</i>"
                            )
                        elif setup["type"] == "SELL_STOP":
                            broadcast(
                                f"🔴 <b>سیگنال فروش ال بروکس (TradingView M5)</b> 🔴\n\n"
                                f"📡 چارت: <code>{html.escape(src_name)}</code>\n"
                                f"📚 ستاپ: <code>{html.escape(setup['setup_name'])}</code>\n\n"
                                f"⚡ <b>نقطه ورود (Sell Stop):</b> <code>${setup['entry']:.2f}</code> (۲۰ سنت زیر کف کندل سیگنال)\n"
                                f"🛑 <b>حد ضرر (SL):</b> <code>${setup['sl']:.2f}</code> (فاصله: ${risk_d:.2f})\n"
                                f"🎯 <b>حد سود ۱ به ۲ (TP):</b> <code>${setup['tp']:.2f}</code> (فاصله: ${rew_d:.2f})\n\n"
                                f"⚠️ <i>اگر کندل ۵ دقیقه جدید کف ${setup['signal_bar_low']:.2f} را نشکست، وارد نشوید!</i>"
                            )

        except Exception as e:
            print(f"Scanner error: {e}")

        time.sleep(15)

# ۷. دستورات تلگرام
if bot:
    @bot.message_handler(commands=["start"])
    def start_cmd(message):
        subscribed_users.add(message.chat.id)
        save_state()
        bot.reply_to(
            message,
            "👨‍🏫 <b>ربات پرایس اکشن ال بروکس (متصل به سرور زنده TradingView) فعال شد!</b>\n\n"
            "📡 چارت متصل: <code>OANDA:XAUUSD</code> (تایم‌فریم ۵ دقیقه)\n"
            "📊 برای دریافت قیمت لحظه‌ای و تحلیل چارت از تریدینگ‌ویو، دستور /status را بزنید.",
            parse_mode="HTML"
        )

    @bot.message_handler(commands=["status"])
    def status_cmd(message):
        wait_msg = bot.reply_to(message, "📡 در حال دریافت مستقیم چارت طلا از سرور TradingView...")
        df, src_name, err = get_al_brooks_data()
        if df is None:
            bot.edit_message_text(
                f"❌ <b>خطا در اتصال:</b>\n<code>{html.escape(str(err))}</code>",
                message.chat.id,
                wait_msg.message_id,
                parse_mode="HTML"
            )
            return

        live_bar = df.iloc[-1]
        closed_df = df.iloc[:-1]
        cycle = get_market_cycle(closed_df)
        tot = stats["wins"] + stats["losses"]
        wr = (stats["wins"] / tot * 100) if tot > 0 else 0.0

        cycle_fa = {
            "ALWAYS_IN_LONG": "🟢 Always In Long (روند صعودی - شکار H1/H2)",
            "ALWAYS_IN_SHORT": "🔴 Always In Short (روند نزولی - شکار L1/L2)",
            "TRADING_RANGE": "🟡 Trading Range (رنج - منتظر شفاف شدن روند)",
            "BARB_WIRE": "⛔ Barb Wire (سیم خاردار! ترید مطلقاً ممنوع)"
        }.get(cycle, cycle)

        bot.edit_message_text(
            f"📊 <b>گزارش زنده از سرور TradingView (تایم ۵ دقیقه):</b>\n\n"
            f"📡 چارت: <code>{html.escape(src_name)}</code>\n"
            f"💰 <b>قیمت لحظه‌ای طلا:</b> <code>${float(live_bar['Close']):.2f}</code>\n"
            f"🧲 <b>مقدار EMA 20:</b> <code>${float(live_bar['EMA20']):.2f}</code>\n"
            f"📏 <b>میانگین قد کندل‌ها (ATR):</b> <code>${float(live_bar['ATR']):.2f}</code>\n\n"
            f"🧭 <b>چرخه بازار (ال بروکس):</b>\n{cycle_fa}\n\n"
            f"🏆 <b>کارنامه سیگنال‌ها:</b>\n"
            f"✅ تارگت (1:2): <code>{stats['wins']}</code> | ❌ استاپ: <code>{stats['losses']}</code> | 🛡️ باطل‌شده: <code>{stats['cancelled']}</code>\n"
            f"📈 وین‌ریت: <b>{wr:.1f}%</b>",
            message.chat.id,
            wait_msg.message_id,
            parse_mode="HTML"
        )

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    threading.Thread(target=al_brooks_scanner, daemon=True).start()

    if bot:
        print("🤖 TradingView Al Brooks Bot Started!")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
