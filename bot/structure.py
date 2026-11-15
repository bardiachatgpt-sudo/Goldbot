"""ساختار بازار با خط‌هایی که خود تریدر می‌کشد (فقط نمایش؛ به معامله‌ها کاری ندارد).

- سوئینگ: سقف/کفی که قیمت بعدش حداقل REV کندل متوسط از آن برگشته (لرزش‌های ریز حساب نمی‌شوند)
- 🚀 اسپایک: یک حرکت تند و یک‌طرفه که از ساختار قبلی بیرون می‌زند: بیرون محدوده‌ی ۲۰ کندل قبل از
     شروعش بسته می‌شود، حداقل SPIKE_SIZE کندل متوسط، سریع، بیشتر کندل‌ها هم‌جهت، بدون پولبک
- 📈 کانال صعودی: دو کف آخر بالاروند و دو سقف آخر بالاروند — خط روند از کف ۱ به کف ۲، خط موازی از
     بلندترین سقف بین آن‌ها. 📉 کانال نزولی برعکس.
- 📦 رنج: بقیه حالت‌ها (خط‌ها تقریباً صاف یا هم‌جهت نیستند) — سقف و کف از دو سقف و دو کف آخر
- خط‌ها تا وقتی کندلی بیش از TOL کندل متوسط آن طرفشان بسته نشده ثابت می‌مانند (سایه‌ها مهم نیستند)
- بعد از شکستن، تا وقتی دو کف و دو سقف تازه شکل نگرفته، ساختار نامشخص است

هر فاز از اولین سوئینگی شروع می‌شود که خطش از آن کشیده شده (همان‌طور که تریدر روی نمودار می‌بیند).
"""
import numpy as np

AVG_N = 20
REV = 1.5           # سوئینگ: برگشت حداقل ۱.۵ کندل متوسط
SPIKE_SIZE = 3.0    # اسپایک: حداقل ۳ کندل متوسط ...
SPIKE_SPEED = 0.8   # ... با سرعت حداقل ۰.۸ کندل متوسط در هر کندل
SPIKE_SAME = 0.7    # ... و حداقل ۷۰٪ کندل‌ها هم‌جهت
FLAT = 1.0          # دو کف (یا دو سقف) با اختلاف کمتر از یک کندل متوسط = هم‌سطح
TOL = 0.5           # شکستن خط: بسته‌شدن بیش از نیم کندل متوسط آن طرف خط
BREAKOUT_N = 20     # اسپایک = بریک‌اوت: بیرون محدوده‌ی ۲۰ کندل قبل از شروعش بسته شود

# ---- نسخه‌ی ۲ (v2=True): رفتار کندل‌ها هم، نه فقط خط‌ها.
# روی داده‌ی واقعی کنار نسخه‌ی ۱ مقایسه شد و نسخه‌ی ۱ بهتر بود؛ در ربات استفاده نمی‌شود و فقط برای امتحان
# ایده‌های جدا در آینده نگه داشته شده.
V2_SPIKE_BODY = 0.55     # اسپایک: میانگین بدنه ≥ ۵۵٪ کندل (ماروبوزو) ...
V2_SPIKE_OVERLAP = 0.40  # ... و میانگین همپوشانی با کندل قبل ≤ ۴۰٪
V2_STRONG = 1.0          # شکستن خط: یک بسته‌شدن ≥ یک کندل متوسط آن طرف خط، یا دو بسته‌شدن پشت‌سرهم
V2_RANGE_N = 20          # رنج از روی رفتار: در ۲۰ کندل آخر ...
V2_RANGE_EFF = 0.15      # ... پیشرفت خالص ≤ ۱۵٪ مسیر طی‌شده ...
V2_RANGE_OVERLAP = 0.45  # ... و میانگین همپوشانی ≥ ۴۵٪
V2_SIDEWAYS = 5          # گذار کانال → رنج: ۵ کندل افقی ...
V2_SIDEWAYS_EFF = 0.35   # ... (پیشرفت خالص ≤ ۳۵٪) و بعد سقف/کف تازه‌ای که بلافاصله برمی‌گردد


def _overlap(h, l):
    """همپوشانی هر کندل با کندل قبل، نسبت به اندازه‌ی خودش (اسپایک ≈ ۰، رنج زیاد)."""
    ov = np.zeros(len(h))
    for t in range(1, len(h)):
        r = max(h[t] - l[t], 1e-12)
        ov[t] = max(0.0, min(h[t], h[t - 1]) - max(l[t], l[t - 1])) / r
    return ov


def _efficiency(c, a, b):
    """پیشرفت خالص / مسیر طی‌شده بین a و b (۱ = کاملاً یک‌طرفه، ۰ = درجا)."""
    path = np.abs(np.diff(c[a:b + 1])).sum()
    return abs(c[b] - c[a]) / path if path > 0 else 0.0


def _avg(h, l):
    r = h - l
    out = np.empty(len(r))
    for i in range(len(r)):
        w = r[max(0, i - AVG_N):i] if i >= 5 else r[:5]
        out[i] = w.mean() if len(w) else r[i]
    return out


def zigzag(h, l, avg):
    """سوئینگ‌ها با تأیید (فقط گذشته): [(اندیس، 'H' یا 'L'، قیمت، اندیس تأیید)].

    یک سقف وقتی سوئینگ است که قیمت بعدش حداقل REV کندل متوسط پایین آمده باشد (و برعکس برای کف)."""
    n = len(h)
    piv = []
    d, hi_i, lo_i, ext = 0, 0, 0, 0
    for i in range(1, n):
        if d == 0:                                   # هنوز جهت اول معلوم نیست
            if h[i] > h[hi_i]:
                hi_i = i
            if l[i] < l[lo_i]:
                lo_i = i
            if h[hi_i] - l[lo_i] >= REV * avg[i]:
                if lo_i < hi_i:
                    piv.append((lo_i, "L", float(l[lo_i]), i))
                    d, ext = 1, hi_i
                else:
                    piv.append((hi_i, "H", float(h[hi_i]), i))
                    d, ext = -1, lo_i
            continue
        if d == 1:                                   # بالا می‌رویم: دنبال سقف
            if h[i] >= h[ext]:
                ext = i
            elif h[ext] - l[i] >= REV * avg[i]:
                piv.append((ext, "H", float(h[ext]), i))
                d = -1
                ext = min(range(ext + 1, i + 1), key=lambda k: l[k])
        else:                                        # پایین می‌رویم: دنبال کف
            if l[i] <= l[ext]:
                ext = i
            elif h[i] - l[ext] >= REV * avg[i]:
                piv.append((ext, "L", float(l[ext]), i))
                d = 1
                ext = max(range(ext + 1, i + 1), key=lambda k: h[k])
    return piv


def detect(o, h, l, c, v2=False):
    """فازها: [{type: SPIKE/CHANNEL/RANGE, side, start, end, lines}] و حالت هر کندل.

    v2=True: علاوه بر خط‌ها، رفتار کندل‌ها (متن ال بروکس درباره‌ی درجه‌ی کنترل):
      - اسپایک فقط با بدنه‌ی بزرگ و همپوشانی کم
      - شکستن خط (کانال یا رنج) با یک بسته‌شدن قوی یا دو بسته‌شدن پشت‌سرهم؛ اولین پولبک عمیق شکست نیست
      - گذار زودتر کانال → رنج: چند کندل افقی و بعد سقف/کف تازه‌ای که بلافاصله برمی‌گردد
      - رنج از روی رفتار (همپوشانی زیاد، پیشرفت کم) حتی قبل از دو کف و دو سقف تازه
    """
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    n = len(c)
    avg = _avg(h, l)
    ov = _overlap(h, l)
    piv = zigzag(h, l, avg)
    phases = []
    state = [None] * n
    cur = None
    floor = 0                      # سوئینگ‌های قبل از این اندیس برای ساختار تازه استفاده نمی‌شوند
    trend_side = 0                 # جهت آخرین اسپایک/کانال؛ با رنج صفر می‌شود
    k = 0                          # سوئینگ‌های تأییدشده تا این کندل
    known = []
    for i in range(n):
        while k < len(piv) and piv[k][3] <= i:
            known.append(piv[k])
            k += 1
        a = avg[i]
        # ---- ساختار فعلی هنوز برقرار است؟
        if cur is not None and cur["type"] != "SPIKE":
            lo, hi = _bounds(cur, i)
            broke = c[i] < lo - TOL * a or c[i] > hi + TOL * a
            if cur["type"] == "CHANNEL":                 # در کانال فقط شکستن خط روند (سایه/عبور از خط کانال نه)
                broke = (c[i] < lo - TOL * a) if cur["side"] > 0 else (c[i] > hi + TOL * a)
            if v2:
                if cur["type"] == "CHANNEL":
                    dist = (lo - c[i]) if cur["side"] > 0 else (c[i] - hi)
                else:
                    dist = max(lo - c[i], c[i] - hi)
                if broke and dist < V2_STRONG * a and not cur.get("pending"):
                    cur["pending"] = True                # اولین بسته‌شدن ضعیف آن طرف خط: هنوز نه
                    broke = False
                elif not broke:
                    cur["pending"] = False
                if not broke and cur["type"] == "CHANNEL" and _sideways_fail(o, h, l, c, i, cur, a):
                    j = i - V2_SIDEWAYS                  # کانال خسته شد: رنج از شروع حرکت افقی
                    cur["end"] = max(cur["start"], j - 1)
                    top, bot = h[j:i + 1].max(), l[j:i + 1].min()
                    cur = {"type": "RANGE", "side": 0, "start": j, "end": i,
                           "lines": {"x0": j, "y0": bot, "slope": 0.0, "off": top - bot}}
                    phases.append(cur)
                    for t in range(j, i + 1):
                        state[t] = ("RANGE", 0)
                    trend_side = 0
                    continue
            if v2 and not broke and cur.get("via") == "behaviour":
                pts = [p for p in known if p[0] >= floor]
                lows = [p for p in pts if p[1] == "L"][-2:]
                highs = [p for p in pts if p[1] == "H"][-2:]
                ch = _build(lows, highs, h, l, a, i) if len(lows) >= 2 and len(highs) >= 2 else None
                if ch is not None and ch["type"] == "CHANNEL":
                    clo, chi = _bounds(ch, i)
                    if clo - TOL * a <= c[i] <= chi + TOL * a:     # خط‌های کانال حالا کشیده شده‌اند
                        cur["end"] = max(cur["start"], ch["start"] - 1) if ch["start"] > cur["start"] else cur["start"]
                        if ch["start"] <= cur["end"]:
                            ch["start"] = cur["end"] + 1
                        ch["end"] = i
                        phases.append(ch)
                        for t in range(ch["start"], i + 1):
                            state[t] = ("CHANNEL", ch["side"])
                        cur = ch
                        trend_side = ch["side"]
                        continue
            if not broke:
                cur["end"] = i
                state[i] = (cur["type"], cur["side"])
                trend_side = cur["side"] if cur["type"] == "CHANNEL" else 0
                continue
            cur = None
            floor = known[-1][0] if known else i
        # ---- اسپایک: چند کندل آخر (۳ تا ۱۲) از پایین‌ترین/بالاترین نقطه‌شان تند و یک‌طرفه رفته‌اند
        spike = _spike_run(o, h, l, c, i, a, ov if v2 else None)
        if spike and (cur is None or cur["type"] != "SPIKE") and trend_side == spike[0]:
            spike = None                                        # ادامه‌ی همان روند، نه اسپایک تازه
        if spike:
            s, j0 = spike
            if cur is None or cur["type"] != "SPIKE" or cur["side"] != s:
                if phases and phases[-1]["end"] >= j0:          # فاز قبلی جایی تمام می‌شود که اسپایک شروع شد
                    phases[-1]["end"] = max(phases[-1]["start"], j0 - 1)
                cur = {"type": "SPIKE", "side": s, "start": j0, "end": i, "lines": None}
                phases.append(cur)
            cur["end"] = i
            state[i] = ("SPIKE", s)
            trend_side = s
            continue
        if cur is not None and cur["type"] == "SPIKE":
            floor = cur["end"] - 1                              # پایان اسپایک: ساختار بعدی از نوک اسپایک
            cur = None
        # ---- ساختن ساختار از دو کف و دو سقف آخر (بعد از آخرین شکستن)
        pts = [p for p in known if p[0] >= floor]
        lows = [p for p in pts if p[1] == "L"][-2:]
        highs = [p for p in pts if p[1] == "H"][-2:]
        cur = _build(lows, highs, h, l, a, i) if len(lows) >= 2 and len(highs) >= 2 else None
        if cur is not None:
            lo, hi = _bounds(cur, i)
            if c[i] < lo - TOL * a or c[i] > hi + TOL * a:   # همین الان بیرون خط‌هاست
                cur = None
        if cur is None and v2:                            # رنج از روی رفتار، قبل از دو کف و دو سقف تازه
            cur = _behaviour_range(h, l, c, ov, i)
        if cur is None:
            continue
        if phases and cur["start"] <= phases[-1]["end"]:
            cur["start"] = phases[-1]["end"] + 1
        cur["end"] = i
        phases.append(cur)
        trend_side = cur["side"] if cur["type"] == "CHANNEL" else 0
        for t in range(cur["start"], i + 1):
            if state[t] is None:
                state[t] = (cur["type"], cur["side"])
    return phases, state, piv, avg


def _sideways_fail(o, h, l, c, i, cur, a):
    """گذار کانال → رنج: V2_SIDEWAYS کندل افقی، بعد این کندل از سقف (کف) خود کانال رد می‌شود و همان‌جا
    زیرش (رویش) بسته می‌شود — یک شکست ناموفق کوچک در انتهای کانال."""
    j = i - V2_SIDEWAYS
    a0 = cur["start"]
    if j < 1 or j <= a0:
        return False
    if _efficiency(c, j, i - 1) > V2_SIDEWAYS_EFF:
        return False
    if cur["side"] > 0:
        top = h[a0:i].max()                       # بالاترین سقف کانال تا قبل از این کندل
        return h[i] > top and c[i] < top
    bot = l[a0:i].min()
    return l[i] < bot and c[i] > bot


def _behaviour_range(h, l, c, ov, i):
    """رنج از روی رفتار کندل‌ها در V2_RANGE_N کندل آخر: همپوشانی زیاد و پیشرفت خالص کم."""
    j = i - V2_RANGE_N + 1
    if j < 1:
        return None
    if _efficiency(c, j, i) > V2_RANGE_EFF or ov[j:i + 1].mean() < V2_RANGE_OVERLAP:
        return None
    top, bot = h[j:i + 1].max(), l[j:i + 1].min()
    return {"type": "RANGE", "side": 0, "start": j, "end": i,
            "lines": {"x0": j, "y0": bot, "slope": 0.0, "off": top - bot}, "via": "behaviour"}


def _spike_run(o, h, l, c, i, a, ov=None):
    """(جهت، شروع) اگر یکی از اجراهای ۳ تا ۱۲ کندل آخر اسپایک باشد، وگرنه None.

    ov (نسخه‌ی ۲): همپوشانی کندل‌ها؛ اسپایک فقط با بدنه‌ی بزرگ و همپوشانی کم."""
    for k in range(3, 13):
        j = i - k
        if j < 0:
            break
        for s in (1, -1):
            seg = range(j, i + 1)
            j0 = min(seg, key=lambda t: l[t]) if s > 0 else max(seg, key=lambda t: h[t])
            bars = i - j0
            if bars < 2:
                continue
            move = (c[i] - l[j0]) * s if s > 0 else (h[j0] - c[i])
            same = sum((c[t] - o[t]) * s > 0 for t in range(j0 + 1, i + 1)) / bars
            if j0 < BREAKOUT_N:                       # بریک‌اوت به ۲۰ کندل سابقه نیاز دارد
                continue
            prior = range(j0 - BREAKOUT_N, j0)
            outside = c[i] > max(h[t] for t in prior) if s > 0 else c[i] < min(l[t] for t in prior)
            if outside and move >= SPIKE_SIZE * a and move / bars >= SPIKE_SPEED * a and same >= SPIKE_SAME:
                if ov is not None:
                    run = range(j0 + 1, i + 1)
                    body = np.mean([abs(c[t] - o[t]) / max(h[t] - l[t], 1e-12) for t in run])
                    if body < V2_SPIKE_BODY or np.mean([ov[t] for t in run]) > V2_SPIKE_OVERLAP:
                        continue
                return s, j0
    return None


def _build(lows, highs, h, l, a, i):
    (jl1, _, pl1, _), (jl2, _, pl2, _) = lows
    (jh1, _, ph1, _), (jh2, _, ph2, _) = highs
    up = pl2 - pl1 > FLAT * a and ph2 - ph1 > -FLAT * a
    down = ph1 - ph2 > FLAT * a and pl1 - pl2 > -FLAT * a
    if up and not down:
        slope = (pl2 - pl1) / (jl2 - jl1)
        seg = range(jl1, jl2 + 1)
        off = max(h[t] - (pl1 + slope * (t - jl1)) for t in seg)
        return {"type": "CHANNEL", "side": 1, "start": min(jl1, jh1), "end": i,
                "lines": {"x0": jl1, "y0": pl1, "slope": slope, "off": off}}
    if down and not up:
        slope = (ph2 - ph1) / (jh2 - jh1)
        seg = range(jh1, jh2 + 1)
        off = min(l[t] - (ph1 + slope * (t - jh1)) for t in seg)
        return {"type": "CHANNEL", "side": -1, "start": min(jl1, jh1), "end": i,
                "lines": {"x0": jh1, "y0": ph1, "slope": slope, "off": off}}
    top, bot = max(ph1, ph2), min(pl1, pl2)
    return {"type": "RANGE", "side": 0, "start": min(jl1, jh1), "end": i,
            "lines": {"x0": min(jl1, jh1), "y0": bot, "slope": 0.0, "off": top - bot}}


def _bounds(cur, i):
    ln = cur["lines"]
    base = ln["y0"] + ln["slope"] * (i - ln["x0"])
    other = base + ln["off"]
    return min(base, other), max(base, other)


# ---------------------------------------------------------------- نمودار
def render(sym, df, title_extra="", v2=False, tf="M5"):
    """df: ستون‌های Open/High/Low/Close (مثل data.py). PNG: کندل‌ها، سوئینگ‌ها، خط‌ها، مستطیل رنگی هر فاز."""
    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt

    o, h, l, c = (df[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    phases, state, piv, avg = detect(o, h, l, c, v2=v2)
    n = len(c)
    COL = {("SPIKE", 1): "#FACC15", ("SPIKE", -1): "#FACC15", ("CHANNEL", 1): "#10B981",
           ("CHANNEL", -1): "#EF4444", ("RANGE", 0): "#60A5FA"}
    NAME = {("SPIKE", 1): "SPIKE ↑", ("SPIKE", -1): "SPIKE ↓", ("CHANNEL", 1): "BULL CHANNEL",
            ("CHANNEL", -1): "BEAR CHANNEL", ("RANGE", 0): "TRADING RANGE"}

    fig, ax = plt.subplots(figsize=(22, 9), dpi=100)
    fig.patch.set_facecolor("#121214")
    ax.set_facecolor("#18181B")
    for s in ax.spines.values():
        s.set_color("#27272A")
    ax.tick_params(colors="#9CA3AF")
    ax.grid(True, color="#27272A", ls="--", alpha=0.5)

    for ph in phases:                                    # مستطیل رنگی هر فاز
        key = (ph["type"], ph["side"])
        a0, a1 = ph["start"], ph["end"]
        y0, y1 = l[a0:a1 + 1].min(), h[a0:a1 + 1].max()
        ax.add_patch(patches.Rectangle((a0 - 0.5, y0), a1 - a0 + 1, y1 - y0, facecolor=COL[key], alpha=0.13,
                                       edgecolor=COL[key], lw=1.4, zorder=1))
        if a1 - a0 >= 3 or ph["type"] == "SPIKE":
            ax.text((a0 + a1) / 2, y1, NAME[key], color=COL[key], ha="center", va="bottom", fontsize=9,
                    fontweight="bold", zorder=6)
        ln = ph["lines"]
        if ln:
            xs = np.array([max(ln["x0"], a0 - 3), a1 + 1])
            base = ln["y0"] + ln["slope"] * (xs - ln["x0"])
            ax.plot(xs, base, color=COL[key], lw=1.8, zorder=4)
            ax.plot(xs, base + ln["off"], color=COL[key], lw=1.4, ls="--", zorder=4)

    for i in range(n):                                   # کندل‌ها
        col = "#10B981" if c[i] >= o[i] else "#EF4444"
        ax.vlines(i, l[i], h[i], color=col, lw=0.8, zorder=3)
        ax.add_patch(patches.Rectangle((i - 0.3, min(o[i], c[i])), 0.6, max(abs(c[i] - o[i]), 1e-9),
                                       color=col, zorder=3))
    pad = (h.max() - l.min()) * 0.015
    for j, t, p, _ in piv:                               # سوئینگ‌ها
        ax.plot(j, p - pad if t == "L" else p + pad, "^" if t == "L" else "v",
                color="#06B6D4" if t == "L" else "#F43F5E", ms=5, zorder=5)

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
    now = state[-1]
    now_txt = NAME.get(now, "unclear (waiting for two new lows and highs)") if now else \
        "unclear (waiting for two new lows and highs)"
    ver = " · v2 (new: candle behaviour + lines)" if v2 else " · v1 (lines only)"
    ax.set_title(f"{sym} {tf} · last {n} candles · structure only{ver}{title_extra}\nNow: {now_txt}",
                 color="#F3F4F6", fontsize=13, fontweight="bold")
    ax.set_xlim(-2, n + 2)
    ax.set_ylim(l.min() - pad * 3, h.max() + pad * 4)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#121214")
    plt.close(fig)
    return buf.getvalue(), phases, now
