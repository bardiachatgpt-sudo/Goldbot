"""چرخه‌ی بازار ال بروکس روی M5: رنج ← اسپایک ← کانال ← کانال در حال تست ← ...

نمودار مثل خود ال بروکس از چپ به راست خوانده می‌شود (فقط با گذشته؛ نتیجه‌ی هر لحظه بعداً عوض نمی‌شود).
همه‌ی اندازه‌ها نسبت به میانگین اندازه‌ی ۲۰ کندل قبلی همان نماد سنجیده می‌شوند.

📦 RANGE    حالت پیش‌فرض و هر جای مبهم («اگر شک داری، رنج است»).
            خروج: اسپایک که بیرون سقف/کف رنج بسته شود.
🚀 SPIKE    یک کندل خیلی بزرگ (≥ ۲ برابر میانگین) یا دو Trend bar قوی پشت‌سرهم که هر کدام فراتر از
            کندل قبلی بسته می‌شوند، بیرون محدوده‌ی ۱۰ کندل اخیر. ادامه تا وقتی هر کندل سقف تازه بسازد
            و قوی بسته شود. اولین پولبک ← کانال.
📈 CHANNEL  شروع کانال = کف اولین پولبک بعد از اسپایک (تا وقتی سقف اسپایک رد شود به‌روز می‌شود).
            خط روند اصلی: از شروع کانال، طوری که همه‌ی کندل‌ها بالای آن بمانند.
            خط کانال: موازی خط روند، از روی بلندترین سقف.
            تنگ: هیچ بسته‌شدنی آن طرف EMA نبوده و پولبک‌ها حداکثر ۳ کندل. وگرنه باز.
            بسته‌شدن زیر خط روند اصلی ← کانال در حال تست.
⚠️ TEST     شکستن خط روند به‌تنهایی پایان کانال نیست؛ تست سقف تصمیم می‌گیرد:
              - بسته‌شدن بالای سقف و کندل بعدی زیر سقف برنگردد ← کانال ادامه دارد (بازتر)
              - رد شدن از سقف فقط با سایه، یا بسته‌شدن بالای سقف و برگشت فوری ← رنج (Double Top)
              - سوئینگ‌های پایین‌تر از سقف (بعد از برگشت حداقل نصف راه) ← رنج (Lower High / Double Top)
              - ۲۰ کندل بدون سقف تازه ← رنج
            اگر بعداً در رنج، کف شکست هم شکسته شود ← «احتمال برگشت».
اسپایک قوی مخالف در هر حالتی ← اسپایک مخالف.
"""
RANGE, SPIKE, CHANNEL, TEST = "RANGE", "SPIKE", "CHANNEL", "TEST"

AVG_N = 20              # میانگین اندازه‌ی کندل از این تعداد کندل قبلی
SPIKE_BIG = 2.0         # کندل اسپایک تکی: ≥ ۲ برابر میانگین
SPIKE_PAIR = 2.0        # دو کندل اسپایک: مجموع اندازه ≥ ۲ برابر میانگین
BREAKOUT_N = 10         # اسپایک باید بیرون محدوده‌ی این تعداد کندل قبلی بسته شود
TEST_BARS = 20          # کانال در حال تست: بیشتر از این بدون سقف تازه ← رنج
FORMING_BARS = 20       # اولین پولبک بعد از اسپایک: بیشتر از این بدون سقف تازه ← رنج
DOUBLE_TOP = 0.5        # سقف دوم تا نصف میانگین اندازه‌ی کندل نزدیک سقف اول ← Double Top
SWING_N = 3             # تأیید سوئینگ تست: ۳ کندل هر طرف
TIGHT_PULLBACK = 3      # کانال تنگ: پولبک‌ها حداکثر ۳ کندل
RANGE_LOOKBACK = 60     # سقف و کف رنج از حداکثر ۶۰ کندل اخیر آن

NAMES = {RANGE: "TRADING RANGE", SPIKE: "SPIKE", CHANNEL: "CHANNEL", TEST: "CHANNEL UNDER TEST"}


def describe_state(state, side, sub=None):
    if state == RANGE:
        return "Trading Range"
    d = "Bull" if side > 0 else "Bear"
    if state == SPIKE:
        return f"{d} Spike"
    if state == CHANNEL:
        return f"{d} Channel" + (f" ({sub})" if sub else "")
    return f"{d} Channel · under test"


class CycleEngine:
    def __init__(self, sym=""):
        self.sym = sym
        self.t, self.o, self.h, self.l, self.c, self.ema, self.avg = [], [], [], [], [], [], []
        self.state, self.side, self.since = RANGE, 0, 0
        self.info = {"hi": None, "lo": None, "magnet": None, "watch": None, "reversal": False}
        self.segments = [{"state": RANGE, "side": 0, "start": 0, "end": None}]
        self.last_channel_start = None

    # ------------------------------------------------------------ داده
    @property
    def n(self):
        return len(self.c)

    def feed(self, df):
        """کندل‌های data.py (ستون‌های Open..Close، ایندکس زمان). رویدادهای تغییر حالت را برمی‌گرداند."""
        events = []
        last = self.t[-1] if self.t else None
        for ts, r in df.iterrows():
            if last is None or ts > last:
                events += self.on_bar(ts, r["Open"], r["High"], r["Low"], r["Close"])
        return events

    def on_bar(self, t, o, h, l, c):
        i = self.n
        rng_prev = [self.h[j] - self.l[j] for j in range(max(0, i - AVG_N), i)]
        self.avg.append(sum(rng_prev) / len(rng_prev) if len(rng_prev) >= 5 else None)
        self.ema.append(c if i == 0 else self.ema[-1] + (c - self.ema[-1]) * 2 / 21)
        self.t.append(t), self.o.append(o), self.h.append(h), self.l.append(l), self.c.append(c)
        if self.avg[i] is None or self.avg[i] <= 0:
            self._range_update(i)
            return []
        before = (self.state, self.side)
        step = {RANGE: self._on_range, SPIKE: self._on_spike,
                CHANNEL: self._on_channel, TEST: self._on_test}[self.state]
        note = step(i)
        if (self.state, self.side) != before or note:
            return [self._event(i, before, note)]
        return []

    # ------------------------------------------------------------ ابزار کندل
    def _rng(self, i):
        return max(self.h[i] - self.l[i], 1e-12)

    def _trend_bar(self, i, s):
        """Trend bar قوی در جهت s: بدنه ≥ ۵۰٪ و بسته‌شدن در ربع انتهایی."""
        r = self._rng(i)
        body = abs(self.c[i] - self.o[i]) / r
        cp = (self.c[i] - self.l[i]) / r
        if s > 0:
            return self.c[i] > self.o[i] and body >= 0.5 and cp >= 0.75
        return self.c[i] < self.o[i] and body >= 0.5 and cp <= 0.25

    def _beyond(self, s, price, level):
        return price > level if s > 0 else price < level

    def _ext(self, s, i):
        """انتهای کندل در جهت s (سقف برای صعودی، کف برای نزولی)."""
        return self.h[i] if s > 0 else self.l[i]

    def _back(self, s, i):
        return self.l[i] if s > 0 else self.h[i]

    def _spike_start(self, i, s):
        """شروع اسپایک در جهت s روی کندل i؛ اندیس اولین کندل اسپایک یا None."""
        if i < BREAKOUT_N + 1:
            return None
        avg = self.avg[i]

        def outside(k):     # بسته‌شدن کندل i بیرون محدوده‌ی BREAKOUT_N کندل قبل از کندل k
            ref = (max if s > 0 else min)((self.h if s > 0 else self.l)[k - BREAKOUT_N:k])
            return self._beyond(s, self.c[i], ref)

        if self._trend_bar(i, s) and self._rng(i) >= SPIKE_BIG * avg and outside(i):
            return i
        j = i - 1
        if (self._trend_bar(j, s) and self._trend_bar(i, s)
                and self._beyond(s, self.c[j], self._ext(s, j - 1))
                and self._beyond(s, self.c[i], self._ext(s, j))
                and self._rng(j) + self._rng(i) >= SPIKE_PAIR * avg
                and self._beyond(s, self._back(s, i), (self.h[j] + self.l[j]) / 2)   # همپوشانی < ۵۰٪
                and outside(j)):
            return j
        return None

    def _opposite_spike(self, i):
        return self._spike_start(i, -self.side) if self.side else None

    # ------------------------------------------------------------ تغییر حالت
    def _set(self, i, state, side, info):
        self.segments[-1]["end"] = i - 1
        self.segments.append({"state": state, "side": side, "start": i, "end": None})
        self.state, self.side, self.since, self.info = state, side, i, info

    def _to_spike(self, i, s, first):
        self.segments[-1]["end"] = first - 1
        self.segments.append({"state": SPIKE, "side": s, "start": first, "end": None})
        self.state, self.side, self.since = SPIKE, s, first
        self.info = {"start_price": self._back(s, first), "start_i": first,
                     "extreme": self._ext(s, i), "extreme_i": i}

    def _to_range(self, i, hi=None, lo=None, watch=None, why=""):
        prev_side = self.side
        self._set(i, RANGE, 0, {"hi": hi, "lo": lo, "magnet": self.last_channel_start,
                                "watch": watch, "reversal": False, "why": why, "from_side": prev_side})
        self._range_update(i)

    def _range_update(self, i):
        inf = self.info
        start = max(self.since, i - RANGE_LOOKBACK + 1)
        hi, lo = max(self.h[start:i + 1]), min(self.l[start:i + 1])
        if i - self.since < RANGE_LOOKBACK and inf.get("hi") is not None:
            hi, lo = max(hi, inf["hi"]), min(lo, inf["lo"])
        inf["hi"], inf["lo"] = hi, lo

    # ------------------------------------------------------------ RANGE
    def _on_range(self, i):
        inf = self.info
        hi, lo = inf["hi"], inf["lo"]
        for s in (1, -1):
            first = self._spike_start(i, s)
            if first is not None and (hi is None or self._beyond(s, self.c[i], hi if s > 0 else lo)):
                self._to_spike(i, s, first)
                return None
        self._range_update(i)
        w = inf.get("watch")
        if w and not inf["reversal"] and self._beyond(-w["side"], self.c[i], w["level"]):
            inf["reversal"] = True
            return "reversal"
        return None

    # ------------------------------------------------------------ SPIKE
    def _on_spike(self, i):
        s = self.side
        first = self._opposite_spike(i)
        if first is not None:
            self._to_spike(i, -s, first)
            return None
        cp = (self.c[i] - self.l[i]) / self._rng(i)
        strong_close = cp >= 0.5 if s > 0 else cp <= 0.5
        if self._beyond(s, self._ext(s, i), self.info["extreme"]) and strong_close and \
                self._beyond(s, self.c[i], self.o[i]):
            self.info["extreme"], self.info["extreme_i"] = self._ext(s, i), i
            return None
        # اولین پولبک ← کانال (در حال شکل‌گیری تا وقتی سقف اسپایک رد شود)
        sp = self.info
        self._set(i, CHANNEL, s, {"spike_start": sp["start_price"], "spike_i": sp["start_i"],
                                  "spike_ext": sp["extreme"], "high": sp["extreme"], "high_i": sp["extreme_i"],
                                  "anchor_i": i, "anchor": self._back(s, i), "forming": True,
                                  "wrong_ema": 0, "pb_run": 0, "pb_max": 0})
        return None

    # ------------------------------------------------------------ CHANNEL
    def line_at(self, k, inf=None):
        """قیمت خط روند اصلی روی کندل k."""
        inf = inf or self.info
        return inf["anchor"] + inf.get("slope", 0.0) * (k - inf["anchor_i"])

    def _fit_line(self, i):
        """خط روند اصلی: از شروع کانال، با کمترین شیب (صعودی) که همه‌ی کندل‌های تا i-1 بالای آن بمانند."""
        inf, s = self.info, self.side
        # اگر کندلی بعد از شروع کانال از آن فراتر رفته، شروع واقعی کانال همان نقطه‌ی فراتر است
        a = inf["anchor_i"]
        for j in range(a + 1, i):
            if self._beyond(-s, self._back(s, j), inf["anchor"]):
                inf["anchor"], inf["anchor_i"] = self._back(s, j), j
        if self.last_channel_start and self.last_channel_start.get("i") == a:
            self.last_channel_start.update(price=inf["anchor"], time=self.t[inf["anchor_i"]], i=inf["anchor_i"])
        a, pa = inf["anchor_i"], inf["anchor"]
        best = None
        if not self._second_point(a, i):            # خط روند دو نقطه لازم دارد؛ تا آن موقع افقی
            inf["slope"] = 0.0
            inf["offset"] = max(self._ext(s, j) - pa for j in range(a, i + 1)) if s > 0 else \
                min(self._ext(s, j) - pa for j in range(a, i + 1))
            return
        for j in range(a + 1, i):
            slope = (self._back(s, j) - pa) / (j - a)
            if best is None or (slope < best if s > 0 else slope > best):
                best = slope
        inf["slope"] = 0.0 if best is None else best
        off = None                                   # خط کانال: موازی، از روی بلندترین فاصله
        for j in range(a, i + 1):
            d = self._ext(s, j) - (pa + inf["slope"] * (j - a))
            if off is None or (d > off if s > 0 else d < off):
                off = d
        inf["offset"] = off

    def _second_point(self, a, i):
        """کف پولبک تأییدشده (سوئینگ) بعد از شروع کانال: نقطه‌ی دوم خط روند."""
        s = self.side
        arr = self.l if s > 0 else self.h
        pick = min if s > 0 else max
        for j in range(a + SWING_N, i - SWING_N + 1):
            if arr[j] == pick(arr[j - SWING_N:j + SWING_N + 1]):
                return True
        return False

    def _on_channel(self, i):
        s, inf = self.side, self.info
        first = self._opposite_spike(i)
        if first is not None and self._beyond(-s, self.c[i], self.ema[i]):
            self._to_spike(i, -s, first)
            return None

        # کانال تنگ یا باز (از اولین پولبک به بعد)
        if self._beyond(-s, self.c[i], self.ema[i]):
            inf["wrong_ema"] += 1
        if not self._beyond(s, self._ext(s, i), self._ext(s, i - 1)):
            inf["pb_run"] += 1
            inf["pb_max"] = max(inf["pb_max"], inf["pb_run"])
        else:
            inf["pb_run"] = 0

        if inf["forming"]:
            if self._beyond(-s, self._back(s, i), inf["anchor"]):
                inf["anchor"], inf["anchor_i"] = self._back(s, i), i
            if self._beyond(-s, self.c[i], inf["spike_start"]):
                self._to_range(i, *self._hilo(inf["spike_i"], i), why="spike_erased")
                return None
            if self._beyond(s, self._ext(s, i), inf["high"]):
                inf["forming"] = False
                self.last_channel_start = {"price": inf["anchor"], "time": self.t[inf["anchor_i"]],
                                           "side": s, "i": inf["anchor_i"]}
            elif i - self.since >= FORMING_BARS:
                self._to_range(i, *self._hilo(inf["spike_i"], i), why="no_new_extreme")
                return None
            else:
                self._track_high(i)
                return None

        self._fit_line(i)
        self._track_high(i)
        if self._beyond(-s, self.c[i], self.line_at(i)):
            strong = self._beyond(-s, self.c[i], self.ema[i]) or (
                self._trend_bar(i, -s) and self._rng(i) >= 1.2 * self.avg[i])
            chan = dict(inf)
            self._set(i, TEST, s, {"channel": chan, "high": inf["high"], "break_i": i,
                                   "break_line": self.line_at(i, chan), "low": self._back(s, i),
                                   "strong": strong, "pending": False})
        return None

    def tightness(self, inf=None):
        inf = inf or self.info
        return "tight" if inf.get("wrong_ema", 0) == 0 and inf.get("pb_max", 0) <= TIGHT_PULLBACK else "broad"

    def _track_high(self, i):
        inf, s = self.info, self.side
        if self._beyond(s, self._ext(s, i), inf["high"]):
            inf["high"], inf["high_i"] = self._ext(s, i), i

    def _hilo(self, a, i):
        return max(self.h[a:i + 1]), min(self.l[a:i + 1])

    # ------------------------------------------------------------ TEST
    def _on_test(self, i):
        s, inf = self.side, self.info
        H, b = inf["high"], inf["break_i"]
        first = self._opposite_spike(i)
        if first is not None:
            self._to_spike(i, -s, first)
            return None

        def to_range(why):
            lo_hi = (H, inf["low"]) if s > 0 else (inf["low"], H)
            hi, lo = max(lo_hi), min(lo_hi)
            self._to_range(i, hi, lo, watch={"side": s, "level": inf["low"]}, why=why)

        if inf["pending"]:                     # کندل قبلی بالای سقف بسته شد
            if self._beyond(s, self.c[i], H) or self.c[i] == H:
                chan = inf["channel"]
                chan["high"], chan["high_i"] = self._ext(s, i), i
                self.segments[-1]["end"] = i - 1
                self.segments.append({"state": CHANNEL, "side": s, "start": i, "end": None})
                self.state, self.since, self.info = CHANNEL, i, chan
                self._fit_line(i)
                return "resumed"
            to_range("hh_double_top")
            return None
        if self._beyond(s, self.c[i], H):
            inf["pending"] = True
            return None
        poke = inf.get("poke")
        if poke is not None and self._beyond(-s, self.c[i], self._back(s, poke)):
            to_range("hh_double_top")          # برگشت بعد از رد شدن با سایه
            return None
        if self._beyond(s, self._ext(s, i), H):
            cp = (self.c[i] - self.l[i]) / self._rng(i)
            if cp < 0.5 if s > 0 else cp > 0.5:          # کندل برگشتی: ضعیف بسته شد
                to_range("hh_double_top")
                return None
            inf["poke"] = i

        if self._beyond(-s, self._back(s, i), inf["low"]):
            inf["low"] = self._back(s, i)

        j = i - SWING_N                         # سوئینگ تست تأییدشده بعد از شکست
        if j > b:
            win = (self.h if s > 0 else self.l)[j - SWING_N:i + 1]
            top = self._ext(s, j)
            if top == (max(win) if s > 0 else min(win)):
                low_j = (min if s > 0 else max)((self.l if s > 0 else self.h)[b:j + 1])
                if abs(top - low_j) >= 0.5 * abs(H - low_j):
                    to_range("double_top" if abs(H - top) <= DOUBLE_TOP * self.avg[i] else "lower_high")
                    return None

        if i - b >= TEST_BARS:
            to_range("test_timeout")
        return None

    # ------------------------------------------------------------ گزارش
    def _event(self, i, before, note):
        return {"kind": "CYCLE", "sym": self.sym, "time": self.t[i], "price": self.c[i],
                "from": before, "to": (self.state, self.side), "note": note, "snap": self.snapshot()}

    def label(self):
        sub = self.tightness() if self.state == CHANNEL and not self.info.get("forming") else None
        return describe_state(self.state, self.side, sub)

    def snapshot(self):
        """وضعیت فعلی با سطح‌هایش (برای پیام و نمودار)."""
        i = self.n - 1
        if i < 0:
            return {"state": RANGE, "side": 0, "label": "Trading Range"}
        s, inf = self.side, self.info
        snap = {"state": self.state, "side": s, "label": self.label(), "price": self.c[i],
                "time": self.t[i], "bars": i - self.since + 1, "since": self.t[self.since],
                "avg": self.avg[i]}
        if self.state == RANGE:
            hi, lo = inf["hi"], inf["lo"]
            pos = (self.c[i] - lo) / (hi - lo) if hi and hi > lo else 0.5
            snap.update(hi=hi, lo=lo, mid=(hi + lo) / 2 if hi else None, pos=pos,
                        magnet=inf.get("magnet"), why=inf.get("why", ""), from_side=inf.get("from_side", 0),
                        reversal=inf.get("reversal"), watch=inf.get("watch"))
        elif self.state == SPIKE:
            size = abs(inf["extreme"] - inf["start_price"]) / self.avg[i]
            snap.update(start_price=inf["start_price"], extreme=inf["extreme"], size=size)
        elif self.state == CHANNEL:
            snap["bars"] = i - inf["anchor_i"] + 1          # از شروع کانال (بعد از ادامه هم)
            snap.update(spike_start=inf["spike_start"], start_price=inf["anchor"],
                        start_time=self.t[inf["anchor_i"]], high=inf["high"], forming=inf["forming"])
            if not inf["forming"] and "slope" in inf:
                tl = self.line_at(i)
                cl = tl + inf["offset"]
                snap.update(trend_line=tl, channel_line=cl, slope=inf["slope"], kind=self.tightness(),
                            pos=(self.c[i] - tl) / (cl - tl) if cl != tl else 0.5,
                            anchor_i=inf["anchor_i"], offset=inf["offset"])
        else:
            chan = inf["channel"]
            snap.update(high=inf["high"], break_low=inf["low"], strong=inf["strong"],
                        bars_left=TEST_BARS - (i - inf["break_i"]), start_price=chan["anchor"],
                        trend_line=self.line_at(i, chan), slope=chan.get("slope", 0.0),
                        anchor_i=chan["anchor_i"], offset=chan.get("offset", 0.0))
        return snap
