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


def _times(t, tf=None, exact=False):
    if not exact:
        t = t + bar_delta(tf)    # زمان بسته‌شدن کندل
    return (f"🕒 <b>{fmt_time(t, TEHRAN)}</b> Tehran\n"
            f"🕒 <b>{fmt_time(t, LONDON)}</b> London\n"
            f"🌍 {session_at(t)}")


def build_alert(ev):
    """هشدار زنده برای ستاپ H/L، Wedge، پین‌بار و بریک‌اوت."""
    sym, s = ev["sym"], ev["side"]
    side = "BULLISH📈" if s > 0 else "BEARISH📉"
    icon = "🟢" if s > 0 else "🔴"
    if ev["kind"] == "WEDGE":
        head = f"{icon} <b>{ev['type'].upper()} · {side}</b>"
        pts = " → ".join(fmt_price(sym, p) for p in ev["points"])
        detail = f"🔺 3 pushes: {pts}\n<i>Possible trend reversal</i>"
    elif ev["kind"] == "WEDGE_BO":
        head = f"💥 <b>WEDGE BREAKOUT · {side}</b>" + ("  ⚡ <b>KEY BAR</b>" if ev["strong"] else "")
        pts = " → ".join(fmt_price(sym, p) for p in ev["points"])
        where = "above" if s > 0 else "below"
        detail = (f"📐 {ev['type']}: {pts}\n"
                  f"🚪 Closed {where} {fmt_price(sym, ev['level'])}\n"
                  f"<i>Breakout out of the wedge · reversal entry</i>")
    elif ev["kind"] == "RANGE_BO":
        head = f"💥 <b>RANGE BREAKOUT · {side}</b>  ⚡ <b>KEY BAR</b>"
        detail = (f"📦 Range: {fmt_price(sym, ev['range_low'])} – {fmt_price(sym, ev['range_high'])}\n"
                  f"<i>Strong bar closed {'above' if s > 0 else 'below'} the trading range · "
                  f"watch next bar for follow-through</i>")
    elif ev["kind"] == "PIN":
        head = f"{icon} <b>PIN BAR · {side}</b>"
        if s > 0:
            detail = (f"📍 Long lower tail rejected a new low ({fmt_price(sym, ev['low'])})\n"
                      f"<i>Reversal signal bar · entry above its high ({fmt_price(sym, ev['high'])})</i>")
        else:
            detail = (f"📍 Long upper tail rejected a new high ({fmt_price(sym, ev['high'])})\n"
                      f"<i>Reversal signal bar · entry below its low ({fmt_price(sym, ev['low'])})</i>")
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
    lines = [f"📊 <b>{label(sym)} · {tf_label()} · Al Brooks PA</b>", LINE]
    if res.get("cycle") is not None:
        lines += [cycle_block(sym, res["cycle"].snapshot()), LINE]
    else:
        lines.append(f"🧭 Market cycle: <b>{res['market_cycle']}</b>")
    lines += [f"💰 Close: <b>{p(last['close'])}</b>   〰️ EMA20: {p(last['ema20'])}",
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


    df = res["df"]
    events = []
    for col, name in (("range_bo", "Range breakout"), ("wedge_bo", "Wedge breakout"), ("pin_bar", "Pin bar")):
        hits = df.index[df[col] != 0]
        if len(hits):
            i = hits[-1]
            events.append((i, name, int(df.at[i, col])))
    for i, name, side in sorted(events, reverse=True):
        icon = "🟢" if side > 0 else "🔴"
        ago = len(df) - 1 - i
        lines.append(f"{icon} Last {name} @ {p(df.at[i, 'close'])} · {ago} bars ago")

    if res["wedges"]:
        w = res["wedges"][-1]
        pts = " → ".join(p(x["price"]) for x in w["points"])
        lines.append(f"📐 Last wedge: {w['type']} ({pts}) · {w['trigger_date'].tz_convert(TEHRAN):%d %b %H:%M} Tehran")

    lines.append(f"{LINE}\n{_times(last['date'])}")
    lines.append("<i>Educational analysis, not financial advice.</i>")
    return "\n".join(lines)


# ---------------------------------------------------------------- چرخه‌ی بازار
CYCLE_ICON = {"RANGE": "📦", "SPIKE": "🚀", "CHANNEL": "📈", "TEST": "⚠️"}


def _cycle_icon(state, side):
    if state == "CHANNEL" and side < 0:
        return "📉"
    return CYCLE_ICON[state]


def _where(pos):
    if pos >= 0.8:
        return "at the top"
    if pos <= 0.2:
        return "at the bottom"
    return "in the upper half" if pos >= 0.5 else "in the lower half"


def _why(code, side):
    """دلیل تشکیل رنج، با کلمات درست برای جهت کانال قبلی."""
    bull = side >= 0
    return {
        "spike_erased": "the spike was fully erased",
        "no_new_extreme": f"no new {'high' if bull else 'low'} after the first pullback",
        "hh_double_top": "higher-high double top" if bull else "lower-low double bottom",
        "double_top": "double top" if bull else "double bottom",
        "lower_high": "lower high" if bull else "higher low",
        "test_timeout": f"20 bars without a new {'high' if bull else 'low'}",
    }.get(code, code)


def cycle_block(sym, snap):
    """وضعیت چرخه‌ی M5 با سطح‌هایش."""
    p = lambda x: fmt_price(sym, x)
    st, sd = snap["state"], snap["side"]
    up = sd > 0
    hi_word, lo_word = ("high", "low") if up else ("low", "high")
    head = f"{_cycle_icon(st, sd)} <b>{snap['label'].upper()}</b> · {snap.get('bars', 0)} bars"
    out = [f"🧭 <b>Market cycle (M5)</b>", head]

    if st == "RANGE":
        if snap.get("hi") is None:
            return "\n".join(out)
        out.append(f"   Top {p(snap['hi'])} · Mid {p(snap['mid'])} · Bottom {p(snap['lo'])}")
        out.append(f"   Price {_where(snap['pos'])} ({snap['pos'] * 100:.0f}% of the range)")
        if snap.get("tight"):
            out.append("   🚧 Tight range (barbwire) · Brooks: don't trade, wait")
        elif snap.get("valid"):
            out.append(f"   ✅ Real range: flat EMA, two-sided · tests: bottom {len(snap.get('bottom_tests') or [])}, "
                       f"top {len(snap.get('top_tests') or [])}")
        else:
            out.append("   ⏳ Not a clean range yet (EMA still sloping or one-sided) · no range trades")
        if snap.get("why"):
            out.append(f"   Formed by: {_why(snap['why'], snap.get('from_side', 0))}")
        if snap.get("magnet"):
            m = snap["magnet"]
            out.append(f"   🎯 Previous channel start {p(m['price'])} · Brooks: usually gets tested")
        w = snap.get("watch")
        if snap.get("reversal") and w:
            if w["side"] > 0:
                out.append(f"   ⚠️ Closed below the break low {p(w['level'])} after a failed test "
                           f"→ possible bear reversal")
            else:
                out.append(f"   ⚠️ Closed above the break high {p(w['level'])} after a failed test "
                           f"→ possible bull reversal")
        out.append("   <i>Brooks: buy low, sell high · most breakouts fail</i>")
    elif st == "SPIKE":
        out.append(f"   From {p(snap['start_price'])} to {p(snap['extreme'])} "
                   f"({snap['size']:.1f}× average bar)")
        out.append(f"   Every bar a new {hi_word} with a strong close · first pullback → channel")
    elif st == "CHANNEL" and snap.get("forming"):
        out.append(f"   First pullback after the spike · channel start so far {p(snap['start_price'])}")
        out.append(f"   Beyond {p(snap['high'])} → channel confirmed · "
                   f"back beyond {p(snap['spike_start'])} → trading range")
    elif st == "CHANNEL":
        if snap.get("via") == "always_in":
            out.append(f"   Trend without a spike: "
                       f"{'higher highs and higher lows' if up else 'lower highs and lower lows'}, "
                       f"price {'above' if up else 'below'} a sloping EMA (Always In {'long' if up else 'short'})")
        out.append(f"   Major trend line now: <b>{p(snap['trend_line'])}</b>")
        out.append(f"   Channel line now: <b>{p(snap['channel_line'])}</b>")
        pos = snap["pos"]
        near = "near the trend line" if pos <= 0.25 else "near the channel line" if pos >= 0.75 else "mid-channel"
        out.append(f"   Price {near} ({pos * 100:.0f}% from trend line to channel line)")
        out.append(f"   Channel start {p(snap['start_price'])} · Brooks: usually tested later")
        out.append(f"   Close {'below' if up else 'above'} the trend line → channel under test")
        if snap.get("kind") == "tight":
            out.append(f"   <i>Tight channel: trade only with the trend · {'H1' if up else 'L1'} is enough</i>")
        else:
            out.append(f"   <i>Broad channel: two-sided · wait for the second entry ({'H2' if up else 'L2'})</i>")
    else:
        strength = "strong break" if snap["strong"] else "weak break"
        out.append(f"   Major trend line broken ({strength}) · line now {p(snap['trend_line'])}")
        out.append(f"   ✅ Close {'above' if up else 'below'} {p(snap['high'])} and hold → channel continues")
        out.append(f"   📦 Lower {hi_word} / double {'top' if up else 'bottom'}, or "
                   f"{max(snap['bars_left'], 0)} more bars without a new {hi_word} → trading range")
        out.append(f"   Break {lo_word}: {p(snap['break_low'])} · beyond it after a failed test → possible reversal")
    return "\n".join(out)


def build_cycle_alert(ev):
    """پیام تغییر چرخه برای کسانی که این نماد را فالو کرده‌اند."""
    from .cycle import describe_state
    sym, snap = ev["sym"], ev["snap"]
    a = describe_state(*ev["from"])
    b = snap["label"]
    note = ev.get("note")
    if note == "resumed":
        head = f"✅ <b>{b.upper()} RESUMED</b> · real breakout beyond the high"
    elif note == "reversal":
        w = snap.get("watch") or {"side": 1}
        head = ("⚠️ <b>POSSIBLE BEAR REVERSAL</b> · range broke below the test low" if w["side"] > 0 else
                "⚠️ <b>POSSIBLE BULL REVERSAL</b> · range broke above the test high")
    else:
        head = f"🔄 <b>{a}  →  {b}</b>"
    return (f"🧭 <b>{label(sym)}</b>  ·  M5 cycle\n{head}\n{LINE}\n"
            f"💰 Price: <b>{fmt_price(sym, ev['price'])}</b>\n"
            f"{cycle_block(sym, snap)}\n{LINE}\n"
            f"{_times(ev['time'])}")


# ---------------------------------------------------------------- معامله
def build_trade_alert(ev):
    """ستاپ (سفارش Stop) / ورود / حد سود یا ضرر / لغو."""
    if ev.get("strategy") == "pin":
        return build_pin_trade_alert(ev)
    from .config import ORDER_BARS, RR
    sym, s, k, mode = ev["sym"], ev["side"], ev["kind"], ev["mode"]
    p = lambda x: fmt_price(sym, x)
    buy = s > 0
    side = "BUY 📈" if buy else "SELL 📉"
    hl = "H" if buy else "L"
    sig = ev["signal"]
    if mode == "RANGE":
        where = "📦 Range · second entry"
        why = (f"second test of the range {'bottom' if buy else 'top'} held "
               f"(first test {p(ev['first_test'])}) · buy low, sell high")
    elif mode == "SPIKE":
        where = f"🚀 First pullback after the spike · {hl}{ev['n_h']}"
        why = f"pullback held the broken range level {p(ev['level'])}"
    else:
        kind = ev.get("channel_kind") or ""
        where = f"📈 With the trend · {hl}{ev['n_h']}" + (f" · {kind} channel" if kind else "")
        why = (f"pullback in a {'bull' if buy else 'bear'} channel · "
               f"{'second entry' if ev['n_h'] >= 2 else 'first entry'} ({hl}{ev['n_h']})")
    lines = []
    if k == "TRADE_PENDING":
        head = (f"🔁 <b>ORDER MOVED · {side}</b>" if ev.get("moved") else f"🎯 <b>SETUP · {side}</b>")
        lines = [f"🧠 {why}",
                 f"⏳ {'Buy' if buy else 'Sell'} stop at <b>{p(ev['planned_entry'])}</b> "
                 f"(M5 signal bar {'high' if buy else 'low'}) · valid {ORDER_BARS} M5 bars",
                 f"🛑 Stop loss: <b>{p(ev['sl'])}</b> (behind the {ev.get('stop_note', 'signal bar')} "
                 f"{'−' if buy else '+'} spread, at least one average M5 bar)",
                 f"✅ Take profit: <b>{p(ev['tp'])}</b> (1:{RR:g})",
                 f"❌ Cancelled if price goes {'below' if buy else 'above'} "
                 f"{p(sig['low'] if buy else sig['high'])} first"]
        if mode == "RANGE" and ((ev["tp"] > ev["range_high"]) if buy else (ev["tp"] < ev["range_low"])):
            edge = ev["range_high"] if buy else ev["range_low"]
            lines.append(f"⚠️ Target is beyond the range {'top' if buy else 'bottom'} ({p(edge)})")
    elif k == "TRADE_OPEN":
        head = f"🚀 <b>ENTRY · {side}</b>"
        lines = [f"➡️ Entry: <b>{p(ev['entry'])}</b> · price broke the M5 signal bar {'high' if buy else 'low'}",
                 f"🛑 Stop loss: <b>{p(ev['sl'])}</b>   ✅ Take profit: <b>{p(ev['tp'])}</b>",
                 f"📏 Risk {p(ev['risk'])} · Reward {p(ev['risk'] * RR)} · 1:{RR:g}"]
        if ev.get("tp_beyond_range"):
            edge = ev["range_high"] if buy else ev["range_low"]
            lines.append(f"⚠️ Take profit is beyond the range {'top' if buy else 'bottom'} ({p(edge)}) · "
                         f"Brooks: ranges often hold")
    elif k == "TRADE_CLOSED":
        win = ev["result"] == "TP"
        head = (f"🏆 <b>TAKE PROFIT · +{ev['r']:g}R</b>" if win else f"🛑 <b>STOP LOSS · {ev['r']:g}R</b>")
        lines = [f"{side} from {p(ev['entry'])} → exit {p(ev['exit'])}",
                 f"⏱ {ev.get('bars', 0)} minutes in the trade"]
    else:
        reason = (f"price went {'below' if buy else 'above'} the signal bar before entry"
                  if ev["reason"] == "tail" else f"no entry within {ORDER_BARS} M5 bars")
        head = f"✖️ <b>SETUP CANCELLED · {side}</b>"
        lines = [f"<i>{reason}</i>"]
    if ev.get("live"):
        lines.append("⚡ <i>Live price</i>")
    return (f"{head}\n<b>{label(sym)}</b>  ·  {where}\n{LINE}\n"
            + "\n".join(lines) + f"\n{LINE}\n{_times(ev['time'], exact=True)}")


def build_pin_trade_alert(ev):
    """ستاپ ورود / ورود / بسته شدن / لغو."""
    from .config import ORDER_BARS, RR
    sym, s, k = ev["sym"], ev["side"], ev["kind"]
    p = lambda x: fmt_price(sym, x)
    buy = s > 0
    side = "BUY 📈" if buy else "SELL 📉"
    where = ("📦 Range trade" if ev["mode"] == "RANGE" else "🚀 Spike pullback trade")
    pin = ev["pin"]
    lines = []

    if k == "TRADE_PENDING":
        if ev["mode"] == "RANGE":
            head = f"🎯 <b>SETUP · {side}</b> · pin bar at the range {'bottom' if buy else 'top'}"
            how = (f"⏳ {'Buy' if buy else 'Sell'} stop at <b>{p(ev['planned_entry'])}</b> "
                   f"(pin bar {'high' if buy else 'low'}) · valid {ORDER_BARS} M1 bars")
        else:
            head = f"🎯 <b>SETUP · {side}</b> · pin bar ends the first pullback after the M5 spike"
            how = (f"⏳ Waiting for an M1 key bar ({ORDER_BARS} bars max) · "
                   f"entry at the open of the next bar\n"
                   f"🧱 Broken range level {p(ev['level'])} held by the pullback")
        lines = [how,
                 f"🛑 Stop loss: <b>{p(ev['sl'])}</b> (pin {'low' if buy else 'high'} "
                 f"{'−' if buy else '+'} spread {p(ev['spread'])})",
                 f"✅ Take profit: <b>{p(ev['tp'])}</b> (1:{RR:g}, from the planned entry)",
                 f"❌ Cancelled if price goes {'below' if buy else 'above'} {p(pin['low'] if buy else pin['high'])} first"]
    elif k == "TRADE_OPEN":
        head = f"🚀 <b>ENTRY · {side}</b>"
        why = (f"price broke the pin bar {'high' if buy else 'low'}" if ev["mode"] == "RANGE"
               else "M1 key bar closed · entry at the next bar's open")
        lines = [f"➡️ Entry: <b>{p(ev['entry'])}</b> · {why}",
                 f"🛑 Stop loss: <b>{p(ev['sl'])}</b>   ✅ Take profit: <b>{p(ev['tp'])}</b>",
                 f"📏 Risk {p(ev['risk'])} · Reward {p(ev['risk'] * RR)} · 1:{RR:g}"]
        if ev.get("tp_beyond_range"):
            edge = ev["range_high"] if buy else ev["range_low"]
            lines.append(f"⚠️ Take profit is beyond the range {'top' if buy else 'bottom'} ({p(edge)}) · "
                         f"Brooks: ranges often hold, consider it")
    elif k == "TRADE_CLOSED":
        win = ev["result"] == "TP"
        head = (f"🏆 <b>TAKE PROFIT · +{ev['r']:g}R</b>" if win else f"🛑 <b>STOP LOSS · {ev['r']:g}R</b>")
        lines = [f"{side} from {p(ev['entry'])} → exit {p(ev['exit'])}",
                 f"⏱ {ev['bars']} M1 bars in the trade"]
    else:
        reason = (f"price went {'below' if buy else 'above'} the pin bar tail before entry"
                  if ev["reason"] == "tail" else f"no entry within {ORDER_BARS} M1 bars")
        head = f"✖️ <b>SETUP CANCELLED · {side}</b>"
        lines = [f"<i>{reason}</i>"]

    if ev.get("live"):
        lines.append("⚡ <i>Live price</i>")
    return (f"{head}\n<b>{label(sym)}</b>  ·  {where}  ·  M5 context → M1 trigger\n{LINE}\n"
            + "\n".join(lines) + f"\n{LINE}\n{_times(ev['time'], exact=True)}")


def build_spike_alert(ev):
    """اسپایک M5 از رنج بیرون زد: آماده‌ی اولین پولبک باشید."""
    sym, snap = ev["sym"], ev["snap"]
    p = lambda x: fmt_price(sym, x)
    up = snap["side"] > 0
    side = "BULLISH📈" if up else "BEARISH📉"
    return (f"🚀 <b>M5 SPIKE · {side}</b>\n<b>{label(sym)}</b>  ·  breakout from the trading range\n{LINE}\n"
            f"💰 Price: <b>{p(ev['price'])}</b>\n"
            f"🧱 Broke the range {'top' if up else 'bottom'} {p(snap['broken'])}\n"
            f"📏 Spike {p(snap['start_price'])} → {p(snap['extreme'])} ({snap['size']:.1f}× average bar)\n"
            f"⏳ <b>Wait for the first pullback</b>: M1 pin bar {'above' if up else 'below'} "
            f"{p(snap['broken'])}, then a key bar → entry\n"
            f"❌ Pullback closing back {'below' if up else 'above'} {p(snap['broken'])} on M5 = failed breakout, no trade\n"
            f"{LINE}\n{_times(ev['time'])}")
