import os
import re
import json
import html
import time
import random
import string
import logging
import threading
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytz
import websocket
import telebot
from flask import Flask, request

# ============================================================
# تنظیمات
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "7860"))
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "15"))
TIMEFRAME = os.getenv("TIMEFRAME", "5")
TV_SYMBOLS = [
    ("TradingView (OANDA:XAUUSD)", "OANDA:XAUUSD"),
    ("TradingView (FOREXCOM:XAUUSD)", "FOREXCOM:XAUUSD"),
    ("TradingView (FX_IDC:XAUUSD)", "FX_IDC:XAUUSD"),
]
# نماد PAXG بازار طلا نیست؛ فقط در صورت فعال‌سازی صریح استفاده می‌شود.
if os.getenv("ALLOW_PAXG_FALLBACK", "false").lower() == "true":
    TV_SYMBOLS.append(("TradingView (BINANCE:PAXGUSDT)", "BINANCE:PAXGUSDT"))

STATE_FILE = os.getenv("STATE_FILE", "bot_state.json")
LOOKBACK_RANGE = 20
MIN_BARS = 80
RR_TARGET = 2.0
MAX_SIGNAL_AGE_MINUTES = 8
ORDER_EXPIRY_BARS = 3
REPORT_EVERY_NEW_CANDLE = os.getenv("REPORT_EVERY_NEW_CANDLE", "true").lower() == "true"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("albrooks-gold-bot")

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN, threaded=True) if BOT_TOKEN else None

state_lock = threading.RLock()
subscribed_users = set()
stats = {"wins": 0, "losses": 0, "cancelled": 0}
active_trade = None          # معامله فعال‌شده
pending_order = None         # سفارش شرطی که هنوز فعال نشده
market_memory = {
    "range_high": None,
    "range_low": None,
    "range_started": None,
    "range_status": "UNKNOWN",
    "breakout_direction": None,
    "breakout_time": None,
    "breakout_level": None,
    "failed_breakout": False,
}
last_source_name = "در حال اتصال به TradingView..."
last_analyzed_candle_time = None
last_report_candle_time = None
last_event_key = None
scanner_started = False

# ============================================================
# ذخیره‌سازی وضعیت
# ============================================================

def _iso(value):
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)

def save_state():
    payload = {
        "users": list(subscribed_users),
        "stats": stats,
        "active_trade": active_trade,
        "pending_order": pending_order,
        "market_memory": market_memory,
        "last_analyzed_candle_time": _iso(last_analyzed_candle_time),
        "last_report_candle_time": _iso(last_report_candle_time),
        "last_event_key": last_event_key,
    }
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception:
        log.exception("Could not save state")

def load_state():
    global subscribed_users, stats, active_trade, pending_order
    global market_memory, last_analyzed_candle_time
    global last_report_candle_time, last_event_key
    try:
        if not os.path.exists(STATE_FILE):
            return
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        subscribed_users = set(data.get("users", []))
        stats.update(data.get("stats", {}))
        active_trade = data.get("active_trade")
        pending_order = data.get("pending_order")
        market_memory.update(data.get("market_memory", {}))
        if data.get("last_analyzed_candle_time"):
            last_analyzed_candle_time = pd.Timestamp(data["last_analyzed_candle_time"])
        if data.get("last_report_candle_time"):
            last_report_candle_time = pd.Timestamp(data["last_report_candle_time"])
        last_event_key = data.get("last_event_key")
    except Exception:
        log.exception("Could not load state")

load_state()

# ============================================================
# تلگرام
# ============================================================

def broadcast(message):
    if not bot:
        return
    for chat_id in list(subscribed_users):
        try:
            bot.send_message(chat_id, message, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            log.exception("Telegram send error for chat_id=%s", chat_id)

def send_to(chat_id, message):
    if bot:
        try:
            bot.send_message(chat_id, message, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            log.exception("Telegram direct message failed")

if bot:
    @bot.message_handler(commands=["start", "subscribe"])
    def cmd_start(message):
        with state_lock:
            subscribed_users.add(message.chat.id)
            save_state()
        send_to(
            message.chat.id,
            "عضویت شما فعال شد.\n"
            "ربات طلا در تایم‌فریم ۵ دقیقه، ساختار بازار و رفتار کندل‌ها را تحلیل می‌کند.\n"
            "برای مشاهده وضعیت از دستور /status و برای توقف پیام‌ها از /stop استفاده کنید."
        )

    @bot.message_handler(commands=["stop", "unsubscribe"])
    def cmd_stop(message):
        with state_lock:
            subscribed_users.discard(message.chat.id)
            save_state()
        send_to(message.chat.id, "ارسال گزارش برای این حساب متوقف شد.")

    @bot.message_handler(commands=["status"])
    def cmd_status(message):
        send_to(message.chat.id, build_status_report(last_market_snapshot, last_source_name)
                if last_market_snapshot is not None else "هنوز داده معتبر بازار دریافت نشده است.")

# ============================================================
# وب‌سرور Render و وب‌هوک
# ============================================================

@app.route("/")
def home():
    return (
        "Al Brooks XAUUSD M5 Analyzer is running. "
        f"Source: {html.escape(last_source_name)}"
    )

@app.route("/health")
def health():
    return {"ok": True, "source": last_source_name, "subscribers": len(subscribed_users)}

@app.route("/webhook", methods=["POST"])
def tv_webhook():
    try:
        data = request.get_data(as_text=True)
        broadcast(
            "🔔 <b>آلارم دریافتی از TradingView</b>\n\n"
            f"<code>{html.escape(data[:3500])}</code>"
        )
        return "OK", 200
    except Exception as exc:
        log.exception("Webhook error")
        return str(exc), 400

def run_web():
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)

# ============================================================
# اتصال به داده‌های کندلی TradingView
# توجه: این اتصال غیررسمی است و ممکن است با تغییرات TradingView قطع شود.
# ============================================================

def _tv_send(ws, method, params):
    payload = json.dumps({"m": method, "p": params}, separators=(",", ":"))
    ws.send(f"~m~{len(payload)}~m~{payload}")

def _extract_tv_messages(raw):
    if not raw:
        return []
    # پاسخ ممکن است چند پیام پشت سر هم داشته باشد.
    chunks = re.split(r"~m~\d+~m~", raw)
    output = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or chunk.startswith("~h~"):
            continue
        try:
            output.append(json.loads(chunk))
        except Exception:
            continue
    return output

def fetch_tradingview_candles(symbol="OANDA:XAUUSD", interval="5", n_bars=220):
    ws = None
    try:
        ws = websocket.create_connection(
            "wss://data.tradingview.com/socket.io/websocket?from=chart%2F",
            header=[
                "Origin: https://www.tradingview.com",
                "User-Agent: Mozilla/5.0"
            ],
            timeout=12,
            enable_multithread=True
        )
        chart_session = "cs_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
        _tv_send(ws, "set_auth_token", ["unauthorized_user_token"])
        _tv_send(ws, "chart_create_session", [chart_session, ""])
        symbol_json = json.dumps(
            {"symbol": symbol, "adjustment": "splits"},
            separators=(",", ":")
        )
        _tv_send(ws, "resolve_symbol", [chart_session, "sym_1", f"={symbol_json}"])
        _tv_send(
            ws, "create_series",
            [chart_session, "ser_1", "s1", "sym_1", str(interval), int(n_bars), ""]
        )

        bars_by_time = {}
        deadline = time.time() + 11
        while time.time() < deadline:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                break
            if not raw:
                break
            if raw.startswith("~h~"):
                try:
                    ws.send(raw)
                except Exception:
                    pass
                continue

            for msg in _extract_tv_messages(raw):
                method = msg.get("m")
                params = msg.get("p", [])
                if method in ("timescale_update", "du"):
                    # ساختار معمول: [chart_session, {series_id: {s: [...]}}]
                    for param in params:
                        if not isinstance(param, dict):
                            continue
                        series = param.get("ser_1") or param.get("sds_1")
                        if not isinstance(series, dict):
                            continue
                        for item in series.get("s", []):
                            values = item.get("v", [])
                            if len(values) >= 5:
                                try:
                                    ts = int(values[0])
                                    bars_by_time[ts] = {
                                        "Time": ts,
                                        "Open": float(values[1]),
                                        "High": float(values[2]),
                                        "Low": float(values[3]),
                                        "Close": float(values[4]),
                                    }
                                except (TypeError, ValueError):
                                    continue
                elif method == "series_completed":
                    # معمولاً ممکن است پیام تکمیلی بعد از این نیز برسد؛
                    # داده‌های دریافت‌شده را نگه می‌داریم.
                    pass

            if len(bars_by_time) >= min(60, n_bars):
                # چند ثانیه برای دریافت به‌روزرسانی نهایی صبر نمی‌کنیم.
                break

        if ws:
            ws.close()
        if len(bars_by_time) < MIN_BARS:
            return None, f"{symbol}: تعداد کندل دریافتی کافی نیست ({len(bars_by_time)})"

        df = pd.DataFrame(list(bars_by_time.values())).sort_values("Time")
        df["Time"] = pd.to_datetime(df["Time"], unit="s", utc=True)
        df = df.set_index("Time")
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df, None
    except Exception as exc:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        return None, f"{symbol}: {str(exc)[:100]}"

def add_indicators(df):
    df = df.copy()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    # ATR وایلدر، نه میانگین ساده TR
    df["ATR"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    return df

def get_al_brooks_data():
    global last_source_name
    errors = []
    for label, symbol in TV_SYMBOLS:
        frame, error = fetch_tradingview_candles(symbol, TIMEFRAME, 220)
        if frame is not None and len(frame) >= MIN_BARS:
            last_source_name = label
            return add_indicators(frame), label, None
        if error:
            errors.append(error)
    return None, None, " | ".join(errors)

# ============================================================
# ابزارهای تحلیل کندل و ساختار بازار
# ============================================================

def safe_float(value, default=0.0):
    try:
        result = float(value)
        return default if not np.isfinite(result) else result
    except Exception:
        return default

def candle_metrics(row):
    high = safe_float(row["High"])
    low = safe_float(row["Low"])
    opn = safe_float(row["Open"])
    close = safe_float(row["Close"])
    rng = max(high - low, 1e-9)
    body = abs(close - opn)
    return {
        "range": rng,
        "body": body,
        "body_ratio": body / rng,
        "close_pos": (close - low) / rng,
        "upper_wick": high - max(opn, close),
        "lower_wick": min(opn, close) - low,
        "bull": close > opn,
        "bear": close < opn,
    }

def is_barb_wire(df):
    if len(df) < 5:
        return False
    last = df.iloc[-5:]
    atr = safe_float(last["ATR"].iloc[-1])
    if atr <= 0:
        return False
    dojis = 0
    ema_touches = 0
    for _, row in last.iterrows():
        m = candle_metrics(row)
        if m["body_ratio"] <= 0.30:
            dojis += 1
        if safe_float(row["Low"]) <= safe_float(row["EMA20"]) <= safe_float(row["High"]):
            ema_touches += 1
    total_range = safe_float(last["High"].max() - last["Low"].min())
    return dojis >= 3 and ema_touches >= 4 and total_range <= atr * 2.0

def get_market_cycle(df):
    if len(df) < 20:
        return "UNKNOWN"
    if is_barb_wire(df):
        return "BARB_WIRE"

    recent = df.iloc[-15:]
    above = int((recent["Close"] > recent["EMA20"]).sum())
    below = int((recent["Close"] < recent["EMA20"]).sum())
    ema_slope = safe_float(recent["EMA20"].iloc[-1] - recent["EMA20"].iloc[-6])
    atr = safe_float(recent["ATR"].iloc[-1])
    if atr <= 0:
        return "UNKNOWN"

    # EMA فقط یکی از شواهد است؛ ساختار سقف و کف نیز دخالت دارد.
    highs = recent["High"].to_numpy()
    lows = recent["Low"].to_numpy()
    rising_structure = highs[-1] > highs[-6] and lows[-1] > lows[-6]
    falling_structure = highs[-1] < highs[-6] and lows[-1] < lows[-6]

    if above >= 10 and ema_slope > atr * 0.18 and rising_structure:
        return "ALWAYS_IN_LONG"
    if below >= 10 and ema_slope < -atr * 0.18 and falling_structure:
        return "ALWAYS_IN_SHORT"
    return "TRADING_RANGE"

def get_range_box(df_closed, lookback=LOOKBACK_RANGE):
    if len(df_closed) < lookback + 2:
        return None
    # کندل آخرِ df_closed از محاسبه مرزها کنار گذاشته می‌شود تا
    # کندل سیگنال مرز خودش را به‌طور مصنوعی جابه‌جا نکند.
    window = df_closed.iloc[-(lookback + 1):-1]
    return (
        safe_float(window["High"].max()),
        safe_float(window["Low"].min()),
        safe_float(window["High"].max() - window["Low"].min())
    )

def classify_breakout(df_closed, range_high, range_low):
    """قدرت شکست را کیفی ارزیابی می‌کند؛ درصد احتمال تولید نمی‌کند."""
    bar = df_closed.iloc[-1]
    m = candle_metrics(bar)
    atr = safe_float(bar["ATR"])
    close = safe_float(bar["Close"])
    if atr <= 0:
        return None

    if close > range_high:
        direction = "UP"
        beyond = close - range_high
        directional_close = m["close_pos"]
    elif close < range_low:
        direction = "DOWN"
        beyond = range_low - close
        directional_close = 1 - m["close_pos"]
    else:
        return None

    score = 0
    reasons = []
    if m["body_ratio"] >= 0.60:
        score += 1
        reasons.append("بدنه نسبتاً بزرگ")
    if directional_close >= 0.80:
        score += 1
        reasons.append("بسته‌شدن نزدیک انتهای کندل")
    if m["range"] >= atr * 0.90:
        score += 1
        reasons.append("دامنه قابل‌توجه نسبت به ATR")
    if beyond >= atr * 0.10:
        score += 1
        reasons.append("بسته‌شدن با فاصله از مرز")

    strength = "قوی" if score >= 3 else ("متوسط" if score == 2 else "ضعیف")
    return {
        "direction": direction,
        "strength": strength,
        "score": score,
        "level": range_high if direction == "UP" else range_low,
        "reasons": reasons,
        "bar_time": df_closed.index[-1].isoformat(),
    }

def analyze_market_context(df_closed):
    cycle = get_market_cycle(df_closed)
    box = get_range_box(df_closed)
    bar = df_closed.iloc[-1]
    price = safe_float(bar["Close"])
    atr = safe_float(bar["ATR"])
    ema = safe_float(bar["EMA20"])

    if box:
        rh, rl, height = box
        location = (price - rl) / height if height > 0 else 0.5
        if price > rh:
            position = "بالاتر از سقف محدوده محاسباتی"
        elif price < rl:
            position = "پایین‌تر از کف محدوده محاسباتی"
        elif location >= 0.75:
            position = "نیمه بالایی و نزدیک سقف محدوده"
        elif location <= 0.25:
            position = "نیمه پایینی و نزدیک کف محدوده"
        else:
            position = "نزدیک مرکز محدوده"
    else:
        rh = rl = height = location = None
        position = "محدوده کافی برای محاسبه وجود ندارد"

    return {
        "cycle": cycle, "price": price, "ema": ema, "atr": atr,
        "range_high": rh, "range_low": rl, "range_height": height,
        "range_location": location, "position": position,
    }

def analyze_candle_behavior(df_closed):
    last = df_closed.iloc[-1]
    prev = df_closed.iloc[-2]
    m = candle_metrics(last)
    atr = safe_float(last["ATR"])
    close = safe_float(last["Close"])
    ema = safe_float(last["EMA20"])

    if m["bull"] and m["body_ratio"] >= 0.60 and m["close_pos"] >= 0.80:
        candle_read = "کندل صعودی قدرتمند با بسته‌شدن نزدیک سقف"
    elif m["bear"] and m["body_ratio"] >= 0.60 and m["close_pos"] <= 0.20:
        candle_read = "کندل نزولی قدرتمند با بسته‌شدن نزدیک کف"
    elif m["body_ratio"] <= 0.25:
        candle_read = "کندل کم‌بدنه؛ تردید و تعادل نسبی"
    elif m["upper_wick"] > m["body"] and m["upper_wick"] > m["lower_wick"]:
        candle_read = "سایه بالایی بلند؛ رد قیمت‌های بالاتر"
    elif m["lower_wick"] > m["body"] and m["lower_wick"] > m["upper_wick"]:
        candle_read = "سایه پایینی بلند؛ رد قیمت‌های پایین‌تر"
    else:
        candle_read = "کندل ترکیبی؛ به‌تنهایی برتری قاطعی نشان نمی‌دهد"

    overlap = max(
        0.0,
        min(safe_float(last["High"]), safe_float(prev["High"])) -
        max(safe_float(last["Low"]), safe_float(prev["Low"]))
    )
    overlap_ratio = overlap / max(m["range"], 1e-9)
    if overlap_ratio >= 0.65:
        overlap_read = "هم‌پوشانی زیاد با کندل قبل"
    elif overlap_ratio <= 0.15:
        overlap_read = "هم‌پوشانی کم؛ حرکت جهت‌دارتر"
    else:
        overlap_read = "هم‌پوشانی متوسط"

    if close > ema:
        ema_read = "قیمت بالای EMA20 است"
    elif close < ema:
        ema_read = "قیمت پایین EMA20 است"
    else:
        ema_read = "قیمت روی EMA20 قرار دارد"

    return {
        "candle": candle_read,
        "overlap": overlap_read,
        "ema": ema_read,
        "body_ratio": m["body_ratio"],
        "close_pos": m["close_pos"],
        "range_atr": m["range"] / atr if atr > 0 else 0,
    }

def update_market_memory(context, breakout):
    """حافظه ساده رویدادمحور؛ شکست تأییدشده رنج قبلی را از معامله رنجی خارج می‌کند."""
    global market_memory
    rh, rl = context["range_high"], context["range_low"]
    if rh is None or rl is None:
        return

    old_high = market_memory.get("range_high")
    old_low = market_memory.get("range_low")
    if old_high is None or old_low is None:
        market_memory.update({
            "range_high": rh, "range_low": rl,
            "range_started": datetime.now(timezone.utc).isoformat(),
            "range_status": "ACTIVE",
            "breakout_direction": None, "breakout_time": None,
            "breakout_level": None, "failed_breakout": False,
        })
        return

    # تغییر محسوس جعبه در حالی که محدوده هنوز فعال است،
