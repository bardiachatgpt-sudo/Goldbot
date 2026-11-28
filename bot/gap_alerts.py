"""هشدار زنده‌ی گپ طلا روی M1 (تلگرام، با عکس) — فقط خود گپ.

هر ~۱۵ ثانیه کندل‌های M1 طلا از TradingView گرفته می‌شود. با بسته شدن کندل ۳ هر گپ (همان قاعده‌ی gap.find_gap:
کف ۱ > سقف ۳ برای فروش و بدنه‌ی کندل ۲ در آن فاصله؛ رنگ کندل‌ها مهم نیست) یک عکس فرستاده می‌شود: ۶۰ کندل M1، جعبه‌ی گپ، و ساختار M5 همان لحظه.
ورود، حد ضرر و حد سود نشان داده نمی‌شوند (کاربر، ۱۷ نوامبر: «فقط گپ را می‌خواهم»).
همه‌ی گپ‌ها (همه‌ی لگ‌ها، بدون فیلتر M5)، ولی نه در سشن Off. هر هشدار می‌گوید گپ «هم‌جهت با روند» است یا «خلاف روند»
(روند از M5؛ تعریفش در GapAlerter.trend — نام شاخص در پیام‌ها نمی‌آید، خواست کاربر). گپ‌های زنجیره‌ای پشت گپ اول (۲-۳-۴ …) هشدار جدا ندارند.
"""
import io

import numpy as np
import pandas as pd

from .config import TEHRAN, session_of
from .gap import find_gap, gap_heads, leg_number

ALERT_SYMBOL = "XAUUSD"
PICTURE_BARS = 60
BG = "#E8F2FD"                  # پس‌زمینه‌ی آبی کم‌رنگ (همان رنگ جعبه‌ی M5 در عکس‌های دیگر)
BOX = "#D2E4F8"                 # جعبه‌ی M5 روی این پس‌زمینه کمی پررنگ‌تر
UP_FACE, DOWN_FACE, EDGE = "white", "black", "black"   # صعودی سفید، نزولی مشکی (خواست کاربر)


class GapAlerter:
    MIN_BARS = 30

    def __init__(self, sym=ALERT_SYMBOL, sessions=True):
        self.sym = sym
        self.sessions = sessions       # False: سشن Off هم هشدار دارد (بیت‌کوین آخر هفته)
        self.last_closed = None        # زمان آخرین کندل بسته‌شده‌ای که بررسی شد
        self.last = None               # آخرین گپ (برای تشخیص زنجیره)

    def _fmt(self, x):
        return f"{x:.2f}" if self.sym in ("XAUUSD", "BTCUSD") else f"{x:.5f}"

    def poll(self, df):
        """df: کندل‌های M1 (Open/High/Low/Close، زمان = شروع کندل)، ردیف آخر = کندل در حال تشکیل (نادیده).
        خروجی: فهرست گپ‌های تازه [("gap", dict)] به ترتیب."""
        if df is None or len(df) < self.MIN_BARS:
            return []
        closed = df.iloc[:-1]
        o, h, l, c = (closed[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
        t = closed.index
        events = []
        if self.last_closed is None:                       # اولین بار: فقط از الان به بعد
            self.last_closed = t[-1]
            return []
        new = np.where(t > self.last_closed)[0]
        heads = gap_heads(o, h, l, c) if len(new) else None
        for i in new:                                      # کندل‌های تازه بسته‌شده، به ترتیب
            side, zone = find_gap(o, h, l, c, i)
            if not side:
                continue
            p = self.last
            if p is not None and p["side"] == side and t[i - 2] <= p["chain"]:
                p["chain"] = t[i]                          # زنجیره‌ی همان گپ: هشدار جدا ندارد
                continue
            self.last = p = {"side": side, "t1": t[i - 2], "t3": t[i], "chain": t[i], "gap_hi": zone[0],
                             "gap_lo": zone[1], "leg": leg_number(heads, h, l, i - 2, side),
                             "session": session_of(t[i]) if self.sessions else "Weekend", "close3": c[i]}
            p.update(self.swing_sl(h, l, t, i, side))
            if p["session"] != "Off":                      # سشن Off: هشدار نمی‌دهد
                events.append(("gap", dict(p, window=closed.tail(PICTURE_BARS))))
        self.last_closed = t[-1]
        return events

    def swing_sl(self, h, l, t, i, side):
        """حد ضرر در لحظه‌ی دیدن گپ (کاربر، ۲۲ نوامبر): از کندل ۳ (= i) به عقب، نزدیک‌ترین کندلی که همسایه‌ی راستش
        بسته شده و کفش از کف هر دو همسایه پایین‌تر است (فروش: سقفش از هر دو بالاتر) → ۱ پیپت آن طرفش.
        چند کندل کنار هم با کف برابر = یک سوینگ (با کندل قبل و بعد از گروه مقایسه می‌شوند).
        فقط سقف/کف، نه کلوز. همان قانون اکسپرت (SL_SWING)؛ اگر ورود دیرتر بخورد ممکن است کندل ۳ خودش سوینگ شود."""
        from .gap import _r, pip
        pp = pip(self.sym)
        x = l if side > 0 else h
        lower = (lambda a, b: a < b) if side > 0 else (lambda a, b: a > b)
        # کندل‌های کنار هم با کف برابر (فروش: سقف برابر) یک سوینگ‌اند و با کندل قبل و بعد از گروه مقایسه می‌شوند
        # (کاربر، ۲۲ نوامبر)؛ e = تازه‌ترین کندل گروه، s = قدیمی‌ترین
        for e in range(i - 1, 0, -1):
            if x[e] == x[e + 1]:
                continue                                   # عضو گروهی که از سمت تازه‌تر بررسی شده
            s = e
            while s - 1 >= 0 and x[s - 1] == x[e]:
                s -= 1
            if s >= 1 and lower(x[e], x[e + 1]) and lower(x[e], x[s - 1]):
                return {"sl": _r(x[e] - pp if side > 0 else x[e] + pp), "sl_t": t[s]}
        return {"sl": None, "sl_t": None}

    # ------------------------------------------------------------ روند (داخلی؛ نام شاخص به کاربر گفته نمی‌شود)
    @staticmethod
    def trend(g, m5):
        """+1 هم‌جهت با روند، −1 خلاف روند، None اگر داده‌ی M5 نباشد.
        روند = علامت عدد هیستوگرام MACD(48,104,36) متاتریدر روی M5 «در همین لحظه» = EMA(48) − EMA(104) بسته‌شدن‌ها
        (در متاتریدر میله‌ها همین‌اند؛ خط سیگنال هیچ نقشی ندارد). کندل‌های M5 بسته‌شده تا بسته شدن کندل ۳ گپ،
        به‌اضافه‌ی کندل M5 در حال تشکیل با قیمت فعلی = بسته‌شدن کندل ۳ (همان میله‌ی آخری که متاتریدر نشان می‌دهد).
        منفی = نزولی، مثبت = صعودی (خواست کاربر، ۱۸ نوامبر)."""
        if m5 is None or len(m5) < 120:
            return None
        end = g["t3"] + pd.Timedelta(minutes=1)
        c5 = m5["Close"][m5.index + pd.Timedelta(minutes=5) <= end].astype(float)
        if len(c5) < 120:
            return None
        if g.get("close3") is not None:
            now = g["t3"].floor("5min")
            if c5.index[-1] < now:                          # کندل ۵ دقیقه‌ی جاری هنوز بسته نشده
                c5 = pd.concat([c5, pd.Series([float(g["close3"])], index=[now])])
        hist = c5.ewm(span=48, adjust=False).mean().iloc[-1] - c5.ewm(span=104, adjust=False).mean().iloc[-1]
        if hist == 0:
            return None
        return 1 if (hist < 0) == (g["side"] < 0) else -1

    # ------------------------------------------------------------ پیام
    def gap_caption(self, g):
        s = g["side"]
        m5 = f" · M5: {g['m5_state']}" if g.get("m5_state") and g["m5_state"] != "-" else ""
        when = g["t3"].tz_convert(TEHRAN).strftime("%a %d %b %H:%M")
        tr = {1: "\n📈 With the trend", -1: "\n↩️ Against the trend"}.get(g.get("trend"), "")
        sl = f"\n🛑 SL {self._fmt(g['sl'])}" if g.get("sl") is not None else ""
        hint = {"with": "\n✅ With the 5-min gap, after its entry → likely TP"}.get(g.get("m5_hint"), "")
        inf = g.get("m5_entry")
        if inf:
            if inf["trig"] is not None:
                hint += (f"\n📍 5-min {'SELL' if inf.get('side', 0) < 0 else 'BUY'} entry TRIGGERED at {self._fmt(inf['entry'])} "
                         f"({inf['trig'].tz_convert(TEHRAN):%H:%M} Tehran)")
            else:
                lv = f" (level now {self._fmt(inf['level'])})" if inf.get("level") is not None else ""
                hint += f"\n⏳ 5-min {'SELL' if inf.get('side', 0) < 0 else 'BUY'} entry NOT triggered yet{lv}"
        return (f"🔔 {'🔴 SELL' if s < 0 else '🟢 BUY'} gap · {self.sym} M1 · Leg {g['leg']} · {g['session']}{m5}\n"
                f"Candle 3 closed {when} Tehran · gap {self._fmt(g['gap_lo'])}–{self._fmt(g['gap_hi'])}{sl}{tr}{hint}")

    def picture(self, g, m5=None):
        """m5: کندل‌های M5 بسته‌شده (اختیاری) → جعبه‌های ساختار M5 زیر کندل‌های M1؛ نامش در g['m5_state']."""
        from .gap_pictures import draw_m5, m5_at
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.patches as patches
        import matplotlib.pyplot as plt
        w = g["window"]
        o, h, l, c = (w[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
        n, s = len(w), g["side"]
        lo, hi = l.min(), h.max()
        if g.get("sl") is not None:                        # خط حد ضرر باید در عکس دیده شود
            lo, hi = min(lo, g["sl"]), max(hi, g["sl"])
        inf = g.get("m5_entry")
        if inf and inf.get("entry") is not None:
            lo, hi = min(lo, inf["entry"]), max(hi, inf["entry"])
        pad = (hi - lo) * 0.05 or 1.0
        fig, ax = plt.subplots(figsize=(12, 7), dpi=100)
        fig.patch.set_facecolor(BG)
        ax.set_facecolor(BG)
        span = hi - lo or 1.0
        g["m5_state"] = draw_m5(ax, self.sym, m5_at(m5, w.index[-1] + pd.Timedelta(minutes=1)) if m5 is not None
                                else None, w.index, lo, hi, span, pad, labels_left=True, fill=BOX)
        for i in range(n):
            up = c[i] >= o[i]
            ax.vlines(i, l[i], h[i], color=EDGE, lw=1, zorder=5)
            ax.add_patch(patches.Rectangle((i - 0.33, min(o[i], c[i])), 0.66, max(abs(c[i] - o[i]), 1e-6),
                                           facecolor=UP_FACE if up else DOWN_FACE, edgecolor=EDGE, lw=0.9,
                                           zorder=5))
        g1 = w.index.get_indexer([g["t1"]])[0]
        g3 = w.index.get_indexer([g["t3"]])[0]
        gc = "#F97316" if s < 0 else "#14B8A6"
        if g1 >= 0 and g3 >= 0:
            ax.add_patch(patches.Rectangle((g1 - 0.5, g["gap_lo"]), g3 - g1 + 1, g["gap_hi"] - g["gap_lo"],
                                           facecolor=gc, alpha=0.45, edgecolor=gc, zorder=6))
            ax.text(g1, h[g1] + pad * 0.3 if s < 0 else l[g1] - pad * 0.3, "1", ha="center",
                    va="bottom" if s < 0 else "top", fontweight="bold", color=gc)
            ax.text(g3, l[g3] - pad * 0.3 if s < 0 else h[g3] + pad * 0.3, "3", ha="center",
                    va="top" if s < 0 else "bottom", fontweight="bold", color=gc)
        if g.get("sl") is not None:                        # حد ضرر: از کندل سوینگ تا آخر عکس، با قیمت
            a = max(w.index.searchsorted(g["sl_t"]) - 0.4, -0.5)
            ax.hlines(g["sl"], a, n + 0.5, color="#DC2626", lw=1.8, zorder=7)
            ax.text(n + 0.8, g["sl"], f"SL {self._fmt(g['sl'])}", color="#DC2626", fontsize=10, fontweight="bold",
                    ha="left", va="center", zorder=8)
        if inf:                                            # ورود ۵ دقیقه: خورد (خط) یا هنوز نه (نوشته)
            if inf.get("entry") is not None:
                a = max(w.index.searchsorted(inf["trig"]) - 0.4, -0.5)
                ax.hlines(inf["entry"], a, n + 0.5, color="#7C3AED", lw=1.8, zorder=7)
                ax.text(a, inf["entry"], f"5-min {'SELL' if inf.get('side', 0) < 0 else 'BUY'} entry triggered here ", color="#7C3AED", fontsize=10,
                        fontweight="bold", ha="right", va="center", zorder=8,
                        bbox=dict(facecolor=BG, edgecolor="none", pad=1.5))
            else:
                lv = f" (level now {self._fmt(inf['level'])})" if inf.get("level") is not None else ""
                ax.text(0.01, 0.97, f"5-min {'SELL' if inf.get('side', 0) < 0 else 'BUY'} entry NOT triggered yet{lv}", transform=ax.transAxes, color="#7C3AED",
                        fontsize=11, fontweight="bold", ha="left", va="top", zorder=9,
                        bbox=dict(facecolor="white", edgecolor="#7C3AED", pad=4))
        step = max(1, n // 9)
        ax.set_xticks(range(0, n, step))
        ax.set_xticklabels([d.strftime("%H:%M") for d in w.index.tz_convert(TEHRAN)[::step]], fontsize=9)
        ax.set_xlim(-1, n + (9 if g.get("sl") is not None else 2))
        ax.set_ylim(lo - pad, hi + pad * 3)
        ax.grid(color="#D6E3F2")
        for sp in ax.spines.values():
            sp.set_color("#A9CDF3")
        tr = {1: " · with the trend", -1: " · against the trend"}.get(g.get("trend"), "")
        ax.set_title(f"{self.sym} M1 · {'SELL' if s < 0 else 'BUY'} gap · Leg {g['leg']}{tr} · "
                     f"{g['t3'].tz_convert(TEHRAN):%a %d %b %H:%M} Tehran", loc="left", fontweight="bold")
        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=BG)
        plt.close(fig)
        return buf.getvalue()


def m5_candles(name=ALERT_SYMBOL):
    """۵۰۰+ کندل M5 بسته‌شده برای ساختار M5 در عکس هشدار (None اگر نشد)."""
    from .data import get_closed_candles
    try:
        return get_closed_candles(name, 600, 100, interval="5", timeout=15)
    except Exception:
        return None


def live_candles(name=ALERT_SYMBOL, n_bars=300, timeout=15):
    """کندل‌های M1 همراه کندل در حال تشکیل (برای هشدار زنده)."""
    from .config import ALL_SYMBOLS
    from .data import fetch_candles
    for tv in ALL_SYMBOLS[name]:
        df, err = fetch_candles(tv, "1", n_bars, timeout=timeout)
        if df is not None and len(df) > 30:
            return df
    return None



# ------------------------------------------------------------------ گپ‌های ۵ دقیقه (عکس جدا)
M5_BG = "#FBF8F1"                   # سفید شیری (خواست کاربر)


class M5GapAlerter(GapAlerter):
    """هر گپ ۵ دقیقه‌ی طلا (صعودی یا نزولی، همان قاعده‌ی find_gap): یک عکس از کندل‌های ۵ دقیقه روی زمینه‌ی سفید
    شیری، بدون ساختار و بدون نوشته‌ی تایم‌فریم؛ متن فقط «Bearish gap» / «Bullish gap» (خواست کاربر، ۱۸ نوامبر).
    کندل‌های ۵ دقیقه از همان کندل‌های ۱ دقیقه ساخته می‌شوند (m5_frame)."""
    MIN_BARS = 5

    def gap_caption(self, g):
        cap = "🔴 Bearish gap" if g["side"] < 0 else "🟢 Bullish gap"
        return cap if self.sym == ALERT_SYMBOL else f"{cap} · {self.sym}"      # طلا: مثل قبل، بدون نام

    def picture(self, g, m5=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.patches as patches
        import matplotlib.pyplot as plt
        w = g["window"]
        o, h, l, c = (w[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
        n, s = len(w), g["side"]
        lo, hi = l.min(), h.max()
        pad = (hi - lo) * 0.05 or 1.0
        fig, ax = plt.subplots(figsize=(12, 7), dpi=100)
        fig.patch.set_facecolor(M5_BG)
        ax.set_facecolor(M5_BG)
        for i in range(n):
            up = c[i] >= o[i]
            ax.vlines(i, l[i], h[i], color=EDGE, lw=1, zorder=5)
            ax.add_patch(patches.Rectangle((i - 0.33, min(o[i], c[i])), 0.66, max(abs(c[i] - o[i]), 1e-6),
                                           facecolor=UP_FACE if up else DOWN_FACE, edgecolor=EDGE, lw=0.9,
                                           zorder=5))
        g1 = w.index.get_indexer([g["t1"]])[0]
        g3 = w.index.get_indexer([g["t3"]])[0]
        gc = "#F97316" if s < 0 else "#14B8A6"
        if g1 >= 0 and g3 >= 0:
            ax.add_patch(patches.Rectangle((g1 - 0.5, g["gap_lo"]), g3 - g1 + 1, g["gap_hi"] - g["gap_lo"],
                                           facecolor=gc, alpha=0.45, edgecolor=gc, zorder=6))
        step = max(1, n // 9)
        ax.set_xticks(range(0, n, step))
        ax.set_xticklabels([d.strftime("%H:%M") for d in w.index.tz_convert(TEHRAN)[::step]], fontsize=9)
        ax.set_xlim(-1, n + 2)
        ax.set_ylim(lo - pad, hi + pad)
        ax.grid(color="#ECE6D8")
        for sp in ax.spines.values():
            sp.set_color("#D9D2C2")
        ax.set_title(f"{self.sym} · {'Bearish' if s < 0 else 'Bullish'} gap", loc="left", fontweight="bold")
        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=M5_BG)
        plt.close(fig)
        return buf.getvalue()


def m5_frame(m1):
    """کندل‌های ۵ دقیقه از کندل‌های ۱ دقیقه؛ ردیف آخر = کندل ۵ دقیقه‌ی در حال تشکیل (برای poll)."""
    if m1 is None or len(m1) == 0:
        return None
    return m1.resample("5min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()


# ------------------------------------------------------------------ معامله‌ی ۵ دقیقه (برای برچسب هشدار ۱ دقیقه)
class M5TradeWatch:
    """کاربر، ۲۲ نوامبر (نسخه‌ی دوم: «فعلاً فقط حد سودها»): بعد از هر گپ ۵ دقیقه (نه زنجیره)، وقتی ورود ۵ دقیقه
    خورد (سقف کندل ۵ دقیقه‌ی قبلی + ۱ پیپت برای فروش، کف − ۱ پیپت برای خرید)، **هر** گپ ۱ دقیقه‌ی هم‌جهت که کندل ۳ آن
    در/بعد از کندل ۱ دقیقه‌ای بسته شود که ورود در آن خورد → «✅ likely TP»؛ تا وقتی گپ ۵ دقیقه پر نشده (خرید: قیمت تا
    سقف کندل ۱ گپ ۵ دقیقه پایین آمد، فروش: تا کف کندل ۱ بالا رفت) و حد ضرر ۵ دقیقه (۱ پیپت آن طرف کندل ۱) نخورده.
    گپ‌های خلاف جهت برچسب ندارند. کندل‌های ۵ دقیقه از کندل‌های ۱ دقیقه‌ی بسته‌شده ساخته می‌شوند."""

    def __init__(self, sym=ALERT_SYMBOL):
        from .gap import pip
        self.sym, self.pp = sym, pip(sym)
        self.ctx, self.last = None, None

    def new_gap(self, ev, m5):
        """ev: گپ ۵ دقیقه (side, t1, t3)؛ m5: کندل‌های ۵ دقیقه که کندل ۱ گپ در آن است."""
        from .gap import _r
        s = ev["side"]
        try:
            c1 = m5.loc[ev["t1"]]
            sl5 = _r(float(c1["High"]) + self.pp if s < 0 else float(c1["Low"]) - self.pp)
            fill = float(c1["Low"]) if s < 0 else float(c1["High"])      # لبه‌ی گپ سمت کندل ۱
        except Exception:
            sl5 = fill = None
        self.ctx = {"side": s, "t3": ev["t3"], "end": ev["t3"] + pd.Timedelta(minutes=5), "sl5": sl5, "fill": fill,
                    "entry": None, "trig": None, "done": False, "first": False}

    def update(self, df):
        """کندل‌های ۱ دقیقه‌ی تازه‌ی بسته‌شده: ورود ۵ دقیقه خورد؟ گپ ۵ دقیقه پر شد یا حد ضرر ۵ دقیقه خورد؟"""
        from .gap import _r
        from .runner import to_m5
        if df is None or len(df) < 3:
            return
        m1 = df.iloc[:-1]
        if self.last is None:
            self.last = m1.index[-1]
            return
        new = m1[m1.index > self.last]
        self.last = m1.index[-1]
        st = self.ctx
        if st is None or st["done"] or st["sl5"] is None or not len(new):
            return
        m5 = to_m5(m1)
        self.m5 = m5
        s = st["side"]
        for ts, bar in new.iterrows():
            if ts < st["end"] or st["done"]:
                continue
            hi, lo = float(bar["High"]), float(bar["Low"])
            if st["entry"] is None:
                prev = ts.floor("5min") - pd.Timedelta(minutes=5)
                if prev >= st["t3"] and prev in m5.index:
                    k = m5.loc[prev]
                    lvl = _r(float(k["High"]) + self.pp if s < 0 else float(k["Low"]) - self.pp)
                    if (hi >= lvl) if s < 0 else (lo <= lvl):
                        st.update(entry=lvl, trig=ts)
            if (hi >= st["fill"]) if s < 0 else (lo <= st["fill"]):
                st["done"] = True                          # گپ ۵ دقیقه پر شد (حد ضرر ۵ دقیقه هم آن طرف‌تر است)

    def entry_info(self, ev):
        """کاربر، ۲۲ و ۲۳ نوامبر: برای هر گپ ۱ دقیقه (هر جهت؛ ۲۳ نوامبر) بعد از گپ ۵ دقیقه (تا وقتی گپ ۵ دقیقه پر نشده) روی عکس
        نشان داده شود ورود ۵ دقیقه خورده یا نه. خروجی: None یا {"trig": زمان یا None, "entry": قیمت یا None,
        "level": سطح ورود ۵ دقیقه‌ی همین لحظه (اگر هنوز نخورده)}."""
        from .gap import _r
        st = self.ctx
        if st is None or st["done"] or ev["t3"] + pd.Timedelta(minutes=1) <= st["end"]:
            return None
        if st["trig"] is not None:
            return {"trig": st["trig"], "entry": st["entry"], "level": None, "side": st["side"]}
        level = None
        prev = (ev["t3"] + pd.Timedelta(minutes=1)).floor("5min") - pd.Timedelta(minutes=5)
        m5 = getattr(self, "m5", None)
        if m5 is not None and prev >= st["t3"] and prev in m5.index:
            k = m5.loc[prev]
            level = _r(float(k["High"]) + self.pp if st["side"] < 0 else float(k["Low"]) - self.pp)
        return {"trig": None, "entry": None, "level": level, "side": st["side"]}

    def hint(self, ev):
        """"with" (هر گپ هم‌جهت بعد از ورود ۵ دقیقه، تا پر شدن گپ) یا None."""
        st = self.ctx
        if (st is None or st["done"] or st["trig"] is None or ev["side"] != st["side"]
                or ev["t3"] + pd.Timedelta(minutes=1) <= st["end"] or ev["t3"] < st["trig"]):
            return None
        return "with"
