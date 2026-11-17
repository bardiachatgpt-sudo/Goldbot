"""M1 با ساختار M5 روی زمینه‌ی سفید: کندل‌های یک دقیقه (خاکستری)، هر فاز M5 یک جعبه‌ی آبی کم‌رنگ
(رنج صاف، کانال مورب) با قیمت سقف و کف، و داخلش چرخه‌های ریز M1 با خط مشکی: همان تشخیص ریز نسخه‌ی ۱
(bot/structure.py: رنج، رنج مشکوک، اسپایک، کانال صعودی/نزولی، با سوئینگ‌ها).

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
MAX_GAP = 480           # نمای گپ: حداکثر ۸ ساعت M1 تا هر ستاپ خوانا باشد

# رنگ‌ها روی زمینه‌ی سفید: همه‌ی ساختار M5 آبی کم‌رنگ (با برچسب «M5» کنار هر جعبه و خط)،
# چرخه‌های M1 با رنگ‌های جدا برای هر حالت، کندل‌ها خاکستری تا رنگ‌ها فقط مال ساختار باشند
M5_FILL, M5_EDGE, M5_LINE, M5_TEXT = "#E8F2FD", "#A9CDF3", "#6FB1EE", "#2F7FC8"
M1_LINE = "#111111"                      # ساختارهای M1: خط مشکی
GAP_SELL, GAP_BUY = "#F59E0B", "#14B8A6"  # جعبه‌ی گپ فروش (نارنجی) و خرید (فیروزه‌ای)
SL_COL, TP_COL = "#DC2626", "#16A34A"
BG, PANEL, GRID, TEXT, MUTED = "#FFFFFF", "#FFFFFF", "#EEF0F4", "#111827", "#6B7280"
UP, DOWN = "#B9BFC9", "#7C8490"         # کندل‌ها خاکستری روشن تا ساختار دیده شود


def fmt_price(sym, x):
    dec = 2 if sym == "XAUUSD" else 1 if sym == "US30" else 3 if "JPY" in sym else 5
    return f"{x:.{dec}f}"


def _edges(ph, c5, h5, l5, piv5, pos):
    """سقف و کف جعبه‌ی یک فاز M5 در جایگاه‌های pos (روی محور M5): رنج صاف (یا مثلثی)، کانال مورب، اسپایک صاف."""
    a, b = ph["start"], ph["end"]
    ls = lines(ph, c5, piv5)
    if len(ls) == 2:
        vals = []
        for x0, y0, x1, y1, _ in ls:
            sl = (y1 - y0) / (x1 - x0) if x1 != x0 else 0.0
            vals.append(y0 + sl * (pos - x0))
        u, d = vals
        return np.maximum(u, d), np.minimum(u, d)
    top, bot = c5[a:b + 1].max(), c5[a:b + 1].min()
    return np.full(len(pos), top), np.full(len(pos), bot)


def micro_cycles(o, h, l, c):
    """چرخه‌های ریز M1 با نسخه‌ی ۱ ساختار (bot/structure.py: سوئینگ با سایه‌ها، برگشت ۱.۵ کندل متوسط):
    فازهای {type, side, start, end, lines, doubt} و سوئینگ‌ها."""
    from .structure import detect
    phases, _, piv, _ = detect(o, h, l, c)
    return phases, piv


def m1_window(m5, m1, zoom=2, max_bars=MAX_M1):
    """بازه‌ی M1 برای عکس: از شروع k فاز آخر M5 تا آخر، محدود به MIN_M1..MAX_M1 کندل."""
    phases, _ = segment(m5["Close"].values.astype(float))
    k = min(zoom, len(phases))
    t0 = m5.index[phases[-k]["start"]] if phases else m1.index[0]
    w = m1[m1.index >= t0]
    if len(w) < MIN_M1:
        w = m1.tail(MIN_M1)
    return w.tail(max_bars)


def render(sym, m5, m1, layer="gaps", m5_full=None):
    """(png، فازهای M5، فازهای M1، وضعیت M5، وضعیت M1). m5/m1: Open/High/Low/Close، زمان = شروع کندل."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt

    c5 = m5["Close"].values.astype(float)
    h5, l5 = m5["High"].values.astype(float), m5["Low"].values.astype(float)
    ph5, piv5 = segment(c5)
    w = m1_window(m5, m1, max_bars=MAX_M1 if layer == "micro" else MAX_GAP)
    o, h, l, c = (w[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    n = len(c)
    if layer == "micro":
        ph1, piv1 = micro_cycles(o, h, l, c)
    else:
        from .gap import m5_target_filter, trades as gap_trades
        src = m5_full if m5_full is not None else m5
        skipped = []
        ph1 = gap_trades(o, h, l, c, sym, allow=m5_target_filter(src, w.index), skipped=skipped)
        piv1 = []
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

    fig, ax = plt.subplots(figsize=(22, 10), dpi=100)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)
    box_lo, box_hi = lo, hi

    # ---- M5: هر فاز یک جعبه (رنج صاف، کانال مورب)، آبی کم‌رنگ، با قیمت سقف و کف
    last5 = len(ph5) - 1
    for k, ph in enumerate(ph5):
        a, b = ph["start"], ph["end"]
        b_pos = p5[-1] + 1 if k == last5 else b      # فاز آخر تا آخرین کندل M1
        on = (p5 >= a) & (p5 <= b_pos)
        if not on.any():
            continue
        xs = np.where(on)[0]
        if len(xs) < 6:                              # فقط لبه‌ای از فاز پیداست: نکش
            continue
        upper, lower = _edges(ph, c5, h5, l5, piv5, p5[xs])
        box_lo, box_hi = min(box_lo, lower.min()), max(box_hi, upper.max())
        ax.fill_between(xs, lower, upper, color=M5_FILL, alpha=0.85, lw=0, zorder=1)
        ax.plot(xs, upper, color=M5_LINE, lw=2.6, zorder=2, solid_capstyle="round")
        ax.plot(xs, lower, color=M5_LINE, lw=2.6, zorder=2, solid_capstyle="round")
        ax.plot([xs[0], xs[0]], [lower[0], upper[0]], color=M5_LINE, lw=1.4, zorder=2)
        ax.plot([xs[-1], xs[-1]], [lower[-1], upper[-1]], color=M5_LINE, lw=1.4, zorder=2)
        name = NAMES[(ph["type"], ph["side"])]
        if len(xs) >= 25:
            ax.text(xs[0] + 2, min(upper[0], h.max() + span * 0.1) + pad * 0.6, f"M5 · {name}", color=M5_TEXT,
                    fontsize=12,
                    fontweight="bold", va="bottom", zorder=9,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.85))
            word = {"RANGE": "range", "CHANNEL": "channel", "SPIKE": "spike"}[ph["type"]]
            vlo, vhi = l.min() - span * 0.12, h.max() + span * 0.12      # همان محدوده‌ی نمایش
            for y, edge, va in ((upper[-1], "top", "bottom"), (lower[-1], "bottom", "top")):
                arrow = "↑ " if y > vhi else "↓ " if y < vlo else ""
                yt = min(max(y, vlo + pad), vhi - pad)
                ax.text(xs[-1] - 1, yt + (pad * 0.4 if va == "bottom" else -pad * 0.4),
                        f"{arrow}M5 {word} {edge}  {fmt_price(sym, y)}", color=M5_TEXT, fontsize=9.5,
                        fontweight="bold", ha="right", va=va, zorder=9,
                        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor=M5_EDGE, lw=0.8))

    if layer == "micro":
        # ---- M1: چرخه‌های ریز (نسخه‌ی ۱، با سایه‌ها) داخل جعبه‌های M5، همه مشکی
        for ph in ph1:
            a, b = ph["start"], ph["end"]
            doubt = bool(ph.get("doubt"))
            y0, y1 = l[a:b + 1].min(), h[a:b + 1].max()
            ax.add_patch(patches.Rectangle((a - 0.5, y0), b - a + 1, y1 - y0, facecolor="none", edgecolor=M1_LINE,
                                           lw=0.9, ls=":" if doubt else "-", alpha=0.55 if doubt else 0.8, zorder=6))
            ln = ph["lines"]
            if ln:
                xs = np.array([max(ln["x0"], a - 3), b + 1])
                base = ln["y0"] + ln["slope"] * (xs - ln["x0"])
                ax.plot(xs, base, color=M1_LINE, lw=1.4, zorder=7)
                ax.plot(xs, base + ln["off"], color=M1_LINE, lw=1.1, ls=(0, (3, 2)), zorder=7)
            if b - a >= 3 or ph["type"] == "SPIKE":
                name = "RANGE (in doubt)" if doubt else NAMES[(ph["type"], ph["side"])]
                ax.text((a + b) / 2, y1 + pad * 0.15, "M1 · " + name, color=M1_LINE, fontsize=7.5, ha="center",
                        va="bottom", alpha=0.7 if doubt else 1.0, zorder=8)
        for j, t, p, _ in piv1:                             # سوئینگ‌های M1 (کم‌رنگ)
            ax.plot(j, p - pad * 0.5 if t == "L" else p + pad * 0.5, "^" if t == "L" else "v", color="#6B7280",
                    ms=3.5, zorder=6)
    # ---- M1: ستاپ گپ (جعبه‌ی گپ، ورود، حد ضرر، حد سود ۱:۱، خروج)
    else:
        for t in skipped:                                  # گرفته نشد: حد سود بیرون از جعبه‌ی M5 (کم‌رنگ)
            i1, i3 = t["gap"]
            gc = GAP_SELL if t["side"] < 0 else GAP_BUY
            ax.add_patch(patches.Rectangle((i1 - 0.5, t["gap_lo"]), i3 - i1 + 1, t["gap_hi"] - t["gap_lo"],
                                           facecolor="none", edgecolor=gc, lw=0.8, ls=":", zorder=6))
            ax.plot(t["entry_i"], t["entry"], "x", color=MUTED, ms=5, zorder=8)
        for t in ph1:
            i1, i3 = t["gap"]
            s_ = t["side"]
            gc = GAP_SELL if s_ < 0 else GAP_BUY
            ax.add_patch(patches.Rectangle((i1 - 0.5, t["gap_lo"]), i3 - i1 + 1, t["gap_hi"] - t["gap_lo"],
                                           facecolor=gc, alpha=0.35, edgecolor=gc, lw=0.8, zorder=6))
            if t.get("entry_i") is None:                 # گپ در انتظار ورود
                ax.text(i3 + 1, t["gap_hi"] if s_ < 0 else t["gap_lo"], " gap: waiting", color=gc, fontsize=8,
                        va="center", zorder=8)
                continue
            e, x_end = t["entry_i"], t["exit_i"] if t["exit_i"] is not None else n - 1
            ax.hlines(t["sl"], e - 0.5, x_end + 0.5, color=SL_COL, lw=1.0, ls=(0, (3, 2)), zorder=7)
            ax.hlines(t["tp"], e - 0.5, x_end + 0.5, color=TP_COL, lw=1.0, ls=(0, (3, 2)), zorder=7)
            ax.plot(e, t["entry"], "v" if s_ < 0 else "^", color=M1_LINE, ms=7, zorder=9, mec="white", mew=0.6)
            if t["exit_i"] is not None:
                win = t["r"] > 0
                ax.plot(t["exit_i"], t["exit"], "o", color=TP_COL if win else SL_COL, ms=5.5, zorder=9,
                        mec="white", mew=0.6)
                ax.plot([e, t["exit_i"]], [t["entry"], t["exit"]], color=M1_LINE, lw=0.8, ls=":", zorder=8)

    # ---- کندل‌های M1 (خاکستری روشن، تا خط‌های مشکی و جعبه‌های آبی دیده شوند)
    width = 0.62
    for i in range(n):
        cl = UP if c[i] >= o[i] else DOWN
        ax.vlines(i, l[i], h[i], color=cl, lw=0.7, zorder=5)
        ax.add_patch(patches.Rectangle((i - width / 2, min(o[i], c[i])), width, max(abs(c[i] - o[i]), span * 1e-4),
                                       color=cl, zorder=5, lw=0))
    # محور قیمت از خود کندل‌های M1 (جعبه‌ی M5 اگر خیلی بیرون باشد بریده می‌شود، کندل‌ها کوچک نمی‌شوند)
    lo = max(min(lo, box_lo), lo - span * 0.12)
    hi = min(max(hi, box_hi), hi + span * 0.12)
    ybot = lo - pad

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
    ax.set_ylim(ybot - pad, hi + pad * 4)
    ax.tick_params(colors=MUTED)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.grid(color=GRID, lw=0.6)
    now5 = now_text(ph5)
    from matplotlib.lines import Line2D
    if layer == "micro":
        now1 = NAMES[(ph1[-1]["type"], ph1[-1]["side"])] if ph1 else "unclear"
        if ph1 and ph1[-1].get("doubt"):
            now1 = "RANGE (in doubt)"
        what = "M1 micro cycles"
        h1 = [Line2D([0], [0], color=M1_LINE, lw=1.5, label="M1 micro cycles inside it (fine detection)")]
    else:
        done = [t for t in ph1 if t.get("exit_i") is not None]
        wins = sum(t["r"] > 0 for t in done)
        now1 = (f"{len(done)} gap trades · {wins} wins · {len(done) - wins} losses · "
                f"{sum(t['r'] for t in done):+.0f}R (1:1) · {len(skipped)} skipped (target outside M5)")
        what = "M1 gap setup"
        h1 = [patches.Patch(facecolor=GAP_SELL, alpha=0.5, label="sell gap"),
              patches.Patch(facecolor=GAP_BUY, alpha=0.5, label="buy gap"),
              Line2D([0], [0], color=SL_COL, lw=1.3, ls="--", label="stop"),
              Line2D([0], [0], color=TP_COL, lw=1.3, ls="--", label="target 1:1")]
    ax.set_title(f"{sym} · M1 candles · M5 structure + {what}\n"
                 f"M5 now: {NAMES[(ph5[-1]['type'], ph5[-1]['side'])]}   ·   "
                 f"M1: {now1}   ·   {n} M1 candles",
                 color=TEXT, fontsize=13, fontweight="bold", loc="left", pad=12)
    # راهنما بالای نمودار، سمت راست (روی نمودار چیزی را نمی‌پوشاند)
    handles = [patches.Patch(facecolor=M5_FILL, edgecolor=M5_LINE, lw=2, label="M5 structure")] + h1
    leg = ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, 1.005), ncol=len(handles), frameon=False,
                    fontsize=10, handlelength=2.6)
    for t in leg.get_texts():
        t.set_color(MUTED)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    return buf.getvalue(), ph5, ph1, now5, now1
