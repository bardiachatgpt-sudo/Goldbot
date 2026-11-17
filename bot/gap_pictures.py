"""عکس بزرگ‌نمایی‌شده‌ی یک معامله‌ی گپ روی M1، با ساختار M5 همان لحظه.

ساختار M5 از ۵۰۰ کندل M5 که تا لحظه‌ی ورود بسته شده‌اند (همان چیزی که آن لحظه دیده می‌شد)؛ هر فاز یک جعبه‌ی آبی.
روی کندل‌های M1: جعبه‌ی گپ (کندل ۱ تا ۳)، ورود، حد ضرر، حد سود ۱:۱ و خروج.
"""
import io

import numpy as np
import pandas as pd

from .mtf import (BG, GAP_BUY, GAP_SELL, GRID, M5_EDGE, M5_FILL, M5_LINE, M5_TEXT, MUTED, SL_COL, TEXT, TP_COL,
                  _edges, fmt_price)
from .structure3 import NAMES, segment

BEFORE, AFTER = 35, 12          # کندل M1 قبل از گپ و بعد از خروج
M5_WINDOW = 500


def m5_at(m5, ts):
    """۵۰۰ کندل M5 که تا زمان ts بسته شده‌اند."""
    step = (m5.index[-1] - m5.index[-2]) if len(m5) > 1 else pd.Timedelta(minutes=5)
    return m5[m5.index + step <= ts].tail(M5_WINDOW)


def trade_picture(sym, m1, m5, t, num=None):
    """m1: همان کندل‌هایی که بک‌تست روی آن اجرا شد (اندیس‌های t نسبت به آن). t: معامله با entry_time."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt

    i1, i3 = t["gap"]
    e, x = t["entry_i"], t.get("exit_i") if t.get("exit_i") is not None else min(len(m1) - 1, t["entry_i"] + 20)
    a = max(0, i1 - BEFORE)
    b = min(len(m1), x + AFTER + 1)
    w = m1.iloc[a:b]
    o, h, l, c = (w[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    n = len(w)
    s = t["side"]
    lo = min(l.min(), t["sl"], t["tp"])
    hi = max(h.max(), t["sl"], t["tp"])
    span = (hi - lo) or 1.0
    pad = span * 0.04

    fig, ax = plt.subplots(figsize=(14, 7.5), dpi=100)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    # ---- M5 در لحظه‌ی ورود
    now5 = "-"
    h5w = m5_at(m5, t["entry_time"]) if m5 is not None else None
    if h5w is not None and len(h5w) >= 100:
        c5 = h5w["Close"].values.astype(float)
        h5, l5 = h5w["High"].values.astype(float), h5w["Low"].values.astype(float)
        ph5, piv5 = segment(c5)
        t5 = h5w.index
        step5 = pd.Timedelta(minutes=5)

        def pos5(ts):
            k = max(int(t5.searchsorted(ts, side="right")) - 1, 0)
            return k + (ts - t5[k]) / step5

        p5 = np.array([pos5(ts) for ts in w.index])
        last5 = len(ph5) - 1
        now5 = NAMES[(ph5[-1]["type"], ph5[-1]["side"])]
        for k, ph in enumerate(ph5):
            pa, pb = ph["start"], ph["end"]
            b_pos = p5[-1] + 1 if k == last5 else pb
            on = (p5 >= pa) & (p5 <= b_pos)
            if not on.any():
                continue
            xs = np.where(on)[0]
            upper, lower = _edges(ph, c5, h5, l5, piv5, p5[xs])
            upper = np.clip(upper, lo - span, hi + span)
            lower = np.clip(lower, lo - span, hi + span)
            ax.fill_between(xs, lower, upper, color=M5_FILL, alpha=0.9, lw=0, zorder=1)
            ax.plot(xs, upper, color=M5_LINE, lw=2.2, zorder=2)
            ax.plot(xs, lower, color=M5_LINE, lw=2.2, zorder=2)
            if len(xs) >= 8:
                ax.text(xs[0] + 0.5, hi + pad * 0.6, f"M5 · {NAMES[(ph['type'], ph['side'])]}", color=M5_TEXT,
                        fontsize=10.5, fontweight="bold", va="bottom", zorder=9)
                for y, edge in ((upper[-1], "top"), (lower[-1], "bottom")):
                    if lo - pad <= y <= hi + pad:
                        ax.text(xs[-1], y, f" M5 {edge} {fmt_price(sym, y)}", color=M5_TEXT, fontsize=8.5,
                                va="center", zorder=9,
                                bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor=M5_EDGE, lw=0.6))

    # ---- کندل‌های M1
    for i in range(n):
        up = c[i] >= o[i]
        col = "#4B5563" if up else "#1F2937"
        ax.vlines(i, l[i], h[i], color=col, lw=1.1, zorder=5)
        ax.add_patch(patches.Rectangle((i - 0.33, min(o[i], c[i])), 0.66, max(abs(c[i] - o[i]), span * 2e-3),
                                       facecolor="white" if up else col, edgecolor=col, lw=1.0, zorder=5))

    # ---- گپ، ورود، حد ضرر، حد سود، خروج
    g1, g3, xe, xx = i1 - a, i3 - a, e - a, x - a
    gc = GAP_SELL if s < 0 else GAP_BUY
    ax.add_patch(patches.Rectangle((g1 - 0.5, t["gap_lo"]), g3 - g1 + 1, t["gap_hi"] - t["gap_lo"], facecolor=gc,
                                   alpha=0.45, edgecolor=gc, lw=1.2, zorder=6))
    ax.text(g1, (h[g1] if s < 0 else l[g1]) + (pad * 0.4 if s < 0 else -pad * 0.4), "1", color=gc, fontsize=10,
            fontweight="bold", ha="center", va="bottom" if s < 0 else "top", zorder=9)
    ax.text(g3, (l[g3] if s < 0 else h[g3]) + (-pad * 0.4 if s < 0 else pad * 0.4), "3", color=gc, fontsize=10,
            fontweight="bold", ha="center", va="top" if s < 0 else "bottom", zorder=9)
    ax.text((g1 + g3) / 2, (t["gap_hi"] + t["gap_lo"]) / 2, "GAP", color="#7C2D12" if s < 0 else "#134E4A",
            fontsize=8, fontweight="bold", ha="center", va="center", zorder=9)
    ax.axvline(xe - 0.5, color=MUTED, lw=1, ls=":", zorder=3)
    for y, col, name in ((t["sl"], SL_COL, "SL"), (t["tp"], TP_COL, "TP 1:1"), (t["entry"], TEXT, "ENTRY")):
        ax.hlines(y, xe - 0.5, xx + 0.5, color=col, lw=1.6 if name != "ENTRY" else 1.0,
                  ls=(0, (5, 3)) if name != "ENTRY" else ":", zorder=7)
        ax.text(xx + 0.8, y, f"{name} {fmt_price(sym, y)}", color=col, fontsize=9, fontweight="bold",
                va="center", zorder=9)
    ax.plot(xe, t["entry"], "v" if s < 0 else "^", color=TEXT, ms=12, zorder=10, mec="white", mew=1)
    if t.get("exit_i") is not None:
        win = t["r"] > 0
        ax.plot(xx, t["exit"], "o", color=TP_COL if win else SL_COL, ms=11, zorder=10, mec="white", mew=1)

    # ---- محور و عنوان
    step = max(1, n // 10)
    ax.set_xticks(range(0, n, step))
    try:
        from .config import TEHRAN
        ax.set_xticklabels([d.strftime("%H:%M") for d in w.index.tz_convert(TEHRAN)[::step]], fontsize=9,
                           color=MUTED)
        day = w.index[0].tz_convert(TEHRAN).strftime("%d %b")
        ax.set_xlabel(f"Tehran time · {day}", color=MUTED)
    except Exception:
        pass
    ax.set_xlim(-1, n + 9)
    ax.set_ylim(lo - pad, hi + pad * 3)
    ax.tick_params(colors=MUTED)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.grid(color=GRID, lw=0.6)
    when = t["entry_time"].tz_convert("Asia/Tehran").strftime("%d %b %H:%M")
    res = "" if t.get("r") is None else f" · {'WIN' if t['r'] > 0 else 'LOSS'} {t['r']:+g}R"
    head = f"#{num} " if num else ""
    ax.set_title(f"{head}{sym} M1 · {'SELL' if s < 0 else 'BUY'} gap · {when} Tehran{res}\nM5 at entry: {now5}",
                 color=TEXT, fontsize=12.5, fontweight="bold", loc="left")
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    return buf.getvalue()


def caption(sym, t, num):
    when = t["entry_time"].tz_convert("Asia/Tehran").strftime("%d %b %H:%M")
    side = "SELL" if t["side"] < 0 else "BUY"
    out = (f"#{num} {side} {when} Tehran · entry {fmt_price(sym, t['entry'])} · SL {fmt_price(sym, t['sl'])} · "
           f"TP {fmt_price(sym, t['tp'])}")
    if t.get("r") is not None:
        out += f" → {'🏆' if t['r'] > 0 else '🛑'} {t['r']:+g}R"
    return out
