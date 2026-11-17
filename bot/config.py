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

# نمادهای دکمه‌ها: فقط طلا، ین ژاپن و یورو (خواست کاربر، ۱۷ نوامبر؛ با STRUCTURE_PAIRS در Render عوض می‌شود).
# بقیه در ALL_SYMBOLS می‌مانند تا اگر لازم شد با یک خط برگردند.
_SX = os.environ.get("STRUCTURE_PAIRS", "XAUUSD,USDJPY,EURUSD")
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


# سشن‌ها با ساعت محلی هر بازار (تغییر ساعت تابستانی خودکار): نام، منطقه‌ی زمانی، شروع، پایان
SESSIONS = [
    ("Tokyo", "Asia/Tokyo", 9, 18),
    ("London", "Europe/London", 8, 17),
    ("NY", "America/New_York", 8, 17),
]


def session_of(ts):
    """زمان (با منطقه‌ی زمانی) → «Tokyo»، «London»، «NY»، همپوشانی مثل «London+NY»، یا «Off» (بیرون هر سه)."""
    names = []
    for name, tz, a, b in SESSIONS:
        local = ts.tz_convert(tz)
        if local.weekday() < 5 and a <= local.hour < b:
            names.append(name)
    return "+".join(names) or "Off"


# بازه‌ی بک‌تست: از آخرین شروع یک سشن تا الان
PERIODS = {
    "T": ("🇯🇵 Since the last Tokyo open", "since the last Tokyo open", "Asia/Tokyo", 9),
    "L": ("🇬🇧 Since the last London open", "since the last London open", "Europe/London", 8),
    "N": ("🇺🇸 Since the last New York open", "since the last New York open", "America/New_York", 8),
}


def last_session_start(code, now):
    """آخرین شروع سشن (T/L/N) تا زمان now (هر دو با منطقه‌ی زمانی)، فقط روزهای کاری. خروجی به وقت UTC."""
    import pandas as pd
    _, _, tz, hour = PERIODS[code]
    local_now = now.tz_convert(tz)
    for back in range(0, 8):
        day = (local_now - pd.Timedelta(days=back)).normalize()
        start = day.replace(hour=hour)
        if start <= local_now and start.weekday() < 5:
            return start.tz_convert("UTC")
    return (now - pd.Timedelta(days=1)).tz_convert("UTC")
