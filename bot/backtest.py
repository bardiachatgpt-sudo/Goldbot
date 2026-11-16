"""بک‌تست: همان قاعده‌های ربات زنده روی داده‌ی گذشته.

- چرخه‌ی M5 کندل‌به‌کندل خوانده می‌شود؛ هر کندل M1 فقط با کندل‌های M5 که قبل از شروعش بسته شده‌اند تصمیم می‌گیرد
- ورود، حد ضرر، حد سود و لغو دقیقاً با TradeManager (همان کد ربات زنده)
- داده‌ی گذشته قیمت زنده ندارد: ترتیب داخل هر کندل M1 از شکل کندل (صعودی: باز←کف←سقف←بسته)
- حساب: موجودی شروع، ریسک ثابت درصدی از موجودی فعلی در هر معامله (مرکب)

اجرا از خط فرمان (با فایل CSV کندل‌های ماشه: time,open,high,low,close):
    python -m bot.backtest XAUUSD --csv m1.csv --days 5 --balance 1000 --tf 5-1
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

# تایم‌فریم‌ها: کلید → (دقیقه‌ی زمینه، دقیقه‌ی ماشه، نام، بازه‌های پیشنهادی به روز معاملاتی)
TF_PRESETS = {
    "5-1": (5, 1, "M5 → M1", (1, 3, 5, 10)),
    "15-3": (15, 3, "M15 → M3", (3, 5, 10, 20)),
    "60-5": (60, 5, "H1 → M5", (5, 10, 20, 40)),
    "5r": (5, 5, "📦 M5 · Range edges (buy the bottom / sell the top)", (5, 10)),
}
RANGE_TF = "5r"             # قاعده‌ی رنج کاربر: فقط M5
LIVE_TF = "5-1"             # تنظیم ربات زنده


def to_tf(df, minutes):
    """کندل‌ها → تایم‌فریم بالاتر مثل TradingView (زمان = شروع کندل). کندل ناقص آخر حذف می‌شود."""
    step = df.index[1] - df.index[0] if len(df) > 1 else pd.Timedelta(minutes=1)
    agg = df.resample(f"{minutes}min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    done = agg.index + pd.Timedelta(minutes=minutes) <= df.index[-1] + step
    return agg[done]


def to_m5(m1):
    return to_tf(m1, 5)


STRATEGY_NAMES = {"pin": "Pin bar (M1)", "pin_wedge": "Pin bar + wedge confirmation",
                  "brooks": "Brooks (M5 signal bar)",
                  "range3_touch": "Range edges: price reaches the bottom → buy, the top → sell; "
                                  "stop ½ range from entry, target the other edge",
                  "range3_touch_trend": "Same, but only in the direction of the move before the range "
                                        "(after a fall: sell the top only; after a rise: buy the bottom only)",
                  "range3_touch_edge": "Same, but stop ½ range beyond the range edge",
                  "range3": "Same, but only after a pin bar (enter on the next candle)",
                  "range3_edge": "Same, but stop ½ range beyond the range edge",
                  "range3_key": "Same, but wait for a key bar after the pin bar"}


def run(sym, trig, ctx=None, start=None, ctx_min=5, trig_min=1, strategy=None):
    """رویدادهای معامله با قاعده‌های strategy (pin یا brooks؛ پیش‌فرض: تنظیم ربات زنده)."""
    from .config import STRATEGY
    strategy = strategy or STRATEGY
    if strategy == "pin":
        return run_pin(sym, trig, ctx, start, ctx_min, trig_min, wedge_filter=False)
    if strategy == "pin_wedge":
        return run_pin(sym, trig, ctx, start, ctx_min, trig_min, wedge_filter=True)
    if strategy.startswith("range3"):
        from . import range_trades
        return range_trades.run(sym, trig, start, "edge" if strategy.endswith("_edge") else "entry",
                                "key" if strategy == "range3_key" else "none",
                                "touch" if strategy.startswith("range3_touch") else "pin",
                                with_trend=strategy.endswith("_trend")), None
    return run_brooks(sym, trig, ctx, start, ctx_min, trig_min)


def run_pin(sym, trig, ctx=None, start=None, ctx_min=5, trig_min=1, wedge_filter=None):
    """نسخه‌ی اول: هر کندل M1 فقط با کندل‌های M5 که قبل از شروعش بسته شده‌اند تصمیم می‌گیرد."""
    from .config import always_in_for
    from .trades_pin import TradeManager as PinTradeManager
    ctx = to_tf(trig, ctx_min) if ctx is None else ctx
    d = analyze(trig, cycle=False)["df"]
    eng = CycleEngine(sym, always_in=always_in_for("pin"))
    tm = PinTradeManager(sym, wedge_filter=wedge_filter)
    ctx_end = ctx.index + pd.Timedelta(minutes=ctx_min)
    k = 0
    events = []
    for _, row in d.iterrows():
        t = row["date"]
        while k < len(ctx) and ctx_end[k] <= t:
            r = ctx.iloc[k]
            eng.on_bar(ctx.index[k], r["Open"], r["High"], r["Low"], r["Close"])
            k += 1
        tm.n += 1
        if start is not None and t < start:
            continue
        snap = eng.snapshot() if eng.n >= MIN_BARS else None
        events += tm._step(row, snap, trig_min)
    return events, tm


def run_brooks(sym, trig, ctx=None, start=None, ctx_min=5, trig_min=1):
    """رویدادهای معامله در بازه‌ی [start, پایان]. کندل‌های قبل از start فقط برای گرم شدن.

    trig: کندل‌های اجرا (M1)، ctx: کندل‌های زمینه و سیگنال (M5). به ترتیب زمان: هر کندل M5 که بسته شد
    اول به چرخه داده می‌شود، بعد کندل سیگنال بررسی می‌شود؛ کندل‌های M1 ورود و خروج را اجرا می‌کنند.
    """
    from .strategy import from_tradingview
    ctx = to_tf(trig, ctx_min) if ctx is None else ctx
    d1 = from_tradingview(trig)
    d5 = from_tradingview(ctx)
    from .config import always_in_for
    eng = CycleEngine(sym, always_in=always_in_for("brooks"))
    tm = TradeManager(sym, signal_tf=ctx_min)
    rows5 = list(d5.itertuples(index=False))
    step5 = pd.Timedelta(minutes=ctx_min)
    k = 0
    events = []
    for r1 in d1.itertuples(index=False):
        t = r1.date
        while k < len(rows5) and rows5[k].date + step5 <= t:     # کندل‌های M5 بسته‌شده تا این لحظه
            r5 = rows5[k]
            eng.on_bar(r5.date, r5.open, r5.high, r5.low, r5.close)
            snap = eng.snapshot() if eng.n >= MIN_BARS else None
            ev = tm.on_m5_close(r5._asdict(), snap)
            if start is None or r5.date + step5 > start:
                events += ev
            else:
                tm.pending = None                                 # قبل از بازه: فقط گرم شدن
            k += 1
        if start is not None and t < start:
            tm.pending, tm.open = None, None
            continue
        events += tm.on_m1(r1._asdict(), trig_min)
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
    res["avg_risk"] = sum(e["risk"] for e in closed) / len(closed) if closed else 0.0
    for mode in ("TREND", "RANGE", "SPIKE"):
        c = [e for e in closed if e["mode"] == mode]
        res["by_mode"][mode] = (len(c), sum(e["r"] > 0 for e in c), sum(e["r"] for e in c))
    for rp in RISKS:
        final, dd, curve = account(events, balance, rp)
        res["accounts"][rp] = {"final": final, "max_dd": dd, "curve": curve}
    return res


def fetch(sym, days, ctx_min=5, trig_min=1, progress=None):
    """داده‌ی TradingView (روی Render): روزهای معاملاتی اخیر + گرم شدن."""
    from .config import ALL_SYMBOLS as SYMBOLS
    from .data import LAST_SOURCE, fetch_candles
    warm = 700 if trig_min == ctx_min else 400               # رنج: ۵۰۰ کندل قبل از اولین روز لازم است
    n_trig = min(days * 1440 // trig_min + warm, 20000)
    n_ctx = min(days * 1440 // ctx_min + 600, 5000)
    errors = []
    for tv in dict.fromkeys(([LAST_SOURCE[sym]] if sym in LAST_SOURCE else []) + SYMBOLS[sym]):
        if progress:
            progress("fetch_trig")
        trig, e1 = fetch_candles(tv, str(trig_min), n_trig, timeout=90)
        if progress:
            progress("fetch_ctx")
        if ctx_min == trig_min:                                  # یک تایم‌فریم: دوباره نگیر
            ctx, e2 = trig, None
        else:
            ctx, e2 = fetch_candles(tv, str(ctx_min), n_ctx, timeout=60)
        if trig is not None and ctx is not None and len(trig) > MIN_BARS and len(ctx) > MIN_BARS:
            return trig.iloc[:-1], ctx.iloc[:-1], None
        errors.append(e1 or e2 or f"{tv}: too few bars")
    return None, None, " | ".join(errors)


def run_days(sym, days, balance=DEFAULT_BALANCE, m1=None, m5=None, tf=LIVE_TF, progress=None,
             strategy=None, compare=True):
    """بک‌تست روزهای معاملاتی اخیر. اگر داده داده نشود از TradingView گرفته می‌شود.

    tf: کلید TF_PRESETS. m1/m5 = کندل‌های ماشه/زمینه (برای تایم‌فریم‌های دیگر هم همین نام‌ها).
    """
    ctx_min, trig_min, tf_name, _ = TF_PRESETS[tf]
    if m1 is None:
        m1, m5, err = fetch(sym, days, ctx_min, trig_min, progress)
        if m1 is None:
            return None, err
    if progress:
        progress("replay")
    end = m1.index[-1] + pd.Timedelta(minutes=trig_min)
    day_list = sorted(set(m1.index.tz_convert("UTC").date))          # روزهایی که داده دارند
    first_day = day_list[-days] if len(day_list) >= days else day_list[0]
    start = pd.Timestamp(first_day, tz="UTC")
    warm = 500 if tf == RANGE_TF else 300
    if (m1.index < start).sum() < warm:                                # گرم شدن کافی
        start = m1.index[min(warm, len(m1) - 1)]
    m5 = m5[m5.index <= m1.index[-1]] if m5 is not None else None
    from .config import STRATEGY, WEDGE_FILTER
    strategy = strategy or STRATEGY
    if tf == RANGE_TF:
        strategy = "range3_touch"
    elif strategy == "pin" and WEDGE_FILTER:                            # همان چیزی که ربات زنده اجرا می‌کند
        strategy = "pin_wedge"
    events, _ = run(sym, m1, m5, start, ctx_min, trig_min, strategy)
    res = summary(sym, events, start, end, balance)
    if compare:                                                         # قاعده‌های دیگر روی همان داده
        res["compare"] = []
        for other in (("range3_touch_trend", "range3_touch_edge", "range3") if strategy.startswith("range3")
                      else ("pin", "pin_wedge", "brooks")):
            if other == strategy:
                continue
            ev2, _ = run(sym, m1, m5, start, ctx_min, trig_min, other)
            res["compare"].append({"strategy": other, **{k: v for k, v in summary(sym, ev2, start, end,
                                                                                  balance).items()
                                                         if k in ("trades", "wins", "net_r")}})
    res.update(strategy=strategy, tf=tf, tf_name=tf_name, days=days,
               days_covered=len([d for d in day_list if pd.Timestamp(d, tz="UTC") >= start.floor("D")]))
    return res, None


# ---------------------------------------------------------------- خروجی
def report_text(res, balance=DEFAULT_BALANCE):
    from .messages import LINE, fmt_price
    sym = res["sym"]
    p = lambda x: fmt_price(sym, x)
    wr = res["wins"] / res["trades"] * 100 if res["trades"] else 0
    lines = [f"🧪 <b>BACKTEST · {label(sym)}</b>",
             f"{res['start']:%d %b %H:%M} → {res['end']:%d %b %H:%M} UTC · "
             f"{res.get('days_covered', '?')} trading days · {res.get('tf_name', 'M5 → M1')} (context → trigger)",
             f"📐 Rules: <b>{STRATEGY_NAMES.get(res.get('strategy'), res.get('strategy', ''))}</b>"
             + ("" if str(res.get("strategy", "")).startswith("range3") else " (live bot)"),
             LINE,
             f"🎯 Setups: {res['setups']} · cancelled: {res['cancelled']}",
             f"📊 Closed trades: <b>{res['trades']}</b> · ✅ {res['wins']} · ❌ {res['losses']} · win rate {wr:.0f}%",
             f"📈 Net: <b>{res['net_r']:+.2f}R</b>  " + (
                 "(win = reaching the other edge, its R varies; loss = −1R)"
                 if str(res.get("strategy", "")).startswith("range3") else f"(each win +{RR:g}R, each loss −1R)")]
    if str(res.get("strategy", "")).startswith("range3"):
        wins = [e["r"] for e in res["closed"] if e["r"] > 0]
        if wins:
            lines.append(f"   🏆 Average win: +{sum(wins) / len(wins):.2f}R")
        for side, name in ((1, "🟢 Buys at the bottom"), (-1, "🔴 Sells at the top")):
            cs = [e for e in res["closed"] if e["side"] == side]
            lines.append(f"   {name}: {len(cs)} trades, {sum(e['r'] > 0 for e in cs)} wins, "
                         f"{sum(e['r'] for e in cs):+.2f}R")
    else:
        for mode, name in (("TREND", "📈 With the trend"), ("RANGE", "📦 Range"), ("SPIKE", "🚀 Spike pullback")):
            n, w, r = res["by_mode"][mode]
            lines.append(f"   {name}: {n} trades, {w} wins, {r:+g}R")
    if res["trades"]:
        lines.append(f"   📏 Average stop distance: {p(res['avg_risk'])}")
    if res["open"]:
        lines.append(f"   ⏳ {res['open']} trade still open at the end (not counted)")
    for cmp in res.get("compare") or []:
        cwr = cmp["wins"] / cmp["trades"] * 100 if cmp["trades"] else 0
        lines.append(f"🔁 {STRATEGY_NAMES[cmp['strategy']]} on the same data: {cmp['trades']} trades, "
                     f"win rate {cwr:.0f}%, {cmp['net_r']:+.2f}R")
    lines.append(LINE)
    lines.append(f"💵 Account ${balance:,.0f}:")
    for rp, a in res["accounts"].items():
        chg = (a["final"] / balance - 1) * 100
        lines.append(f"   Risk {rp:g}% per trade → <b>${a['final']:,.2f}</b> ({chg:+.1f}%) · "
                     f"max drawdown {a['max_dd']:.1f}%")
    if res["closed"]:
        lines.append(LINE + "\n<b>Trades</b>")
        shown = 30 if str(res.get("strategy", "")).startswith("range3") else 15
        for e in res["closed"][-shown:]:
            icon = "🏆" if e["r"] > 0 else "🛑"
            side = "BUY" if e["side"] > 0 else "SELL"
            mode = {"RANGE": "Range", "SPIKE": "Spike", "TREND": "Trend"}.get(e["mode"], e["mode"])
            if e.get("n_h"):
                mode += f" {'H' if e['side'] > 0 else 'L'}{e['n_h']}"
            lines.append(f"{icon} {e['opened']:%d %b %H:%M} {mode} {side} {p(e['entry'])} → {p(e['exit'])} "
                         f"({e['r']:+.2f}R)")
        if len(res["closed"]) > shown:
            lines.append(f"<i>… {len(res['closed']) - shown} earlier trades not listed</i>")
    lines.append(LINE)
    if str(res.get("strategy", "")).startswith("range3"):
        lines.append("<i>The range is read at every candle from the last 500 closed M5 candles only (no look-ahead), "
                     "exactly like the 📐 Structure picture at that moment.</i>")
    lines.append(f"<i>Spread {spread(sym):g} in the stop · no commission or slippage · inside each trigger bar the order "
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
    ax.set_title(f"{res['sym']} {res.get('tf_name', '')} backtest · {res['trades']} trades · {res['net_r']:+.2f}R",
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
    ap.add_argument("--tf", default=LIVE_TF, choices=list(TF_PRESETS))
    args = ap.parse_args()
    m1 = load_csv(args.csv) if args.csv else None
    ctx = to_tf(m1, TF_PRESETS[args.tf][0]) if m1 is not None else None
    res, err = run_days(args.sym, args.days, args.balance, m1=m1, m5=ctx, tf=args.tf)
    if res is None:
        print("error:", err)
        return
    import re
    print(re.sub(r"<[^>]+>", "", report_text(res, args.balance)))


if __name__ == "__main__":
    main()
