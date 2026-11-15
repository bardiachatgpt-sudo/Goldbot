"""نسخه‌ی اول (پیش‌فرض، STRATEGY=pin): پین‌بار M1، زمینه‌ی چرخه‌ی M5.

در بک‌تست ۵ روزه‌ی طلا ۴۰٪ برد داشت. حالا چرخه‌ی M5 روند بدون اسپایک (Always In) را هم تشخیص می‌دهد،
پس در سقوط‌ها و صعودهای آرام «رنج» دیده نمی‌شود و خرید/فروش رنجی خلاف روند گرفته نمی‌شود.

📦 RANGE (چرخه‌ی M5 در حالت رنج)
   پین‌بار رنج روی M1 (کف/سقف ۱۰ کندل را رد کرده) در ربع پایینی رنج برای خرید، ربع بالایی برای فروش
   ورود: Buy Stop روی سقف پین‌بار / Sell Stop روی کف آن، حداکثر ORDER_BARS کندل M1
   لغو: عبور قیمت از سایه‌ی پین‌بار قبل از ورود، یا تمام شدن ORDER_BARS

🚀 SPIKE (اولین پولبک بعد از اسپایک M5 که از رنج بیرون زده)
   پنجره: تا وقتی چرخه‌ی M5 در «پولبک معتبر» است (سطح شکسته‌شده‌ی رنج حفظ شده و سقف اسپایک هنوز رد نشده)
   پین‌بار پولبک روی M1 در جهت اسپایک که آن طرف سطح شکسته‌شده بسته شود
   سپس Key bar در همان جهت، حداکثر ORDER_BARS کندل بعد از پین‌بار
   ورود: شروع کندل بعد از Key bar (= بسته‌شدن Key bar)
   لغو: عبور قیمت از سایه‌ی پین‌بار قبل از Key bar، یا تمام شدن ORDER_BARS
   فقط یک ورود برای هر اسپایک

هر دو: حد ضرر = پشت سایه‌ی پین‌بار ± اسپرد، حد سود = ورود ± RR × ریسک. یک معامله در هر لحظه برای هر نماد.

ترتیب رسیدن قیمت به سطح‌ها (ورود رنج / سایه / حد ضرر / حد سود):
   - با قیمت زنده (on_price): همان ترتیبی که در بازار رخ داد
   - برای دقیقه‌ای که قیمت زنده نداشتیم: از شکل کندل M1
       صعودی: باز ← کف ← سقف ← بسته     نزولی: باز ← سقف ← کف ← بسته
"""
import pandas as pd

from .config import ORDER_BARS, RANGE_EDGE, RR, spread

RANGE, SPIKE = "RANGE", "SPIKE"


def candle_path(o, h, l, c):
    """مسیر فرضی قیمت داخل کندل وقتی قیمت زنده نداریم."""
    return [o, l, h, c] if c >= o else [o, h, l, c]


def walk(path, levels):
    """اولین سطحی که مسیر قیمت به آن می‌رسد.

    levels: {نام: (قیمت، جهت)} — جهت +1 یعنی «رسیدن از پایین یا بالاتر بودن» (قیمت ≥ سطح)،
    -1 یعنی قیمت ≤ سطح. برمی‌گرداند (نام، قیمت اجرا، باقی‌مانده‌ی مسیر) یا None.
    اگر قیمت از همان اول آن طرف سطح باشد (گپ)، اجرا با همان قیمت اول است.
    """
    def beyond(p, lvl, d):
        return p >= lvl if d > 0 else p <= lvl

    for name, (lvl, d) in levels.items():
        if beyond(path[0], lvl, d):
            return name, path[0], path
    for k, (a, b) in enumerate(zip(path, path[1:])):
        best = None
        for name, (lvl, d) in levels.items():
            if not beyond(a, lvl, d) and beyond(b, lvl, d):
                dist = abs(lvl - a)
                if best is None or dist < best[0]:
                    best = (dist, name, lvl)
        if best:
            return best[1], best[2], [best[2]] + path[k + 1:]
    return None


class TradeManager:
    def __init__(self, sym, wedge_filter=None):
        from .config import WEDGE_FILTER
        self.sym = sym
        # تأیید وج (از ریپازیتوری اول): پین‌بار رنج فقط وقتی که خودش فشار سوم یک وج باشد
        self.wedge_filter = WEDGE_FILTER if wedge_filter is None else wedge_filter
        self.last = None          # آخرین کندل M1 پردازش‌شده (زمان شروع)
        self.pending = None       # ستاپ منتظر ورود
        self.open = None          # معامله‌ی باز
        self.used_spikes = set()  # یک ورود برای هر اسپایک
        self.n = 0
        self.live_from = None     # از این زمان، قیمت زنده‌ی این نماد بی‌وقفه دریافت شده

    def busy(self):
        return self.pending is not None or self.open is not None

    def needs_live(self):
        """قیمت زنده فقط وقتی لازم است که سفارش رنج یا معامله‌ی باز داریم."""
        return self.open is not None or (self.pending is not None and self.pending["mode"] == RANGE)

    # ------------------------------------------------------------ قیمت زنده
    def live_started(self, t):
        if self.live_from is None:
            self.live_from = t

    def live_stopped(self):
        self.live_from = None

    def on_price(self, price, t):
        """یک قیمت زنده: سفارش رنج (ورود/شکستن سایه) و حد ضرر/سود معامله‌ی باز."""
        self.live_started(t)
        price = float(price)
        if self.open is not None:
            return self._exit_on(self.open, [price], t, live=True)
        if self.pending is not None and self.pending["mode"] == RANGE:
            return self._range_fill_on(self.pending, [price], t, live=True)
        return []

    def _covered(self, bar_start):
        return self.live_from is not None and self.live_from <= bar_start

    # ------------------------------------------------------------ کندل‌ها
    def process(self, d, ctx=None, bar_minutes=1):
        """d: analyze(m1, cycle=False)["df"]؛ ctx: snapshot چرخه‌ی M5 (تا آخرین کندل بسته‌شده)."""
        if d is None or d.empty:
            return []
        if self.last is None:                     # اولین اجرا: فقط نقطه‌ی شروع
            self.last = d["date"].iloc[-1]
            return []
        rows = d[d["date"] > self.last]
        out = []
        for _, row in rows.iterrows():
            self.n += 1
            out += self._step(row, ctx, bar_minutes)
        if len(rows):
            self.last = rows["date"].iloc[-1]
        return out

    # ------------------------------------------------------------ ابزار
    def _ev(self, kind, t, time, price, **extra):
        return {**t, **extra, "kind": kind, "sym": self.sym, "setup": "TRADE", "time": time,
                "price": float(price), "strategy": "pin"}

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

    def _exit_on(self, t, path, time, live=False):
        """حد ضرر / حد سود روی مسیر قیمت."""
        s = t["side"]
        hit = walk(path, {"SL": (t["sl"], -s), "TP": (t["tp"], s)})
        if not hit:
            return []
        name, _, _ = hit
        lvl = t["sl"] if name == "SL" else t["tp"]
        self.open = None
        return [self._ev("TRADE_CLOSED", t, time, lvl, result=name, r=RR if name == "TP" else -1.0,
                         exit=lvl, bars=self.n - t["opened_n"], live=live)]

    def _range_fill_on(self, t, path, time, live=False):
        """سفارش Stop رنج روی مسیر قیمت: اول ورود یا اول شکستن سایه؟ بعد از ورود، بقیه‌ی همان مسیر."""
        s, pin = t["side"], t["pin"]
        trig = pin["high"] if s > 0 else pin["low"]
        tail = pin["low"] if s > 0 else pin["high"]
        # شکستن سایه = رفتن آن طرف سایه (برابر بودن هنوز شکستن نیست)
        tail_lvl = tail - 1e-12 * max(1.0, abs(tail)) * s
        hit = walk(path, {"ENTRY": (trig, s), "TAIL": (tail_lvl, -s)})
        if not hit:
            return []
        name, price, rest = hit
        if name == "TAIL":
            self.pending = None
            return [self._ev("TRADE_CANCELLED", t, time, price, reason="tail", live=live)]
        entry = price if (price - trig) * s > 0 else trig      # گپ از روی سطح: اجرا با قیمت گپ
        out = [self._open(t, time, entry, live=live)]
        out += self._exit_on(self.open, [entry] + rest[1:], time, live=live)
        return out

    # ------------------------------------------------------------ هر کندل M1
    def _step(self, row, ctx, bar_minutes):
        o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
        start = row["date"]
        end = start + pd.Timedelta(minutes=bar_minutes)
        live = self._covered(start)                  # این دقیقه را قیمت زنده پوشش داده؟
        path = candle_path(o, h, l, c)

        # ۱) معامله‌ی باز
        if self.open is not None:
            return [] if live else self._exit_on(self.open, path, end)

        # ۲) ستاپ در انتظار
        if self.pending is not None:
            t = self.pending
            s, pin = t["side"], t["pin"]
            t["waited"] += 1
            if t["mode"] == RANGE:
                if not live:
                    res = self._range_fill_on(t, path, end)
                    if res:
                        return res
            else:                                          # اسپایک: منتظر Key bar
                if (l < pin["low"]) if s > 0 else (h > pin["high"]):
                    self.pending = None
                    return [self._ev("TRADE_CANCELLED", t, end, c, reason="tail")]
                if int(row["key_bar"]) == s:
                    t["key"] = self._pin(row)
                    return [self._open(t, end, c)]
            if self.pending is not None and t["waited"] >= ORDER_BARS:
                self.pending = None
                return [self._ev("TRADE_CANCELLED", t, end, c, reason="expired")]
            return []

        # ۳) ستاپ تازه
        if not ctx:
            return []
        pin = self._pin(row)
        if ctx.get("state") == "CHANNEL" and ctx.get("pullback") and ctx.get("spike_id") not in self.used_spikes:
            s = ctx["side"]
            if int(row.get("pin_pullback", 0)) == s and \
                    (pin["close"] > ctx["broken"] if s > 0 else pin["close"] < ctx["broken"]):
                self.used_spikes.add(ctx["spike_id"])
                return [self._pending(SPIKE, s, pin, end, level=ctx["broken"], spike_id=ctx["spike_id"],
                                      spike_high=ctx.get("high"))]
        pin_side = int(row["pin_bar"])
        if pin_side and ctx.get("state") == "RANGE" and ctx.get("hi") is not None and ctx["hi"] > ctx["lo"]:
            top, bot = ctx["hi"], ctx["lo"]
            edge = RANGE_EDGE * (top - bot)
            if (pin_side > 0 and pin["low"] <= bot + edge) or (pin_side < 0 and pin["high"] >= top - edge):
                if self.wedge_filter and int(row.get("wedge_push", 0)) != pin_side:
                    return []                              # بدون وج: رد
                return [self._pending(RANGE, pin_side, pin, end, range_high=top, range_low=bot,
                                      wedge=bool(int(row.get("wedge_push", 0)) == pin_side))]
        return []

    def _pending(self, mode, side, pin, time, **extra):
        planned = (pin["high"] if side > 0 else pin["low"]) if mode == RANGE else pin["close"]
        sl, tp, risk = self._levels(side, pin, planned)
        self.pending = {"mode": mode, "side": side, "pin": pin, "waited": 0, "planned_entry": planned,
                        "sl": sl, "tp": tp, "risk": risk, "spread": spread(self.sym), **extra}
        return self._ev("TRADE_PENDING", self.pending, time, pin["close"])

    def _open(self, t, time, entry, live=False):
        sl, tp, risk = self._levels(t["side"], t["pin"], entry)
        t.update(entry=entry, sl=sl, tp=tp, risk=risk, opened=time, opened_n=self.n)
        if t["mode"] == RANGE:
            t["tp_beyond_range"] = bool(tp > t["range_high"] if t["side"] > 0 else tp < t["range_low"])
        self.pending, self.open = None, t
        return self._ev("TRADE_OPEN", t, time, entry, live=live)
