"""ساختار بازار، نسخه‌ی ۳ (فقط نمایش) — بر اساس خط‌هایی که کاربر روی ۶ نمودار M5 کشید.

قاعده‌ها:
  • فقط قیمت بسته‌شدن (نمودار خطی)؛ سایه‌ها کف و سقف نمی‌سازند.
  • هر لحظه در یکی از سه حالتیم: اسپایک، کانال، رنج. هر چه اسپایک یا کانال نباشد رنج است.
  • کانال: سقف بالاتر + کف بالاتر (یا پایین‌تر + پایین‌تر). سقف/کف جدید باید واقعاً جدید باشد.
  • رنج چسبنده است: فقط با بریک‌اوتی تمام می‌شود که قیمت به رنج برنگردد.
    بیرون‌زدنی که برگردد (حتی اسپایک تند) جزو رنج است و لبه‌ی رنج را تا آنجا می‌برد.
  • اسپایک: پایه‌ی تند و صاف که از رنج بیرون می‌زند و برنمی‌گردد.
  • نگاه به گذشته: کانالی که رنجِ بعدش کامل خنثی‌اش کند، فقط یک پایه‌ی رنج بوده.
  • آخر نمودار موقت است: با کندل‌های بعدی ممکن است عوض شود.
مقیاس کف و سقف نسبت به ارتفاع کل نمودار است (مثل چشم تریدر روی همان ۵۰۰ کندل).
"""
import numpy as np

CFG = dict(
    T=0.10,             # کف/سقف: برگشت ≥ ۱۰٪ ارتفاع نمودار (روی بسته‌شدن‌ها)
    tol=0.15,           # بیرون‌زدن کمتر از ۱۵٪ ارتفاع رنج = هنوز داخل رنج
    ret=0.15,           # «برگشت به رنج» یعنی حداقل ۱۵٪ ارتفاع رنج به داخل
    mg=0.5,             # سقف/کف جدید کانال باید حداقل نصف T جلوتر باشد
    rt=0.9,             # کانالی که ۹۰٪ آن پس گرفته شود → جزو رنج
    spike_size=0.12,    # اسپایک: حرکت ≥ ۱۲٪ ارتفاع نمودار
    spike_eff=0.45,     # و صاف (حرکت خالص / مسیر)
    spike_speed=2.5,    # و تند (سرعت ≥ ۲.۵ برابر میانه‌ی تغییر هر کندل)
    spike_maxbars=25,
    first_leg=0.30,     # نمودار با حرکت جهت‌دار ≥ ۳۰٪ ارتفاع شروع شود → کانال/اسپایک، نه رنج
    deep=0.60,          # پولبکی که ≥ ۶۰٪ کل حرکت کانال را پس بگیرد → کانال تمام
)

NAMES = {("SPIKE", 1): "SPIKE ↑", ("SPIKE", -1): "SPIKE ↓", ("CHANNEL", 1): "BULL CHANNEL",
         ("CHANNEL", -1): "BEAR CHANNEL", ("RANGE", 0): "TRADING RANGE"}


def zigzag(c, T):
    """کف و سقف روی بسته‌شدن‌ها: [[idx, 'H'/'L', price]]، یکی در میان، برگشت ≥ T. آخری هنوز تأیید نشده."""
    n = len(c)
    piv = []
    d = 0
    ext = lo = hi = 0
    for i in range(1, n):
        if d == 0:
            if c[i] > c[hi]:
                hi = i
            if c[i] < c[lo]:
                lo = i
            if c[hi] - c[lo] >= T:
                if hi > lo:
                    piv.append([lo, "L", c[lo]]); d = 1; ext = hi
                else:
                    piv.append([hi, "H", c[hi]]); d = -1; ext = lo
        elif d == 1:
            if c[i] > c[ext]:
                ext = i
            elif c[ext] - c[i] >= T:
                piv.append([ext, "H", c[ext]]); d = -1; ext = i
        else:
            if c[i] < c[ext]:
                ext = i
            elif c[i] - c[ext] >= T:
                piv.append([ext, "L", c[ext]]); d = 1; ext = i
    if d:
        piv.append([ext, "H" if d == 1 else "L", c[ext]])
    return piv


def _is_spike(c, a, b, hgt, mad, cfg):
    n = b - a
    if n < 1 or n > cfg["spike_maxbars"]:
        return False
    mv = abs(c[b] - c[a])
    path = np.abs(np.diff(c[a:b + 1])).sum() + 1e-12
    return mv >= cfg["spike_size"] * hgt and mv / path >= cfg["spike_eff"] and mv / n >= cfg["spike_speed"] * mad


def _spike_head(c, a, b, hgt, mad, cfg):
    """اولِ پایه‌ی a→b یک اسپایک تند است (بعدش قیمت رنج می‌زند)؟ ته اسپایک یا None."""
    best, sgn = None, np.sign(c[b] - c[a])
    for j in range(a + 1, min(b, a + cfg["spike_maxbars"]) + 1):
        if np.sign(c[j] - c[a]) == sgn and _is_spike(c, a, j, hgt, mad, cfg):
            if best is None or (c[j] - c[best]) * sgn > 0:
                best = j
    return best


def segment(close, cfg=None):
    """close: بسته‌شدن‌ها. خروجی: (فازها، کف/سقف‌ها). هر فاز: {type, side, start, end[, prov]}؛
    فازها کل نمودار را بی‌فاصله پوشش می‌دهند."""
    cfg = dict(CFG, **(cfg or {}))
    c = np.asarray(close, float)
    n = len(c)
    hgt = float(c.max() - c.min()) or 1e-12
    mad = float(np.median(np.abs(np.diff(c)))) + 1e-12
    piv = zigzag(c, cfg["T"] * hgt)
    P = [[0, "S", c[0]]] + [p for p in piv if 0 < p[0] < n - 1] + [[n - 1, "E", c[n - 1]]]
    m = len(P)
    out = []

    def add(typ, side, s, e, **kw):
        if e <= s:
            return
        if out and out[-1]["type"] == typ and out[-1]["side"] == side and typ != "SPIKE":
            out[-1]["end"] = e
            out[-1].update(kw)
            return
        out.append(dict(type=typ, side=side, start=s, end=e, **kw))

    state, side, start, tstart = "RANGE", 0, 0, 0
    lo, hi = min(P[0][2], P[1][2]), max(P[0][2], P[1][2])
    last_h = last_l = None
    k = 1
    f = 2 if m >= 4 and abs(P[1][2] - P[0][2]) < cfg["T"] * hgt else 1      # اولین پایه‌ی واقعی (نه تکان اول)
    if state == "RANGE" and m >= f + 2 and abs(P[f][2] - P[f - 1][2]) >= cfg["first_leg"] * hgt:
        # نمودار با یک حرکت بزرگ شروع می‌شود (مثلاً صعود): کانال/اسپایک است، نه رنجی از اول نمودار تا اولین سقف
        state, side = "TREND", (1 if P[f][2] > P[f - 1][2] else -1)
        last_h, last_l = max(P[f - 1][2], P[f][2]), min(P[f - 1][2], P[f][2])
        if _is_spike(c, P[f - 1][0], P[f][0], hgt, mad, cfg):
            add("SPIKE", side, 0, P[f][0])
        k = f + 1
    if state == "RANGE" and m >= 5:                                   # شروع نمودار وسط یک کانال؟
        hs = [p[2] for p in P[1:5] if p[1] == "H"]
        ls = [p[2] for p in P[1:5] if p[1] == "L"]
        if len(hs) >= 2 and len(ls) >= 2 and (hs[1] - hs[0]) * (ls[1] - ls[0]) > 0:
            state, side = "TREND", (1 if hs[1] > hs[0] else -1)
            last_h = [p for p in P[1:3] if p[1] == "H"][-1][2]
            last_l = [p for p in P[1:3] if p[1] == "L"][-1][2]
    while k < m:
        p = P[k]
        nxt = P[k + 1] if k + 1 < m and P[k + 1][1] != "E" else None
        if state == "RANGE":
            bh = max(hi - lo, 1e-12)
            tol = cfg["tol"] * bh
            if lo - tol <= p[2] <= hi + tol:
                k += 1
                continue
            up = p[2] > hi
            if p[1] == "E":                      # آخر نمودار بیرون رنج: احتمالاً بریک‌اوت (هنوز معلوم نیست)
                add("RANGE", 0, start, p[0], prov="up" if up else "down")
                k += 1
                continue
            back = nxt is not None and ((nxt[2] < hi - cfg["ret"] * bh) if up else (nxt[2] > lo + cfg["ret"] * bh))
            if back:                             # بیرون زد و برگشت: هنوز رنج، لبه تا آنجا می‌رود
                hi, lo = max(hi, p[2]), min(lo, p[2])
                k += 1
                continue
            b0 = P[k - 1][0]                     # بریک‌اوت ماند: رنج تا شروع این پایه
            add("RANGE", 0, start, b0)
            side = 1 if up else -1
            if _is_spike(c, b0, p[0], hgt, mad, cfg):
                add("SPIKE", side, b0, p[0])
            else:
                j = _spike_head(c, b0, p[0], hgt, mad, cfg)
                if j is not None and p[0] - j >= 8:      # اسپایک اول پایه، بعد کانال
                    add("SPIKE", side, b0, j)
            state, tstart = "TREND", b0
            last_h = p[2] if up else P[k - 1][2]
            last_l = P[k - 1][2] if up else p[2]
            k += 1
            continue
        # ---- TREND (کانال)
        if p[1] == "E":
            s0 = out[-1]["end"] if out and out[-1]["type"] == "SPIKE" else tstart
            broke = p[2] < last_l if side == 1 else p[2] > last_h      # آخرین بسته‌شدن آن طرف آخرین کف/سقف کانال
            base = min(c[s0], last_l) if side == 1 else max(c[s0], last_h)
            top = last_h if side == 1 else last_l
            deep = abs(top - base) > 0 and (top - p[2]) * side >= cfg["deep"] * abs(top - base)
            e = P[k - 1][0]
            j = _spike_head(c, e, p[0], hgt, mad, cfg) if (broke or deep) and e > s0 else None
            if j is not None and p[0] - j >= 8:          # برگشت با اسپایک و بعد رنج (موقت)
                add("CHANNEL", side, s0, e)
                add("SPIKE", -side, e, j)
                add("RANGE", 0, j, p[0], prov="down" if side == 1 else "up")
                k += 1
                continue
            if broke and e > s0 and p[0] - e >= 2:
                add("CHANNEL", side, s0, e)              # کانال تا آخرین سقف/کف تمام شد؛ پایه‌ی آخر جدا (موقت)
                if _is_spike(c, e, p[0], hgt, mad, cfg):
                    add("SPIKE", -side, e, p[0])
                else:
                    add("CHANNEL", -side, e, p[0])
            else:
                add("CHANNEL", side, s0, p[0])
            k += 1
            continue
        with_trend = p[1] == ("H" if side == 1 else "L")
        if with_trend:
            mg = cfg["mg"] * cfg["T"] * hgt
            ok = p[2] > last_h + mg if side == 1 else p[2] < last_l - mg
        else:
            ok = p[2] > last_l if side == 1 else p[2] < last_h
            s0 = out[-1]["end"] if out and out[-1]["type"] == "SPIKE" else tstart
            base = min(c[s0], last_l) if side == 1 else max(c[s0], last_h)
            top = last_h if side == 1 else last_l
            if ok and abs(top - base) > 0 and abs(top - p[2]) >= cfg["deep"] * abs(top - base):
                ok = False                       # پولبک خیلی عمیق: کانال تمام شد
        if ok:
            if p[1] == "H":
                last_h = p[2]
            else:
                last_l = p[2]
            k += 1
            continue
        e = P[k - 1][0]                          # کانال تمام: رنج از آخرین سقف/کف کانال
        s0 = out[-1]["end"] if out and out[-1]["type"] == "SPIKE" else tstart
        add("CHANNEL", side, s0, e)
        state, start = "RANGE", e
        lo, hi = min(P[k - 1][2], p[2]), max(P[k - 1][2], p[2])
        j = _spike_head(c, e, p[0], hgt, mad, cfg)
        if j is not None and p[0] - j >= 8:      # برگشت با اسپایک تند و بعد رنج: اسپایک جدا، رنج بعد از آن
            add("SPIKE", -side, e, j)
            start = j
            lo, hi = float(c[j:p[0] + 1].min()), float(c[j:p[0] + 1].max())
        k += 1
    if state == "RANGE" and (not out or out[-1]["end"] < n - 1):
        add("RANGE", 0, start, n - 1)
    return _merge_tiny(_fold_retraced(out, c, cfg)), piv


def _fold_retraced(out, c, cfg):
    """کانالی که رنجِ بعدش ≥ rt آن را پس بگیرد، فقط پایه‌ای از رنج بوده."""
    changed = True
    while changed:
        changed = False
        for i, s in enumerate(out[:-1]):
            nx = out[i + 1]
            if s["type"] != "CHANNEL" or nx["type"] != "RANGE":
                continue
            mv = c[s["end"]] - c[s["start"]]
            if mv == 0:
                continue
            seg = c[nx["start"]:nx["end"] + 1]
            back = (c[s["end"]] - seg.min()) / mv if mv > 0 else (seg.max() - c[s["end"]]) / -mv
            if back >= cfg["rt"]:
                s.update(type="RANGE", side=0)
                changed = True
        merged = []
        for s in out:
            if merged and s["type"] == "RANGE" and merged[-1]["type"] == "RANGE":
                merged[-1]["end"] = s["end"]
                if "prov" in s:
                    merged[-1]["prov"] = s["prov"]
                else:
                    merged[-1].pop("prov", None)
            else:
                merged.append(s)
        out = merged
    return out


def _merge_tiny(out, min_bars=8):
    """تکه‌های خیلی کوتاه (غیر از اسپایک) به همسایه می‌چسبند؛ برای نمودار ۵۰۰ کندلی معنی ندارند."""
    out = [dict(s) for s in out]
    i = 0
    while i < len(out) and len(out) > 1:
        s = out[i]
        if s["type"] != "SPIKE" and s["end"] - s["start"] < min_bars:
            if i + 1 < len(out) and out[i + 1]["type"] != "SPIKE":
                out[i + 1]["start"] = s["start"]
            elif i > 0:
                out[i - 1]["end"] = s["end"]
            else:
                i += 1
                continue
            out.pop(i)
            i = max(i - 1, 0)
            continue
        i += 1
    merged = []
    for s in out:
        if merged and s["type"] == merged[-1]["type"] == "RANGE":
            merged[-1]["end"] = s["end"]
        else:
            merged.append(s)
    return merged


# ------------------------------------------------------------------ خط‌ها (مثل تریدر)
def _hull_edge(pts, upper, xs=None, seg=None):
    """ضلعی از پوسته‌ی محدب (بالا یا پایین) روی نقطه‌ها: خطی که دو کف/سقف را لمس می‌کند و همه یک طرفش‌اند.
    بین ضلع‌های بلند (≥ ۳۰٪ طول)، آن که به بسته‌شدن‌ها نزدیک‌تر است (مثل خطی که تریدر می‌کشد)."""
    pts = sorted(set(pts))
    if len(pts) < 2:
        return None
    hull = []
    for x, y in pts:
        while len(hull) >= 2:
            (x1, y1), (x2, y2) = hull[-2], hull[-1]
            cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
            if (cross >= 0) if upper else (cross <= 0):
                hull.pop()
            else:
                break
        hull.append((x, y))
    edges = list(zip(hull, hull[1:]))
    span = pts[-1][0] - pts[0][0]
    long_e = [e for e in edges if e[1][0] - e[0][0] >= 0.3 * span] or [max(edges, key=lambda e: e[1][0] - e[0][0])]

    def fit(e):
        (x1, y1), (x2, y2) = e
        sl = (y2 - y1) / (x2 - x1)
        return sl, y1 - sl * x1

    if xs is None:
        return fit(max(long_e, key=lambda e: e[1][0] - e[0][0]))

    def gap(e):
        sl, ic = fit(e)
        d = seg - (sl * xs + ic)
        d = d - (d.max() if upper else d.min())          # خط را تا آخرین بسته‌شدن بیرونی جابه‌جا کن
        return np.abs(d).mean()

    return fit(min(long_e, key=gap))


def lines(ph, c, piv):
    """خط‌های هر فاز: [(x0, y0, x1, y1, نقش)]. رنج: سقف و کف (افقی یا مثلثی)؛ کانال: خط روند + خط موازی."""
    a, b = ph["start"], ph["end"]
    seg = c[a:b + 1]
    xs = np.arange(a, b + 1)
    inside = [p for p in piv if a <= p[0] <= b]
    if ph["type"] == "RANGE":
        res = []
        bh = float(seg.max() - seg.min()) or 1e-12
        for upper, kind in ((True, "H"), (False, "L")):
            pts = [(p[0], p[2]) for p in inside if p[1] == kind]
            ext = seg.max() if upper else seg.min()
            e = _hull_edge(pts, upper, xs, seg) if len(pts) >= 2 else None
            if e:
                sl, ic = e
                y = sl * xs + ic
                off = (seg - y).max() if upper else (seg - y).min()     # هیچ بسته‌شدنی بیرون خط نماند
                ic += off
                if abs(sl) * (b - a) < 0.15 * bh:                        # تقریباً افقی → صاف
                    res.append((a, ext, b, ext, "edge"))
                else:
                    res.append((a, sl * a + ic, b, sl * b + ic, "edge"))
            else:
                res.append((a, ext, b, ext, "edge"))
        sl = [(r[3] - r[1]) for r in res]
        if sl[0] * sl[1] > 0:                    # هر دو لبه هم‌جهت کج: این مثلث نیست → دو خط افقی
            res = [(a, seg.max(), b, seg.max(), "edge"), (a, seg.min(), b, seg.min(), "edge")]
        return res
    if ph["type"] == "CHANNEL":
        bull = ph["side"] == 1
        kind = "L" if bull else "H"
        pts = [(p[0], p[2]) for p in inside if p[1] == kind] + [(a, c[a]), (b, c[b])]
        e = _hull_edge(pts, not bull, xs, seg)
        if not e:
            return []
        sl, ic = e
        y = sl * xs + ic
        ic += (seg - y).min() if bull else (seg - y).max()             # خط روند زیر/بالای همه‌ی بسته‌شدن‌ها
        par = (seg - (sl * xs + ic)).max() if bull else (seg - (sl * xs + ic)).min()
        return [(a, sl * a + ic, b, sl * b + ic, "trend"),
                (a, sl * a + ic + par, b, sl * b + ic + par, "parallel")]
    return []


def now_text(phases):
    if not phases:
        return "unclear"
    last = phases[-1]
    txt = NAMES[(last["type"], last["side"])]
    if last.get("prov") == "up":
        txt += " — probably breaking out UP (not confirmed yet)"
    elif last.get("prov") == "down":
        txt += " — probably breaking out DOWN (not confirmed yet)"
    else:
        txt += " (may still change with the next candles)"
    return txt


def render(sym, df, tf="M5", zoom=0):
    """PNG: کندل‌ها، مستطیل رنگی هر فاز، خط‌های رنج/کانال. (png, phases, now_text)
    zoom=k: ساختار روی همه‌ی کندل‌ها حساب می‌شود، ولی فقط k فاز آخر (حداقل ۸۰ کندل) بزرگ نشان داده می‌شود."""
    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt

    o, h, l, c = (df[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    n = len(c)
    phases, piv = segment(c)
    v0 = 0
    if zoom and phases:
        v0 = max(0, min(phases[-min(zoom, len(phases))]["start"] - 5, n - 80))
    hv, lv = h[v0:], l[v0:]
    fig, ax = plt.subplots(figsize=(22, 9), dpi=100)
    fig.patch.set_facecolor("#121214")
    ax.set_facecolor("#18181B")
    col = {"SPIKE": "#FBBF24", "RANGE": "#60A5FA", ("CHANNEL", 1): "#10B981", ("CHANNEL", -1): "#EF4444"}
    pad = (hv.max() - lv.min()) * 0.015
    for ph in phases:
        if ph["end"] < v0:
            continue
        a, b = ph["start"], ph["end"]
        cc = col[("CHANNEL", ph["side"])] if ph["type"] == "CHANNEL" else col[ph["type"]]
        top, bot = h[max(a, v0):b + 1].max(), l[max(a, v0):b + 1].min()
        ax.add_patch(patches.Rectangle((a - 0.5, bot - pad), b - a + 1, top - bot + 2 * pad,
                                       facecolor=cc, alpha=0.10, edgecolor=cc, lw=1.0, zorder=1))
        if b - max(a, v0) >= 12:                 # فازی که فقط لبه‌اش دیده می‌شود برچسب نمی‌گیرد
            ax.text(max(a, v0) + 1, top + pad * 1.3, NAMES[(ph["type"], ph["side"])], color=cc, fontsize=10,
                    fontweight="bold", zorder=6, va="bottom")
        for x0, y0, x1, y1, role in lines(ph, c, piv):
            ax.plot([x0, x1], [y0, y1], color=cc, lw=2.2 if role != "parallel" else 1.6,
                    ls="-" if role != "parallel" else "--", zorder=5)
    for i in range(v0, n):
        cl = "#10B981" if c[i] >= o[i] else "#EF4444"
        ax.vlines(i, l[i], h[i], color=cl, lw=0.8 if not zoom else 1.4, zorder=3)
        ax.add_patch(patches.Rectangle((i - 0.3, min(o[i], c[i])), 0.6, max(abs(c[i] - o[i]), 1e-9),
                                       color=cl, zorder=3))
    if hasattr(df.index, "tz_convert"):
        try:
            from .config import TEHRAN
            dates = df.index.tz_convert(TEHRAN)
            step = max(1, (n - v0) // 12)
            ax.set_xticks(range(v0, n, step))
            ax.set_xticklabels([d.strftime("%d %b %H:%M") for d in dates[v0::step]], rotation=30, fontsize=8)
            ax.set_xlabel("Tehran time", color="#9CA3AF")
        except Exception:
            pass
    now = now_text(phases)
    what = (f"zoom: last {min(zoom, len(phases))} structures ({n - v0} candles)" if zoom
            else f"last {n} candles · structure (closes only, like a line chart)")
    ax.set_title(f"{sym} {tf} · {what}\nNow: {now}", color="#F3F4F6", fontsize=13, fontweight="bold")
    ax.set_xlim(v0 - 2, n + 2)
    ax.set_ylim(lv.min() - pad * 3, hv.max() + pad * 6)
    ax.tick_params(colors="#9CA3AF")
    for s in ax.spines.values():
        s.set_color("#3F3F46")
    ax.grid(color="#27272A", lw=0.5)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#121214")
    plt.close(fig)
    return buf.getvalue(), phases, now


def swing_labels(piv):
    """هر سقف با سقف قبلی و هر کف با کف قبلی: HH / LH / HL / LL (اولی فقط H یا L)."""
    out = []
    last = {"H": None, "L": None}
    for i, t, p in piv:
        prev = last[t]
        if prev is None:
            tag = t
        elif t == "H":
            tag = "HH" if p > prev else "LH"
        else:
            tag = "HL" if p > prev else "LL"
        out.append((i, t, p, tag))
        last[t] = p
    return out


def render_line(sym, df, tf="M5"):
    """نمودار خطی (فقط بسته‌شدن‌ها) با همان فازها و خط‌ها، و هر سقف/کف با برچسب HH/LH/HL/LL.
    همان چیزی است که ساختار رویش ساخته شده، تا معلوم باشد دقیقاً کجا سقف و کف گرفته شده."""
    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    c = df["Close"].values.astype(float)
    n = len(c)
    phases, piv = segment(c)
    fig, ax = plt.subplots(figsize=(22, 9), dpi=100)
    fig.patch.set_facecolor("#121214")
    ax.set_facecolor("#18181B")
    col = {"SPIKE": "#FBBF24", "RANGE": "#60A5FA", ("CHANNEL", 1): "#10B981", ("CHANNEL", -1): "#EF4444"}
    span = c.max() - c.min()
    pad = span * 0.02
    for ph in phases:
        a, b = ph["start"], ph["end"]
        cc = col[("CHANNEL", ph["side"])] if ph["type"] == "CHANNEL" else col[ph["type"]]
        ax.axvspan(a, b, color=cc, alpha=0.07, zorder=0)
        ax.text(a + 1, c.max() + pad * 2.5, NAMES[(ph["type"], ph["side"])], color=cc, fontsize=10,
                fontweight="bold", va="bottom")
        for x0, y0, x1, y1, role in lines(ph, c, piv):
            ax.plot([x0, x1], [y0, y1], color=cc, lw=1.8 if role != "parallel" else 1.3,
                    ls="-" if role != "parallel" else "--", zorder=2)
    ax.plot(range(n), c, color="#E4E4E7", lw=1.2, zorder=3)
    tag_col = {"HH": "#10B981", "HL": "#10B981", "LH": "#EF4444", "LL": "#EF4444", "H": "#A1A1AA", "L": "#A1A1AA"}
    for i, t, p, tag in swing_labels(piv):
        cc = tag_col[tag]
        ax.plot(i, p, "o", color=cc, ms=6, zorder=5)
        ax.text(i, p + pad if t == "H" else p - pad, tag, color=cc, fontsize=10, fontweight="bold",
                ha="center", va="bottom" if t == "H" else "top", zorder=6)
    if hasattr(df.index, "tz_convert"):
        try:
            from .config import TEHRAN
            dates = df.index.tz_convert(TEHRAN)
            step = max(1, n // 12)
            ax.set_xticks(range(0, n, step))
            ax.set_xticklabels([d.strftime("%d %b %H:%M") for d in dates[::step]], rotation=30, fontsize=8)
            ax.set_xlabel("Tehran time", color="#9CA3AF")
        except Exception:
            pass
    ax.set_title(f"{sym} {tf} · line chart (closes) · the highs and lows the structure is built from\n"
                 f"HH/HL = higher high / higher low (green) · LH/LL = lower high / lower low (red) · "
                 f"a high or low counts after a {CFG['T']:.0%}-of-chart pullback",
                 color="#F3F4F6", fontsize=12, fontweight="bold")
    ax.set_xlim(-2, n + 2)
    ax.set_ylim(c.min() - pad * 3, c.max() + pad * 6)
    ax.tick_params(colors="#9CA3AF")
    for s in ax.spines.values():
        s.set_color("#3F3F46")
    ax.grid(color="#27272A", lw=0.5)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#121214")
    plt.close(fig)
    return buf.getvalue()
