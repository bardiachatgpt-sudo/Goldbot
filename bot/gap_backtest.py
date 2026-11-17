"""بک‌تست ستاپ گپ روی M1، M5 یا M15: همان قاعده‌ی bot/gap.py روی همه‌ی کندل‌هایی که TradingView می‌دهد.

حساب ۱۰۰۰ دلاری، ریسک ثابت درصدی از موجودی فعلی (مرکب) برای ۱٪ و ۲٪. بدون اسپرد و کمیسیون.
داخل هر کندل ترتیب قیمت از شکل کندل است (صعودی: باز ← کف ← سقف ← بسته)، پس نتیجه‌ی واقعی کمی فرق می‌کند.
"""
import io

import pandas as pd

from .config import TEHRAN, label
from .gap import RR, trades

BALANCE = 1000.0
RISKS = (1.0, 2.0)
M1_BARS = 5000          # حداکثر کندل که از TradingView گرفته می‌شود (M1 ≈ ۴–۶ روز، M5 ≈ ۳ هفته، M15 ≈ ۲ ماه)
BT_TIMEFRAMES = {"1": "M1", "5": "M5", "15": "M15"}
DAYS = 3                # بک‌تست روی ۳ روز معاملاتی اخیر


def account(closed, risk_pct, balance=BALANCE):
    bal = peak = balance
    max_dd, curve = 0.0, []
    for t in closed:
        bal += t["r"] * bal * risk_pct / 100.0
        peak = max(peak, bal)
        max_dd = max(max_dd, (peak - bal) / peak * 100)
        curve.append((t["exit_time"], bal))
    return bal, max_dd, curve


def last_days(df, days=DAYS):
    """فقط days روز معاملاتی آخر (روزهایی که کندل دارند، به وقت UTC)."""
    dates = sorted(set(df.index.tz_convert("UTC").date))
    if len(dates) <= days:
        return df
    start = pd.Timestamp(dates[-days], tz="UTC")
    return df[df.index >= start]


def run(sym, m1, tf="1", days=DAYS):
    """m1: کندل‌های تایم‌فریم tf (Open/High/Low/Close، زمان = شروع کندل). خروجی: dict نتیجه.
    days: فقط این تعداد روز معاملاتی آخر (None = همه)."""
    step = pd.Timedelta(minutes=int(tf))
    if days:
        m1 = last_days(m1, days)
    o, h, l, c = (m1[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    idx = m1.index
    all_t = trades(o, h, l, c, sym)
    for t in all_t:
        if t.get("entry_i") is not None:
            t["entry_time"] = idx[t["entry_i"]]
        if t.get("exit_i") is not None:
            t["exit_time"] = idx[t["exit_i"]] + step
    closed = [t for t in all_t if t.get("exit_i") is not None]
    for k, t in enumerate(closed, 1):
        t["num"] = k
    wins = [t for t in closed if t["r"] > 0]
    res = {"sym": sym, "tf": BT_TIMEFRAMES.get(tf, tf), "start": idx[0], "end": idx[-1] + step, "bars": len(m1),
           "closed": closed, "trades": len(closed), "wins": len(wins), "losses": len(closed) - len(wins),
           "net_r": sum(t["r"] for t in closed),
           "open": [t for t in all_t if t.get("entry_i") is not None and t.get("exit_i") is None],
           "waiting": [t for t in all_t if t.get("entry_i") is None], "accounts": {},
           "days": len(set(idx.tz_convert("UTC").date)), "candles": m1}
    for side, key in ((-1, "sells"), (1, "buys")):
        cs = [t for t in closed if t["side"] == side]
        res[key] = (len(cs), sum(t["r"] > 0 for t in cs), sum(t["r"] for t in cs))
    res["avg_risk"] = sum(abs(t["sl"] - t["entry"]) for t in closed) / len(closed) if closed else 0.0
    for rp in RISKS:
        final, dd, curve = account(closed, rp)
        res["accounts"][rp] = {"final": final, "max_dd": dd, "curve": curve}
    return res


def report_text(res, decimals=2, shown=25):
    sym = res["sym"]
    p = lambda x: f"{x:.{decimals}f}"
    tz = lambda ts: ts.tz_convert(TEHRAN)
    wr = res["wins"] / res["trades"] * 100 if res["trades"] else 0
    tfn = res.get("tf", "M1")
    lines = [f"🧪 <b>GAP BACKTEST · {label(sym)} · {tfn}</b>",
             f"{tz(res['start']):%d %b %H:%M} → {tz(res['end']):%d %b %H:%M} Tehran · {res['bars']} {tfn} candles "
             f"({res['days']} days)",
             "📐 Gap on 3 candles → enter 1 pipette beyond the previous candle → stop behind candle 1 → target 1:1",
             "━━━━━━━━━━━━━━━━",
             f"📊 Trades: <b>{res['trades']}</b> · ✅ {res['wins']} · ❌ {res['losses']} · win rate <b>{wr:.0f}%</b>",
             f"📈 Net: <b>{res['net_r']:+.0f}R</b>  (win +{RR:g}R, loss −1R)",
             f"   🔴 Sells: {res['sells'][0]} trades, {res['sells'][1]} wins, {res['sells'][2]:+.0f}R",
             f"   🟢 Buys: {res['buys'][0]} trades, {res['buys'][1]} wins, {res['buys'][2]:+.0f}R"]
    if res["trades"]:
        lines.append(f"   📏 Average stop distance: {p(res['avg_risk'])}")
    if res["open"]:
        lines.append("   ⏳ 1 trade still open at the end (not counted)")
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append(f"💵 Account ${BALANCE:,.0f}:")
    for rp, a in res["accounts"].items():
        chg = (a["final"] / BALANCE - 1) * 100
        lines.append(f"   Risk {rp:g}% per trade → <b>${a['final']:,.2f}</b> ({chg:+.1f}%) · "
                     f"max drawdown {a['max_dd']:.1f}%")
    if res["closed"]:
        lines.append("━━━━━━━━━━━━━━━━\n<b>Latest trades</b> (Tehran time)")
        for t in res["closed"][-shown:]:
            icon = "🏆" if t["r"] > 0 else "🛑"
            side = "SELL" if t["side"] < 0 else "BUY"
            lines.append(f"{icon} #{t['num']} {tz(t['entry_time']):%d %b %H:%M} {side} {p(t['entry'])} → {p(t['exit'])} "
                         f"({t['r']:+g}R)")
        if len(res["closed"]) > shown:
            lines.append(f"<i>… {len(res['closed']) - shown} earlier trades not listed</i>")
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append(f"<i>No spread, commission or slippage. Inside each {tfn} candle the order of prices comes from the "
                 "candle shape, so live results can differ. Past results do not predict the future.</i>")
    return "\n".join(lines)


def equity_chart(res):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(12, 5), dpi=110)
    fig.patch.set_facecolor("white")
    colors = {1.0: "#2F7FC8", 2.0: "#EA580C"}
    for rp, a in res["accounts"].items():
        xs = [res["start"]] + [t for t, _ in a["curve"]] + [res["end"]]
        ys = [BALANCE] + [b for _, b in a["curve"]] + [a["final"]]
        ax.step(xs, ys, where="post", color=colors.get(rp, "#111111"), lw=2,
                label=f"Risk {rp:g}% → ${a['final']:,.2f}")
    ax.axhline(BALANCE, color="#9CA3AF", ls=":", lw=1)
    ax.set_title(f"{res['sym']} {res.get('tf', 'M1')} gap setup · {res['trades']} trades · {res['net_r']:+.0f}R",
                 fontsize=13, fontweight="bold", color="#111827")
    ax.set_ylabel("Account ($)", color="#6B7280")
    ax.grid(True, color="#EEF0F4")
    ax.legend(loc="upper left", frameon=False)
    for s in ax.spines.values():
        s.set_color("#E5E7EB")
    fig.autofmt_xdate()
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
