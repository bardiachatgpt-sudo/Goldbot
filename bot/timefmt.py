"""زمان: تبدیل به وقت تهران و تشخیص سشن."""
import pytz

from .config import SESSIONS, TEHRAN

_SESS_TZ = {n: pytz.timezone(tz) for n, tz, a, b in SESSIONS}


def to_tehran(ts):
    return ts.tz_convert(TEHRAN).strftime("%Y-%m-%d %H:%M")


def to_tehran_short(ts):
    return ts.tz_convert(TEHRAN).strftime("%d %b %H:%M")


def fmt_gap(td):
    m = int(td.total_seconds() // 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def is_weekend(ts):
    """آخر هفته‌ی فارکس: جمعه 21:00 تا یکشنبه 21:00 به وقت UTC (فقط BTC در این بازه داده دارد)."""
    u = ts.tz_convert("UTC")
    wd, hr = u.weekday(), u.hour
    return (wd == 4 and hr >= 21) or wd == 5 or (wd == 6 and hr < 21)


def session_at(ts):
    if is_weekend(ts):
        return "Weekend"
    act = []
    for n, tz, a, b in SESSIONS:
        if a <= ts.tz_convert(_SESS_TZ[n]).hour < b:
            act.append(n)
    if not act:
        return "Off-hours"
    return " · ".join(act) + (" (overlap)" if len(act) > 1 else "")
