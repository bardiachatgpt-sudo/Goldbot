"""ستاپ گپ (روی M1).

گپ نزولی (فروش): کف کندل ۱ بالاتر از سقف کندل ۳، و بدنه‌ی کندل ۲ با این فاصله هم‌پوشانی دارد.
گپ صعودی (خرید): برعکس (سقف کندل ۱ پایین‌تر از کف کندل ۳).
از بسته شدن کندل ۳ دنبال کردن شروع می‌شود: فروش وقتی قیمت حداقل ۱ پیپت بالاتر از سقف کندل قبلی برود
(ورود = سقف کندل قبلی + ۱ پیپت)؛ خرید وقتی ۱ پیپت پایین‌تر از کف کندل قبلی برود.
حد ضرر: ۱ پیپت آن طرف کندل ۱ (فروش: بالای سقفش)؛ حد سود ۱:۱.
یک معامله در هر لحظه؛ گپ تازه قبل از ورود، جای گپ قبلی را می‌گیرد. باطل شدن گپ: فعلاً ندارد.
داخل هر کندل، ترتیب قیمت از شکل کندل: صعودی باز ← کف ← سقف ← بسته، نزولی باز ← سقف ← کف ← بسته.
"""
RR = 1.0


def pip(sym):
    """کوچک‌ترین واحد قیمت (پیپت)."""
    if sym == "XAUUSD":
        return 0.01
    if sym == "US30":
        return 0.1
    return 0.001 if "JPY" in sym else 0.00001


def find_gap(o, h, l, c, i):
    """گپ با کندل ۳ = i: -1 فروش، +1 خرید، 0 نیست. (لبه‌ی بالا، لبه‌ی پایین) گپ هم برمی‌گرداند."""
    if i < 2:
        return 0, None
    b_lo, b_hi = min(o[i - 1], c[i - 1]), max(o[i - 1], c[i - 1])
    if l[i - 2] > h[i]:                                   # نزولی: فاصله‌ی بین سقف ۳ و کف ۱
        lo, hi = h[i], l[i - 2]
        if max(lo, b_lo) < min(hi, b_hi):
            return -1, (hi, lo)
    if h[i - 2] < l[i]:                                   # صعودی: فاصله‌ی بین سقف ۱ و کف ۳
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


def trades(o, h, l, c, sym="XAUUSD"):
    """معامله‌های ستاپ گپ روی کندل‌ها (آرایه‌ها). هر معامله:
    {side, gap: (i1, i3), gap_hi, gap_lo, entry_i, entry, sl, tp, exit_i, exit, result, r}
    و آخری ممکن است باز (exit_i=None) یا گپ در انتظار ورود (entry_i=None) باشد."""
    n = len(c)
    pp = pip(sym)
    out, pending, open_t = [], None, None
    for i in range(n):
        if open_t is not None:                             # ۱) معامله‌ی باز
            path = _path(o[i], h[i], l[i], c[i])
            hit = _exit(path, open_t["sl"], open_t["tp"], open_t["side"])
            if hit:
                open_t.update(exit_i=i, exit=hit[1], result=hit[0], r=RR if hit[0] == "TP" else -1.0)
                open_t = None
            continue
        if pending is not None and i > pending["gap"][1]:  # ۲) دنبال کردن سقف/کف کندل قبلی
            s = pending["side"]
            lvl = h[i - 1] + pp if s < 0 else l[i - 1] - pp
            hit = _cross(_path(o[i], h[i], l[i], c[i]), lvl, up=s < 0)
            if hit:
                entry, rest = hit
                i1 = pending["gap"][0]
                sl = h[i1] + pp if s < 0 else l[i1] - pp
                risk = abs(sl - entry)
                if risk > 0 and (sl - entry) * s < 0:       # حد ضرر آن طرف درست ورود است
                    tp = entry + s * RR * risk
                    t = dict(pending, entry_i=i, entry=entry, sl=sl, tp=tp, exit_i=None, exit=None,
                             result=None, r=None)
                    out.append(t)
                    pending = None
                    hit2 = _exit(rest, sl, tp, s)
                    if hit2:
                        t.update(exit_i=i, exit=hit2[1], result=hit2[0], r=RR if hit2[0] == "TP" else -1.0)
                    else:
                        open_t = t
                    continue
        side, zone = find_gap(o, h, l, c, i)               # ۳) گپ تازه (جای قبلی را می‌گیرد)
        if side:
            pending = {"side": side, "gap": (i - 2, i), "gap_hi": zone[0], "gap_lo": zone[1], "entry_i": None}
    if pending is not None:
        out.append(pending)
    return out
