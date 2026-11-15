"""ساخت متن پیام‌های تلگرام (انگلیسی، HTML)."""
import pytz

from .config import TEHRAN, bar_delta, decimals, label, tf_label
from .timefmt import session_at

LONDON = pytz.timezone("Europe/London")
LINE = "━" * 16

SETUP_DESC = {
    "H1": "High 1 · first bull pullback entry",
    "H2": "High 2 · second bull pullback entry",
    "L1": "Low 1 · first bear pullback entry",
    "L2": "Low 2 · second bear pullback entry",
}


def fmt_price(sym, x):
    return f"{x:.{decimals(sym)}f}"


def fmt_time(ts, tz):
    """مثلاً: Saturday 2026-11-14 04:37 (روز هفته به وقت همان شهر)"""
    return ts.tz_convert(tz).strftime("%A %Y-%m-%d %H:%M")


def _times(t):
    t = t + bar_delta()          # زمان بسته‌شدن کندل
    return (f"🕒 <b>{fmt_time(t, TEHRAN)}</b> Tehran\n"
            f"🕒 <b>{fmt_time(t, LONDON)}</b> London\n"
            f"🌍 {session_at(t)}")


def build_alert(ev):
    """هشدار زنده برای ستاپ H/L یا Wedge."""
    sym, s = ev["sym"], ev["side"]
    side = "BULLISH📈" if s > 0 else "BEARISH📉"
    icon = "🟢" if s > 0 else "🔴"
    if ev["kind"] == "WEDGE":
        head = f"{icon} <b>{ev['type'].upper()} · {side}</b>"
        pts = " → ".join(fmt_price(sym, p) for p in ev["points"])
        detail = f"🔺 3 pushes: {pts}\n<i>Possible trend reversal</i>"
    else:
        head = f"{icon} <b>{ev['setup']} · {side}</b>"
        detail = f"<i>{SETUP_DESC.get(ev['setup'], ev['setup'] + ' pullback entry')}</i>"
    return (f"{head}\n"
            f"<b>{label(sym)}</b>  ·  {tf_label()}\n{LINE}\n"
            f"💰 Price: <b>{fmt_price(sym, ev['price'])}</b>\n"
            f"〰️ EMA20: {fmt_price(sym, ev['ema20'])}\n"
            f"🧭 {ev['cycle']}\n"
            f"{detail}\n{LINE}\n"
            f"{_times(ev['time'])}")


def build_report(sym, res):
    """گزارش کامل وضعیت فعلی بازار (دستور /analyze)."""
    p = lambda x: fmt_price(sym, x)
    last = res["latest"]
    lines = [f"📊 <b>{label(sym)} · {tf_label()} · Al Brooks PA</b>", LINE,
             f"🧭 Market cycle: <b>{res['market_cycle']}</b>",
             f"   ({res['bars_above_ema']}/15 recent bars closed above EMA20)",
             f"💰 Close: <b>{p(last['close'])}</b>   〰️ EMA20: {p(last['ema20'])}",
             f"🕯 Last bar: {last['bar_type']}  (H {p(last['high'])} · L {p(last['low'])})"]

    if res["active_setups"]:
        lines.append(f"{LINE}\n🎯 <b>Active setups (last 3 bars)</b>")
        for a in res["active_setups"]:
            icon = "🟢" if a["side"] > 0 else "🔴"
            lines.append(f"{icon} {a['setup']} @ {p(a['price'])}  ·  {a['date'].tz_convert(TEHRAN):%H:%M} Tehran")
    else:
        lines.append(f"{LINE}\n🎯 No H1/H2/L1/L2 setup on the last 3 bars")

    sh = [p(x["price"]) for x in res["swing_highs"][-3:]]
    sl = [p(x["price"]) for x in res["swing_lows"][-3:]]
    lines.append(f"{LINE}\n🔻 Swing highs (resistance): {', '.join(sh) or '-'}")
    lines.append(f"🔺 Swing lows (support): {', '.join(sl) or '-'}")

    if res["wedges"]:
        w = res["wedges"][-1]
        pts = " → ".join(p(x["price"]) for x in w["points"])
        lines.append(f"📐 Last wedge: {w['type']} ({pts}) · {w['trigger_date'].tz_convert(TEHRAN):%d %b %H:%M} Tehran")

    lines.append(f"{LINE}\n{_times(last['date'])}")
    lines.append("<i>Educational analysis, not financial advice.</i>")
    return "\n".join(lines)
