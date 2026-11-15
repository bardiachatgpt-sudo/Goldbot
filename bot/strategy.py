"""تشخیص پرایس اکشن به روش Al Brooks.

منطق از ریپازیتوری price-action-skills-albrooks (scripts/pa_analyzer.py) آمده است:
  - EMA 20 و نوع هر کندل (Trend / Doji / Trading Range)
  - نقاط سوئینگ (Swing High / Swing Low)
  - شمارش پولبک H1/H2 در روند صعودی و L1/L2 در روند نزولی
  - الگوی Wedge (سه فشار): Wedge Bottom و Wedge Top
  - تشخیص فاز بازار از روی ۱۵ کندل آخر نسبت به EMA 20

اضافه‌شده در Goldbot:
  - پین‌بار (Reversal bar) که یک کف یا سقف تازه را رد می‌کند
  - بریک‌اوت از وج: بسته‌شدن بیرون از آخرین پولبک داخل وج
  - بریک‌اوت از تریدینگ رنج: کندل بریک‌اوت قوی (Key bar) که بیرون رنج بسته می‌شود
"""
import numpy as np
import pandas as pd

SWING_WINDOW = 3        # تعداد کندل هر طرف برای تأیید سوئینگ
WEDGE_MAX_BARS = 40     # حداکثر فاصله‌ی فشار اول تا سوم
CYCLE_BARS = 15         # کندل‌های آخر برای تشخیص فاز بازار

AVG_BARS = 20           # میانگین اندازه‌ی کندل‌ها از این تعداد کندل قبلی
PIN_TAIL = 0.6          # پین‌بار: سایه ≥ ۶۰٪ رنج کندل
PIN_LOOKBACK = 10       # پین‌بار باید کف/سقف این تعداد کندل قبلی را بشکند و رد کند
STRONG_BODY = 0.5       # کندل بریک‌اوت قوی: بدنه ≥ ۵۰٪ رنج
STRONG_SIZE = 1.2       # و رنج ≥ ۱.۲ برابر میانگین
STRONG_CLOSE = 0.25     # و بسته‌شدن نزدیک انتها (سایه‌ی سمت بسته‌شدن ≤ ۲۵٪)
RANGE_BARS = 20         # پنجره‌ی تشخیص تریدینگ رنج
RANGE_HEIGHT = 6.0      # ارتفاع رنج ≤ ۶ برابر میانگین اندازه‌ی کندل
WEDGE_BO_BARS = 20      # بریک‌اوت وج باید تا این تعداد کندل بعد از فشار سوم رخ دهد


def wedge_level(df, w):
    """سطح بریک‌اوت وج: بلندترین سقف (Wedge Bottom) یا پایین‌ترین کف (Wedge Top) بین فشار دوم و سوم."""
    b, c = w["points"][1]["index"], w["points"][2]["index"]
    if w["side"] > 0:
        return float(df["high"].values[b:c + 1].max())
    return float(df["low"].values[b:c + 1].min())


def from_tradingview(df):
    """کندل‌های data.py (ستون‌های Open..Close، ایندکس زمان UTC) → قالب تحلیل‌گر."""
    out = df.rename(columns=str.lower)[["open", "high", "low", "close"]].copy()
    out.insert(0, "date", out.index)
    return out.reset_index(drop=True)


class AlBrooksPAAnalyzer:
    def __init__(self, df):
        self.df = df.copy()
        if not self.df.empty:
            self.df = self.df.sort_values("date").reset_index(drop=True)
            self._preprocess()

    def _preprocess(self):
        d = self.df
        d["ema20"] = d["close"].ewm(span=20, adjust=False).mean()
        d["range"] = (d["high"] - d["low"]).replace(0, 0.0001)
        d["body"] = (d["close"] - d["open"]).abs()
        d["body_pct"] = d["body"] / d["range"]
        d["upper_tail"] = d["high"] - d[["open", "close"]].max(axis=1)
        d["lower_tail"] = d[["open", "close"]].min(axis=1) - d["low"]

    def classify_bars(self):
        """Trend bar: بدنه ≥ ۴۵٪ رنج. Doji: بدنه < ۲۵٪. بقیه: Trading Range."""
        d = self.df
        trend = d["body_pct"] >= 0.45
        doji = d["body_pct"] < 0.25
        bull = d["close"] > d["open"]
        d["bar_type"] = np.select(
            [trend & bull, trend & ~bull, doji],
            ["Bull Trend", "Bear Trend", "Doji"], default="Trading Range")

    def find_swing_points(self, window=SWING_WINDOW):
        highs = self.df["high"].values
        lows = self.df["low"].values
        dates = self.df["date"].values
        swing_highs, swing_lows = [], []
        for i in range(window, len(self.df) - window):
            if all(highs[i] >= highs[i - w] for w in range(1, window + 1)) and \
               all(highs[i] >= highs[i + w] for w in range(1, window + 1)):
                swing_highs.append({"index": i, "date": pd.Timestamp(dates[i], tz="UTC"),
                                    "price": float(highs[i])})
            if all(lows[i] <= lows[i - w] for w in range(1, window + 1)) and \
               all(lows[i] <= lows[i + w] for w in range(1, window + 1)):
                swing_lows.append({"index": i, "date": pd.Timestamp(dates[i], tz="UTC"),
                                   "price": float(lows[i])})
        return swing_highs, swing_lows

    def count_pullback_setups(self):
        """شمارش High 1/2 (H1/H2) و Low 1/2 (L1/L2)."""
        close = self.df["close"].values
        high = self.df["high"].values
        low = self.df["low"].values
        ema = self.df["ema20"].values
        n = len(self.df)
        h_signals = [0] * n
        l_signals = [0] * n
        h_count = l_count = 0
        in_bull_pullback = in_bear_pullback = False
        highest_trend_high = -1.0
        lowest_trend_low = 1e18

        for i in range(1, n):
            if close[i] > ema[i]:
                # --- زمینه‌ی صعودی: H1 / H2 ---
                l_count = 0
                in_bear_pullback = False
                lowest_trend_low = 1e18
                if high[i] > highest_trend_high:          # سقف جدید روند → صفر شدن شمارش
                    highest_trend_high = high[i]
                    h_count = 0
                    in_bull_pullback = False
                if high[i] < high[i - 1]:                  # Lower High → شروع پولبک
                    in_bull_pullback = True
                if in_bull_pullback and high[i] > high[i - 1]:
                    h_count += 1
                    h_signals[i] = h_count
                    in_bull_pullback = False
            elif close[i] < ema[i]:
                # --- زمینه‌ی نزولی: L1 / L2 ---
                h_count = 0
                in_bull_pullback = False
                highest_trend_high = -1.0
                if low[i] < lowest_trend_low:
                    lowest_trend_low = low[i]
                    l_count = 0
                    in_bear_pullback = False
                if low[i] > low[i - 1]:                    # Higher Low → شروع پولبک
                    in_bear_pullback = True
                if in_bear_pullback and low[i] < low[i - 1]:
                    l_count += 1
                    l_signals[i] = l_count
                    in_bear_pullback = False
            else:
                h_count = l_count = 0
                in_bull_pullback = in_bear_pullback = False

        self.df["h_setup"] = h_signals
        self.df["l_setup"] = l_signals

    def detect_wedges(self, swing_highs, swing_lows):
        wedges = []
        for i in range(len(swing_lows) - 2):
            a, b, c = swing_lows[i:i + 3]
            if a["price"] > b["price"] > c["price"] and c["index"] - a["index"] < WEDGE_MAX_BARS:
                wedges.append({"type": "Wedge Bottom", "side": 1, "points": [a, b, c],
                               "trigger_index": c["index"], "trigger_date": c["date"]})
        for i in range(len(swing_highs) - 2):
            a, b, c = swing_highs[i:i + 3]
            if a["price"] < b["price"] < c["price"] and c["index"] - a["index"] < WEDGE_MAX_BARS:
                wedges.append({"type": "Wedge Top", "side": -1, "points": [a, b, c],
                               "trigger_index": c["index"], "trigger_date": c["date"]})
        wedges.sort(key=lambda w: w["trigger_index"])
        return wedges

    def detect_pin_bars(self):
        """+1 پین‌بار صعودی (سایه‌ی پایین بلند روی کف تازه)، -1 نزولی (سایه‌ی بالا روی سقف تازه)."""
        d = self.df
        avg = d["range"].rolling(AVG_BARS, min_periods=5).mean().shift(1)
        big_enough = d["range"] >= 0.8 * avg
        new_low = d["low"] <= d["low"].rolling(PIN_LOOKBACK).min().shift(1)
        new_high = d["high"] >= d["high"].rolling(PIN_LOOKBACK).max().shift(1)
        bull_shape = (d["lower_tail"] >= PIN_TAIL * d["range"]) & big_enough
        bear_shape = (d["upper_tail"] >= PIN_TAIL * d["range"]) & big_enough
        d["pin_bar"] = np.where(bull_shape & new_low, 1, np.where(bear_shape & new_high, -1, 0))
        # پین‌بار پولبک (برای ورود بعد از بریک‌اوت): همان شکل، با کفی پایین‌تر از ۳ کندل قبل
        pb_low = d["low"] <= d["low"].rolling(3).min().shift(1)
        pb_high = d["high"] >= d["high"].rolling(3).max().shift(1)
        d["pin_pullback"] = np.where(bull_shape & pb_low, 1, np.where(bear_shape & pb_high, -1, 0))

    def _strong_bars(self):
        """کندل بریک‌اوت قوی (Key bar): بدنه‌ی بزرگ، بزرگ‌تر از معمول، بسته‌شدن نزدیک انتها."""
        d = self.df
        avg = d["range"].rolling(AVG_BARS, min_periods=5).mean().shift(1)
        core = (d["body_pct"] >= STRONG_BODY) & (d["range"] >= STRONG_SIZE * avg)
        bull = core & (d["close"] > d["open"]) & (d["upper_tail"] <= STRONG_CLOSE * d["range"])
        bear = core & (d["close"] < d["open"]) & (d["lower_tail"] <= STRONG_CLOSE * d["range"])
        return bull.values, bear.values, avg.values

    def detect_range_breakouts(self):
        """رنج = RANGE_BARS کندل قبلی با ارتفاع کم که دو طرف EMA20 معامله شده‌اند.
        بریک‌اوت = کندل قوی که بیرون سقف/کف رنج بسته شود."""
        d = self.df
        bull_k, bear_k, avg = self._strong_bars()
        high, low, close = d["high"].values, d["low"].values, d["close"].values
        above = (d["close"] > d["ema20"]).values
        n = len(d)
        sig = np.zeros(n, dtype=int)
        r_hi = np.full(n, np.nan)
        r_lo = np.full(n, np.nan)
        last_bo = {1: -10**9, -1: -10**9}
        for i in range(RANGE_BARS, n):
            if np.isnan(avg[i]):
                continue
            hi = high[i - RANGE_BARS:i].max()
            lo = low[i - RANGE_BARS:i].min()
            frac = above[i - RANGE_BARS:i].mean()
            if hi - lo > RANGE_HEIGHT * avg[i] or not 0.25 <= frac <= 0.75:
                continue
            side = 1 if close[i] > hi and bull_k[i] else -1 if close[i] < lo and bear_k[i] else 0
            if side and i - last_bo[side] > RANGE_BARS:
                sig[i], r_hi[i], r_lo[i] = side, hi, lo
                last_bo[side] = i
        d["range_bo"], d["range_hi"], d["range_lo"] = sig, r_hi, r_lo

    def detect_wedge_breakouts(self, wedges):
        """Wedge Bottom: بسته‌شدن بالای بلندترین سقف بین فشار دوم و سوم (برگشت صعودی).
        Wedge Top: بسته‌شدن زیر پایین‌ترین کف بین فشار دوم و سوم (برگشت نزولی).
        اگر قبل از بریک‌اوت، قیمت از فشار سوم عبور کند وج باطل است."""
        d = self.df
        bull_k, bear_k, _ = self._strong_bars()
        high, low, close = d["high"].values, d["low"].values, d["close"].values
        n = len(d)
        sig = np.zeros(n, dtype=int)
        found = {}
        for w in wedges:
            c = w["points"][2]["index"]
            side = w["side"]
            level = wedge_level(d, w)
            extreme = w["points"][2]["price"]
            for i in range(c + SWING_WINDOW, min(n, c + WEDGE_BO_BARS + 1)):
                if (side > 0 and low[i] < extreme) or (side < 0 and high[i] > extreme):
                    break                                             # وج شکست خورد
                if (side > 0 and close[i] > level) or (side < 0 and close[i] < level):
                    if (i, side) not in found:
                        found[(i, side)] = {"index": i, "side": side, "level": float(level),
                                            "wedge": w, "strong": bool(bull_k[i] if side > 0 else bear_k[i])}
                        sig[i] = side
                    break
        d["wedge_bo"] = sig
        return sorted(found.values(), key=lambda x: x["index"])

    def run_analysis(self):
        if self.df.empty:
            return {"error": "Empty dataframe"}
        self.classify_bars()
        self.count_pullback_setups()
        swing_highs, swing_lows = self.find_swing_points()
        wedges = self.detect_wedges(swing_highs, swing_lows)
        self.detect_pin_bars()
        self.detect_range_breakouts()
        wedge_bos = self.detect_wedge_breakouts(wedges)
        bull_k, bear_k, _ = self._strong_bars()
        self.df["key_bar"] = np.where(bull_k, 1, np.where(bear_k, -1, 0))

        last_idx = len(self.df) - 1
        last = self.df.iloc[last_idx]
        recent = self.df.tail(CYCLE_BARS)
        above = int((recent["close"] > recent["ema20"]).sum())
        if above >= 11:
            cycle = "Bull Channel / Bull Trend"
        elif above <= 4:
            cycle = "Bear Channel / Bear Trend"
        else:
            cycle = "Trading Range"

        active = []
        for offset in range(3):
            idx = last_idx - offset
            if idx < 0:
                continue
            row = self.df.iloc[idx]
            if row["h_setup"] > 0:
                active.append({"date": row["date"], "bar_index": idx, "setup": f"H{row['h_setup']}",
                               "side": 1, "price": float(row["close"])})
            if row["l_setup"] > 0:
                active.append({"date": row["date"], "bar_index": idx, "setup": f"L{row['l_setup']}",
                               "side": -1, "price": float(row["close"])})

        return {
            "market_cycle": cycle,
            "bars_above_ema": above,
            "latest": {"date": last["date"], "open": float(last["open"]), "high": float(last["high"]),
                       "low": float(last["low"]), "close": float(last["close"]),
                       "ema20": float(last["ema20"]), "bar_type": last["bar_type"]},
            "active_setups": active,
            "swing_highs": swing_highs[-10:],
            "swing_lows": swing_lows[-10:],
            "wedges": wedges[-3:],
            "all_wedges": wedges,
            "wedge_breakouts": wedge_bos,
            "trading_range": self.current_range(),
            "df": self.df,
        }


    def current_range(self):
        """اگر الان بازار در تریدینگ رنج باشد: سقف و کف آن (برای گزارش)."""
        d = self.df
        if len(d) < RANGE_BARS + 5:
            return None
        w = d.tail(RANGE_BARS)
        avg = d["range"].iloc[-RANGE_BARS - AVG_BARS:-RANGE_BARS].mean()
        frac = (w["close"] > w["ema20"]).mean()
        hi, lo = float(w["high"].max()), float(w["low"].min())
        if hi - lo <= RANGE_HEIGHT * avg and 0.25 <= frac <= 0.75:
            return {"high": hi, "low": lo}
        return None


def analyze(candles, cycle=True, engine=None):
    """کندل‌های TradingView → نتیجه‌ی تحلیل.

    cycle: چرخه‌ی بازار (رنج/اسپایک/کانال/تست) هم محاسبه شود. engine: موتور چرخه‌ی زنده‌ی اسکنر،
    اگر باشد از همان استفاده می‌شود تا وضعیت گزارش با هشدارها یکی باشد.
    """
    res = AlBrooksPAAnalyzer(from_tradingview(candles)).run_analysis()
    if cycle and "df" in res:
        from .cycle import CycleEngine
        if engine is None or not engine.t or engine.t[-1] != candles.index[-1]:
            engine = CycleEngine()
            engine.feed(candles)
        res["cycle"] = engine
        res["market_cycle"] = engine.label()
    return res


def new_events(sym, res, since):
    """رویدادهای تازه از کندل‌هایی که بعد از `since` بسته شده‌اند.

    ستاپ H/L روی همان کندل تشخیص داده می‌شود. Wedge وقتی تأیید می‌شود که
    SWING_WINDOW کندل بعد از فشار سوم بسته شده باشد، پس زمان تأییدش ملاک است.
    """
    df = res["df"]
    events = []
    new_idx = df.index[df["date"] > since] if since is not None else df.index[-1:]
    for i in new_idx:
        row = df.loc[i]
        for col, side, prefix in (("h_setup", 1, "H"), ("l_setup", -1, "L")):
            if row[col] > 0:
                events.append({"kind": "SETUP", "sym": sym, "setup": f"{prefix}{row[col]}", "side": side,
                               "time": row["date"], "price": float(row["close"]),
                               "cycle": res["market_cycle"], "ema20": float(row["ema20"])})
        base = {"sym": sym, "time": row["date"], "price": float(row["close"]),
                "cycle": res["market_cycle"], "ema20": float(row["ema20"])}
        if row["pin_bar"]:
            events.append({**base, "kind": "PIN", "setup": "PIN", "side": int(row["pin_bar"]),
                           "high": float(row["high"]), "low": float(row["low"])})
        if row["range_bo"]:
            events.append({**base, "kind": "RANGE_BO", "setup": "RANGE_BO", "side": int(row["range_bo"]),
                           "range_high": float(row["range_hi"]), "range_low": float(row["range_lo"])})
    new_set = set(new_idx)
    for bo in res["wedge_breakouts"]:
        if bo["index"] in new_set:
            row = df.loc[bo["index"]]
            events.append({"kind": "WEDGE_BO", "sym": sym, "setup": "WEDGE_BO", "side": bo["side"],
                           "type": bo["wedge"]["type"], "level": bo["level"], "strong": bo["strong"],
                           "points": [p["price"] for p in bo["wedge"]["points"]],
                           "time": row["date"], "price": float(row["close"]),
                           "cycle": res["market_cycle"], "ema20": float(row["ema20"])})
    for w in res["all_wedges"]:
        confirm = w["trigger_index"] + SWING_WINDOW
        if confirm in new_set:
            row = df.loc[confirm]
            events.append({"kind": "WEDGE", "sym": sym, "setup": "WEDGE", "type": w["type"],
                           "side": w["side"], "time": row["date"], "price": float(row["close"]),
                           "points": [p["price"] for p in w["points"]], "cycle": res["market_cycle"],
                           "ema20": float(row["ema20"])})
    return events


def breakout_levels(res):
    """سطح‌هایی که الان روی تایم‌فریم زمینه (M5) ارزش زیر نظر گرفتن دارند.

    - رنج فعلی: سقف (بریک‌اوت صعودی) و کف (بریک‌اوت نزولی)
    - وج‌های تأییدشده‌ای که هنوز نه باطل شده‌اند و نه از آن‌ها بریک‌اوت شده
    """
    if "df" not in res:
        return []
    df = res["df"]
    n = len(df)
    levels = []
    tr = res.get("trading_range")
    if tr:
        for side, lvl in ((1, tr["high"]), (-1, tr["low"])):
            levels.append({"key": ("RANGE", side), "kind": "RANGE", "side": side, "level": lvl,
                           "range_high": tr["high"], "range_low": tr["low"]})
    seen = set()
    for w in reversed(res["all_wedges"]):
        c, side = w["trigger_index"], w["side"]
        if c + SWING_WINDOW > n - 1 or n - 1 - c > WEDGE_BO_BARS:
            continue
        level, extreme = wedge_level(df, w), w["points"][2]["price"]
        after = df.iloc[c + 1:]
        if side > 0 and ((after["low"] < extreme).any() or (after["close"] > level).any()):
            continue
        if side < 0 and ((after["high"] > extreme).any() or (after["close"] < level).any()):
            continue
        if (side, round(level, 10)) in seen:
            continue
        seen.add((side, round(level, 10)))
        levels.append({"key": ("WEDGE", w["trigger_date"], side), "kind": "WEDGE", "side": side,
                       "level": level, "extreme": extreme, "type": w["type"],
                       "points": [p["price"] for p in w["points"]]})
    return levels
