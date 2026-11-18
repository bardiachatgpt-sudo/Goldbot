"""ستاپ «رانر» طلا (۵ دقیقه + ۱ دقیقه) — هشدار با عکس و برچسب «احتمالاً ستاپ قوی».

ایده‌ی کاربر (۱۸ نوامبر): گپ ۵ دقیقه (همان قاعده‌ی gap.find_gap) تشکیل شود؛ بعد از بسته شدن کندل سوم آن، اولین
گپ هم‌جهتِ ۱ دقیقه = ورود با حد ضرر کوچک ۱ دقیقه، و نگه داشتن تا هدف ستاپ ۵ دقیقه (ریسک به ریوارد بزرگ).
ربات فقط ستاپ را خبر می‌دهد؛ مدیریت (جابه‌جا کردن حد ضرر) با کاربر است.
- کندل‌های ۵ دقیقه از همان کندل‌های ۱ دقیقه‌ی بسته‌شده ساخته می‌شوند (فقط بازه‌های ۵ دقیقه‌ای که کامل گذشته‌اند).
- برای هر گپ ۵ دقیقه فقط یک هشدار (اولین گپ ۱ دقیقه). گپ ۵ دقیقه‌ی تازه (هر جهت) ستاپ قبلی را تمام می‌کند؛
  اگر قیمت قبل از گپ ۱ دقیقه از حد ضرر ۵ دقیقه رد شود هم تمام است. سشن Off: هشدار نمی‌دهد.
- مهم (کاربر، ۱۸ نوامبر): رانر فقط تا وقتی معتبر است که ورود ستاپ ۵ دقیقه فعال نشده؛ اگر قیمت قبل از گپ ۱ دقیقه
  از سقف کندل ۵ دقیقه‌ی قبلی + ۱ پیپت رد شد (خرید: کف − ۱ پیپت)، ستاپ تمام است و هشداری نمی‌آید.
- متن پیام انگلیسی و کوتاه است و هیچ حرفی از ۵ دقیقه نمی‌زند؛ عکس فقط دو خط عمودی (شروع و پایان کندل اولِ ۵ دقیقه)
  روی کندل‌های ۱ دقیقه دارد، بدون نوشته، به‌اضافه‌ی جعبه‌ی گپ ۱ دقیقه (خواست کاربر).
"""
import io

import numpy as np
import pandas as pd

from .config import TEHRAN, session_of
from .gap import _r, find_gap, pip
from .gap_alerts import BG, DOWN_FACE, EDGE, UP_FACE

M5 = pd.Timedelta(minutes=5)
M1 = pd.Timedelta(minutes=1)


def to_m5(m1):
    """کندل‌های ۵ دقیقه از کندل‌های ۱ دقیقه‌ی بسته‌شده؛ فقط بازه‌هایی که تا آخر گذشته‌اند."""
    if m1 is None or len(m1) == 0:
        return m1
    m5 = m1.resample("5min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    return m5[m5.index + M5 <= m1.index[-1] + M1]


class RunnerWatcher:
    def __init__(self, sym="XAUUSD"):
        self.sym = sym
        self.pp = pip(sym)
        self.last_m1 = None            # آخرین کندل ۱ دقیقه‌ی بسته‌شده که بررسی شد
        self.last_m5 = None            # آخرین کندل ۵ دقیقه‌ی کامل که بررسی شد
        self.setup = None              # گپ ۵ دقیقه‌ی فعال

    def _fmt(self, x):
        return f"{x:.2f}" if self.sym == "XAUUSD" else f"{x:.5f}"

    def poll(self, df):
        """df: کندل‌های ۱ دقیقه، ردیف آخر = کندل در حال تشکیل (نادیده). خروجی: [("runner", dict)]."""
        if df is None or len(df) < 40:
            return []
        m1 = df.iloc[:-1]
        m5 = to_m5(m1)
        if self.last_m1 is None:                           # اولین بار: فقط از الان به بعد
            self.last_m1, self.last_m5 = m1.index[-1], (m5.index[-1] if len(m5) else None)
            return []
        o, h, l, c = (m1[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
        o5, h5, l5, c5 = (m5[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
        t1, t5 = m1.index, m5.index
        events = []
        # کندل‌های ۱ دقیقه‌ی تازه، به ترتیب زمان؛ هر وقت یک کندل ۵ دقیقه کامل شد، اول آن بررسی می‌شود
        for i in np.where(t1 > self.last_m1)[0]:
            for k in np.where((t5 > (self.last_m5 if self.last_m5 is not None else t5[0] - M5))
                              & (t5 + M5 <= t1[i] + M1))[0]:
                side, zone = find_gap(o5, h5, l5, c5, k)
                if side:                                   # گپ ۵ دقیقه‌ی تازه: جای قبلی را می‌گیرد
                    self.setup = {"side": side, "t1": t5[k - 2], "t3": t5[k], "ready": t5[k] + M5,
                                  "gap_hi": zone[0], "gap_lo": zone[1], "sent": False,
                                  "sl5": _r(h5[k - 2] + self.pp if side < 0 else l5[k - 2] - self.pp)}
                self.last_m5 = t5[k]
            st = self.setup
            if st is None or st["sent"] or t1[i] < st["ready"]:
                continue
            if (h[i] >= st["sl5"]) if st["side"] < 0 else (l[i] <= st["sl5"]):
                self.setup = None                          # از حد ضرر ۵ دقیقه رد شد: ستاپ تمام
                continue
            lvl5 = self._entry5(st, t1[i], h5, l5, t5)
            if lvl5 is not None and ((h[i] >= lvl5) if st["side"] < 0 else (l[i] <= lvl5)):
                self.setup = None                          # ورود ۵ دقیقه فعال شد: دیگر رانر نیست
                continue
            if t1[i - 2] < st["ready"]:                    # گپ ۱ دقیقه باید کامل بعد از کندل سوم ۵ دقیقه باشد
                continue
            side, zone = find_gap(o, h, l, c, i)
            if side != st["side"]:
                continue
            st["sent"] = True
            if session_of(t1[i]) == "Off":
                continue
            ev = dict(st, m1_t1=t1[i - 2], m1_t3=t1[i], m1_hi=zone[0], m1_lo=zone[1],
                      sl1=_r(h[i - 2] + self.pp if side < 0 else l[i - 2] - self.pp), session=session_of(t1[i]),
                      window=m1[(t1 >= st["t1"] - 20 * M1) & (t1 <= t1[i])].tail(120))
            events.append(("runner", ev))
        self.last_m1 = t1[-1]
        return events

    def _entry5(self, st, ts, h5, l5, t5):
        """سطح ورود ستاپ ۵ دقیقه برای کندل ۱ دقیقه‌ی ts: سقف کندل ۵ دقیقه‌ی قبلِ بازه‌ی همین کندل + ۱ پیپت
        (خرید: کف − ۱ پیپت). None اگر آن کندل ۵ دقیقه در داده نباشد."""
        prev = ts.floor("5min") - M5
        if prev < st["t3"]:
            return None
        k = t5.get_indexer([prev])[0]
        if k < 0:
            return None
        return _r(h5[k] + self.pp if st["side"] < 0 else l5[k] - self.pp)

    # ------------------------------------------------------------ پیام و عکس
    def caption(self, e):
        s = e["side"]
        tz = lambda x: x.tz_convert(TEHRAN).strftime("%H:%M")
        return (f"🔥 Possible runner · {'🔴 SELL' if s < 0 else '🟢 BUY'} · {self.sym} M1 · "
                f"{tz(e['m1_t3'] + M1)} Tehran")

    def picture(self, e):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.patches as patches
        import matplotlib.pyplot as plt
        w = e["window"]
        o, h, l, c = (w[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
        n, s = len(w), e["side"]
        lo, hi = l.min(), h.max()
        pad = (hi - lo) * 0.05 or 1.0
        x = lambda ts: w.index.searchsorted(ts) - 0.5
        fig, ax = plt.subplots(figsize=(12, 7), dpi=100)
        fig.patch.set_facecolor(BG)
        ax.set_facecolor(BG)
        for t in (e["t1"], e["t1"] + M5):                  # دو خط عمودی: شروع و پایان کندل اولِ ۵ دقیقه (بدون نوشته)
            ax.axvline(x(t), color="#1E3A8A", lw=1.4, ls=(0, (6, 3)), zorder=3)
        for i in range(n):
            up = c[i] >= o[i]
            ax.vlines(i, l[i], h[i], color=EDGE, lw=1, zorder=5)
            ax.add_patch(patches.Rectangle((i - 0.33, min(o[i], c[i])), 0.66, max(abs(c[i] - o[i]), 1e-6),
                                           facecolor=UP_FACE if up else DOWN_FACE, edgecolor=EDGE, lw=0.9,
                                           zorder=5))
        g1 = "#EA580C" if s < 0 else "#0D9488"
        a1, b1 = x(e["m1_t1"]), x(e["m1_t3"]) + 1
        ax.add_patch(patches.Rectangle((a1, e["m1_lo"]), b1 - a1, e["m1_hi"] - e["m1_lo"], facecolor=g1,
                                       alpha=0.5, edgecolor=g1, zorder=6))
        step = max(1, n // 10)
        ax.set_xticks(range(0, n, step))
        ax.set_xticklabels([d.strftime("%H:%M") for d in w.index.tz_convert(TEHRAN)[::step]], fontsize=9)
        ax.set_xlim(-1, n + 2)
        ax.set_ylim(lo - pad, hi + pad * 3)
        ax.grid(color="#D6E3F2")
        for sp in ax.spines.values():
            sp.set_color("#A9CDF3")
        ax.set_title(f"{self.sym} M1 · {'SELL' if s < 0 else 'BUY'} · possible runner · "
                     f"{(e['m1_t3'] + M1).tz_convert(TEHRAN):%a %d %b %H:%M} Tehran", loc="left", fontweight="bold")
        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=BG)
        plt.close(fig)
        return buf.getvalue()
