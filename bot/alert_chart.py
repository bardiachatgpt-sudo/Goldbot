"""عکس لحظه‌ی هر هشدار: کندل سیگنال پررنگ و برچسب‌خورده، با سطح‌های همان هشدار.

- هشدارهای M5 (H2/L2، پین‌بار، وج، بریک‌اوت M5، تغییر چرخه): نمودار M5 با خط روند و کانال
- هشدارهای معامله (ستاپ / ورود / حد سود و ضرر / لغو): نمودار M1 با خطوط ورود، حد ضرر و حد سود
"""
from .chart import render_chart
from .messages import fmt_price

M5_BARS = 100
M1_BARS = 90


def _lv(sym, price, text, color="#FDE047", style="-"):
    return {"price": float(price), "price_txt": fmt_price(sym, price), "text": text, "color": color,
            "style": style}


def _cycle_focus(sym, ev):
    snap = ev["snap"]
    st, up = snap["state"], snap["side"] >= 0
    names = {"RANGE": "TRADING RANGE", "SPIKE": "SPIKE", "CHANNEL": "CHANNEL", "TEST": "UNDER TEST"}
    text = "RESUMED" if ev.get("note") == "resumed" else \
        "POSSIBLE REVERSAL" if ev.get("note") == "reversal" else names[st]
    f = {"time": ev["time"], "text": text, "side": 1 if up else -1, "title": snap["label"], "levels": []}
    if st == "TEST":
        f["levels"] = [_lv(sym, snap["high"], "Test level", "#A78BFA", "--"),
                       _lv(sym, snap["break_low"], "Break " + ("low" if up else "high"), "#F472B6", ":")]
    elif st == "RANGE" and snap.get("hi") is not None:
        f["zone"] = (snap["lo"], snap["hi"])
        f["levels"] = [_lv(sym, snap["hi"], "Top", "#60A5FA", "--"), _lv(sym, snap["lo"], "Bottom", "#60A5FA", "--")]
        w = snap.get("watch")
        if w:
            f["levels"].append(_lv(sym, w["level"], "Break " + ("low" if w["side"] > 0 else "high"), "#F472B6", ":"))
    elif st == "SPIKE":
        f["levels"] = [_lv(sym, snap["start_price"], "Spike start", "#FACC15", ":")]
        if snap.get("broken") is not None:
            f["levels"].append(_lv(sym, snap["broken"], "Broken range level", "#60A5FA", "--"))
    return f


def _m5_focus(sym, ev):
    k = ev["kind"]
    side = ev.get("side", 1)
    if k == "CYCLE":
        return _cycle_focus(sym, ev)
    if k == "PIN":
        entry = ev["high"] if side > 0 else ev["low"]
        return {"time": ev["time"], "text": "PIN BAR", "side": side, "title": "Pin bar",
                "levels": [_lv(sym, entry, "Entry " + ("above" if side > 0 else "below"))]}
    if k == "WEDGE":
        return {"time": ev["time"], "text": ev["type"].upper(), "side": side, "title": ev["type"]}
    if k == "WEDGE_BO":
        return {"time": ev["time"], "text": "KEY BAR · BREAKOUT" if ev.get("strong") else "BREAKOUT",
                "side": side, "title": "Wedge breakout", "levels": [_lv(sym, ev["level"], "Wedge level")]}
    if k == "RANGE_BO":
        return {"time": ev["time"], "text": "KEY BAR · BREAKOUT", "side": side, "title": "Range breakout",
                "zone": (ev["range_low"], ev["range_high"]),
                "levels": [_lv(sym, ev["range_high"], "Range top", "#60A5FA", "--"),
                           _lv(sym, ev["range_low"], "Range bottom", "#60A5FA", "--")]}
    return {"time": ev["time"], "text": ev["setup"], "side": side, "title": f"{ev['setup']} setup"}


def m5_alert_chart(sym, res, ev):
    return render_chart(sym, res, n=M5_BARS, focus=_m5_focus(sym, ev))


def trade_chart(sym, res5, ev):
    """نمودار M5 معامله (نمودار ال بروکس): کندل سیگنال پررنگ، خطوط ورود / حد ضرر / حد سود، و زمینه."""
    import pandas as pd
    k, side, mode = ev["kind"], ev["side"], ev["mode"]
    sig = ev["signal"]
    entry = ev.get("entry", ev.get("planned_entry"))
    text = {"TRADE_PENDING": "SIGNAL BAR", "TRADE_OPEN": "ENTRY", "TRADE_CLOSED": ev.get("result", ""),
            "TRADE_CANCELLED": "CANCELLED"}[k]
    name = {"RANGE": "Range second entry", "SPIKE": "Spike pullback", "TREND": "With the trend"}[mode]
    hl = ("H" if side > 0 else "L") + str(ev.get("n_h", "")) if mode != "RANGE" else ""
    title = {"TRADE_PENDING": "Setup", "TRADE_OPEN": "Entry", "TRADE_CLOSED": "Trade closed",
             "TRADE_CANCELLED": "Setup cancelled"}[k] + f" · {name} {hl} " + ("BUY" if side > 0 else "SELL")
    dates = res5["df"]["date"]
    t = pd.Timestamp(ev["time"])
    bar = dates[dates < t].iloc[-1] if (dates < t).any() else dates.iloc[-1]   # کندل M5 همان لحظه
    focus = {"time": bar, "text": text, "side": side, "title": title,
             "levels": [_lv(sym, entry, "Entry", "#E5E7EB", "--"),
                        _lv(sym, ev["sl"], "Stop loss", "#EF4444"),
                        _lv(sym, ev["tp"], "Take profit", "#10B981")]}
    if mode == "RANGE" and ev.get("range_high") is not None:
        focus["zone"] = (ev["range_low"], ev["range_high"])
    if mode == "SPIKE" and ev.get("level") is not None:
        focus["levels"].append(_lv(sym, ev["level"], "Broken range level", "#FDE047", ":"))
    focus["marks"] = [{"time": sig["time"], "text": "SIGNAL BAR"}] if sig["time"] != bar else []
    return render_chart(sym, res5, n=M5_BARS, focus=focus)


def pin_trade_chart(sym, res_m1, ev):
    """نمودار M1 معامله: پین‌بار پررنگ، Key bar، و خطوط ورود / حد ضرر / حد سود."""
    k, side = ev["kind"], ev["side"]
    pin = ev["pin"]
    entry = ev.get("entry", ev.get("planned_entry"))
    text = {"TRADE_PENDING": "PIN BAR", "TRADE_OPEN": "ENTRY", "TRADE_CLOSED": ev.get("result", ""),
            "TRADE_CANCELLED": "CANCELLED"}[k]
    title = {"TRADE_PENDING": "Setup", "TRADE_OPEN": "Entry", "TRADE_CLOSED": "Trade closed",
             "TRADE_CANCELLED": "Setup cancelled"}[k]
    title += " · " + ("Range" if ev["mode"] == "RANGE" else "Spike pullback") + (" BUY" if side > 0 else " SELL")
    # زمان رویداد = بسته‌شدن کندل (یا لحظه‌ی قیمت زنده)؛ کندلی که باید پررنگ شود
    import pandas as pd
    t = pd.Timestamp(ev["time"])
    bar = t - pd.Timedelta(minutes=1) if t == t.floor("min") else t.floor("min")
    dates = set(res_m1["df"]["date"])
    if bar not in dates:
        bar = res_m1["df"]["date"].iloc[-1]
    focus = {"time": bar, "text": text, "side": side, "title": title,
             "levels": [_lv(sym, entry, "Entry", "#E5E7EB", "--"),
                        _lv(sym, ev["sl"], "Stop loss", "#EF4444"),
                        _lv(sym, ev["tp"], "Take profit", "#10B981")]}
    if ev["mode"] == "RANGE" and ev.get("range_high") is not None:
        focus["zone"] = (ev["range_low"], ev["range_high"])
    if ev["mode"] == "SPIKE" and ev.get("level") is not None:
        focus["levels"].append(_lv(sym, ev["level"], "Broken range level (M5)", "#FDE047", ":"))
    marks = []
    if pin["time"] != bar:
        marks.append({"time": pin["time"], "text": "PIN BAR"})
    if ev.get("key") and ev["key"]["time"] != bar:
        marks.append({"time": ev["key"]["time"], "text": "KEY BAR"})
    focus["marks"] = marks
    res_m1 = {**res_m1, "market_cycle": "", "cycle": None}
    return render_chart(sym, res_m1, n=M1_BARS, focus=focus, tf="1", clean=True)
