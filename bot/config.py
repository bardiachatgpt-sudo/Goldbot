"""تنظیمات عمومی و تعریف نمادها."""
import os

import pytz

TEHRAN = pytz.timezone("Asia/Tehran")

# تایم‌فریم TradingView: "1", "5", "15", "60", "240", "D" ...
TIMEFRAME = os.environ.get("TIMEFRAME", "5")
BARS = int(os.environ.get("BARS", "500"))          # تعداد کندل برای هر تحلیل
MIN_BARS = 60                                      # کمتر از این تحلیل نمی‌شود
CHART_BARS = 120                                   # تعداد کندل در تصویر نمودار

# بریک‌اوت چندتایم‌فریمی: زمینه روی TIMEFRAME (M5)، ماشه روی TRIGGER_TF (M1)
CONTEXT_TF = TIMEFRAME
TRIGGER_TF = os.environ.get("TRIGGER_TF", "1")
TRIGGER_BARS = int(os.environ.get("TRIGGER_BARS", "300"))   # تعداد کندل M1 در هر بررسی
HOLD_BARS = 10          # اگر قیمت این تعداد کندل M1 بیرون سطح بماند → تأیید
BO_COOLDOWN = 15        # بعد از پایان یک تلاش، تا این تعداد کندل M1 تلاش جدید روی همان رنج شروع نشود

# ستاپ‌هایی که هشدار زنده می‌فرستند:
#   روی M5: H1,H2,L1,L2,WEDGE,PIN و (بدون M1) WEDGE_BO,RANGE_BO
#   M5→M1: MTF_BO  (آماده باش / تأیید شد / شکست خورد)
ALERT_SETUPS = {s.strip().upper() for s in
                os.environ.get("ALERT_SETUPS", "H2,L2,WEDGE,PIN,MTF_BO").split(",")
                if s.strip()}

# کانال یا گروه تلگرام که هشدارها به آن هم فرستاده می‌شود (مثلاً @mychannel یا -100...)
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()

STATE_FILE = "bot_state.json"

WORKERS = 5             # تعداد نمادهایی که هم‌زمان دریافت می‌شوند


def _chain(base):
    return [f"OANDA:{base}", f"FOREXCOM:{base}", f"FX:{base}"]


# نماد → فهرست منابع TradingView به ترتیب اولویت
SYMBOLS = {
    "XAUUSD": ["OANDA:XAUUSD", "FOREXCOM:XAUUSD", "FX_IDC:XAUUSD"],
    "EURUSD": _chain("EURUSD"),
    "GBPUSD": _chain("GBPUSD"),
    "USDJPY": _chain("USDJPY"),
    "USDCHF": _chain("USDCHF"),
    "USDCAD": _chain("USDCAD"),
    "AUDUSD": _chain("AUDUSD"),
    "NZDUSD": _chain("NZDUSD"),
    "BTCUSD": ["BINANCE:BTCUSDT", "COINBASE:BTCUSD"],
}

FLAGS = {
    "XAUUSD": "🥇🇺🇸",
    "EURUSD": "🇪🇺🇺🇸",
    "GBPUSD": "🇬🇧🇺🇸",
    "USDJPY": "🇺🇸🇯🇵",
    "USDCHF": "🇺🇸🇨🇭",
    "USDCAD": "🇺🇸🇨🇦",
    "AUDUSD": "🇦🇺🇺🇸",
    "NZDUSD": "🇳🇿🇺🇸",
    "BTCUSD": "₿🇺🇸",
}

# تعداد رقم اعشار قیمت؛ نمادهای ذکرنشده: ین 3 رقم، بقیه 5 رقم
DECIMALS = {
    "BTCUSD": 0,
    "XAUUSD": 2,
}

# سشن‌ها: ساعت محلی هر بازار (تقریبی؛ تغییر ساعت تابستانی خودکار اعمال می‌شود)
SESSIONS = [
    ("Sydney", "Australia/Sydney", 7, 16),
    ("Tokyo", "Asia/Tokyo", 9, 18),
    ("London", "Europe/London", 8, 17),
    ("New York", "America/New_York", 8, 17),
]

_TF_NAMES = {"1": "M1", "3": "M3", "5": "M5", "15": "M15", "30": "M30",
             "60": "H1", "120": "H2", "240": "H4", "D": "D1", "1D": "D1", "W": "W1"}


def tf_label(tf=None):
    tf = tf or TIMEFRAME
    return _TF_NAMES.get(tf, tf)


def bar_delta(tf=None):
    """طول هر کندل؛ زمان TradingView شروع کندل است و پیام‌ها زمان بسته‌شدن را نشان می‌دهند."""
    import pandas as pd
    tf = (tf or TIMEFRAME).upper()
    if tf.isdigit():
        return pd.Timedelta(minutes=int(tf))
    num = int(tf[:-1] or 1)
    return pd.Timedelta(days=num * {"D": 1, "W": 7}.get(tf[-1], 1))


def label(name):
    return f"{FLAGS.get(name, '')} {name}".strip()


def decimals(name):
    if name in DECIMALS:
        return DECIMALS[name]
    return 3 if "JPY" in name else 5
