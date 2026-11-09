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
    return f"TradingView Al Brooks Triple Fractal Bot (1H + 5M + 1M) is LIVE! Source: {last_source_name}"

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

def fetch_tradingview_candles(symbol="OANDA:XAUUSD", interval="1", n_bars=250):
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
            if len(bars) >= 60:
                break
        ws.close()
        if len(bars) < 40:
            return None, f"TradingView({symbol}, {interval}) bars={len(bars)}"
            
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

# ۳. دریافت داده‌های ۳ تایم‌فریمی (۱ ساعت، ۵ دقیقه، ۱ دقیقه)
def get_triple_fractal_data():
    global last_source_name
    tv_symbols = [
        ("OANDA:XAUUSD", "OANDA:XAUUSD"),
        ("FOREXCOM:XAUUSD", "FOREXCOM:XAUUSD"),
        ("FX_IDC:XAUUSD", "FX_IDC:XAUUSD"),
        ("BINANCE:PAXGUSDT", "BINANCE:PAXGUSDT")
    ]
    
    df_1m, df_5m, df_1h, chosen_source = None, None, None, ""
    err_msg = ""
    
    for label, sym in tv_symbols:
        res_1m, e1 = fetch_tradingview_candles(sym, "1", 200)
        res_5m, e2 = fetch_tradingview_candles(sym, "5", 120)
        res_1h, e3 = fetch_tradingview_candles(sym, "60", 80) # 1 ساعت
        
        if res_1m is not None and res_5m is not None and res_1h is not None:
            df_1m = res_1m
            df_5m = res_5m
            df_1h = res_1h
            chosen_source = label
            break
        else:
            err_msg = f"{e1} | {e2} | {e3}"
            
    if df_1m is None or df_5m is None or df_1h is None:
        return None, None, None, None, f"خطا در ارتباط با تریدینگ‌ویو: {err_msg}"
        
    # اندیکاتورهای ۱ ساعت (Macro Context)
    df_1h["EMA20"] = df_1h["Close"].ewm(span=20, adjust=False).mean()
    df_1h["ATR"] = (df_1h["High"] - df_1h["Low"]).rolling(14).mean()
    cycle_1h = get_market_cycle(df_1h)
    
    # اندیکاتورهای ۵ دقیقه (Intermediate Context)
    df_5m["EMA20"] = df_5m["Close"].ewm(span=20, adjust=False).mean()
    df_5m["ATR"] = (df_5m["High"] - df_5m["Low"]).rolling(14).mean()
    cycle_5m = get_market_cycle(df_5m)
    
    # اندیکاتورهای ۱ دقیقه (Trigger)
    df_1m["EMA20"] = df_1m["Close"].ewm(span=20, adjust=False).mean()
    df_1m["ATR"] = (df_1m["High"] - df_1m["Low"]).rolling(14).mean()
    
    last_source_name = chosen_source
    return df_1m, cycle_1h, cycle_5m, chosen_source, None

# ۴. توابع تشخیص سایکل و محدوده رنج دقیق
def is_barb_wire(df_slice):
    last5 = df_slice.iloc[-5:]
    doji_count = 0
    ema_crosses = 0
    atr = float(df_slice["ATR"].iloc[-1])
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
    slope_thresh = max(atr_now * 0.20, 0.20)
    
    if above_ema >= 11 and ema_slope > slope_thresh:
        return "ALWAYS_IN_LONG"
    elif below_ema >= 11 and ema_slope < -slope_thresh:
        return "ALWAYS_IN_SHORT"
    else:
        return "TRADING_RANGE"

def get_precise_range_box(df_closed, lookback=30):
    box_slice = df_closed.iloc[-lookback:]
    r_high = float(box_slice["High"].quantile(0.92))
    r_low = float(box_slice["Low"].quantile(0.08))
    r_height = r_high - r_low
    return r_high, r_low, r_height

# ۵. هسته تحلیل ۳ تایم‌فریمی و صدور دستور صریح (BUY / SELL / WAIT)
def analyze_triple_fractal_setup(df_1m_closed, cycle_1h, cycle_5m):
    if len(df_1m_closed) < 35:
        return "WAIT", "داده‌های کافی نیست - صبر کن ⏳"
        
    # اگر تایم‌های بالا درگیر سیم خاردار یا بلاتکلیفی شدید هستند 👈 صبر کن
    if cycle_1h == "BARB_WIRE" or cycle_5m == "BARB_WIRE":
        return "WAIT", "بازار در تایم بالا درگیر سیم خاردار (Barb Wire) است - صبر کن ⛔"

    sb = df_1m_closed.iloc[-1]      # کندل بسته شده (Signal Bar)
    prev1 = df_1m_closed.iloc[-2]   # کندل قبل
    
    sb_high = float(sb["High"])
    sb_low = float(sb["Low"])
    sb_open = float(sb["Open"])
    sb_close = float(sb["Close"])
    sb_ema = float(sb["EMA20"])
    sb_atr = float(sb["ATR"])
    
    if pd.isna(sb_atr) or sb_atr <= 0:
        return "WAIT", "محاسبه ATR نامعتبر - صبر کن ⏳"
        
    sb_range = sb_high - sb_low
    if sb_range < (sb_atr * 0.3) or sb_range > (sb_atr * 3.0):
        return "WAIT", "نوسان غیرعادی کندل - صبر کن ⏳"
        
    body_size = abs(sb_close - sb_open)
    close_position = (sb_close - sb_low) / sb_range
    range_high, range_low, _ = get_precise_range_box(df_1m_closed, lookback=30)

    # =========================================================================
    # الف) بررسی شرایط خرید (BUY)
    # شرط: ۱ ساعت صعودی/رنج + ۵ دقیقه صعودی + ستاپ معتبر در ۱ دقیقه
    # =========================================================================
    is_bullish_context = (cycle_1h in ["ALWAYS_IN_LONG", "TRADING_RANGE"]) and (cycle_5m == "ALWAYS_IN_LONG")
    
    bull_trap = (float(prev1["Low"]) < range_low and sb_close > range_low and sb_close > sb_open)
    bull_pullback = (sb_low <= sb_ema + (sb_atr * 0.35)) and (sb_close > sb_ema) and (close_position >= 0.58)

    if is_bullish_context and (bull_trap or bull_pullback):
        setup_name = "🚨 تله نزولی در روند صعودی (Buy Trap)" if bull_trap else "📈 پولبک صعودی هم‌جهت با 1h و 5m"
        entry_stop = sb_high + 0.08
        raw_sl = min(sb_low, float(prev1["Low"])) - 0.12
        risk = max(entry_stop - raw_sl, max(sb_atr * 0.8, 1.0))
        sl = entry_stop - risk
        tp = entry_stop + (risk * 2.0)
        
        return "BUY", {
            "type": "BUY_STOP", "mode": "TRIPLE_BUY",
            "setup_name": setup_name,
            "signal_bar_high": sb_high, "signal_bar_low": sb_low,
            "entry": entry_stop, "sl": sl, "tp": tp, "risk": risk, "reward": risk * 2.0
        }

    # =========================================================================
    # ب) بررسی شرایط فروش (SELL)
    # شرط: ۱ ساعت نزولی/رنج + ۵ دقیقه نزولی + ستاپ معتبر در ۱ دقیقه
    # =========================================================================
    is_bearish_context = (cycle_1h in ["ALWAYS_IN_SHORT", "TRADING_RANGE"]) and (cycle_5m == "ALWAYS_IN_SHORT")
    
    bear_trap = (float(prev1["High"]) > range_high and sb_close < range_high and sb_close < sb_open)
    bear_pullback = (sb_
