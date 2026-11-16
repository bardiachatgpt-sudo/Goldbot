"""M1 با ساختار M5 روی زمینه‌ی سفید: کندل‌های یک دقیقه، ساختار M5 (آبی کم‌رنگ، با برچسب M5 کنار هر جعبه و خط)
و چرخه‌های کوچک M1 (خط‌های رنگی نازک و نوار پایین؛ هر حالت یک رنگ).

- ساختار M5 دقیقاً همان دکمه‌ی M5 است (۵۰۰ کندل M5، bot/structure3.py)؛ فقط با زمان روی M1 نشانده می‌شود.
  خط‌های فاز آخر M5 تا آخرین کندل M1 ادامه دارند (کندل M5 در حال تشکیل هنوز در ساختار نیست).
- چرخه‌های M1 با همان قاعده روی همان کندل‌های M1 که در عکس هست (مقیاس خودش).
- بازه‌ی عکس: دو ساختار آخر M5 (حداقل MIN_M1، حداکثر MAX_M1 کندل یک دقیقه).
"""
import io

import numpy as np
import pandas as pd

from .structure3 import NAMES, lines, now_text, segment

MIN_M1, MAX_M1 = 300, 1200

# رنگ‌ها روی زمینه‌ی سفید: همه‌ی ساختار M5 آبی کم‌رنگ (با برچسب «M5» کنار هر جعبه و خط)،
# چرخه‌های M1 با رنگ‌های جدا برای هر حالت، کندل‌ها خاکستری تا رنگ‌ها فقط مال ساختار باشند
M5_FILL, M5_EDGE, M5_LINE, M5_TEXT = "#E8F2FD", "#A9CDF3", "#6FB1EE", "#2F7FC8"
MICRO = {"RANGE": "#8B5CF6", "SPIKE": "#EA580C", 1: "#16A34A", -1: "#DC2626"}
BG, PANEL, GRID, TEXT, MUTED = "#FFFFFF", "#FFFFFF", "#EEF0F4", "#111827", "#6B7280"
UP, DOWN = "#A3A9B4", "#3F4652"         # کندل صعودی خاکستری روشن، نزولی خاکستری تیره


def _color(table, ph):
    return table[ph["side"]] if ph["type"] == "CHANNEL" else table[ph["type"]]


def m1_window(m5, m1, zoom=2):
    """بازه‌ی M1 برای عکس: از شروع k فاز آخر M5 تا آخر، محدود به MIN_M1..MAX_M1 کندل."""
    phases, _ = segment(m5["Close"].values.astype(float))
    k = min(zoom, len(phases))
    t0 = m5.index[phases[-k]["start"]] if phases else m1.index[0]
    w = m1[m1.index >= t0]
    if len(w) < MIN_M1:
        w = m1.tail(MIN_M1)
    return w.tail(MAX_M1)


def render(sym, m5, m1):
    """(png، فازهای M5، فازهای M1، وضعیت M5، وضعیت M1). m5/m1: Open/High/Low/Close، زمان = شروع کندل."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt

    c5 = m5["Close"].values.astype(float)
    h5, l5 = m5["High"].values.astype(float), m5["Low"].values.astype(float)
    ph5, piv5 = segment(c5)
    w = m1_window(m5, m1)
    o, h, l, c = (w[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    n = len(c)
    ph1, piv1 = segment(c)
    t1 = w.index
    t5 = m5.index
    step5 = (t5[-1] - t5[-2]) if len(t5) > 1 else pd.Timedelta(minutes=5)

    def pos5(ts):
        """زمان → جایگاه (اعشاری) روی محور M5؛ وسط کندل‌های بسته نشده هم ادامه دارد."""
        k = int(t5.searchsorted(ts, side="right")) - 1
        k = max(k, 0)
        return k + (ts - t5[k]) / step5

    p5 = np.array([pos5(ts) for ts in t1])          # جایگاه M5 هر کندل M1
    lo, hi = l.min(), h.max()
    span = hi - lo
    pad = span * 0.02
    ribbon_h = span * 0.035
    ybot = lo - pad - ribbon_h * 1.8                 # نوار چرخه‌های M1 پایین نمودار

    fig, ax = plt.subplots(figsize=(22, 10), dpi=100)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    # ---- M5: جعبه‌ها و خط‌ها (پررنگ)
    last5 = len(ph5) - 1
    for k, ph in enumerate(ph5):
        a, b = ph["start"], ph["end"]
        if k == last5:
            b_pos = p5[-1] + 1                       # فاز آخر تا آخرین کندل M1
        else:
            b_pos = b
        on = (p5 >= a) & (p5 <= b_pos)
        if not on.any():
            continue
        xa, xb = int(np.argmax(on)), int(len(on) - 1 - np.argmax(on[::-1]))
        if xb - xa < 5:                              # فقط لبه‌ای از فاز پیداست: نکش
            continue
        top = max(h5[a:b + 1].max(), h[xa:xb + 1].max())
        bot = min(l5[a:b + 1].min(), l[xa:xb + 1].min())
        ax.add_patch(patches.FancyBboxPatch((xa - 0.5, bot - pad * 0.6), xb - xa + 1, top - bot + pad * 1.2,
                                            boxstyle="round,pad=0,rounding_size=2", facecolor=M5_FILL, alpha=0.75,
                                            edgecolor=M5_EDGE, lw=1.4, zorder=1))
        if xb - xa >= 25:
            ax.text(xa + 2, top + pad * 0.9, f"M5 · {NAMES[(ph['type'], ph['side'])]}", color=M5_TEXT, fontsize=12,
                    fontweight="bold", va="bottom", zorder=7)
        ls5 = lines(ph, c5, piv5)
        if ph["type"] == "RANGE":
            roles = ["M5 range top", "M5 range bottom"]
        elif ph["type"] == "CHANNEL":
            roles = ["M5 trend line", "M5 parallel line"]
        else:
            roles = []
        for (x0, y0, x1, y1, role), name in zip(ls5, roles):
            if k == last5:                           # خط‌های فاز آخر تا حال ادامه دارند
                x1n = max(x1, p5[-1] + 1)
                y1 = y0 + (y1 - y0) * (x1n - x0) / (x1 - x0) if x1 != x0 else y1
                x1 = x1n
            seg = on & (p5 >= x0) & (p5 <= x1)
            if not seg.any() or x1 == x0:
                continue
            xs = np.where(seg)[0]
            ys = y0 + (y1 - y0) * (p5[xs] - x0) / (x1 - x0)
            ax.plot(xs, ys, color=M5_LINE, lw=3.0 if role != "parallel" else 2.2,
                    ls="-" if role != "parallel" else (0, (6, 3)), alpha=0.95, zorder=5, solid_capstyle="round")
            if len(xs) >= 25:                        # «M5 …» جلوی همان خط
                above = name != "M5 range bottom"
                ax.text(xs[-1], ys[-1] + (pad * 0.5 if above else -pad * 0.5), name, color=M5_TEXT, fontsize=9,
                        fontweight="bold", ha="right", va="bottom" if above else "top", zorder=8,
                        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.8))

    # ---- M1: خط‌های چرخه‌های کوچک (نازک) و نوار رنگی پایین
    for ph in ph1:
        cc = _color(MICRO, ph)
        a, b = ph["start"], ph["end"]
        for x0, y0, x1, y1, role in lines(ph, c, piv1):
            ax.plot([x0, x1], [y0, y1], color=cc, lw=1.5, ls=(0, (2, 2)) if role == "parallel" else "-",
                    alpha=0.9, zorder=4)
        ax.add_patch(patches.Rectangle((a - 0.5, ybot), b - a + 1, ribbon_h, facecolor=cc, alpha=0.9,
                                       edgecolor=PANEL, lw=1.5, zorder=2))
        if b - a >= 18:
            short = {"TRADING RANGE": "range", "BULL CHANNEL": "bull ch.", "BEAR CHANNEL": "bear ch."}
            name = NAMES[(ph["type"], ph["side"])]
            ax.text((a + b) / 2, ybot + ribbon_h / 2, "M1 " + short.get(name, name.lower()), color="white", fontsize=8,
                    fontweight="bold", ha="center", va="center", zorder=3)
    ax.text(0, ybot + ribbon_h * 1.25, "M1 micro cycles", color=MUTED, fontsize=9, va="bottom")

    # ---- کندل‌های M1
    width = 0.62
    for i in range(n):
        cl = UP if c[i] >= o[i] else DOWN
        ax.vlines(i, l[i], h[i], color=cl, lw=0.7, zorder=6, alpha=0.9)
        ax.add_patch(patches.Rectangle((i - width / 2, min(o[i], c[i])), width, max(abs(c[i] - o[i]), span * 1e-4),
                                       color=cl, zorder=6, lw=0))

    # ---- محورها و عنوان
    stepx = max(1, n // 12)
    ax.set_xticks(range(0, n, stepx))
    try:
        from .config import TEHRAN
        ax.set_xticklabels([d.strftime("%d %b %H:%M") for d in t1.tz_convert(TEHRAN)[::stepx]], rotation=30,
                           fontsize=8, color=MUTED)
        ax.set_xlabel("Tehran time", color=MUTED)
    except Exception:
        pass
    ax.set_xlim(-2, n + 3)
    ax.set_ylim(ybot - pad * 0.5, hi + pad * 4)
    ax.tick_params(colors=MUTED)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.grid(color=GRID, lw=0.6)
    now5, now1 = now_text(ph5), now_text(ph1)
    ax.set_title(f"{sym} · M1 candles · M5 structure + M1 micro cycles\n"
                 f"M5 now: {NAMES[(ph5[-1]['type'], ph5[-1]['side'])]}   ·   "
                 f"M1 now: {NAMES[(ph1[-1]['type'], ph1[-1]['side'])]}   ·   {n} M1 candles",
                 color=TEXT, fontsize=13, fontweight="bold", loc="left", pad=12)
    # راهنما بالای نمودار، سمت راست (روی نمودار چیزی را نمی‌پوشاند)
    from matplotlib.lines import Line2D
    handles = [Line2D([0], [0], color=M5_LINE, lw=3.2, label="M5 structure"),
               Line2D([0], [0], color=MICRO["RANGE"], lw=1.6, label="M1 range"),
               Line2D([0], [0], color=MICRO[1], lw=1.6, label="M1 bull channel"),
               Line2D([0], [0], color=MICRO[-1], lw=1.6, label="M1 bear channel"),
               Line2D([0], [0], color=MICRO["SPIKE"], lw=1.6, label="M1 spike")]
    leg = ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, 1.005), ncol=5, frameon=False,
                    fontsize=10, handlelength=2.6)
    for t in leg.get_texts():
        t.set_color(MUTED)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    return buf.getvalue(), ph5, ph1, now5, now1
