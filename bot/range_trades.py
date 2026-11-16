"""قاعده‌ی رنج کاربر (یکی از سه پایه‌اش) روی M5 — فعلاً فقط بک‌تست.

۱) رنج با ساختار نسخه‌ی ۳ (bot/structure3.py) تشخیص داده می‌شود، فقط با ۵۰۰ کندل M5 که تا همان لحظه بسته
   شده‌اند (بدون نگاه به آینده). فاز آخر باید رنج باشد، حداقل MIN_RANGE_BARS کندل، و «احتمالاً بریک‌اوت» نباشد.
۲) کف رنج خرید، سقف رنج فروش: پین‌بار M5 که سایه‌اش در ربع پایینی (خرید) یا بالایی (فروش) رنج است.
۳) ورود: باز شدن کندل بعد از پین‌بار (پیش‌فرض، confirm="none").
   با confirm="key": اول Key bar هم‌جهت تا ORDER_BARS کندل بعد از پین‌بار (اگر قبلش قیمت از سایه‌ی پین‌بار
   رد شود، لغو)، ورود در باز شدن کندل بعد از Key bar.
۴) حد ضرر: نصف عرض رنج (+ اسپرد) — از قیمت ورود (پیش‌فرض) یا از لبه‌ی رنج (stop_from="edge").
۵) حد سود: لبه‌ی مقابل رنج (خرید در کف → سقف رنج).
یک معامله در هر لحظه. داخل هر کندل ترتیب قیمت از شکل کندل (مثل بقیه‌ی بک‌تست‌ها).

entry="touch" (قاعده‌ی اصلی کاربر، بدون پین‌بار): قیمت به کف رنج برسد → خرید روی همان کف،
به سقف برسد → فروش روی همان سقف (سفارش Limit روی لبه). رنج و لبه‌هایش از کندل‌های بسته‌شده تا کندل قبل.
حد ضرر و حد سود مثل بالا.
"""
import numpy as np
import pandas as pd

from .config import ORDER_BARS, spread
from .structure3 import lines, segment
from .trades_pin import candle_path, walk

WINDOW = 500            # همان ۵۰۰ کندلی که دکمه‌ی 📐 Structure نشان می‌دهد
MIN_RANGE_BARS = 20     # رنج کوتاه‌تر از این هنوز «تشخیص داده نشده»
EDGE = 0.25             # سایه‌ی پین‌بار در ربع پایینی/بالایی رنج


def range_at(close, t, window=WINDOW):
    """رنجِ فاز آخر با کندل‌های تا t (شامل t): (سقف، کف، طول، جهت حرکت قبل از رنج) یا None.
    جهت قبل از رنج: +1 اگر فاز قبلی کانال/اسپایک صعودی بوده، -1 نزولی، 0 اگر نبوده."""
    a = max(0, t - window + 1)
    c = np.asarray(close[a:t + 1], float)
    if len(c) < 100:
        return None
    phases, piv = segment(c)
    ph = phases[-1]
    if ph["type"] != "RANGE" or ph.get("prov") or ph["end"] - ph["start"] < MIN_RANGE_BARS:
        return None
    (_, _, x1, top, _), (_, _, _, bot, _) = lines(ph, c, piv)     # مقدار خط‌ها در آخرین کندل
    if top <= bot:
        return None
    prev = phases[-2]["side"] if len(phases) >= 2 else 0
    return float(top), float(bot), ph["end"] - ph["start"], int(prev)


def run(sym, m5, start=None, stop_from="entry", confirm="none", entry="pin", with_trend=False,
        rr=None, cache=None):
    """رویدادها با همان قالب بقیه‌ی بک‌تست‌ها (TRADE_PENDING / OPEN / CLOSED / CANCELLED).

    rr: None = حد سود لبه‌ی مقابل رنج؛ عدد = حد سود ثابت rr × ریسک (۱ یعنی ۱:۱، ۲ یعنی ۱:۲).
    cache: dict مشترک برای رنج هر کندل، وقتی چند نسخه روی همان داده اجرا می‌شوند.
    """
    from .strategy import analyze
    d = analyze(m5, cycle=False)["df"]
    o, h, l, c = (d[k].values.astype(float) for k in ("open", "high", "low", "close"))
    cache = {} if cache is None else cache

    def rng_at(t):
        if t not in cache:
            cache[t] = range_at(c, t)
        return cache[t]
    pin_bar, key_bar = d["pin_bar"].values.astype(int), d["key_bar"].values.astype(int)
    times = list(d["date"])
    sp = spread(sym)
    n = len(d)
    events, pending, open_t = [], None, None

    def open_trade(setup, i, price=None, at=None):
        """ورود در باز شدن کندل i+1 (یا با price در کندل at). رویداد ورود، یا لغو اگر جایی تا لبه‌ی مقابل نمانده."""
        nonlocal open_t
        s = setup["side"]
        k = i + 1 if at is None else at
        entry = (o[k] if price is None else price) + (sp if s > 0 else 0.0)   # خرید با Ask
        top, bot = setup["range_high"], setup["range_low"]
        half = (top - bot) / 2
        ref = entry if stop_from == "entry" else (bot if s > 0 else top)
        sl = ref - half - sp if s > 0 else ref + half + sp
        tp = (top if s > 0 else bot) if rr is None else entry + s * rr * abs(entry - sl)
        if (tp - entry) * s <= 0:                                       # جایی تا لبه‌ی مقابل نمانده
            return ev("TRADE_CANCELLED", setup, i, c[i], reason="no_room")
        open_t = {**setup, "entry": float(entry), "sl": float(sl), "tp": float(tp), "risk": float(abs(entry - sl)),
                  "opened": times[k], "opened_i": k, "_fresh": True, "signal_time": times[i]}
        return ev("TRADE_OPEN", open_t, i, entry)

    def ev(kind, t, i, price, **extra):
        return {**t, **extra, "kind": kind, "sym": sym, "setup": "TRADE", "mode": "RANGE",
                "time": times[i] + pd.Timedelta(minutes=5), "price": float(price), "strategy": "range3"}

    def exits(i, path):
        """حد ضرر / حد سود معامله‌ی باز روی مسیر قیمت کندل i."""
        nonlocal open_t
        s = open_t["side"]
        hit = walk(path, {"SL": (open_t["sl"], -s), "TP": (open_t["tp"], s)})
        if hit:
            name = hit[0]
            lvl = open_t["sl"] if name == "SL" else open_t["tp"]
            r = (lvl - open_t["entry"]) * s / open_t["risk"]
            events.append(ev("TRADE_CLOSED", open_t, i, lvl, result=name, r=round(r, 2), exit=lvl,
                             bars=i - open_t["opened_i"]))
            open_t = None

    for i in range(n):
        if start is not None and times[i] < start:
            continue
        # ۱) معامله‌ی باز: حد ضرر / حد سود روی مسیر این کندل
        if open_t is not None:
            path = candle_path(o[i], h[i], l[i], c[i])
            if open_t.pop("_fresh", False):
                path = [open_t["entry"]] + path[1:]
            exits(i, path)
            continue
        # ۱ب) بدون پین‌بار: رسیدن قیمت به کف/سقف رنج (لبه‌ها از کندل‌های تا i-1)
        if entry == "touch":
            rng = rng_at(i - 1) if i > 0 else None
            if rng is None:
                continue
            top, bot, length, prev = rng
            levels = {"BUY": (bot, -1), "SELL": (top, 1)}
            if with_trend and prev:                    # بعد از ریزش فقط فروش در سقف، بعد از صعود فقط خرید در کف
                levels.pop("BUY" if prev < 0 else "SELL")
            if not levels:
                continue
            hit = walk(candle_path(o[i], h[i], l[i], c[i]), levels)
            if not hit:
                continue
            name, price, rest = hit
            setup = {"side": 1 if name == "BUY" else -1, "range_high": top, "range_low": bot, "range_bars": length,
                     "before": prev}
            events.append(ev("TRADE_PENDING", setup, i, price))
            e = open_trade(setup, i, price=price, at=i)
            events.append(e)
            if open_t is not None:                     # بقیه‌ی همین کندل بعد از ورود
                open_t.pop("_fresh", None)
                exits(i, rest)
            continue
        # ۲) منتظر Key bar
        if pending is not None:
            s, pin = pending["side"], pending["pin"]
            pending["waited"] += 1
            if (l[i] < pin["low"]) if s > 0 else (h[i] > pin["high"]):
                events.append(ev("TRADE_CANCELLED", pending, i, c[i], reason="tail"))
                pending = None
            elif key_bar[i] == s:
                if i + 1 >= n:
                    break
                events.append(open_trade(pending, i))
                pending = None
            elif pending["waited"] >= ORDER_BARS:
                events.append(ev("TRADE_CANCELLED", pending, i, c[i], reason="expired"))
                pending = None
            continue
        # ۳) پین‌بار در لبه‌ی رنج
        s = pin_bar[i]
        if not s:
            continue
        rng = rng_at(i)
        if rng is None:
            continue
        top, bot, length, prev = rng
        if with_trend and prev and s != prev:
            continue
        zone = EDGE * (top - bot)
        if (s > 0 and l[i] <= bot + zone) or (s < 0 and h[i] >= top - zone):
            setup = {"side": int(s), "waited": 0, "range_high": top, "range_low": bot, "range_bars": length,
                     "pin": {"time": times[i], "high": float(h[i]), "low": float(l[i]), "close": float(c[i])}}
            events.append(ev("TRADE_PENDING", setup, i, c[i]))
            if confirm == "key":
                pending = setup
            elif i + 1 < n:
                events.append(open_trade(setup, i))
    for e in events:
        e.pop("_fresh", None)
    return events
