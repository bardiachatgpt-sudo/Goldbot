"""تنظیمات عمومی و تعریف نمادها."""
import os

import pytz

TEHRAN = pytz.timezone("Asia/Tehran")

# تایم‌فریم TradingView: "1", "5", "15", "60", "240", "D" ...
TIMEFRAME = os.environ.get("TIMEFRAME", "5")
BARS = int(os.environ.get("BARS", "500"))          # تعداد کندل برای هر تحلیل
MIN_BARS = 60                                      # کمتر از این تحلیل نمی‌شود
CHART_BARS = 120                                   # تعداد کندل در تصویر نمودار

# زمینه روی TIMEFRAME (M5: اسپایک / کانال / رنج)، ماشه روی TRIGGER_TF (M1: ورود)
CONTEXT_TF = TIMEFRAME
TRIGGER_TF = os.environ.get("TRIGGER_TF", "1")
TRIGGER_BARS = int(os.environ.get("TRIGGER_BARS", "300"))   # تعداد کندل M1 در هر بررسی

# پیام‌هایی که برای همه (و کانال) فرستاده می‌شوند:
#   TRADE  ستاپ ورود، ورود، حد سود/ضرر، لغو
#   SPIKE  اسپایک M5 از رنج بیرون زد، منتظر پولبک باشید
#   اطلاعاتی M5 (پیش‌فرض خاموش): H1,H2,L1,L2,WEDGE,PIN,WEDGE_BO,RANGE_BO
# تغییرات چرخه همیشه برای کسانی که نماد را فالو کرده‌اند فرستاده می‌شود.
ALERT_SETUPS = {s.strip().upper() for s in
                os.environ.get("ALERT_SETUPS", "TRADE,SPIKE").split(",")
                if s.strip()}

# قیمت زنده برای سفارش‌ها و معامله‌های باز (ترتیب واقعی رسیدن به ورود / حد ضرر / حد سود)
LIVE_PRICES = os.environ.get("LIVE_PRICES", "1") not in ("0", "false", "no")

# ---------------------------------------------------------------- معامله
# pin    = نسخه‌ی اول (پیش‌فرض): پین‌بار M1 در لبه‌ی رنج M5 و اولین پولبک اسپایک، با زمینه‌ی Always In
# brooks = کندل سیگنال M5، H1/H2 در جهت روند، ورود دوم در رنج، حد ضرر ساختاری
STRATEGY = os.environ.get("STRATEGY", "pin").strip().lower()
if STRATEGY not in ("pin", "brooks"):
    STRATEGY = "pin"

# Always In (روند بدون اسپایک، از جزوه‌ی چینی فصل ۰۲) در چرخه‌ی M5.
# پیش‌فرض: خاموش برای pin (دقیقاً مثل نسخه‌ی اول؛ با روشن بودنش بک‌تست طلا از +7R به −5R رسید)،
# روشن برای brooks (که بر اساس آن طراحی شده). با ALWAYS_IN=1 یا 0 می‌شود هر کدام را تحمیل کرد.
_ALWAYS_IN_ENV = os.environ.get("ALWAYS_IN", "").strip()


# تأیید وج برای پین‌بار رنج (قاعده‌ی pin): فقط وقتی پین‌بار فشار سوم یک Wedge Bottom/Top است.
# پیش‌فرض خاموش تا بک‌تست روی چند جفت نشان بدهد بهتر است؛ بک‌تست همیشه هر دو را گزارش می‌کند.
WEDGE_FILTER = os.environ.get("WEDGE_FILTER", "0").strip() not in ("0", "false", "no", "")


def always_in_for(strategy=None):
    if _ALWAYS_IN_ENV:
        return _ALWAYS_IN_ENV not in ("0", "false", "no")
    return (strategy or STRATEGY) == "brooks"
RR = float(os.environ.get("RR", "2"))                 # ریسک به ریوارد
ORDER_BARS = int(os.environ.get("ORDER_BARS", "3"))   # سفارش/انتظار Key bar حداکثر این تعداد کندل M1
ARM_BARS = 20           # پین‌بار باید تا این تعداد کندل M1 بعد از تأیید بریک‌اوت بیاید
RANGE_EDGE = 0.25       # پین‌بار رنج: در ربع پایینی/بالایی رنج M5

# اسپرد پیش‌فرض (به واحد قیمت). هر کدام با متغیر محیطی SPREAD_<نماد> عوض می‌شود، مثلاً SPREAD_XAUUSD=0.25
DEFAULT_SPREADS = {
    "XAUUSD": 0.30,
    "EURUSD": 0.00012, "GBPUSD": 0.00015, "USDJPY": 0.015, "USDCHF": 0.00015,
    "USDCAD": 0.00018, "AUDUSD": 0.00014, "NZDUSD": 0.00018,
    "BTCUSD": 15.0,
}


def spread(sym):
    v = os.environ.get(f"SPREAD_{sym}")
    try:
        return float(v) if v else DEFAULT_SPREADS.get(sym, 0.0)
    except ValueError:
        return DEFAULT_SPREADS.get(sym, 0.0)


# هر هشدار یک عکس از همان لحظه هم دارد (کندل سیگنال پررنگ، خط روند/کانال، سطح‌ها)
ALERT_CHARTS = os.environ.get("ALERT_CHARTS", "1") not in ("0", "false", "no")

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
