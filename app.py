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
import websocket
from flask import Flask, request
import telebot
import pandas as pd
import numpy as np

# ۱. وب‌سرور برای روشن ماندن ۲۴ ساعته در Render
app = Flask(__name__)
last_source_name = "در حال اتصال به TradingView..."

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

STATE_FILE = "bot_state.json"
subscribed_users = set()
active_trade = None
stats = {"wins": 0, "losses": 0, "cancelled": 0}
last_pre_alert_time = None
last_analyzed_candle_time = None

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
    return f"TradingView Al Brooks M5 Gold Bot (Range + Breakout + Trend) is LIVE! Source: {last_source_name}"

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

# ۲. موتور اتصال مستقیم به وب‌سوکت زنده تریدینگ‌ویو
def _tv_send(ws, func, params):
    payload = json.dumps({"m": func, "p": params}, separators=(",", ":"))
    frame = f"~m~{len(payload)}~m~{payload}"
    ws.send(frame)

def fetch_tradingview_candles(symbol="OANDA:XAUUSD", interval="5", n_bars=220):
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

    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()

    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    true_range = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1)
    df["ATR"] = true_range.rolling(14).mean()

    last_source_name = chosen_source
    return df, chosen_source, None

# ۳. محاسبه سقف و کف رنج (Trading Range Box) + تشخیص سیم خاردار
def get_range_box(df_closed, lookback=20):
    """
    محاسبه سقف و کف رنج از روی ۲۰ کندل قبل از کندل سیگنال
    """
    box_slice = df_closed.iloc[-(lookback + 1):-1]
    r_high = float(box_slice["High"].max())
    r_low = float(box_slice["Low"].min())
    r_height = r_high - r_low
    return r_high, r_low, r_height

def is_barb_wire(df_slice):
    last5 = df_slice.iloc[-5:]
    doji_count = 0
    ema_crosses = 0
    atr = float(df_slice["ATR"].iloc[-1])

    # اگر کل نوسان ۵ کندل اخیر کمتر از ۱.۲ برابر ATR باشد و پر از دوجی باشد = سیم خاردار تنگ
    total_rng = float(last5["High"].max() - last5["Low"].min())

    for _, row in last5.iterrows():
        rng = float(row["High"] - row["Low"])
        body = abs(float(row["Close"] - row["Open"]))
        ema = float(row["EMA20"])

        if rng > 0 and (body / rng) < 0.28:
            doji_count += 1
        if float(row["Low"]) <= ema <= float(row["High"]):
            ema_crosses += 1

    return (ema_crosses >= 4 and doji_count >= 3 and total_rng < atr * 1.5)

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

# ۴. موتور ۳ دنده ال بروکس: ۱. شکست رنج (Breakout) ۲. نوسان‌گیری سقف و کف رنج (BLSHS) ۳. پولبک روند (H2/L2)
def analyze_al_brooks_setup(df_closed):
    if len(df_closed) < 25:
        return None

    cycle = get_market_cycle(df_closed)
    if cycle == "BARB_WIRE":
        return None

    sb = df_closed.iloc[-1]       # کندل ۵ دقیقه‌ای که همین الان بسته شد
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
    if sb_range < (sb_atr * 0.35) or sb_range > (sb_atr * 3.2):
        return None

    body_size = abs(sb_close - sb_open)
    body_ratio = body_size / sb_range
    close_position = (sb_close - sb_low) / sb_range

    # محاسبه سقف و کف رنج ۲۰ کندل قبلی
    range_high, range_low, range_height = get_range_box(df_closed, lookback=20)

    # =========================================================================
    # دنده ۱: شکار شکست سقف یا کف رنج (Breakout / Spike به سبک ال بروکس)
    # =========================================================================
    # الف) شکست پرقدرت سقف رنج رو به بالا (Bull Breakout)
    if sb_close > range_high and sb_close > sb_open and body_ratio >= 0.50 and close_position >= 0.68 and sb_range >= (sb_atr * 0.7):
        entry_stop = sb_high + 0.15
        raw_sl = min(sb_low, range_high - (sb_atr * 0.5)) - 0.20
        risk = max(entry_stop - raw_sl, max(sb_atr * 1.0, 2.0))
        sl = entry_stop - risk
        tp = entry_stop + (risk * 2.0)

        return {
            "type": "BUY_STOP",
            "mode": "BREAKOUT",
            "setup_name": f"🚀 شکست پرقدرت سقف رنج (${range_high:.2f}) - Bull Breakout",
            "signal_bar_high": sb_high,
            "signal_bar_low": sb_low,
            "entry": entry_stop,
            "sl": sl,
            "tp": tp,
            "risk": risk,
            "reward": risk * 2.0,
        }

    # ب) شکست پرقدرت کف رنج رو به پایین (Bear Breakout)
    if sb_close < range_low and sb_close < sb_open and body_ratio >= 0.50 and close_position <= 0.32 and sb_range >= (sb_atr * 0.7):
        entry_stop = sb_low - 0.15
        raw_sl = max(sb_high, range_low + (sb_atr * 0.5)) + 0.20
        risk = max(raw_sl - entry_stop, max(sb_atr * 1.0, 2.0))
        sl = entry_stop + risk
        tp = entry_stop - (risk * 2.0)

        return {
            "type": "SELL_STOP",
            "mode": "BREAKOUT",
            "setup_name": f"💥 شکست پرقدرت کف رنج (${range_low:.2f}) - Bear Breakout",
            "signal_bar_high": sb_high,
            "signal_bar_low": sb_low,
            "entry": entry_stop,
            "sl": sl,
            "tp": tp,
            "risk": risk,
            "reward": risk * 2.0,
        }

    # =========================================================================
    # دنده ۲: معامله داخل خودِ رنج (خرید در کف رنج / فروش در سقف رنج - BLSHS)
    # =========================================================================
    if cycle == "TRADING_RANGE" and range_height >= (sb_atr * 1.4):
        zone_buffer = max(range_height * 0.22, sb_atr * 0.45)

        # الف) خرید در کف رنج (Buy Low) یا شکست فیک کف رنج (Failed Bear Breakout)
        tested_bottom = (sb_low <= range_low + zone_buffer) or (float(prev1["Low"]) <= range_low + zone_buffer)
        bull_reversal = (sb_close > range_low) and (close_position >= 0.55) and (sb_close >= sb_open or close_position >= 0.70)

        if tested_bottom and bull_reversal:
            entry_stop = sb_high + 0.20
            lowest_point = min(sb_low, float(prev1["Low"]), range_low)
            raw_sl = lowest_point - max(0.30, sb_atr * 0.25)
            risk = max(entry_stop - raw_sl, max(sb_atr * 0.9, 1.8))
            sl = entry_stop - risk
            tp = entry_stop + (risk * 2.0)

            return {
                "type": "BUY_STOP",
                "mode": "RANGE_FADE",
                "setup_name": f"🧲 خرید در کف رنج (${range_low:.2f}) - Al Brooks Buy Low",
                "signal_bar_high": sb_high,
                "signal_bar_low": sb_low,
                "entry": entry_stop,
                "sl": sl,
                "tp": tp,
                "risk": risk,
                "reward": risk * 2.0,
            }

        # ب) فروش در سقف رنج (Sell High) یا شکست فیک سقف رنج (Failed Bull Breakout)
        tested_top = (sb_high >= range_high - zone_buffer) or (float(prev1["High"]) >= range_high - zone_buffer)
        bear_reversal = (sb_close < range_high) and (close_position <= 0.45) and (sb_close <= sb_open or close_position <= 0.30)

        if tested_top and bear_reversal:
            entry_stop = sb_low - 0.20
            highest_point = max(sb_high, float(prev1["High"]), range_high)
            raw_sl = highest_point + max(0.30, sb_atr * 0.25)
            risk = max(raw_sl - entry_stop, max(sb_atr * 0.9, 1.8))
            sl = entry_stop + risk
            tp = entry_stop - (risk * 2.0)

            return {
                "type": "SELL_STOP",
                "mode": "RANGE_FADE",
                "setup_name": f"🧲 فروش در سقف رنج (${range_high:.2f}) - Al Brooks Sell High",
                "signal_bar_high": sb_high,
                "signal_bar_low": sb_low,
                "entry": entry_stop,
                "sl": sl,
                "tp": tp,
                "risk": risk,
                "reward": risk * 2.0,
            }

    # =========================================================================
    # دنده ۳: پولبک در روندهای قوی (Always In Long / Short -> H1/H2 & L1/L2)
    # =========================================================================
    if cycle == "ALWAYS_IN_LONG":
        touched_ema = (sb_low <= sb_ema + (sb_atr * 0.3)) or (float(prev1["Low"]) <= float(prev1["EMA20"]) + (sb_atr * 0.25))
        is_pullback = (sb_low < float(prev2["Low"])) or (float(prev1["Low"]) < float(prev3["Low"]))
        valid_bull_sb = (sb_close > sb_ema) and (close_position >= 0.62) and (sb_close >= sb_open)

        if touched_ema and is_pullback and valid_bull_sb:
            leg_type = "📈 پولبک روند صعودی H1 به EMA20"
            if float(prev2["High"]) > float(prev3["High"]) and float(prev1["Low"]) < float(prev2["Low"]):
                leg_type = "📈 ستاپ طلایی دو لِگه H2 روی EMA20 ⭐"

            entry_stop = sb_high + 0.20
            swing_low = min(sb_low, float(prev1["Low"])) - 0.20
            risk = max(entry_stop - swing_low, max(sb_atr * 1.1, 2.0))
            sl = entry_stop - risk
            tp = entry_stop + (risk * 2.0)

            return {
                "type": "BUY_STOP",
                "mode": "TREND_PULLBACK",
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
        touched_ema = (sb_high >= sb_ema - (sb_atr * 0.3)) or (float(prev1["High"]) >= float(prev1["EMA20"]) - (sb_atr * 0.25))
        is_pullback = (sb_high > float(prev2["High"])) or (float(prev1["High"]) > float(prev3["High"]))
        valid_bear_sb = (sb_close < sb_ema) and (close_position <= 0.38) and (sb_close <= sb_open)

        if touched_ema and is_pullback and valid_bear_sb:
            leg_type = "📉 پولبک روند نزولی L1 به EMA20"
            if float(prev2["Low"]) < float(prev3["Low"]) and float(prev1["High"]) > float(prev2["High"]):
                leg_type = "📉 ستاپ طلایی دو لِگه L2 روی EMA20 ⭐"

            entry_stop = sb_low - 0.20
            swing_high = max(sb_high, float(prev1["High"])) + 0.20
            risk = max(swing_high - entry_stop, max(sb_atr * 1.1, 2.0))
            sl = entry_stop + risk
            tp = entry_stop - (risk * 2.0)

            return {
                "type": "SELL_STOP",
                "mode": "TREND_PULLBACK",
                "signal_bar_high": sb_high,
                "signal_bar_low": sb_low,
                "setup_name": leg_type,
                "entry": entry_stop,
                "sl": sl,
                "tp": tp,
                "risk": risk,
                "reward": risk * 2.0,
            }

    return None

def send_setup_signal(setup, src_name):
    risk_d = setup["risk"]
    rew_d = setup["reward"]
    mode_badge = {
        "BREAKOUT": "🔥 <b>[سیگنال شکست رنج - BREAKOUT]</b>",
        "RANGE_FADE": "🔄 <b>[نوسان‌گیری سقف و کف رنج - RANGE TRADE]</b>",
        "TREND_PULLBACK": "🌊 <b>[پولبک در روند - TREND PULLBACK]</b>"
    }.get(setup.get("mode"), "")

    if setup["type"] == "BUY_STOP":
        broadcast(
            f"🟢 <b>سیگنال خودکار خرید طلا (BUY - تایم ۵ دقیقه)</b> 🟢\n"
            f"{mode_badge}\n\n"
            f"📡 چارت: <code>{html.escape(src_name)}</code>\n"
            f"📚 <b>علت ورود:</b> <code>{html.escape(setup['setup_name'])}</code>\n\n"
            f"⚡ <b>نقطه ورود (Buy Stop / شکست سقف کندل):</b> <code>${setup['entry']:.2f}</code>\n"
            f"🛑 <b>حد ضرر دقیق (Stop Loss):</b> <code>${setup['sl']:.2f}</code> (ریسک: ${risk_d:.2f})\n"
            f"🎯 <b>حد سود ۱ به ۲ (Take Profit):</b> <code>${setup['tp']:.2f}</code> (سود: ${rew_d:.2f})\n\n"
            f"📌 <i>به محض عبور قیمت از ${setup['entry']:.2f} وارد شوید و استاپ را روی ${setup['sl']:.2f} قرار دهید.</i>"
        )
    elif setup["type"] == "SELL_STOP":
        broadcast(
            f"🔴 <b>سیگنال خودکار فروش طلا (SELL - تایم ۵ دقیقه)</b> 🔴\n"
            f"{mode_badge}\n\n"
            f"📡 چارت: <code>{html.escape(src_name)}</code>\n"
            f"📚 <b>علت ورود:</b> <code>{html.escape(setup['setup_name'])}</code>\n\n"
            f"⚡ <b>نقطه ورود (Sell Stop / شکست کف کندل):</b> <code>${setup['entry']:.2f}</code>\n"
            f"🛑 <b>حد ضرر دقیق (Stop Loss):</b> <code>${setup['sl']:.2f}</code> (ریسک: ${risk_d:.2f})\n"
            f"🎯 <b>حد سود ۱ به ۲ (Take Profit):</b> <code>${setup['tp']:.2f}</code> (سود: ${rew_d:.2f})\n\n"
            f"📌 <i>به محض عبور قیمت از ${setup['entry']:.2f} وارد شوید و استاپ را روی ${setup['sl']:.2f} قرار دهید.</i>"
        )

# ۵. حلقه اصلی اسکنر خودکار ۲۴ ساعته (بدون نیاز به زدن /status)
def al_brooks_scanner():
    global active_trade, last_pre_alert_time, last_analyzed_candle_time, stats

    while True:
        try:
            if not subscribed_users:
                time.sleep(10)
                continue

            now_utc = datetime.now(pytz.utc)
            df, src_name, err = get_al_brooks_data()
            if df is None:
                time.sleep(15)
                continue

            live_bar = df.iloc[-1]
            closed_df = df.iloc[:-1]
            live_time = df.index[-1]
            closed_time = closed_df.index[-1]

            # در اولین اجرای ربات، زمان آخرین کندل را ثبت کن تا سیگنال قدیمی نفرستد
            if last_analyzed_candle_time is None:
                last_analyzed_candle_time = closed_time

            market_is_live = (now_utc - live_time) <= pd.Timedelta(minutes=10)
            live_high = float(live_bar["High"])
            live_low = float(live_bar["Low"])
            live_close = float(live_bar["Close"])

            # -----------------------------------------------------------------
            # بخش اول: پیگیری لحظه‌ای معامله باز (TP / SL / ابطال سفارش)
            # -----------------------------------------------------------------
            if active_trade:
                status = active_trade["type"]
                sig_time = active_trade.get("signal_time")

                if status == "BUY_STOP":
                    if live_high >= active_trade["entry"]:
                        active_trade["type"] = "BUY_ACTIVE"
                        broadcast(
                            f"⚡ <b>پوزیشن BUY فعال شد! (قیمت از ${active_trade['entry']:.2f} عبور کرد)</b> 🟢\n"
                            f"🛑 حد ضرر: <code>${active_trade['sl']:.2f}</code> | 🎯 حد سود (1:2): <code>${active_trade['tp']:.2f}</code>"
                        )
                    elif live_low < active_trade["signal_bar_low"] or (closed_time > sig_time):
                        stats["cancelled"] += 1
                        save_state()
                        broadcast("🚫 <b>سفارش Buy Stop باطل شد!</b>\nکندل بعدی سقف کندل سیگنال را نشکست. 🛡️")
                        active_trade = None

                elif status == "SELL_STOP":
                    if live_low <= active_trade["entry"]:
                        active_trade["type"] = "SELL_ACTIVE"
                        broadcast(
                            f"⚡ <b>پوزیشن SELL فعال شد! (قیمت از ${active_trade['entry']:.2f} عبور کرد)</b> 🔴\n"
                            f"🛑 حد ضرر: <code>${active_trade['sl']:.2f}</code> | 🎯 حد سود (1:2): <code>${active_trade['tp']:.2f}</code>"
                        )
                    elif live_high > active_trade["signal_bar_high"] or (closed_time > sig_time):
                        stats["cancelled"] += 1
                        save_state()
                        broadcast("🚫 <b>سفارش Sell Stop باطل شد!</b>\nکندل بعدی کف کندل سیگنال را نشکست. 🛡️")
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
                        broadcast(
                            f"🛑 <b>استاپ‌لاس خرید زده شد (-1R روی ${active_trade['sl']:.2f}).</b>\n"
                            f"🔍 <i>در حال بررسی فوری احتمال شکست رنج (Breakout) در جهت مخالف...</i>\n"
                            f"🏆 وین‌ریت: <b>{wr:.1f}%</b>"
                        )
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
                        broadcast(
                            f"🛑 <b>استاپ‌لاس فروش زده شد (-1R روی ${active_trade['sl']:.2f}).</b>\n"
                            f"🔍 <i>در حال بررسی فوری احتمال شکست رنج (Breakout) در جهت مخالف...</i>\n"
                            f"🏆 وین‌ریت: <b>{wr:.1f}%</b>"
                        )
                        active_trade = None

            # -----------------------------------------------------------------
            # بخش دوم: بررسی خودکار هر کندل ۵ دقیقه جدید به محض بسته شدن!
            # -----------------------------------------------------------------
            if closed_time > last_analyzed_candle_time and market_is_live:
                last_analyzed_candle_time = closed_time

                # اگر معامله‌ای باز نیست (یا همین الان استاپ خورد و شکست رنج رخ داد)، کندل بسته شده را بررسی کن
                if active_trade is None:
                    setup = analyze_al_brooks_setup(closed_df)
                    if setup:
                        setup["signal_time"] = closed_time
                        active_trade = setup
                        send_setup_signal(setup, src_name)

            # -----------------------------------------------------------------
            # بخش سوم: آژیر آماده‌باش ۲ دقیقه قبل از بسته شدن کندل (سقف/کف رنج و EMA20)
            # -----------------------------------------------------------------
            if active_trade is None and market_is_live:
                minute_mod = now_utc.minute % 5
                if minute_mod in (3, 4) and last_pre_alert_time != live_time:
                    cycle = get_market_cycle(closed_df)
                    ema20 = float(live_bar["EMA20"])
                    atr = float(live_bar["ATR"])
                    r_high, r_low, r_height = get_range_box(df, lookback=20)

                    # آژیر برخورد به سقف رنج
                    if abs(live_high - r_high) <= (atr * 0.35) or live_high > r_high:
                        last_pre_alert_time = live_time
                        broadcast(
                            f"⚠️ <b>آژیر ۲ دقیقه‌ای: طلا در سقف رنج (${r_high:.2f})!</b>\n\n"
                            f"💰 قیمت لحظه‌ای: <code>${live_close:.2f}</code>\n"
                            f"📌 <b>دو سناریوی آماده در ۲ دقیقه آینده:</b>\n"
                            f"1️⃣ اگر کندل زیر سقف رنج ضعیف بسته شود 👈 سیگنال <b>فروش در سقف رنج (SELL)</b>\n"
                            f"2️⃣ اگر کندل با بدنه پرقدرت بالای سقف بسته شود 👈 سیگنال <b>شکست رنج (BUY Breakout)</b>\n"
                            f"📱 <i>متاتریدر را باز و آماده کنید!</i>"
                        )
                    # آژیر برخورد به کف رنج
                    elif abs(live_low - r_low) <= (atr * 0.35) or live_low < r_low:
                        last_pre_alert_time = live_time
                        broadcast(
                            f"⚠️ <b>آژیر ۲ دقیقه‌ای: طلا در کف رنج (${r_low:.2f})!</b>\n\n"
                            f"💰 قیمت لحظه‌ای: <code>${live_close:.2f}</code>\n"
                            f"📌 <b>دو سناریوی آماده در ۲ دقیقه آینده:</b>\n"
                            f"1️⃣ اگر کندل بالای کف رنج برگشتی بسته شود 👈 سیگنال <b>خرید در کف رنج (BUY)</b>\n"
                            f"2️⃣ اگر کندل با بدنه پرقدرت زیر کف بسته شود 👈 سیگنال <b>شکست رنج (SELL Breakout)</b>\n"
                            f"📱 <i>متاتریدر را باز و آماده کنید!</i>"
                        )
                    # آژیر پولبک به EMA20 در روند
                    elif cycle in ("ALWAYS_IN_LONG", "ALWAYS_IN_SHORT") and abs(live_close - ema20) <= (atr * 0.35):
                        last_pre_alert_time = live_time
                        broadcast(
                            f"⚠️ <b>آژیر ۲ دقیقه‌ای: پولبک طلا به EMA 20 (${ema20:.2f})!</b>\n"
                            f"📱 آماده دریافت سیگنال هم‌جهت روند در کلوز کندل ۵ دقیقه باشید."
                        )

        except Exception as e:
            print(f"Scanner error: {e}")

        time.sleep(12)

# ۶. دستورات تلگرام
if bot:
    @bot.message_handler(commands=["start"])
    def start_cmd(message):
        subscribed_users.add(message.chat.id)
        save_state()
        bot.reply_to(
            message,
            "👨‍🏫 <b>موتور ۳ دنده ال بروکس (متصل به TradingView) فعال شد!</b>\n\n"
            "✅ <b>نیازی به زدن /status نیست!</b> ربات خودش ۲۴ ساعته چارت ۵ دقیقه طلا را رصد می‌کند و در ۳ حالت به صورت خودکار سیگنال + استاپ‌لاس + تارگت ۱ به ۲ می‌فرستد:\n"
            "1️⃣ <b>داخل رنج:</b> خرید در کف رنج و فروش در سقف رنج\n"
            "2️⃣ <b>شکست رنج (Breakout):</b> ورود فوری به محض شکسته شدن سقف یا کف رنج\n"
            "3️⃣ <b>داخل روند:</b> شکار پولبک‌های H1/H2 و L1/L2 روی EMA 20\n\n"
            "📊 برای دیدن سقف و کف فعلی رنج هر زمان خواستید /status را بزنید.",
            parse_mode="HTML"
        )

    @bot.message_handler(commands=["status"])
    def status_cmd(message):
        wait_msg = bot.reply_to(message, "📡 در حال استخراج سقف و کف رنج از TradingView...")
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
        r_high, r_low, r_height = get_range_box(closed_df, lookback=20)

        tot = stats["wins"] + stats["losses"]
        wr = (stats["wins"] / tot * 100) if tot > 0 else 0.0

        cycle_fa = {
            "ALWAYS_IN_LONG": "🟢 Always In Long (روند صعودی - شکار پولبک و شکست سقف)",
            "ALWAYS_IN_SHORT": "🔴 Always In Short (روند نزولی - شکار پولبک و شکست کف)",
            "TRADING_RANGE": "🟡 Trading Range (فعال: فروش در سقف رنج / خرید در کف رنج / آماده شکست)",
            "BARB_WIRE": "⛔ Barb Wire (سیم خاردار تنگ - ترید موقتاً قفل است)"
        }.get(cycle, cycle)

        bot.edit_message_text(
            f"📊 <b>گزارش زنده از سرور TradingView (تایم ۵ دقیقه):</b>\n\n"
            f"📡 چارت: <code>{html.escape(src_name)}</code>\n"
            f"💰 <b>قیمت لحظه‌ای طلا:</b> <code>${float(live_bar['Close']):.2f}</code>\n"
            f"🔼 <b>سقف رنج فعلی (مقاومت):</b> <code>${r_high:.2f}</code>\n"
            f"🔽 <b>کف رنج فعلی (حمایت):</b> <code>${r_low:.2f}</code>\n"
            f"↔️ عرض کانال رنج: <code>${r_height:.2f}</code>\n"
            f"🧲 مقدار EMA 20: <code>${float(live_bar['EMA20']):.2f}</code>\n"
            f"📏 میانگین قد کندل‌ها (ATR): <code>${float(live_bar['ATR']):.2f}</code>\n\n"
            f"🧭 <b>حالت اتوماتیک فعال:</b>\n{cycle_fa}\n\n"
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
        print("🤖 TradingView Al Brooks 3-Mode Bot Started!")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
