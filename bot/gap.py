"""ستاپ گپ (روی M1).

گپ نزولی (فروش): کف کندل ۱ بالاتر از سقف کندل ۳، بدنه‌ی کندل ۲ با این فاصله هم‌پوشانی دارد، و هر سه کندل
نزولی (هم‌رنگ) هستند.
گپ صعودی (خرید): برعکس (سقف کندل ۱ پایین‌تر از کف کندل ۳، هر سه صعودی).
فیلتر ساختار M5 (اختیاری، allow): اگر حد سود ۱:۱ بیرون از جعبه‌ی ساختار M5 همان لحظه باشد، معامله گرفته نمی‌شود.
از بسته شدن کندل ۳ دنبال کردن شروع می‌شود: فروش وقتی قیمت حداقل ۱ پیپت بالاتر از سقف کندل قبلی برود
(ورود = سقف کندل قبلی + ۱ پیپت)؛ خرید وقتی ۱ پیپت پایین‌تر از کف کندل قبلی برود.
حد ضرر: ۱ پیپت آن طرف کندل ۱ (فروش: بالای سقفش)؛ حد سود ۱:۱.
یک معامله در هر لحظه. گپ همیشه سه کندل است: گپ‌های هم‌جهتی که بلافاصله پشت گپ اول ساخته می‌شوند (۲-۳-۴،
۳-۴-۵ …) نادیده گرفته می‌شوند؛ کندل ۱، جعبه و حد ضرر همان گپ اول است و دنبال کردن بعد از کندل ۳ آن شروع می‌شود.
گپ جدا یا خلاف جهت، جای قبلی را می‌گیرد.
باطل شدن گپ: فعلاً ندارد.
داخل هر کندل، ترتیب قیمت از شکل کندل: صعودی باز ← کف ← سقف ← بسته، نزولی باز ← سقف ← کف ← بسته.
"""
RR = 1.0


def pip(sym):
    """کوچک‌ترین واحد قیمت (پیپت)."""
    if sym in ("XAUUSD", "BTCUSD"):
        return 0.01
    if sym == "US30":
        return 0.1
    return 0.001 if "JPY" in sym else 0.00001


def find_gap(o, h, l, c, i, same_color=True):
    """گپ با کندل ۳ = i: -1 فروش، +1 خرید، 0 نیست. (لبه‌ی بالا، لبه‌ی پایین) گپ هم برمی‌گرداند.
    same_color: هر سه کندل گپ هم‌رنگ باشند (فروش: هر سه نزولی، خرید: هر سه صعودی)."""
    if i < 2:
        return 0, None
    b_lo, b_hi = min(o[i - 1], c[i - 1]), max(o[i - 1], c[i - 1])
    red = all(c[k] < o[k] for k in (i - 2, i - 1, i))
    green = all(c[k] > o[k] for k in (i - 2, i - 1, i))
    if l[i - 2] > h[i] and (red or not same_color):                                   # نزولی: فاصله‌ی بین سقف ۳ و کف ۱
        lo, hi = h[i], l[i - 2]
        if max(lo, b_lo) < min(hi, b_hi):
            return -1, (hi, lo)
    if h[i - 2] < l[i] and (green or not same_color):     # صعودی: فاصله‌ی بین سقف ۱ و کف ۳
        lo, hi = h[i - 2], l[i]
        if max(lo, b_lo) < min(hi, b_hi):
            return 1, (hi, lo)
    return 0, None


def _path(o, h, l, c):
    return [o, l, h, c] if c >= o else [o, h, l, c]


def _cross(path, level, up):
    """اولین جای مسیر که قیمت به level می‌رسد (up: از پایین به بالا). (قیمت اجرا، باقی مسیر) یا None."""
    if (path[0] >= level) if up else (path[0] <= level):
        return path[0], path
    for k in range(len(path) - 1):
        a, b = path[k], path[k + 1]
        if (a < level <= b) if up else (a > level >= b):
            return level, [level] + path[k + 1:]
    return None


def _exit(path, sl, tp, side):
    """اول حد ضرر یا حد سود؟ (نام، قیمت) یا None."""
    for k in range(len(path)):
        p = path[k]
        if (p >= sl) if side < 0 else (p <= sl):
            return "SL", sl
        if (p <= tp) if side < 0 else (p >= tp):
            return "TP", tp
        if k + 1 < len(path):
            a, b = p, path[k + 1]
            lo, hi = min(a, b), max(a, b)
            hit_sl, hit_tp = lo <= sl <= hi, lo <= tp <= hi
            if hit_sl and hit_tp:                          # هر دو در یک تکه: اول نزدیک‌تر
                return ("SL", sl) if abs(sl - a) <= abs(tp - a) else ("TP", tp)
            if hit_sl:
                return "SL", sl
            if hit_tp:
                return "TP", tp
    return None


def gap_heads(o, h, l, c, same_color=True):
    """همه‌ی گپ‌ها، مستقل از معامله‌ها: [(i1, side)]. گپ‌های زنجیره‌ای پشت‌سرهم (هم‌جهت) یک گپ حساب می‌شوند."""
    heads, last = [], {1: -10, -1: -10}
    for i in range(2, len(c)):
        side, _ = find_gap(o, h, l, c, i, same_color)
        if not side:
            continue
        if i - 2 > last[side]:                             # گپ تازه (نه ادامه‌ی زنجیره)
            heads.append((i - 2, side))
        last[side] = i
    return heads


def leg_number(heads, h, l, i1, side):
    """شماره‌ی لگ گپی که کندل ۱ آن i1 است: ۱ اگر در همین حرکت قبلش گپ هم‌جهتی نبوده، ۲ اگر یکی بوده و …
    حرکت (فروش) از بالاترین سقف بعد از آخرین گپ خلاف جهت شروع می‌شود؛ خرید: از پایین‌ترین کف."""
    opp = [k for k, sd in heads if sd == -side and k < i1]
    a = opp[-1] if opp else 0
    seg = h[a:i1 + 1] if side < 0 else l[a:i1 + 1]
    start = a + int(seg.argmax() if side < 0 else seg.argmin())
    return 1 + sum(1 for k, sd in heads if sd == side and start <= k < i1)


MAX_LEG = 2             # فقط لگ ۱ و ۲؛ لگ ۳ به بالا گرفته نمی‌شود


def _r(x):
    """گرد کردن سطح‌ها تا خطای اعشار کامپیوتر (مثلاً 1.09925 − 0.00001 = 1.0992399999…) ورودِ دقیقاً ۱ پیپتی را
    نیندازد؛ عدد گردشده همان عددی است که از داده خوانده می‌شود."""
    return round(x, 8)


WATCH_BEFORE = 3        # چند کندل قبل از کندل ۱ هم در جدول عکس


def trades(o, h, l, c, sym="XAUUSD", allow=None, same_color=True, skipped=None, max_leg=MAX_LEG, session_ok=None):
    """معامله‌های ستاپ گپ روی کندل‌ها (آرایه‌ها). هر معامله:
    {side, gap: (i1, i3), gap_hi, gap_lo, entry_i, entry, sl, tp, exit_i, exit, result, r}
    و آخری ممکن است باز (exit_i=None) یا گپ در انتظار ورود (entry_i=None) باشد.
    allow(i, side, entry, tp) → False یعنی ورود گرفته نشود (مثلاً حد سود بیرون از ساختار M5)؛ آن گپ کنار گذاشته
    می‌شود و اگر skipped یک لیست باشد، به آن اضافه می‌شود (با reason: "m5" یا "leg").
    max_leg: گپ‌هایی که لگشان بیشتر از این است گرفته نمی‌شوند (None/0 = همه‌ی لگ‌ها).
    session_ok(i) → False یعنی کندل ورود بیرون از سشن‌هاست (Off) و معامله گرفته نمی‌شود (reason "off").
    هر معامله watch هم دارد: وضعیت هر کندل از کمی قبل از کندل ۱ تا ورود [(i, سطح لازم یا None, [کدها])]
    کدها: open/exit (معامله‌ی دیگری باز بود)، nogap (گپی در انتظار نبود)، c1/c2/c3، chain، replace،
    miss (به سطح نرسید)، entry، badsl (ورود آن طرف حد ضرر می‌افتاد)، skip_m5، skip_leg، skip_off."""
    n = len(c)
    pp = pip(sym)
    heads = gap_heads(o, h, l, c, same_color)
    notes, lvls = [[] for _ in range(n)], [None] * n
    out, pending, open_t = [], None, None
    for i in range(n):
        if open_t is not None:                             # ۱) معامله‌ی باز
            path = _path(o[i], h[i], l[i], c[i])
            hit = _exit(path, open_t["sl"], open_t["tp"], open_t["side"])
            notes[i].append("exit" if hit else "open")
            if hit:
                open_t.update(exit_i=i, exit=hit[1], result=hit[0], r=RR if hit[0] == "TP" else -1.0)
                open_t = None
            continue
        if pending is None:
            notes[i].append("nogap")
        if pending is not None and i > pending["gap"][1]:  # ۲) دنبال کردن سقف/کف کندل قبلی
            s = pending["side"]
            lvl = _r(h[i - 1] + pp if s < 0 else l[i - 1] - pp)
            lvls[i] = lvl
            hit = _cross(_path(o[i], h[i], l[i], c[i]), lvl, up=s < 0)
            if not hit:
                notes[i].append("miss")
            if hit:
                entry, rest = hit
                i1 = pending["gap"][0]
                sl = _r(h[i1] + pp if s < 0 else l[i1] - pp)
                risk = abs(sl - entry)
                if not (risk > 0 and (sl - entry) * s < 0):
                    notes[i].append("badsl")
                if risk > 0 and (sl - entry) * s < 0:       # حد ضرر آن طرف درست ورود است
                    tp = _r(entry + s * RR * risk)
                    reason = None
                    if max_leg and pending.get("leg", 1) > max_leg:
                        reason = "leg"                     # لگ ۳ به بالا
                    elif session_ok is not None and not session_ok(i):
                        reason = "off"                     # بیرون از سشن‌ها: اسپرد بالا، کاربر معامله نمی‌کند
                    elif allow is not None and not allow(i, s, entry, tp):
                        reason = "m5"                      # حد سود بیرون از جعبه‌ی M5
                    if reason:
                        notes[i].append("skip_" + reason)
                        if skipped is not None:
                            skipped.append(dict(pending, entry_i=i, entry=entry, sl=sl, tp=tp, reason=reason))
                        pending = None
                        continue
                    t = dict(pending, entry_i=i, entry=entry, sl=sl, tp=tp, exit_i=None, exit=None,
                             result=None, r=None)
                    out.append(t)
                    notes[i].append("entry")
                    pending = None
                    hit2 = _exit(rest, sl, tp, s)
                    if hit2:
                        t.update(exit_i=i, exit=hit2[1], result=hit2[0], r=RR if hit2[0] == "TP" else -1.0)
                    else:
                        open_t = t
                    continue
        side, zone = find_gap(o, h, l, c, i, same_color)   # ۳) گپ تازه
        if side:
            if pending is not None and pending["side"] == side and i - 2 <= pending.get("chain", pending["gap"][1]):
                # گپ هم‌جهت که با گپ قبلی زنجیره است (۲-۳-۴، ۳-۴-۵ …): نادیده؛ گپ همیشه سه کندل است و
                # کندل ۱، جعبه و حد ضرر همان گپ اول می‌مانند
                pending["chain"] = i
                notes[i].append("chain")
            else:                                          # گپ جدا یا خلاف جهت: جای قبلی را می‌گیرد
                if pending is not None:
                    notes[i].append("replace")
                for k, code in ((i - 2, "c1"), (i - 1, "c2"), (i, "c3")):
                    notes[k].append(code)
                pending = {"side": side, "gap": (i - 2, i), "gap_hi": zone[0], "gap_lo": zone[1], "entry_i": None,
                           "leg": leg_number(heads, h, l, i - 2, side)}
    if pending is not None:
        out.append(pending)
    for t in out + (skipped or []):                         # وضعیت کندل‌های قبل از ورود، برای عکس
        if t.get("entry_i") is not None and "watch" not in t:
            a = max(0, t["gap"][0] - WATCH_BEFORE)
            t["watch"] = [(k, lvls[k], list(notes[k])) for k in range(a, t["entry_i"] + 1)]
    return out


def in_session(times):
    """session_ok(i): کندل i داخل توکیو، لندن یا نیویورک است (نه Off)."""
    from .config import session_of
    return lambda i: session_of(times[i]) != "Off"


def m5_target_filter(m5, times, window=500):
    """allow(i, side, entry, tp): حد سود باید داخل جعبه‌ی ساختار M5 همان لحظه باشد
    (فروش: بالای کف جعبه، خرید: زیر سقف جعبه). ساختار از `window` کندل M5 که تا آن لحظه بسته شده‌اند.
    times: زمان شروع کندل‌های تایم‌فریم پایین (M1). نتیجه‌ی هر کندل M5 کش می‌شود."""
    import numpy as np
    import pandas as pd

    from .mtf import _edges
    from .structure3 import segment
    step = pd.Timedelta(minutes=5)
    t5 = m5.index
    c5_all = m5["Close"].values.astype(float)
    h5_all, l5_all = m5["High"].values.astype(float), m5["Low"].values.astype(float)
    cache = {}

    def box(ts):
        k = int(t5.searchsorted(ts - step, side="right"))   # کندل‌های M5 که تا ts بسته شده‌اند: [k-window, k)
        if k not in cache:
            a = max(0, k - window)
            if k - a < 100:
                cache[k] = None
            else:
                c5, h5, l5 = c5_all[a:k], h5_all[a:k], l5_all[a:k]
                ph, piv = segment(c5)
                cache[k] = (ph[-1], c5, h5, l5, piv, t5[a:k])
        if cache[k] is None:
            return None
        ph, c5, h5, l5, piv, tt = cache[k]
        pos = (len(tt) - 1) + (ts - tt[-1]) / step
        up, lo = _edges(ph, c5, h5, l5, piv, np.array([pos]))
        return float(up[0]), float(lo[0])

    def allow(i, side, entry, tp):
        b = box(times[i])
        if b is None:
            return True
        top, bot = b
        return tp >= bot if side < 0 else tp <= top

    return allow
