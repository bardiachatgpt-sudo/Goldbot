"""تنظیمات ربات ساختار: نمادها و تایم‌فریم‌ها."""
import os

import pytz

TEHRAN = pytz.timezone("Asia/Tehran")

STRUCTURE_BARS = 500        # تعداد کندل هر عکس ساختار
MIN_BARS = 60               # کمتر از این ساختار کشیده نمی‌شود


def _chain(base):
    return [f"OANDA:{base}", f"FOREXCOM:{base}", f"FX:{base}"]


# نماد → فهرست منابع TradingView به ترتیب اولویت
ALL_SYMBOLS = {
    "XAUUSD": ["OANDA:XAUUSD", "FOREXCOM:XAUUSD", "FX_IDC:XAUUSD"],
    "EURUSD": _chain("EURUSD"),
    "GBPUSD": _chain("GBPUSD"),
    "USDJPY": _chain("USDJPY"),
    "USDCHF": _chain("USDCHF"),
    "USDCAD": _chain("USDCAD"),
    "AUDUSD": _chain("AUDUSD"),
    "NZDUSD": _chain("NZDUSD"),
    "US30": ["OANDA:US30USD", "FOREXCOM:DJI", "CAPITALCOM:US30", "TVC:DJI"],     # داوجونز (CFD تقریباً ۲۳ ساعته)
}

# نمادهای دکمه‌ها: طلا، ماژورها و داوجونز (با STRUCTURE_PAIRS در Render عوض می‌شود)
_SX = os.environ.get("STRUCTURE_PAIRS", "XAUUSD,EURUSD,GBPUSD,USDJPY,USDCHF,USDCAD,AUDUSD,NZDUSD,US30")
STRUCTURE_SYMBOLS = [s for s in (p.strip().upper() for p in _SX.split(",")) if s in ALL_SYMBOLS] or ["XAUUSD"]

# تایم‌فریم TradingView → نام
TIMEFRAMES = {"1": "M1", "5": "M5", "15": "M15", "30": "M30", "60": "H1", "240": "H4", "D": "D1"}

FLAGS = {
    "XAUUSD": "🥇🇺🇸",
    "EURUSD": "🇪🇺🇺🇸",
    "GBPUSD": "🇬🇧🇺🇸",
    "USDJPY": "🇺🇸🇯🇵",
    "USDCHF": "🇺🇸🇨🇭",
    "USDCAD": "🇺🇸🇨🇦",
    "AUDUSD": "🇦🇺🇺🇸",
    "NZDUSD": "🇳🇿🇺🇸",
    "US30": "🇺🇸📊",
}


def label(name):
    return f"{FLAGS.get(name, '')} {name}".strip()
