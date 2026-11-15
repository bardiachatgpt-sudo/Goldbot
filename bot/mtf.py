"""بریک‌اوت چندتایم‌فریمی: زمینه روی M5، ماشه روی M1.

برای هر سطح M5 (سقف/کف رنج، سطح بریک‌اوت وج):
  ⚡ BO_READY      یک Key bar روی M1 بیرون سطح بسته شد → آماده‌ی تأیید یا شکست باشید
  ✅ BO_CONFIRMED  Follow-through: یک کندل M1 فراتر از انتهای Key bar بسته شد،
                   یا قیمت HOLD_BARS کندل M1 بیرون سطح ماند
  ❌ BO_FAILED     قبل از تأیید، یک کندل M1 دوباره داخل سطح بسته شد (بریک‌اوت فیک)

زمینه‌ی هر کندل M1 فقط از کندل‌های M5 ساخته می‌شود که قبل از شروع آن کندل M1 بسته شده‌اند،
پس نتیجه به زمان اجرای اسکنر بستگی ندارد.
"""
import pandas as pd

from .config import BO_COOLDOWN, CONTEXT_TF, HOLD_BARS, MIN_BARS, TRIGGER_TF, bar_delta
from .strategy import analyze, breakout_levels


class BreakoutWatcher:
    def __init__(self, sym):
        self.sym = sym
        self.last = None          # زمان آخرین کندل M1 پردازش‌شده
        self.ctx_n = None         # تعداد کندل‌های M5 که زمینه‌ی فعلی از آن‌ها ساخته شده
        self.levels = []
        self.active = {}          # key → تلاش بریک‌اوت در جریان
        self.blocked = {}         # key → تا این زمان تلاش جدید شروع نشود
        self.used = set()         # وج‌هایی که تکلیفشان روشن شده

    def process(self, m5, m1):
        """m5 و m1: کندل‌های بسته‌شده (خروجی data.py). رویدادهای تازه را برمی‌گرداند."""
        if m1 is None or m5 is None or len(m1) < MIN_BARS:
            return []
        d = analyze(m1, cycle=False)["df"]
        if self.last is None:                       # اولین اجرا: فقط نقطه‌ی شروع
            self.last = d["date"].iloc[-1]
            return []
        rows = d[d["date"] > self.last]
        if rows.empty:
            return []
        m5_end = m5.index + bar_delta(CONTEXT_TF)
        events = []
        for _, row in rows.iterrows():
            n = int((m5_end <= row["date"]).sum())
            if n != self.ctx_n:
                self.ctx_n = n
                self.levels = breakout_levels(analyze(m5.iloc[:n], cycle=False)) if n >= MIN_BARS else []
            events += self._step(row)
        self.last = rows["date"].iloc[-1]
        return events

    def _event(self, kind, a, row, **extra):
        return {"kind": kind, "setup": "MTF_BO", "sym": self.sym, "side": a["side"],
                "ctx": a["kind"], "level": a["level"], "time": row["date"],
                "price": float(row["close"]), "tf": TRIGGER_TF,
                "range_high": a.get("range_high"), "range_low": a.get("range_low"),
                "type": a.get("type"), "points": a.get("points"),
                "started": a["start"], "key_high": a["key_high"], "key_low": a["key_low"], **extra}

    def _finish(self, key, a, t):
        del self.active[key]
        if a["kind"] == "WEDGE":
            self.used.add(key)
        else:
            self.blocked[key] = t + BO_COOLDOWN * bar_delta(TRIGGER_TF)

    def _step(self, row):
        t, close = row["date"], row["close"]
        out = []

        # ۱) تلاش‌های در جریان: تأیید یا شکست
        for key, a in list(self.active.items()):
            side = a["side"]
            a["bars"] += 1
            if (side > 0 and close <= a["level"]) or (side < 0 and close >= a["level"]):
                out.append(self._event("BO_FAILED", a, row))
                self._finish(key, a, t)
            elif (side > 0 and close > a["key_high"]) or (side < 0 and close < a["key_low"]):
                out.append(self._event("BO_CONFIRMED", a, row, reason="follow"))
                self._finish(key, a, t)
            elif a["bars"] >= HOLD_BARS:
                out.append(self._event("BO_CONFIRMED", a, row, reason="hold"))
                self._finish(key, a, t)

        # ۲) شروع تلاش جدید: Key bar روی M1 که بیرون سطح M5 بسته شود
        for lv in self.levels:
            key, side = lv["key"], lv["side"]
            if key in self.active or key in self.used or self.blocked.get(key, t) > t:
                continue
            if lv["kind"] == "WEDGE" and ((side > 0 and row["low"] < lv["extreme"]) or
                                          (side < 0 and row["high"] > lv["extreme"])):
                self.used.add(key)                  # وج قبل از بریک‌اوت باطل شد
                continue
            beyond = close > lv["level"] if side > 0 else close < lv["level"]
            if beyond and row["key_bar"] == side:
                a = {**lv, "start": t, "bars": 0,
                     "key_high": float(row["high"]), "key_low": float(row["low"])}
                self.active[key] = a
                out.append(self._event("BO_READY", a, row))
        return out


def minutes_between(a, b):
    return int((pd.Timestamp(b) - pd.Timestamp(a)).total_seconds() // 60)
