"""هشدار زنده‌ی گپ طلا روی M1 (تلگرام، با عکس).

هر ~۱۵ ثانیه کندل‌های M1 طلا از TradingView (همراه کندل در حال تشکیل) گرفته می‌شود.
- با بسته شدن کندل ۳ هر گپ (همان قاعده‌ی gap.find_gap: سه کندل هم‌رنگ، کف ۱ > سقف ۳ برای فروش) یک عکس فرستاده
  می‌شود: جعبه‌ی گپ، سطح ورود فعلی (سقف/کف کندل قبلی ± ۱ پیپت)، حد ضرر پشت کندل ۱ و حد سود ۱:۱.
  همه‌ی گپ‌ها (همه‌ی لگ‌ها، بدون فیلتر M5، همه‌ی ساعت‌هایی که بازار باز است) — خواست کاربر، ۱۷ نوامبر.
  گپ‌های زنجیره‌ای پشت گپ اول (۲-۳-۴ …) هشدار جدا ندارند؛ گپ جدا یا خلاف جهت جای قبلی را می‌گیرد.
- وقتی قیمت (حتی وسط کندل در حال تشکیل) ۱ پیپت از سقف کندل قبلی بالاتر برود (خرید: پایین‌تر از کف)، پیام کوتاه
  «ورود خورد» با ورود، حد ضرر و حد سود ۱:۱. بعد از آن، آن گپ تمام است.
"""
import io

import numpy as np

from .config import TEHRAN, session_of
from .gap import _r, find_gap, gap_heads, leg_number, pip

ALERT_SYMBOL = "XAUUSD"
PICTURE_BARS = 45


class GapAlerter:
    def __init__(self, sym=ALERT_SYMBOL):
        self.sym = sym
        self.pp = pip(sym)
        self.last_closed = None        # زمان آخرین کندل بسته‌شده‌ای که بررسی شد
        self.pending = None            # گپ در انتظار ورود

    def _fmt(self, x):
        return f"{x:.2f}" if self.sym == "XAUUSD" else f"{x:.5f}"

    def poll(self, df):
        """df: کندل‌های M1 (Open/High/Low/Close، زمان = شروع کندل)، ردیف آخر = کندل در حال تشکیل.
        خروجی: فهرست رویدادها [("gap", dict) | ("entry", dict)] به ترتیب."""
        if df is None or len(df) < 30:
            return []
        closed, live = df.iloc[:-1], df.iloc[-1]
        o, h, l, c = (closed[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
        t = closed.index
        events = []
        if self.last_closed is None:                       # اولین بار: فقط از الان به بعد
            self.last_closed = t[-1]
            return []
        new = np.where(t > self.last_closed)[0]
        heads = gap_heads(o, h, l, c) if len(new) else None
        for i in new:                                      # کندل‌های تازه بسته‌شده، به ترتیب
            ev = self._entry_on_closed(i, h, l, t)
            if ev:
                events.append(ev)
            side, zone = find_gap(o, h, l, c, i)
            if not side:
                continue
            p = self.pending
            if p is not None and p["side"] == side and t[i - 2] <= p["chain"]:
                p["chain"] = t[i]                          # زنجیره‌ی همان گپ: هشدار جدا ندارد
                continue
            sl = _r(h[i - 2] + self.pp if side < 0 else l[i - 2] - self.pp)
            self.pending = p = {"side": side, "t1": t[i - 2], "t3": t[i], "chain": t[i], "gap_hi": zone[0],
                                "gap_lo": zone[1], "sl": sl, "leg": leg_number(heads, h, l, i - 2, side),
                                "session": session_of(t[i])}
            events.append(("gap", dict(p, level=self._level(i, h, l), window=closed.tail(PICTURE_BARS))))
        self.last_closed = t[-1]
        ev = self._entry_live(live, h, l)                  # کندل در حال تشکیل
        if ev:
            events.append(ev)
        return events

    def _level(self, i, h, l):
        """سطح ورود برای کندل بعد از i: سقف کندل i + ۱ پیپت (فروش) / کف − ۱ پیپت (خرید)."""
        return _r(h[i] + self.pp if self.pending["side"] < 0 else l[i] - self.pp)

    def _entry(self, level, when):
        p, s = self.pending, self.pending["side"]
        risk = abs(p["sl"] - level)
        self.pending = None
        if risk <= 0 or (p["sl"] - level) * s > 0:         # ورود آن طرف حد ضرر: معامله نیست
            return None
        return ("entry", dict(p, entry=level, tp=_r(level + s * risk), risk=risk, when=when))

    def _entry_on_closed(self, i, h, l, t):
        """کندل i (تازه بسته شده) از سطح کندل قبلش رد شده؟ (اگر بین دو بار گرفتن داده جا مانده باشد)"""
        p = self.pending
        if p is None or t[i] <= p["t3"] or i < 1:
            return None
        lvl = _r(h[i - 1] + self.pp if p["side"] < 0 else l[i - 1] - self.pp)
        hit = h[i] >= lvl if p["side"] < 0 else l[i] <= lvl
        return self._entry(lvl, t[i]) if hit else None

    def _entry_live(self, live, h, l):
        p = self.pending
        if p is None or live.name <= p["t3"]:
            return None
        lvl = _r(h[-1] + self.pp if p["side"] < 0 else l[-1] - self.pp)
        hit = float(live["High"]) >= lvl if p["side"] < 0 else float(live["Low"]) <= lvl
        return self._entry(lvl, live.name) if hit else None

    # ------------------------------------------------------------ پیام‌ها
    def gap_caption(self, g):
        s = g["side"]
        lvl, sl = g["level"], g["sl"]
        tp = _r(lvl + s * abs(sl - lvl))
        when = g["t3"].tz_convert(TEHRAN).strftime("%a %d %b %H:%M")
        return (f"🔔 {'🔴 SELL' if s < 0 else '🟢 BUY'} gap · {self.sym} M1 · Leg {g['leg']} · {g['session']}\n"
                f"Candle 3 closed {when} Tehran · gap {self._fmt(g['gap_lo'])}–{self._fmt(g['gap_hi'])}\n"
                f"Entry if price trades {'above' if s < 0 else 'below'} {self._fmt(lvl)} "
                f"({'previous high + 1 pipette' if s < 0 else 'previous low − 1 pipette'}; moves with each candle)\n"
                f"SL {self._fmt(sl)} · TP 1:1 ≈ {self._fmt(tp)} (stop ${abs(sl - lvl):.2f})")

    def entry_text(self, e):
        s = e["side"]
        when = e["when"].tz_convert(TEHRAN).strftime("%H:%M")
        return (f"✅ Entry hit · {'🔴 SELL' if s < 0 else '🟢 BUY'} {self.sym} at {self._fmt(e['entry'])} "
                f"({when} Tehran candle) · SL {self._fmt(e['sl'])} · TP 1:1 {self._fmt(e['tp'])} "
                f"(stop ${e['risk']:.2f}) · Leg {e['leg']}")

    def picture(self, g):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.patches as patches
        import matplotlib.pyplot as plt
        w = g["window"]
        o, h, l, c = (w[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
        n, s = len(w), g["side"]
        lvl, sl = g["level"], g["sl"]
        tp = lvl + s * abs(sl - lvl)
        lo, hi = min(l.min(), sl, tp), max(h.max(), sl, tp)
        pad = (hi - lo) * 0.05 or 1.0
        fig, ax = plt.subplots(figsize=(11, 6.5), dpi=100)
        fig.patch.set_facecolor("white")
        for i in range(n):
            up = c[i] >= o[i]
            col = "#16A34A" if up else "#DC2626"
            ax.vlines(i, l[i], h[i], color=col, lw=1)
            ax.add_patch(patches.Rectangle((i - 0.33, min(o[i], c[i])), 0.66, max(abs(c[i] - o[i]), 1e-6),
                                           facecolor=col, edgecolor=col))
        g1 = w.index.get_indexer([g["t1"]])[0]
        g3 = w.index.get_indexer([g["t3"]])[0]
        gc = "#F97316" if s < 0 else "#14B8A6"
        if g1 >= 0 and g3 >= 0:
            ax.add_patch(patches.Rectangle((g1 - 0.5, g["gap_lo"]), g3 - g1 + 1, g["gap_hi"] - g["gap_lo"],
                                           facecolor=gc, alpha=0.4, edgecolor=gc, zorder=3))
            ax.text(g1, h[g1] + pad * 0.3 if s < 0 else l[g1] - pad * 0.3, "1", ha="center",
                    va="bottom" if s < 0 else "top", fontweight="bold", color=gc)
            ax.text(g3, l[g3] - pad * 0.3 if s < 0 else h[g3] + pad * 0.3, "3", ha="center",
                    va="top" if s < 0 else "bottom", fontweight="bold", color=gc)
        for y, col, name in ((lvl, "#EA580C", f"ENTRY {'>' if s < 0 else '<'} {self._fmt(lvl)}"),
                             (sl, "#DC2626", f"SL {self._fmt(sl)}"), (tp, "#16A34A", f"TP 1:1 {self._fmt(tp)}")):
            ax.hlines(y, max(g3, 0) + 0.5, n + 3, color=col, lw=1.5, ls=(0, (5, 3)))
            ax.text(n + 3.2, y, name, color=col, va="center", fontsize=9, fontweight="bold")
        step = max(1, n // 9)
        ax.set_xticks(range(0, n, step))
        ax.set_xticklabels([d.strftime("%H:%M") for d in w.index.tz_convert(TEHRAN)[::step]], fontsize=9)
        ax.set_xlim(-1, n + 12)
        ax.set_ylim(lo - pad, hi + pad)
        ax.grid(color="#EEF0F4")
        ax.set_title(f"{self.sym} M1 · {'SELL' if s < 0 else 'BUY'} gap · Leg {g['leg']} · "
                     f"{g['t3'].tz_convert(TEHRAN):%a %d %b %H:%M} Tehran", loc="left", fontweight="bold")
        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor="white")
        plt.close(fig)
        return buf.getvalue()


def live_candles(name=ALERT_SYMBOL, n_bars=300, timeout=15):
    """کندل‌های M1 همراه کندل در حال تشکیل (برای هشدار زنده)."""
    from .config import ALL_SYMBOLS
    from .data import fetch_candles
    for tv in ALL_SYMBOLS[name]:
        df, err = fetch_candles(tv, "1", n_bars, timeout=timeout)
        if df is not None and len(df) > 30:
            return df
    return None

