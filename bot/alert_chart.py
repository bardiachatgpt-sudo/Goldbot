"""عکس لحظه‌ی هر هشدار: کندل سیگنال پررنگ و برچسب‌خورده، با سطح‌های همان هشدار.

- هشدارهای M5 (H2/L2، پین‌بار، وج، بریک‌اوت M5، تغییر چرخه): نمودار M5 با خط روند و کانال
- هشدارهای M5→M1 (آماده باش / تأیید شد / شکست خورد): نمودار M1 با سطح M5 که شکسته شده
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


def m1_alert_chart(sym, res_m1, ev):
    """res_m1: analyze(m1, cycle=False)."""
    k, side = ev["kind"], ev["side"]
    text = {"BO_READY": "KEY BAR · BREAKOUT", "BO_CONFIRMED": "CONFIRMED", "BO_FAILED": "FAILED"}[k]
    what = "Range" if ev["ctx"] == "RANGE" else "Wedge"
    title = {"BO_READY": f"Get ready · {what} breakout", "BO_CONFIRMED": f"{what} breakout confirmed",
             "BO_FAILED": f"{what} breakout failed"}[k]
    focus = {"time": ev["time"], "text": text, "side": side if k != "BO_FAILED" else -side, "title": title,
             "levels": [_lv(sym, ev["level"], "M5 level")]}
    if ev["ctx"] == "RANGE" and ev.get("range_high") is not None:
        focus["zone"] = (ev["range_low"], ev["range_high"])
        other = ev["range_low"] if side > 0 else ev["range_high"]
        focus["levels"].append(_lv(sym, other, "M5 range " + ("bottom" if side > 0 else "top"), "#60A5FA", "--"))
    if k != "BO_READY" and ev["started"] != ev["time"]:
        focus["marks"] = [{"time": ev["started"], "text": "KEY BAR"}]
    res_m1 = {**res_m1, "market_cycle": "", "cycle": None}
    return render_chart(sym, res_m1, n=M1_BARS, focus=focus, tf="1", clean=True)
