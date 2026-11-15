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

روند بدون اسپایک (Always In): از رنج، اگر سقف و کف بالاتر/پایین‌تر، شیب EMA20 و ۱۵ از ۲۰ کندل آخر یک
طرف EMA باشد ← کانال (جزوه فصل ۰۲). رنج «واقعی» فقط با EMA صاف، عبور از دو طرف EMA و ارتفاع بیشتر از
Barbwire (فصل ۰۶). snapshot تست‌های کف و سقف رنج را هم برمی‌گرداند (ورود دوم، فصل ۰۴ و ۰۵).

اسپایکی که از رنج بیرون می‌زند سطح شکسته‌شده را به خاطر می‌سپارد. اولین پولبک بعدش تا وقتی آن طرف این
سطح بسته نشده «پولبک معتبر» است (snapshot["pullback"]) و ستاپ ورود اسپایک فقط در همین پنجره فعال است.
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

# روند بدون اسپایک (Always In) — ال بروکس / جزوه فصل ۰۲: سه سؤال زمینه
TREND_N = 20            # از ۲۰ کندل اخیر ...
TREND_FRAC = 0.75       # ... حداقل ۷۵٪ (۱۵ کندل) یک طرف EMA20 بسته شده باشند
EMA_SLOPE_N = 10        # شیب EMA در ۱۰ کندل ...
EMA_SLOPE_MIN = 1.0     # ... حداقل یک کندل متوسط
STRUCT_N = 40           # سقف و کف پایین‌تر (یا بالاتر) در ۴۰ کندل اخیر

# رنج واقعی — جزوه فصل ۰۶
RANGE_MIN_BARS = 10     # رنج باید حداقل ۱۰ کندل عمر داشته باشد
FLAT_N = 20             # EMA در ۲۰ کندل ...
FLAT_MAX = 1.5          # ... حداکثر ۱.۵ کندل متوسط جابه‌جا شده باشد (تقریباً صاف)
CROSS_N = 30            # در ۳۰ کندل اخیر ...
CROSS_MIN = 2           # ... حداقل ۲ بار بسته‌شدن از این طرف EMA به آن طرف
BARBWIRE = 3.0          # ارتفاع رنج ≤ ۳ کندل متوسط = رنج تنگ (Barbwire): معامله نکن
EDGE = 0.25             # لبه‌ی رنج = ربع پایینی/بالایی

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

    def _to_spike(self, i, s, first, broken=None):
        """broken: سطح رنجی که اسپایک شکست (سقف برای صعودی، کف برای نزولی)؛ فقط برای اسپایک از رنج."""
        self.segments[-1]["end"] = first - 1
        self.segments.append({"state": SPIKE, "side": s, "start": first, "end": None})
        self.state, self.side, self.since = SPIKE, s, first
        self.info = {"start_price": self._back(s, first), "start_i": first,
                     "extreme": self._ext(s, i), "extreme_i": i, "broken": broken,
                     "spike_id": self.t[first]}

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
                self._to_spike(i, s, first, broken=(hi if s > 0 else lo) if hi is not None else None)
                return None
        side = self._always_in(i)                    # روند بدون اسپایک
        if side:
            self._to_trend_channel(i, side)
            return None
        self._range_update(i)
        w = inf.get("watch")
        if w and not inf["reversal"] and self._beyond(-w["side"], self.c[i], w["level"]):
            inf["reversal"] = True
            return "reversal"
        return None

    # ------------------------------------------------------------ Always In
    def _swings(self, a, i, w=2):
        """سوئینگ‌های تأییدشده بین a و i (هر طرف w کندل)."""
        hs, ls = [], []
        for j in range(max(a, w), i - w + 1):
            if self.h[j] == max(self.h[j - w:j + w + 1]):
                hs.append((j, self.h[j]))
            if self.l[j] == min(self.l[j - w:j + w + 1]):
                ls.append((j, self.l[j]))
        return hs, ls

    def _always_in(self, i):
        """+1/-1 اگر بازار بدون اسپایک هم آشکارا در روند است، وگرنه 0.

        ال بروکس (Always In) و جزوه فصل ۰۲: (۱) سقف و کف بالاتر/پایین‌تر، (۲) شیب EMA20 و
        سمت قیمت، (۳) کندل‌های ۲۰ تای اخیر در هم نرفته‌اند. هر سه باید برقرار باشند.
        """
        if i < STRUCT_N or self.avg[i] is None:
            return 0
        closes = self.c[i - TREND_N + 1:i + 1]
        emas = self.ema[i - TREND_N + 1:i + 1]
        above = sum(c > e for c, e in zip(closes, emas)) / TREND_N
        slope = self.ema[i] - self.ema[i - EMA_SLOPE_N]
        hs, ls = self._swings(i - STRUCT_N, i)
        if len(hs) < 2 or len(ls) < 2:
            return 0
        for side in (1, -1):
            frac = above if side > 0 else 1 - above
            if frac < TREND_FRAC or slope * side < EMA_SLOPE_MIN * self.avg[i]:
                continue
            (_, h1), (_, h2) = hs[-2], hs[-1]
            (_, l1), (_, l2) = ls[-2], ls[-1]
            if (h2 - h1) * side > 0 and (l2 - l1) * side > 0:
                return side
        return 0

    def _to_trend_channel(self, i, s):
        """رنج ← کانال بدون اسپایک. شروع کانال = دورترین نقطه‌ی مخالف در ۴۰ کندل اخیر."""
        a0 = i - STRUCT_N
        arr = self.l if s > 0 else self.h
        pick = min if s > 0 else max
        anchor = pick(arr[a0:i + 1])
        anchor_i = max(j for j in range(a0, i + 1) if arr[j] == anchor)
        ext_arr = self.h if s > 0 else self.l
        ext = (max if s > 0 else min)(ext_arr[anchor_i:i + 1])
        ext_i = max(j for j in range(anchor_i, i + 1) if ext_arr[j] == ext)
        self._set(i, CHANNEL, s, {"spike_start": anchor, "spike_i": anchor_i, "spike_ext": ext,
                                  "high": ext, "high_i": ext_i, "anchor_i": anchor_i, "anchor": anchor,
                                  "forming": False, "wrong_ema": 0, "pb_run": 0, "pb_max": 0,
                                  "broken": None, "spike_id": None, "level_lost": False, "via": "always_in"})
        self.last_channel_start = {"price": anchor, "time": self.t[anchor_i], "side": s, "i": anchor_i}
        self._fit_line(i)

    # ------------------------------------------------------------ رنج واقعی
    def _range_quality(self, i):
        """(واقعی؟، Barbwire؟، تست‌های کف، تست‌های سقف) — جزوه فصل ۰۶ و ۰۵."""
        inf = self.info
        hi, lo, avg = inf.get("hi"), inf.get("lo"), self.avg[i]
        if hi is None or avg is None or hi <= lo:
            return False, False, [], []
        height = hi - lo
        tight = height <= BARBWIRE * avg
        flat = i >= FLAT_N and abs(self.ema[i] - self.ema[i - FLAT_N]) <= FLAT_MAX * avg
        a = max(1, i - CROSS_N + 1)
        sides = [self.c[j] > self.ema[j] for j in range(a - 1, i + 1)]
        crosses = sum(x != y for x, y in zip(sides, sides[1:]))
        old_enough = i - self.since + 1 >= RANGE_MIN_BARS
        valid = old_enough and flat and crosses >= CROSS_MIN and not tight
        start = max(self.since, i - RANGE_LOOKBACK + 1)
        bottom, top = [], []
        for zone_hit, out, pick in ((lambda j: self.l[j] <= lo + EDGE * height, bottom, self.l),
                                    (lambda j: self.h[j] >= hi - EDGE * height, top, self.h)):
            prev = False
            for j in range(start, i + 1):
                hit = zone_hit(j)
                if hit and not prev:
                    out.append(pick[j])
                elif hit and prev:
                    out[-1] = min(out[-1], pick[j]) if pick is self.l else max(out[-1], pick[j])
                prev = hit
        return valid, tight, bottom, top

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
                                  "wrong_ema": 0, "pb_run": 0, "pb_max": 0,
                                  "broken": sp["broken"], "spike_id": sp["spike_id"], "level_lost": False})
        self._check_level(i)
        return None

    # ------------------------------------------------------------ CHANNEL
    def _check_level(self, i):
        """پولبک بعد از اسپایک: بسته‌شدن آن طرف سطح شکسته‌شده‌ی رنج = بریک‌اوت شکست خورد (بدون معامله)."""
        inf = self.info
        if inf.get("broken") is not None and self._beyond(-self.side, self.c[i], inf["broken"]):
            inf["level_lost"] = True

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
            self._check_level(i)
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
                "avg": self.avg[i], "ema": self.ema[i]}
        if self.state == RANGE:
            hi, lo = inf["hi"], inf["lo"]
            pos = (self.c[i] - lo) / (hi - lo) if hi and hi > lo else 0.5
            valid, tight, bottom, top = self._range_quality(i)
            snap.update(hi=hi, lo=lo, mid=(hi + lo) / 2 if hi else None, pos=pos,
                        magnet=inf.get("magnet"), why=inf.get("why", ""), from_side=inf.get("from_side", 0),
                        reversal=inf.get("reversal"), watch=inf.get("watch"),
                        valid=valid, tight=tight, bottom_tests=bottom, top_tests=top)
        elif self.state == SPIKE:
            size = abs(inf["extreme"] - inf["start_price"]) / self.avg[i]
            snap.update(start_price=inf["start_price"], extreme=inf["extreme"], size=size,
                        broken=inf.get("broken"), spike_id=inf.get("spike_id"))
        elif self.state == CHANNEL:
            snap["bars"] = i - inf["anchor_i"] + 1          # از شروع کانال (بعد از ادامه هم)
            snap.update(spike_start=inf["spike_start"], start_price=inf["anchor"],
                        start_time=self.t[inf["anchor_i"]], high=inf["high"], forming=inf["forming"],
                        via=inf.get("via", "spike"),
                        broken=inf.get("broken"), spike_id=inf.get("spike_id"),
                        level_lost=inf.get("level_lost", False),
                        # اولین پولبک بعد از اسپایکی که از رنج بیرون زده و سطح شکسته‌شده هنوز حفظ شده
                        pullback=bool(inf["forming"] and inf.get("broken") is not None
                                      and not inf.get("level_lost")))
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
