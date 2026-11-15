"""ستاپ‌های ورود به روش ال بروکس (و جزوه‌ی چینی).

کندل سیگنال روی M5 (مثل خود ال بروکس)؛ ورود با سفارش Stop روی سقف/کف کندل سیگنال؛ حد ضرر پشت ساختار
(کف پولبک، یا Double Bottom در رنج) ± اسپرد و حداقل یک کندل متوسط M5؛ حد سود = ورود ± RR × ریسک. کندل‌های M1 و قیمت زنده فقط برای اینکه دقیق بفهمیم
ورود / حد ضرر / حد سود کدام اول خورد.

📈 TREND — معامله در جهت روند (جزوه فصل ۰۳–۰۴؛ «در روند فقط در جهت روند»)
   زمینه: کانال M5 (از اسپایک یا Always In)، سمت = جهت کانال
   کندل سیگنال: کندل پولبک (سقف پایین‌تر از کندل قبل در کانال صعودی) که قوی بسته شده (نیمه‌ی بالایی)
   H1 کافی است در کانال تنگ؛ در کانال باز H2 لازم است (ورود دوم، فصل ۰۴). حداکثر H3.
   پولبک سالم: حداکثر ۶۲٪ حرکت از شروع کانال تا سقف، و تا نزدیک EMA20 برگشته باشد (فصل ۰۳)
   در ربع بیرونی کانال (نزدیک خط کانال) ورود نمی‌شود

🚀 SPIKE — اولین پولبک بعد از اسپایکی که از رنج بیرون زده (همان قاعده‌ی TREND، با H1)
   تا وقتی پولبک روی M5 به داخل رنج قبلی بسته نشده و سقف اسپایک دوباره رد نشده

📦 RANGE — بالا بفروش، پایین بخر (فصل ۰۶) — فقط در «رنج واقعی»:
   EMA تقریباً صاف، قیمت از دو طرف EMA عبور کرده، و رنج تنگ (Barbwire) نیست
   کندل سیگنال صعودی در ربع پایینی رنج، که بیرون رنج بسته نشده باشد
   ورود دوم (فصل ۰۴ و ۰۵): کف رنج قبلاً یک بار تست شده و این تست کف قبلی را بیش از یک کندل
   متوسط نشکسته (Double Bottom). برعکس برای فروش در سقف.

ترمز (فصل ۰۸): دو ضرر پشت‌سرهم در یک جهت ← آن جهت تا تغییر زمینه‌ی M5 بسته می‌شود.
لغو: قیمت قبل از ورود از سر دیگر کندل سیگنال رد شود، یا ORDER_BARS کندل M5 بگذرد.
سفارش در انتظار با کندل سیگنال تازه‌تر در همان جهت جابه‌جا می‌شود (ال بروکس سفارش را دنبال می‌کند).
یک معامله در هر لحظه برای هر نماد.

ترتیب داخل کندل وقتی قیمت زنده نداریم: صعودی باز ← کف ← سقف ← بسته، نزولی باز ← سقف ← کف ← بسته.
"""
from collections import deque

import pandas as pd

from .config import ORDER_BARS, RR, spread

RANGE, SPIKE, TREND = "RANGE", "SPIKE", "TREND"
SIGNAL_TF = 5               # کندل سیگنال M5
PULLBACK_MAX = 0.62         # پولبک سالم حداکثر ۶۲٪ (فصل ۰۳)
MAX_H = 3                   # حداکثر H3 / L3
SECOND_TEST_SLACK = 1.0     # تست دوم کف قبلی را حداکثر یک کندل متوسط بشکند
EDGE = 0.25
LOSS_BRAKE = 2
VALUE_ZONE = 0.5            # پولبک در جهت روند باید تا نیم کندل متوسط از EMA20 برسد (فصل ۰۳)
CHANNEL_EDGE = 0.75         # ورود در جهت روند در ربع بیرونی کانال (نزدیک خط کانال) ممنوع
MIN_RISK = 1.0              # حد ضرر حداقل یک کندل متوسط M5 از ورود


def candle_path(o, h, l, c):
    """مسیر فرضی قیمت داخل کندل وقتی قیمت زنده نداریم."""
    return [o, l, h, c] if c >= o else [o, h, l, c]


def walk(path, levels):
    """اولین سطحی که مسیر قیمت به آن می‌رسد.

    levels: {نام: (قیمت، جهت)} — جهت +1 یعنی قیمت ≥ سطح، -1 یعنی قیمت ≤ سطح.
    برمی‌گرداند (نام، قیمت اجرا، باقی‌مانده‌ی مسیر) یا None. گپ: اجرا با همان قیمت اول.
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


def signal_bar(side, o, h, l, c):
    """کندل سیگنال ال بروکس: در جهت معامله نزدیک انتهایش بسته شده (نیمه‌ی بالایی برای خرید)
    یا سایه‌ی بلند خلاف جهت دارد (پین‌بار)."""
    r = h - l
    if r <= 0:
        return False
    cp = (c - l) / r
    if side > 0:
        return cp >= 0.5 and (c >= o or (min(o, c) - l) >= 0.5 * r)
    return cp <= 0.5 and (c <= o or (h - max(o, c)) >= 0.5 * r)


class TradeManager:
    def __init__(self, sym, signal_tf=SIGNAL_TF):
        self.sym = sym
        self.signal_tf = signal_tf    # دقیقه‌ی کندل سیگنال (M5)
        self.pending = None
        self.open = None
        self.used_spikes = set()
        self.live_from = None
        self.last1 = None             # آخرین کندل M1 پردازش‌شده
        self.last5 = None             # آخرین کندل M5 پردازش‌شده
        self.prev5 = None             # کندل M5 قبلی (برای پولبک)
        self.ranges = deque(maxlen=20)
        self.trend = None             # شمارش H/L در کانال فعلی
        self.losses = {1: 0, -1: 0}
        self.blocked = {}             # جهت → زمینه‌ای که در آن بسته شد
        self.n = 0

    def busy(self):
        return self.pending is not None or self.open is not None

    def needs_live(self):
        return self.busy()

    # ------------------------------------------------------------ قیمت زنده
    def live_started(self, t):
        if self.live_from is None:
            self.live_from = t

    def live_stopped(self):
        self.live_from = None

    def on_price(self, price, t):
        self.live_started(t)
        price = float(price)
        if self.open is not None:
            return self._exit_on([price], t, live=True)
        if self.pending is not None:
            return self._fill_on([price], t, live=True)
        return []

    def _covered(self, bar_start):
        return self.live_from is not None and self.live_from <= bar_start

    # ------------------------------------------------------------ ورود / خروج روی مسیر قیمت
    def _ev(self, kind, t, time, price, **extra):
        return {**t, **extra, "kind": kind, "sym": self.sym, "setup": "TRADE", "time": time,
                "price": float(price)}

    def _exit_on(self, path, time, live=False):
        t = self.open
        s = t["side"]
        hit = walk(path, {"SL": (t["sl"], -s), "TP": (t["tp"], s)})
        if not hit:
            return []
        name = hit[0]
        lvl = t["sl"] if name == "SL" else t["tp"]
        self.open = None
        win = name == "TP"
        self._record(s, win, t)
        return [self._ev("TRADE_CLOSED", t, time, lvl, result=name, r=RR if win else -1.0, exit=lvl,
                         bars=t.get("bars_open", 0), live=live)]

    def _fill_on(self, path, time, live=False):
        """سفارش Stop: اول ورود یا اول شکستن سر دیگر کندل سیگنال؟ بعد از ورود، بقیه‌ی همان مسیر."""
        t = self.pending
        s, sig = t["side"], t["signal"]
        trig = sig["high"] if s > 0 else sig["low"]
        tail = sig["low"] if s > 0 else sig["high"]
        tail_lvl = tail - 1e-12 * max(1.0, abs(tail)) * s
        hit = walk(path, {"ENTRY": (trig, s), "TAIL": (tail_lvl, -s)})
        if not hit:
            return []
        name, price, rest = hit
        if name == "TAIL":
            self.pending = None
            return [self._ev("TRADE_CANCELLED", t, time, price, reason="tail", live=live)]
        entry = price if (price - trig) * s > 0 else trig       # گپ: اجرا با قیمت گپ
        out = [self._open(time, entry, live)]
        out += self._exit_on([entry] + rest[1:], time, live)
        return out

    def _open(self, time, entry, live=False):
        t = self.pending
        sl, tp, risk = self._levels(t["side"], t["stop_ref"], entry, t["min_risk"])
        t.update(entry=entry, sl=sl, tp=tp, risk=risk, opened=time, bars_open=0)
        if t["mode"] == RANGE:
            t["tp_beyond_range"] = bool(tp > t["range_high"] if t["side"] > 0 else tp < t["range_low"])
        self.pending, self.open = None, t
        return self._ev("TRADE_OPEN", t, time, entry, live=live)

    def _levels(self, side, stop_ref, entry, min_risk=0.0):
        """حد ضرر پشت stop_ref ± اسپرد، و حداقل min_risk از ورود (تا داخل نویز نباشد)."""
        sp = spread(self.sym)
        sl = stop_ref - sp if side > 0 else stop_ref + sp
        if abs(entry - sl) < min_risk:
            sl = entry - min_risk if side > 0 else entry + min_risk
        risk = abs(entry - sl)
        tp = entry + RR * risk if side > 0 else entry - RR * risk
        return sl, tp, risk

    def _record(self, side, win, t):
        self.losses[side] = 0 if win else self.losses[side] + 1
        if self.losses[side] >= LOSS_BRAKE:
            self.blocked[side] = t.get("ctx_key")

    # ------------------------------------------------------------ کندل M1: اجرا
    def on_m1(self, row, bar_minutes=1):
        o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
        start = row["date"]
        end = start + pd.Timedelta(minutes=bar_minutes)
        if self.open is not None:
            self.open["bars_open"] = self.open.get("bars_open", 0) + 1
        if self.pending is not None and start >= self.pending["valid_until"]:
            t, self.pending = self.pending, None
            return [self._ev("TRADE_CANCELLED", t, t["valid_until"], o, reason="expired")]
        if self._covered(start):                       # قیمت زنده این دقیقه را دیده
            return []
        path = candle_path(o, h, l, c)
        if self.open is not None:
            return self._exit_on(path, end)
        if self.pending is not None:
            return self._fill_on(path, end)
        return []

    # ------------------------------------------------------------ کندل M5: ستاپ
    def on_m5_close(self, row, ctx):
        """row: کندل M5 تازه بسته‌شده (با ema20)؛ ctx: snapshot چرخه بعد از همین کندل."""
        o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
        end = row["date"] + pd.Timedelta(minutes=self.signal_tf)
        avg = sum(self.ranges) / len(self.ranges) if len(self.ranges) >= 5 else None
        self.ranges.append(h - l)
        prev, self.prev5 = self.prev5, {"high": h, "low": l}
        if not ctx or avg is None or prev is None:
            return []
        key = (ctx.get("state"), ctx.get("side"), ctx.get("since"))
        for side in list(self.blocked):                # ترمز تا تغییر زمینه
            if self.blocked[side] != key:
                del self.blocked[side]
                self.losses[side] = 0
        self._count_pushes(ctx, h, l, prev)
        if self.open is not None:
            return []
        sig = {"time": row["date"], "high": h, "low": l, "close": c}
        setup = self._trend_setup(ctx, sig, o, h, l, c, prev, avg) or self._range_setup(ctx, sig, o, h, l, c, avg)
        if not setup:
            return []
        mode, side, extra = setup
        if side in self.blocked:
            return []
        if self.pending is not None and self.pending["side"] != side:
            return []                                  # یک ستاپ در هر لحظه
        moved = self.pending is not None
        planned = h if side > 0 else l
        stop_ref = extra.pop("stop_ref")
        min_risk = MIN_RISK * avg
        sl, tp, risk = self._levels(side, stop_ref, planned, min_risk)
        self.pending = {"mode": mode, "side": side, "signal": sig, "pin": sig, "planned_entry": planned,
                        "stop_ref": stop_ref, "min_risk": min_risk,
                        "sl": sl, "tp": tp, "risk": risk, "spread": spread(self.sym), "ctx_key": key,
                        "valid_until": end + pd.Timedelta(minutes=self.signal_tf * ORDER_BARS), **extra}
        if mode == SPIKE:
            self.used_spikes.add(ctx.get("spike_id"))
        return [self._ev("TRADE_PENDING", self.pending, end, c, moved=moved)]

    def _count_pushes(self, ctx, h, l, prev):
        """شمارش H1/H2/H3 (L1/L2/L3) در کانال: هر بار که قیمت از سقف کندل قبل رد شود ولی سقف تازه
        نسازد، یک تلاش شکست‌خورده است؛ با سقف تازه صفر می‌شود."""
        if ctx.get("state") != "CHANNEL":
            self.trend = None
            return
        s = ctx["side"]
        key = (s, ctx.get("start_time"))
        ext = h if s > 0 else l
        back = l if s > 0 else h
        if self.trend is None or self.trend["key"] != key:
            self.trend = {"key": key, "ext": ctx.get("high", ext), "pushes": 0, "in_pb": False, "pb_back": back}
        tr = self.trend
        if (ext - tr["ext"]) * s > 0:                  # سقف تازه
            tr.update(ext=ext, pushes=0, in_pb=False, pb_back=back)
            return
        tr["pb_back"] = min(tr["pb_back"], back) if s > 0 else max(tr["pb_back"], back)   # کف پولبک
        hp = prev["high"] if s > 0 else prev["low"]
        if (ext - hp) * s < 0:                          # کندل پولبک
            tr["in_pb"] = True
        elif (ext - hp) * s > 0 and tr["in_pb"]:        # تلاشی که سقف تازه نساخت
            tr["pushes"] += 1
            tr["in_pb"] = False

    def _trend_setup(self, ctx, sig, o, h, l, c, prev, avg):
        if ctx.get("state") != "CHANNEL" or self.trend is None:
            return None
        s = ctx["side"]
        forming = ctx.get("forming")
        if forming and not ctx.get("pullback"):
            return None                                # اسپایکی که از رنج نبوده یا سطحش از دست رفته
        if forming and ctx.get("spike_id") in self.used_spikes:
            return None
        ext = h if s > 0 else l
        hp = prev["high"] if s > 0 else prev["low"]
        if (ext - hp) * s >= 0 or not signal_bar(s, o, h, l, c):
            return None                                # کندل پولبک با بسته‌شدن قوی
        n_h = self.trend["pushes"] + 1                  # ورود بعدی = H{n}
        need = 1 if forming or ctx.get("kind") == "tight" else 2
        if n_h < need or n_h > MAX_H:
            return None
        start = ctx.get("start_price")
        back = l if s > 0 else h
        if start is not None and abs(self.trend["ext"] - start) > 0:
            depth = (self.trend["ext"] - back) * s / abs(self.trend["ext"] - start)
            if depth > PULLBACK_MAX:
                return None
        swing = self.trend["pb_back"]                   # حد ضرر پشت کف پولبک (Swing stop)
        if forming:
            if (c - ctx["broken"]) * s <= 0:            # کندل سیگنال باید آن طرف سطح شکسته‌شده بسته شود
                return None
            return SPIKE, s, {"level": ctx["broken"], "spike_id": ctx.get("spike_id"), "n_h": n_h,
                              "stop_ref": swing, "stop_note": "pullback " + ("low" if s > 0 else "high")}
        # ناحیه‌ی ارزش: پولبک باید تا نزدیک EMA20 برگشته باشد (فصل ۰۳: «قیمت به خط روند/EMA برمی‌گردد»)
        ema = ctx.get("ema")
        if ema is not None and (back - ema) * s > VALUE_ZONE * avg:
            return None
        # نزدیک خط کانال جای برگشت است، نه ورود در جهت روند
        if ctx.get("pos") is not None and ctx["pos"] >= CHANNEL_EDGE:
            return None
        return TREND, s, {"n_h": n_h, "channel_kind": ctx.get("kind"), "trend_line": ctx.get("trend_line"),
                          "stop_ref": swing, "stop_note": "pullback " + ("low" if s > 0 else "high")}

    def _range_setup(self, ctx, sig, o, h, l, c, avg):
        if ctx.get("state") != "RANGE" or not ctx.get("valid") or ctx.get("tight"):
            return None
        top, bot = ctx["hi"], ctx["lo"]
        height = top - bot
        for s, tests in ((1, ctx.get("bottom_tests") or []), (-1, ctx.get("top_tests") or [])):
            near = l <= bot + EDGE * height if s > 0 else h >= top - EDGE * height
            inside = c >= bot if s > 0 else c <= top
            if not (near and inside and signal_bar(s, o, h, l, c)) or len(tests) < 2:
                continue
            first, cur = tests[-2], tests[-1]
            if (first - cur) * s > SECOND_TEST_SLACK * avg:
                continue                               # تست دوم کف اول را خیلی شکسته: رنج دارد می‌شکند
            dbl = min(first, cur, l) if s > 0 else max(first, cur, h)     # حد ضرر پشت Double Bottom/Top
            return RANGE, s, {"range_high": top, "range_low": bot, "first_test": first, "stop_ref": dbl,
                              "stop_note": "double " + ("bottom" if s > 0 else "top")}
        return None

    # ------------------------------------------------------------ برای اسکنر زنده
    def process(self, d1, d5, ctx):
        """کندل‌های تازه‌ی M1 و M5 به ترتیب زمان. ctx: snapshot چرخه بعد از آخرین کندل M5."""
        out = []
        if self.last1 is None or self.last5 is None:   # اولین اجرا: فقط نقطه‌ی شروع
            if d1 is not None and len(d1):
                self.last1 = d1["date"].iloc[-1]
            if d5 is not None and len(d5):
                self.last5 = d5["date"].iloc[-1]
                for _, r in d5.tail(25).iterrows():
                    self.ranges.append(float(r["high"] - r["low"]))
                    self.prev5 = {"high": float(r["high"]), "low": float(r["low"])}
            return out
        new1 = d1[d1["date"] > self.last1] if d1 is not None else d1
        new5 = d5[d5["date"] > self.last5] if d5 is not None else d5
        closes = [] if new5 is None else [(r["date"] + pd.Timedelta(minutes=self.signal_tf), r)
                                          for _, r in new5.iterrows()]
        rows1 = [] if new1 is None else [r for _, r in new1.iterrows()]
        k = 0
        for t5, r5 in closes:
            while k < len(rows1) and rows1[k]["date"] < t5:
                out += self.on_m1(rows1[k])
                k += 1
            out += self.on_m5_close(r5, ctx)
        while k < len(rows1):
            out += self.on_m1(rows1[k])
            k += 1
        if new1 is not None and len(new1):
            self.last1 = new1["date"].iloc[-1]
        if new5 is not None and len(new5):
            self.last5 = new5["date"].iloc[-1]
        return out
