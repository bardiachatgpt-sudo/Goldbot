"""بک‌تست ستاپ گپ روی M1، M5 یا M15: همان قاعده‌ی bot/gap.py روی همه‌ی کندل‌هایی که TradingView می‌دهد.

حساب ۱۰۰۰ دلاری، ریسک ثابت درصدی از موجودی فعلی (مرکب) برای ۱٪ و ۲٪. بدون اسپرد و کمیسیون.
داخل هر کندل ترتیب قیمت از شکل کندل است (صعودی: باز ← کف ← سقف ← بسته)، پس نتیجه‌ی واقعی کمی فرق می‌کند.
"""
import io

import pandas as pd

from .config import TEHRAN, label, session_of
from .gap import RR, m5_target_filter, trades

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


def run(sym, m1, tf="1", days=DAYS, m5=None, compare=True, last_bars=None, max_leg=None):
    """m1: کندل‌های تایم‌فریم tf (Open/High/Low/Close، زمان = شروع کندل). خروجی: dict نتیجه.
    days: فقط این تعداد روز معاملاتی آخر (None = همه). last_bars: یا فقط این تعداد کندل آخر (مثلاً ۱۴۴۰ = ۲۴ ساعت M1).
    max_leg: فقط لگ ۱ تا max_leg (پیش‌فرض gap.MAX_LEG = ۲).
    m5: اگر باشد، فیلتر ساختار M5: حد سود بیرون از جعبه‌ی M5 همان لحظه → معامله گرفته نمی‌شود.
    compare: همان داده بدون فیلتر M5 هم حساب و در گزارش مقایسه شود."""
    from .gap import MAX_LEG
    max_leg = MAX_LEG if max_leg is None else max_leg
    step = pd.Timedelta(minutes=int(tf))
    if days:
        m1 = last_days(m1, days)
    if last_bars:
        m1 = m1.tail(last_bars)
    o, h, l, c = (m1[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    idx = m1.index
    skipped = []
    allow = m5_target_filter(m5, idx) if m5 is not None and len(m5) >= 100 else None
    all_t = trades(o, h, l, c, sym, allow=allow, skipped=skipped, max_leg=max_leg)
    for t in all_t:
        if t.get("entry_i") is not None:
            t["entry_time"] = idx[t["entry_i"]]
        if t.get("exit_i") is not None:
            t["exit_time"] = idx[t["exit_i"]] + step
    closed = [t for t in all_t if t.get("exit_i") is not None]
    for k, t in enumerate(closed, 1):
        t["num"] = k
        t["gap_times"] = (idx[t["gap"][0]], idx[t["gap"][1]])
        t["session"] = session_of(t["entry_time"])
    if m5 is not None and len(m5) >= 100:                 # ساختار M5 در لحظه‌ی ورود هر معامله
        from .gap_pictures import m5_at
        from .structure3 import NAMES, segment
        for t in closed:
            w5 = m5_at(m5, t["entry_time"])
            if len(w5) >= 100:
                ph = segment(w5["Close"].values.astype(float))[0][-1]
                t["m5_state"] = NAMES[(ph["type"], ph["side"])]
    wins = [t for t in closed if t["r"] > 0]
    res = {"sym": sym, "tf": BT_TIMEFRAMES.get(tf, tf), "start": idx[0], "end": idx[-1] + step, "bars": len(m1),
           "closed": closed, "trades": len(closed), "wins": len(wins), "losses": len(closed) - len(wins),
           "net_r": sum(t["r"] for t in closed),
           "open": [t for t in all_t if t.get("entry_i") is not None and t.get("exit_i") is None],
           "waiting": [t for t in all_t if t.get("entry_i") is None], "accounts": {},
           "days": len(set(idx.tz_convert("UTC").date)), "candles": m1,
           "m5_filter": allow is not None, "skipped": skipped, "max_leg": max_leg}

    def summ(ts):
        ts = [t for t in ts if t.get("exit_i") is not None]
        return len(ts), sum(t["r"] > 0 for t in ts), sum(t["r"] for t in ts)

    if allow is not None and compare:                     # همان داده بدون فیلتر M5 (همان فیلتر لگ)
        res["no_filter"] = summ(trades(o, h, l, c, sym, max_leg=max_leg))
    if max_leg and compare:                               # همان داده با همه‌ی لگ‌ها (همان فیلتر M5)
        res["all_legs"] = summ(trades(o, h, l, c, sym, allow=m5_target_filter(m5, idx) if allow else None,
                                      max_leg=0))
    for side, key in ((-1, "sells"), (1, "buys")):
        cs = [t for t in closed if t["side"] == side]
        res[key] = (len(cs), sum(t["r"] > 0 for t in cs), sum(t["r"] for t in cs))
    sessions = {}                                         # نتیجه‌ی هر سشن (همپوشانی‌ها جدا)
    for t in closed:
        n_, w_, r_ = sessions.get(t["session"], (0, 0, 0.0))
        sessions[t["session"]] = (n_ + 1, w_ + (t["r"] > 0), r_ + t["r"])
    order = ["Tokyo", "Tokyo+London", "London", "London+NY", "NY", "Off"]
    res["sessions"] = sorted(sessions.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)
    for name, pick in (("leg1", lambda t: t.get("leg", 1) == 1), ("leg2", lambda t: t.get("leg", 1) >= 2)):
        cs = [t for t in closed if pick(t)]
        res[name] = (len(cs), sum(t["r"] > 0 for t in cs), sum(t["r"] for t in cs))
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
             "📐 Gap on 3 same-colour candles → enter 1 pipette beyond the previous candle → stop behind candle 1 → "
             "target 1:1" + (" · only if the target is inside the M5 structure box" if res.get("m5_filter") else "")
             + (f" · legs 1–{res['max_leg']} only" if res.get("max_leg") else ""),
             "━━━━━━━━━━━━━━━━",
             f"📊 Trades: <b>{res['trades']}</b> · ✅ {res['wins']} · ❌ {res['losses']} · win rate <b>{wr:.0f}%</b>",
             f"📈 Net: <b>{res['net_r']:+.0f}R</b>  (win +{RR:g}R, loss −1R)",
             f"   🔴 Sells: {res['sells'][0]} trades, {res['sells'][1]} wins, {res['sells'][2]:+.0f}R",
             f"   🟢 Buys: {res['buys'][0]} trades, {res['buys'][1]} wins, {res['buys'][2]:+.0f}R"]
    for key, name in (("leg1", "1️⃣ Leg 1 (first gap of the move)"), ("leg2", "2️⃣ Leg 2+ (a gap came before in the move)")):
        if key in res:
            n_, w_, r_ = res[key]
            lines.append(f"   {name}: {n_} trades, {w_} wins ({w_ / n_ * 100 if n_ else 0:.0f}%), {r_:+.0f}R")
    if res.get("sessions"):
        lines.append("   🕐 By session:")
        for name, (n_, w_, r_) in res["sessions"]:
            lines.append(f"      {name}: {n_} trades, {w_} wins ({w_ / n_ * 100 if n_ else 0:.0f}%), {r_:+.0f}R")
    if res["trades"]:
        lines.append(f"   📏 Average stop distance: {p(res['avg_risk'])}")
    if res["open"]:
        lines.append("   ⏳ 1 trade still open at the end (not counted)")
    if res.get("m5_filter"):
        lines.append(f"   🚫 Not taken (1:1 target outside the M5 box): "
                     f"{sum(t.get('reason') == 'm5' for t in res['skipped'])}")
    if res.get("max_leg"):
        lines.append(f"   🚫 Not taken (leg {res['max_leg'] + 1}+): {sum(t.get('reason') == 'leg' for t in res['skipped'])}")
    if res.get("no_filter"):
        n0, w0, r0 = res["no_filter"]
        lines.append(f"🔁 Same data without the M5 filter: {n0} trades, win {w0 / n0 * 100 if n0 else 0:.0f}%, "
                     f"{r0:+.0f}R")
    if res.get("all_legs"):
        n0, w0, r0 = res["all_legs"]
        lines.append(f"🔁 Same data with all legs: {n0} trades, win {w0 / n0 * 100 if n0 else 0:.0f}%, {r0:+.0f}R")
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
            leg = (f" L{t['leg']}" if t.get("leg") else "") + (f" {t['session']}" if t.get("session") else "")
            lines.append(f"{icon} #{t['num']} {tz(t['entry_time']):%d %b %H:%M} {side}{leg} {p(t['entry'])} → {p(t['exit'])} "
                         f"({t['r']:+g}R)")
        if len(res["closed"]) > shown:
            lines.append(f"<i>… {len(res['closed']) - shown} earlier trades not listed</i>")
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append(f"<i>No spread, commission or slippage. Inside each {tfn} candle the order of prices comes from the "
                 "candle shape, so live results can differ. Past results do not predict the future.</i>")
    return "\n".join(lines)


def losers_text(res, decimals=2, limit=3900):
    """فهرست همه‌ی معامله‌هایی که حد ضرر خوردند، با شماره‌ی عکس؛ چند پیام اگر طولانی باشد."""
    p = lambda x: f"{x:.{decimals}f}"
    tz = lambda ts: ts.tz_convert(TEHRAN)
    losers = [t for t in res["closed"] if t["r"] < 0]
    if not losers:
        return []
    head = (f"🛑 <b>Stopped-out trades · {res['sym']} {res.get('tf', 'M1')}</b> ({len(losers)}) · "
            f"#number = picture number · Tehran time")
    rows = []
    for t in losers:
        g1, g3 = t["gap_times"]
        rows.append(f"#{t['num']} · {tz(t['entry_time']):%d %b %H:%M} · {'SELL' if t['side'] < 0 else 'BUY'} · "
                    f"L{t.get('leg', '?')} · {t.get('session', '?')} · gap {tz(g1):%H:%M}–{tz(g3):%H:%M} · "
                    f"entry {p(t['entry'])} · "
                    f"SL {p(t['sl'])} · TP {p(t['tp'])} · exit {tz(t['exit_time']):%H:%M}"
                    + (f" · M5: {t['m5_state']}" if t.get("m5_state") else ""))
    out, cur = [], head
    for r in rows:
        if len(cur) + len(r) + 1 > limit:
            out.append(cur)
            cur = "🛑 (continued)"
        cur += "\n" + r
    out.append(cur)
    return out


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


ALL_BARS = 1440         # «۲۴ ساعت اخیر» = ۱۴۴۰ کندل M1 معاملاتی آخر (آخر هفته‌ها حساب نمی‌شوند)
ALL_RISK = 2.0


def all_pairs_text(rows, risk=ALL_RISK):
    """rows: [(نماد، نتیجه با فیلتر M5، نتیجه بدون فیلتر M5، خطا)]. جدول خلاصه برای همه‌ی جفت‌ها، با و بدون فیلتر M5."""
    head = (f"🌍 <b>GAP SETUP · ALL PAIRS · M1 · last 24h</b>\n"
            f"Legs 1–2 · target 1:1 · ${BALANCE:,.0f} at {risk:g}% risk per trade · no spread")

    def block(title, pick):
        lines = [f"\n<b>{title}</b>", "<pre>Pair     Tr  Win    R    $1000 →"]
        tot_n = tot_w = 0
        tot_r = 0.0
        for sym, rf, rn, err in rows:
            r = pick(rf, rn)
            if err or r is None:
                lines.append(f"{sym:<7}   no data")
                continue
            n, w, rr = r["trades"], r["wins"], r["net_r"]
            final = r["accounts"][risk]["final"]
            tot_n, tot_w, tot_r = tot_n + n, tot_w + w, tot_r + rr
            wr = f"{w / n * 100:3.0f}%" if n else "  -"
            money = "$" + format(final, ",.0f")
            lines.append(f"{sym:<7}{n:>4} {wr} {rr:+5.0f} {money:>7} ({(final / BALANCE - 1) * 100:+.1f}%)")
        wr = f"{tot_w / tot_n * 100:3.0f}%" if tot_n else "  -"
        lines.append(f"{'ALL':<7}{tot_n:>4} {wr} {tot_r:+5.0f}")
        lines.append("</pre>")
        return lines

    out = [head]
    out += block("📦 With the M5 filter (target inside the M5 box)", lambda rf, rn: rf)
    out += block("🔓 Without the M5 filter", lambda rf, rn: rn)
    best = [(sym, rf) for sym, rf, rn, err in rows if rf is not None and not err and rf["trades"]]
    if best:
        top = max(best, key=lambda x: x[1]["net_r"])
        low = min(best, key=lambda x: x[1]["net_r"])
        out.append(f"🏆 Best (with filter): {top[0]} {top[1]['net_r']:+.0f}R · 🔻 Worst: {low[0]} {low[1]['net_r']:+.0f}R")
    out.append("<i>Each pair is its own $1,000 account. No spread, commission or slippage; inside each M1 candle the "
               "order of prices comes from the candle shape. 24 hours is a small sample.</i>")
    return "\n".join(out)
