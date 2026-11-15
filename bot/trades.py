"""ستاپ‌های ورود، روی M1:

📦 رنج (چرخه‌ی M5 در حالت رنج):
   پین‌بار صعودی در ربع پایینی رنج (یا زیر کف آن) / نزولی در ربع بالایی (یا بالای سقف)
   ورود: Buy Stop روی سقف پین‌بار / Sell Stop روی کف پین‌بار، حداکثر ORDER_BARS کندل معتبر
   اگر قبل از ورود قیمت از سایه‌ی پین‌بار عبور کند ← باطل

💥 بریک‌اوت (بعد از «BREAKOUT CONFIRMED» روی M1):
   تا ARM_BARS کندل بعد از تأیید، پین‌بار پولبک در جهت بریک‌اوت (سایه‌ی بلند، کف پایین‌تر از ۳ کندل قبل)
   که بیرون سطح بسته شود
   سپس Key bar در همان جهت، حداکثر ORDER_BARS کندل بعد از پین‌بار
   ورود: شروع کندل بعد از Key bar (= بسته‌شدن Key bar)
   اگر قبل از Key bar قیمت از سایه‌ی پین‌بار عبور کند ← باطل

هر دو: حد ضرر = پشت سایه‌ی پین‌بار ± اسپرد، حد سود = ورود ± RR × ریسک.
اگر یک کندل هم به حد ضرر و هم به حد سود برسد، محافظه‌کارانه حد ضرر حساب می‌شود.
"""
from .config import ARM_BARS, ORDER_BARS, RANGE_EDGE, RR, spread

RANGE, BREAKOUT = "RANGE", "BREAKOUT"


class TradeManager:
    def __init__(self, sym):
        self.sym = sym
        self.last = None          # آخرین کندل M1 پردازش‌شده
        self.armed = []           # بریک‌اوت‌های تأییدشده که منتظر پین‌بارند
        self.pending = None       # ستاپی که منتظر ورود است
        self.open = None          # معامله‌ی باز
        self.n = 0                # شماره‌ی کندل M1

    def busy(self):
        return self.pending is not None or self.open is not None

    def process(self, d, ctx=None, mtf_events=()):
        """d: analyze(m1, cycle=False)["df"]؛ ctx: snapshot چرخه‌ی M5؛ mtf_events: رویدادهای BreakoutWatcher."""
        for ev in mtf_events:
            if ev["kind"] == "BO_CONFIRMED":
                self.armed.append({"side": ev["side"], "level": ev["level"], "time": ev["time"],
                                   "ctx": ev["ctx"], "left": ARM_BARS})
        if d is None or d.empty:
            return []
        if self.last is None:                     # اولین اجرا: فقط نقطه‌ی شروع
            self.last = d["date"].iloc[-1]
            return []
        rows = d[d["date"] > self.last]
        out = []
        for _, row in rows.iterrows():
            self.n += 1
            out += self._step(row, ctx)
        if len(rows):
            self.last = rows["date"].iloc[-1]
        return out

    # ------------------------------------------------------------ ابزار
    def _ev(self, kind, t, row, **extra):
        return {"kind": kind, "sym": self.sym, "setup": "TRADE", "time": row["date"],
                "price": float(row["close"]), **{k: v for k, v in t.items() if k != "row"}, **extra}

    def _levels(self, side, pin, entry):
        sp = spread(self.sym)
        sl = pin["low"] - sp if side > 0 else pin["high"] + sp
        risk = abs(entry - sl)
        tp = entry + RR * risk if side > 0 else entry - RR * risk
        return sl, tp, risk

    @staticmethod
    def _pin(row):
        return {"time": row["date"], "high": float(row["high"]), "low": float(row["low"]),
                "close": float(row["close"])}

    # ------------------------------------------------------------ هر کندل
    def _step(self, row, ctx):
        out = []
        hi, lo = float(row["high"]), float(row["low"])
        for a in self.armed:                                # پنجره‌ی بعد از تأیید بریک‌اوت
            if a["time"] < row["date"]:
                a["left"] -= 1
        self.armed = [a for a in self.armed if a["left"] >= 0]

        # ۱) معامله‌ی باز: حد ضرر یا حد سود
        if self.open is not None:
            t = self.open
            s = t["side"]
            hit_sl = lo <= t["sl"] if s > 0 else hi >= t["sl"]
            hit_tp = hi >= t["tp"] if s > 0 else lo <= t["tp"]
            if hit_sl or hit_tp:
                result = "SL" if hit_sl else "TP"
                r = -1.0 if hit_sl else RR
                out.append(self._ev("TRADE_CLOSED", t, row, result=result, r=r,
                                    exit=t["sl"] if hit_sl else t["tp"], bars=self.n - t["opened_n"]))
                self.open = None
            return out                                      # یک معامله در هر لحظه

        # ۲) ستاپ در انتظار ورود
        if self.pending is not None:
            t = self.pending
            s, pin = t["side"], t["pin"]
            t["waited"] += 1
            broke_tail = lo < pin["low"] if s > 0 else hi > pin["high"]
            if t["mode"] == RANGE:
                trig = pin["high"] if s > 0 else pin["low"]
                fired = hi >= trig if s > 0 else lo <= trig
                if fired:
                    entry = max(float(row["open"]), trig) if s > 0 else min(float(row["open"]), trig)
                    out.append(self._open(t, row, entry))
                    o = self.open                           # همان کندل از حد ضرر هم رد شد؟ محافظه‌کارانه: باخت
                    if (lo <= o["sl"] if s > 0 else hi >= o["sl"]):
                        out.append(self._ev("TRADE_CLOSED", o, row, result="SL", r=-1.0, exit=o["sl"], bars=0))
                        self.open = None
                    return out
            else:
                if not broke_tail and row["key_bar"] == s:
                    t["key"] = self._pin(row)
                    return out + [self._open(t, row, float(row["close"]))]
            if broke_tail:
                out.append(self._ev("TRADE_CANCELLED", t, row, reason="tail"))
                self.pending = None
            elif t["waited"] >= ORDER_BARS:
                out.append(self._ev("TRADE_CANCELLED", t, row, reason="expired"))
                self.pending = None
            return out

        # ۳) ستاپ تازه
        pin = self._pin(row)
        pb_side = int(row.get("pin_pullback", 0))
        for a in self.armed:                                # بریک‌اوت تأییدشده: پین‌بار پولبک در جهت بریک‌اوت
            if a["time"] < row["date"] and a["side"] == pb_side and \
                    (pin["close"] > a["level"] if pb_side > 0 else pin["close"] < a["level"]):
                self.armed.remove(a)
                return out + [self._pending(BREAKOUT, pb_side, pin, row, level=a["level"], bo_ctx=a["ctx"])]

        pin_side = int(row["pin_bar"])                     # رنج: پین‌بار که کف/سقف تازه را رد کرده
        if not pin_side:
            return out

        if ctx and ctx.get("state") == "RANGE" and ctx.get("hi") is not None and ctx["hi"] > ctx["lo"]:
            top, bot = ctx["hi"], ctx["lo"]
            edge = RANGE_EDGE * (top - bot)
            if (pin_side > 0 and pin["low"] <= bot + edge) or (pin_side < 0 and pin["high"] >= top - edge):
                return out + [self._pending(RANGE, pin_side, pin, row, range_high=top, range_low=bot)]
        return out

    def _pending(self, mode, side, pin, row, **extra):
        planned = (pin["high"] if side > 0 else pin["low"]) if mode == RANGE else pin["close"]
        sl, tp, risk = self._levels(side, pin, planned)
        self.pending = {"mode": mode, "side": side, "pin": pin, "waited": 0, "planned_entry": planned,
                        "sl": sl, "tp": tp, "risk": risk, "spread": spread(self.sym), **extra}
        return self._ev("TRADE_PENDING", self.pending, row)

    def _open(self, t, row, entry):
        sl, tp, risk = self._levels(t["side"], t["pin"], entry)
        t.update(entry=entry, sl=sl, tp=tp, risk=risk, opened=row["date"], opened_n=self.n)
        if t["mode"] == RANGE:
            beyond = tp > t["range_high"] if t["side"] > 0 else tp < t["range_low"]
            t["tp_beyond_range"] = bool(beyond)
        self.pending, self.open = None, t
        return self._ev("TRADE_OPEN", t, row)
