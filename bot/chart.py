"""نمودار کندلی با EMA20، سوئینگ‌ها، ستاپ‌های H/L و Wedge (برگرفته از chart_plotter.py)."""
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as patches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .config import CHART_BARS, TEHRAN, label, tf_label  # noqa: E402

BULL, BEAR, DOJI, EMA = "#10B981", "#EF4444", "#9CA3AF", "#F59E0B"


SEG_COLORS = {"RANGE": "#60A5FA", "SPIKE": "#FACC15", "CHANNEL": None, "TEST": "#A78BFA"}
SEG_TEXT = {"RANGE": "RANGE", "SPIKE": "SPIKE", "CHANNEL": "CHANNEL", "TEST": "TEST"}


def _draw_cycle(ax, eng, n_full, start, n_vis, top, pad):
    """بخش‌های چرخه (سایه‌ی پس‌زمینه + برچسب) و خطوط کانال/رنج فعلی."""
    off = eng.n - n_full                         # اندیس موتور → اندیس df

    def vis(k):
        return k - off - start

    for seg in eng.segments:
        a = vis(seg["start"])
        b = vis(seg["end"] if seg["end"] is not None else eng.n - 1)
        if b < 0 or a > n_vis - 1:
            continue
        a, b = max(a, 0), min(b, n_vis - 1)
        col = SEG_COLORS[seg["state"]] or (BULL if seg["side"] > 0 else BEAR)
        ax.axvspan(a - 0.5, b + 0.5, color=col, alpha=0.06, linewidth=0)
        arrow = "" if seg["side"] == 0 else ("↑" if seg["side"] > 0 else "↓")
        if b - a >= 2:
            ax.text((a + b) / 2, top + pad * 8, SEG_TEXT[seg["state"]] + arrow, color=col, fontsize=7,
                    ha="center", va="bottom", fontweight="bold", alpha=0.9)

    snap = eng.snapshot()
    last = n_vis - 1
    if snap["state"] in ("CHANNEL", "TEST") and "trend_line" in snap:
        a = vis(snap["anchor_i"])
        xs = np.array([max(a, 0), last + 5])
        k = xs + off + start                     # برگشت به اندیس موتور
        tl = snap["start_price"] + snap["slope"] * (k - snap["anchor_i"])
        col = BULL if snap["side"] > 0 else BEAR
        ax.plot(xs, tl, color=col, linewidth=1.6, label="Major trend line")
        if snap["state"] == "CHANNEL":
            ax.plot(xs, tl + snap["offset"], color=col, linewidth=1.0, linestyle="--", label="Channel line")
        else:
            ax.axhline(snap["high"], color="#A78BFA", linewidth=1.0, linestyle=":", label="High to test")
    elif snap["state"] == "RANGE" and snap.get("hi"):
        a = max(vis(eng.since), 0)
        for y in (snap["hi"], snap["lo"]):
            ax.plot([a, last + 3], [y, y], color="#60A5FA", linewidth=1.2, linestyle="--")
        ax.plot([a, last + 3], [snap["mid"]] * 2, color="#60A5FA", linewidth=0.7, linestyle=":")


def render_chart(sym, res, n=CHART_BARS):
    """تصویر PNG به‌صورت bytes."""
    full = res["df"]
    start = max(0, len(full) - n)
    df = full.iloc[start:].reset_index(drop=True)
    x = np.arange(len(df))
    span = float(df["high"].max() - df["low"].min()) or 1.0
    pad = span * 0.02

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(14, 7), dpi=110)
    fig.patch.set_facecolor("#121214")
    ax.set_facecolor("#18181B")
    ax.plot(x, df["ema20"], color=EMA, linewidth=1.6, label="20 EMA", alpha=0.9)

    for i, r in df.iterrows():
        o, h, l, c = r["open"], r["high"], r["low"], r["close"]
        color = BULL if c > o else BEAR if c < o else DOJI
        ax.vlines(i, l, h, color=color, linewidth=1)
        ax.add_patch(patches.Rectangle((i - 0.3, min(o, c)), 0.6, max(abs(c - o), span * 0.001),
                                       facecolor=color, edgecolor=color, linewidth=0.6))
        if r["h_setup"] > 0:
            ax.text(i, l - pad, f"H{int(r['h_setup'])}", color=BULL, fontsize=8,
                    fontweight="bold", ha="center", va="top")
        if r["l_setup"] > 0:
            ax.text(i, h + pad, f"L{int(r['l_setup'])}", color=BEAR, fontsize=8,
                    fontweight="bold", ha="center", va="bottom")

        if r["pin_bar"]:
            up = r["pin_bar"] > 0
            ax.text(i, (l - pad * 4) if up else (h + pad * 4), "PIN", color=BULL if up else BEAR,
                    fontsize=7, ha="center", va="top" if up else "bottom")
        if r["range_bo"] or r["wedge_bo"]:
            up = (r["range_bo"] or r["wedge_bo"]) > 0
            ax.annotate("BO", xy=(i, h if up else l), xytext=(i, (h + pad * 6) if up else (l - pad * 6)),
                        color="#FACC15", fontsize=8, fontweight="bold", ha="center",
                        arrowprops=dict(arrowstyle="->", color="#FACC15"))

    if res.get("cycle") is not None:
        _draw_cycle(ax, res["cycle"], len(full), start, len(df), df["high"].max(), pad)

    for s in res["swing_highs"]:
        if s["index"] >= start:
            ax.plot(s["index"] - start, s["price"] + pad * 2.5, marker="v", color="#F43F5E", markersize=5)
    for s in res["swing_lows"]:
        if s["index"] >= start:
            ax.plot(s["index"] - start, s["price"] - pad * 2.5, marker="^", color="#06B6D4", markersize=5)

    for w in res["wedges"]:
        pts = [p for p in w["points"] if p["index"] >= start]
        if len(pts) == 3:
            ax.plot([p["index"] - start for p in pts], [p["price"] for p in pts],
                    color=BULL if w["side"] > 0 else BEAR, linestyle="--", linewidth=1.2)

    dates = df["date"].dt.tz_convert(TEHRAN)
    step = max(1, len(df) // 10)
    ax.set_xticks(x[::step])
    ax.set_xticklabels(dates.dt.strftime("%d %b %H:%M")[::step], rotation=30, color="#9CA3AF", fontsize=8)
    ax.tick_params(axis="y", colors="#9CA3AF")
    ax.grid(True, linestyle="--", color="#27272A", alpha=0.7)
    for spine in ax.spines.values():
        spine.set_color("#27272A")
    ax.set_xlim(-1, len(df) + 6)
    ax.set_title(f"{label(sym).split()[-1]} {tf_label()} · Al Brooks Price Action · {res['market_cycle']}",
                 color="#F3F4F6", fontsize=13, fontweight="bold")
    ax.set_xlabel("Tehran time", color="#9CA3AF", fontsize=8)
    ax.legend(facecolor="#18181B", edgecolor="#27272A", loc="upper left")
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#121214")
    plt.close(fig)
    return buf.getvalue()
