"""عکس هر معامله‌ی بک‌تست رنج: رنجی که ربات در لحظه‌ی ورود دید، ورود، حد ضرر، حد سود و خروج.

سمت چپ خط عمودی خاکستری = همان چیزی که ربات هنگام ورود می‌دید؛ سمت راست = بعد از ورود تا خروج.
"""
import io

import pandas as pd

BEFORE = 120            # کندل قبل از ورود
AFTER = 15              # کندل بعد از خروج


def trade_chart(df, t, num=None, sym="", decimals=2):
    """df: کندل‌های M5 (Open/High/Low/Close، زمان = شروع کندل). t: رویداد TRADE_CLOSED (یا باز)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt

    idx = df.index
    i_in = int(idx.searchsorted(t["opened"]))
    exit_time = t.get("time")
    i_out = int(idx.searchsorted(exit_time - pd.Timedelta(minutes=5))) if exit_time is not None and \
        t.get("kind") == "TRADE_CLOSED" else min(len(df) - 1, i_in + 30)
    i_out = max(i_out, i_in)
    rb = int(t.get("range_bars") or 0)
    a = max(0, min(i_in - BEFORE, i_in - rb - 10))
    b = min(len(df), i_out + AFTER + 1)
    d = df.iloc[a:b]
    o, h, l, c = (d[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    n = len(d)
    x_in, x_out = i_in - a, i_out - a

    fig, ax = plt.subplots(figsize=(13, 6.5), dpi=90)
    fig.patch.set_facecolor("#121214")
    ax.set_facecolor("#18181B")
    ax.axvspan(x_in - 0.5, n, color="#FFFFFF", alpha=0.03, zorder=0)           # بعد از ورود
    ax.axvline(x_in - 0.5, color="#71717A", lw=1, ls=":", zorder=1)
    for i in range(n):
        col = "#10B981" if c[i] >= o[i] else "#EF4444"
        ax.vlines(i, l[i], h[i], color=col, lw=1, zorder=3)
        ax.add_patch(patches.Rectangle((i - 0.3, min(o[i], c[i])), 0.6, max(abs(c[i] - o[i]), 1e-9),
                                       color=col, zorder=3))
    # رنج در لحظه‌ی ورود
    top, bot = t.get("range_high"), t.get("range_low")
    if top is not None and bot is not None:
        r0 = max(0, x_in - max(rb, 1))
        ax.add_patch(patches.Rectangle((r0 - 0.5, bot), x_in - r0, top - bot, facecolor="#60A5FA", alpha=0.10,
                                       edgecolor="#60A5FA", lw=1.2, zorder=2))
        ax.text(r0, top, "  range the bot saw", color="#60A5FA", fontsize=9, va="bottom")
    side = t["side"]
    ent, sl, tp = t["entry"], t["sl"], t["tp"]
    fmt = f"{{:.{decimals}f}}"
    ax.hlines(sl, x_in - 0.5, x_out + 0.5, color="#EF4444", lw=1.6, ls="--", zorder=4)
    ax.hlines(tp, x_in - 0.5, x_out + 0.5, color="#10B981", lw=1.6, ls="--", zorder=4)
    ax.text(x_out + 0.8, sl, "SL " + fmt.format(sl), color="#EF4444", fontsize=9, va="center")
    ax.text(x_out + 0.8, tp, "TP " + fmt.format(tp), color="#10B981", fontsize=9, va="center")
    ax.plot(x_in, ent, "^" if side > 0 else "v", color="#FBBF24", ms=13, zorder=6, mec="#121214")
    ax.text(x_in - 1, ent, ("BUY " if side > 0 else "SELL ") + fmt.format(ent) + "  ", color="#FBBF24",
            fontsize=10, fontweight="bold", ha="right", va="center", zorder=6)
    if t.get("kind") == "TRADE_CLOSED":
        ex = t["exit"]
        win = t["r"] > 0
        ax.plot(x_out, ex, "o", color="#10B981" if win else "#EF4444", ms=11, zorder=6, mec="#121214")
        ax.plot([x_in, x_out], [ent, ex], color="#FBBF24", lw=1, ls=":", zorder=5)
    lo = min(l.min(), sl, tp)
    hi = max(h.max(), sl, tp)
    pad = (hi - lo) * 0.05
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xlim(-1, n + 6)
    step = max(1, n // 10)
    ax.set_xticks(range(0, n, step))
    try:
        from .config import TEHRAN
        dates = d.index.tz_convert(TEHRAN)
        ax.set_xticklabels([x.strftime("%d %b %H:%M") for x in dates[::step]], rotation=30, fontsize=8)
        ax.set_xlabel("Tehran time", color="#9CA3AF")
    except Exception:
        pass
    res = ""
    if t.get("kind") == "TRADE_CLOSED":
        res = f" · {'WIN' if t['r'] > 0 else 'LOSS'} {t['r']:+.2f}R"
    when = t["opened"].tz_convert("Asia/Tehran").strftime("%d %b %H:%M") if hasattr(t["opened"], "tz_convert") \
        else str(t["opened"])
    head = f"#{num} " if num else ""
    ax.set_title(f"{head}{sym} M5 · {'BUY at the range bottom' if side > 0 else 'SELL at the range top'} · "
                 f"{when} Tehran{res}", color="#F3F4F6", fontsize=12, fontweight="bold")
    ax.tick_params(colors="#9CA3AF")
    for s in ax.spines.values():
        s.set_color("#3F3F46")
    ax.grid(color="#27272A", lw=0.5)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#121214")
    plt.close(fig)
    return buf.getvalue()


def caption(t, num, decimals=2):
    fmt = f"{{:.{decimals}f}}"
    when = t["opened"].tz_convert("Asia/Tehran").strftime("%d %b %H:%M")
    side = "BUY" if t["side"] > 0 else "SELL"
    out = (f"#{num} {side} {when} Tehran · entry {fmt.format(t['entry'])} · SL {fmt.format(t['sl'])} · "
           f"TP {fmt.format(t['tp'])}")
    if t.get("kind") == "TRADE_CLOSED":
        out += f" → {'🏆' if t['r'] > 0 else '🛑'} {fmt.format(t['exit'])} ({t['r']:+.2f}R)"
    return out
