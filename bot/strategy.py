"""تشخیص پرایس اکشن به روش Al Brooks.

منطق از ریپازیتوری price-action-skills-albrooks (scripts/pa_analyzer.py) آمده است:
  - EMA 20 و نوع هر کندل (Trend / Doji / Trading Range)
  - نقاط سوئینگ (Swing High / Swing Low)
  - شمارش پولبک H1/H2 در روند صعودی و L1/L2 در روند نزولی
  - الگوی Wedge (سه فشار): Wedge Bottom و Wedge Top
  - تشخیص فاز بازار از روی ۱۵ کندل آخر نسبت به EMA 20
"""
import numpy as np
import pandas as pd

SWING_WINDOW = 3        # تعداد کندل هر طرف برای تأیید سوئینگ
WEDGE_MAX_BARS = 40     # حداکثر فاصله‌ی فشار اول تا سوم
CYCLE_BARS = 15         # کندل‌های آخر برای تشخیص فاز بازار


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

    def run_analysis(self):
        if self.df.empty:
            return {"error": "Empty dataframe"}
        self.classify_bars()
        self.count_pullback_setups()
        swing_highs, swing_lows = self.find_swing_points()
        wedges = self.detect_wedges(swing_highs, swing_lows)

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
            "df": self.df,
        }


def analyze(candles):
    """کندل‌های TradingView → نتیجه‌ی تحلیل."""
    return AlBrooksPAAnalyzer(from_tradingview(candles)).run_analysis()


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
    new_set = set(new_idx)
    for w in res["all_wedges"]:
        confirm = w["trigger_index"] + SWING_WINDOW
        if confirm in new_set:
            row = df.loc[confirm]
            events.append({"kind": "WEDGE", "sym": sym, "setup": "WEDGE", "type": w["type"],
                           "side": w["side"], "time": row["date"], "price": float(row["close"]),
                           "points": [p["price"] for p in w["points"]], "cycle": res["market_cycle"],
                           "ema20": float(row["ema20"])})
    return events
