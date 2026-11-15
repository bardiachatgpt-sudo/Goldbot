"""بک‌تست: همان قاعده‌های ربات زنده روی داده‌ی گذشته.

- چرخه‌ی M5 کندل‌به‌کندل خوانده می‌شود؛ هر کندل M1 فقط با کندل‌های M5 که قبل از شروعش بسته شده‌اند تصمیم می‌گیرد
- ورود، حد ضرر، حد سود و لغو دقیقاً با TradeManager (همان کد ربات زنده)
- داده‌ی گذشته قیمت زنده ندارد: ترتیب داخل هر کندل M1 از شکل کندل (صعودی: باز←کف←سقف←بسته)
- حساب: موجودی شروع، ریسک ثابت درصدی از موجودی فعلی در هر معامله (مرکب)

اجرا از خط فرمان (با فایل CSV کندل‌های M1: time,open,high,low,close):
    python -m bot.backtest XAUUSD --csv m1.csv --balance 1000 --risk 1
"""
import argparse
import io

import pandas as pd

from .config import MIN_BARS, RR, label, spread
from .cycle import CycleEngine
from .strategy import analyze
from .trades import TradeManager

DEFAULT_BALANCE = 1000.0
RISKS = (1.0, 2.0)          # درصد ریسک هر معامله که گزارش می‌شود


def to_m5(m1):
    """M1 → M5 مثل TradingView (زمان = شروع کندل). کندل ناقص آخر حذف می‌شود."""
    agg = m1.resample("5min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    done = agg.index + pd.Timedelta(minutes=5) <= m1.index[-1] + pd.Timedelta(minutes=1)
    return agg[done]


def run(sym, m1, m5=None, start=None):
    """رویدادهای معامله در بازه‌ی [start, پایان]. کندل‌های قبل از start فقط برای گرم شدن."""
    m5 = to_m5(m1) if m5 is None else m5
    d = analyze(m1, cycle=False)["df"]
    eng = CycleEngine(sym)
    tm = TradeManager(sym)
    m5_end = m5.index + pd.Timedelta(minutes=5)
    k = 0
    events = []
    for _, row in d.iterrows():
        t = row["date"]
        while k < len(m5) and m5_end[k] <= t:          # کندل‌های M5 بسته‌شده تا شروع این کندل M1
            r = m5.iloc[k]
            eng.on_bar(m5.index[k], r["Open"], r["High"], r["Low"], r["Close"])
            k += 1
        tm.n += 1
        if start is not None and t < start:
            continue
        ctx = eng.snapshot() if eng.n >= MIN_BARS else None
        events += tm._step(row, ctx, 1)
    return events, tm


def account(events, balance=DEFAULT_BALANCE, risk_pct=1.0):
    """منحنی موجودی با ریسک درصدی ثابت از موجودی فعلی."""
    bal = balance
    peak, max_dd = bal, 0.0
    curve = []
    risk_at_open = {}                                  # زمان ورود → دلار ریسک‌شده
    for e in events:
        if e["kind"] == "TRADE_OPEN":
            risk_at_open[e["opened"]] = bal * risk_pct / 100.0
        elif e["kind"] == "TRADE_CLOSED":
            bal += e["r"] * risk_at_open.pop(e["opened"], bal * risk_pct / 100.0)
            peak = max(peak, bal)
            max_dd = max(max_dd, (peak - bal) / peak * 100)
            curve.append((e["time"], bal))
    return bal, max_dd, curve


def summary(sym, events, start, end, balance=DEFAULT_BALANCE):
    closed = [e for e in events if e["kind"] == "TRADE_CLOSED"]
    opened = [e for e in events if e["kind"] == "TRADE_OPEN"]
    still_open = len(opened) - len(closed)
    wins = [e for e in closed if e["r"] > 0]
    net_r = sum(e["r"] for e in closed)
    res = {"sym": sym, "start": start, "end": end, "setups": sum(e["kind"] == "TRADE_PENDING" for e in events),
           "cancelled": sum(e["kind"] == "TRADE_CANCELLED" for e in events), "trades": len(closed),
           "wins": len(wins), "losses": len(closed) - len(wins), "net_r": net_r, "open": still_open,
           "by_mode": {}, "closed": closed, "accounts": {}}
    for mode in ("RANGE", "SPIKE"):
        c = [e for e in closed if e["mode"] == mode]
        res["by_mode"][mode] = (len(c), sum(e["r"] > 0 for e in c), sum(e["r"] for e in c))
    for rp in RISKS:
        final, dd, curve = account(events, balance, rp)
        res["accounts"][rp] = {"final": final, "max_dd": dd, "curve": curve}
    return res


def fetch(sym, days):
    """داده‌ی TradingView (روی Render). روزهای معاملاتی اخیر + گرم شدن."""
    from .data import fetch_candles, LAST_SOURCE
    from .config import SYMBOLS
    n1 = min(days * 1440 + 400, 20000)
    n5 = min(days * 288 + 600, 5000)
    errors = []
    for tv in ([LAST_SOURCE[sym]] if sym in LAST_SOURCE else []) + SYMBOLS[sym]:
        m1, e1 = fetch_candles(tv, "1", n1, timeout=60)
        m5, e5 = fetch_candles(tv, "5", n5, timeout=60)
        if m1 is not None and m5 is not None and len(m1) > MIN_BARS and len(m5) > MIN_BARS:
            return m1.iloc[:-1], m5.iloc[:-1], None
        errors.append(e1 or e5 or f"{tv}: too few bars")
    return None, None, " | ".join(errors)


def run_days(sym, days, balance=DEFAULT_BALANCE, m1=None, m5=None):
    """بک‌تست روزهای اخیر. اگر m1/m5 داده نشود از TradingView گرفته می‌شود."""
    if m1 is None:
        m1, m5, err = fetch(sym, days)
        if m1 is None:
            return None, err
    end = m1.index[-1] + pd.Timedelta(minutes=1)
    # شروع: days روز معاملاتی آخر (بر اساس روزهایی که داده دارند)
    day_list = sorted(set(m1.index.tz_convert("UTC").date))
    first_day = day_list[-days] if len(day_list) >= days else day_list[0]
    start = pd.Timestamp(first_day, tz="UTC")
    if (m1.index < start).sum() < 300:                    # گرم شدن کافی
        start = m1.index[min(300, len(m1) - 1)]
    m5 = m5[m5.index <= m1.index[-1]] if m5 is not None else None
    events, _ = run(sym, m1, m5, start)
    return summary(sym, events, start, end, balance), None


# ---------------------------------------------------------------- خروجی
def report_text(res, balance=DEFAULT_BALANCE):
    from .messages import LINE, fmt_price
    sym = res["sym"]
    p = lambda x: fmt_price(sym, x)
    wr = res["wins"] / res["trades"] * 100 if res["trades"] else 0
    lines = [f"🧪 <b>BACKTEST · {label(sym)}</b>",
             f"{res['start']:%d %b %H:%M} → {res['end']:%d %b %H:%M} UTC · M5 context → M1 trigger",
             LINE,
             f"🎯 Setups: {res['setups']} · cancelled: {res['cancelled']}",
             f"📊 Closed trades: <b>{res['trades']}</b> · ✅ {res['wins']} · ❌ {res['losses']} · win rate {wr:.0f}%",
             f"📈 Net: <b>{res['net_r']:+g}R</b>  (each win +{RR:g}R, each loss −1R)"]
    for mode, name in (("RANGE", "📦 Range"), ("SPIKE", "🚀 Spike pullback")):
        n, w, r = res["by_mode"][mode]
        lines.append(f"   {name}: {n} trades, {w} wins, {r:+g}R")
    if res["open"]:
        lines.append(f"   ⏳ {res['open']} trade still open at the end (not counted)")
    lines.append(LINE)
    lines.append(f"💵 Account ${balance:,.0f}:")
    for rp, a in res["accounts"].items():
        chg = (a["final"] / balance - 1) * 100
        lines.append(f"   Risk {rp:g}% per trade → <b>${a['final']:,.2f}</b> ({chg:+.1f}%) · "
                     f"max drawdown {a['max_dd']:.1f}%")
    if res["closed"]:
        lines.append(LINE + "\n<b>Trades</b>")
        for e in res["closed"][-15:]:
            icon = "🏆" if e["r"] > 0 else "🛑"
            side = "BUY" if e["side"] > 0 else "SELL"
            mode = "Range" if e["mode"] == "RANGE" else "Spike"
            lines.append(f"{icon} {e['opened']:%d %b %H:%M} {mode} {side} {p(e['entry'])} → {p(e['exit'])} "
                         f"({e['r']:+g}R)")
        if len(res["closed"]) > 15:
            lines.append(f"<i>… {len(res['closed']) - 15} earlier trades not listed</i>")
    lines.append(LINE)
    lines.append(f"<i>Spread {spread(sym):g} in the stop · no commission or slippage · inside each M1 bar the order "
                 f"comes from the candle shape (live trading uses real-time prices) · past results do not "
                 f"predict the future</i>")
    return "\n".join(lines)


def equity_chart(res, balance=DEFAULT_BALANCE):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(12, 5), dpi=110)
    fig.patch.set_facecolor("#121214")
    ax.set_facecolor("#18181B")
    colors = {1.0: "#10B981", 2.0: "#F59E0B"}
    for rp, a in res["accounts"].items():
        xs = [res["start"]] + [t for t, _ in a["curve"]] + [res["end"]]
        ys = [balance] + [b for _, b in a["curve"]] + [a["final"]]
        ax.step(xs, ys, where="post", color=colors.get(rp, "#60A5FA"), linewidth=2,
                label=f"Risk {rp:g}% → ${a['final']:,.2f}")
        for t, b in a["curve"]:
            ax.plot(t, b, "o", color=colors.get(rp, "#60A5FA"), markersize=4)
    ax.axhline(balance, color="#9CA3AF", linestyle=":", linewidth=1)
    ax.set_title(f"{res['sym']} backtest · {res['trades']} trades · {res['net_r']:+g}R",
                 color="#F3F4F6", fontsize=13, fontweight="bold")
    ax.set_ylabel("Account ($)", color="#9CA3AF")
    ax.tick_params(colors="#9CA3AF")
    ax.grid(True, linestyle="--", color="#27272A", alpha=0.7)
    ax.legend(facecolor="#18181B", edgecolor="#27272A", loc="upper left")
    fig.autofmt_xdate()
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#121214")
    plt.close(fig)
    return buf.getvalue()


def load_csv(path):
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    tcol = next(cols[c] for c in ("time", "date", "datetime", "timestamp") if c in cols)
    t = df[tcol]
    idx = pd.to_datetime(t, unit="s", utc=True) if pd.api.types.is_numeric_dtype(t) else pd.to_datetime(t, utc=True)
    out = pd.DataFrame({k.capitalize(): df[cols[k]].astype(float).values for k in ("open", "high", "low", "close")},
                       index=idx).sort_index()
    return out[~out.index.duplicated()]


def main():
    ap = argparse.ArgumentParser(description="Goldbot backtest")
    ap.add_argument("sym", nargs="?", default="XAUUSD")
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--csv", help="M1 candles CSV (time,open,high,low,close); otherwise TradingView")
    ap.add_argument("--balance", type=float, default=DEFAULT_BALANCE)
    args = ap.parse_args()
    m1 = load_csv(args.csv) if args.csv else None
    res, err = run_days(args.sym, args.days, args.balance, m1=m1, m5=to_m5(m1) if m1 is not None else None)
    if res is None:
        print("error:", err)
        return
    import re
    print(re.sub(r"<[^>]+>", "", report_text(res, args.balance)))


if __name__ == "__main__":
    main()
