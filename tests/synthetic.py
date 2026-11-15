"""داده‌ی ساختگی قطعی (با seed ثابت) برای تست‌ها، با همان قالب خروجی data.py."""
import math
import random

import pandas as pd

START = "2026-11-12 00:00"


def candles(n=600, p0=2650.0, vol=0.0012, seed=7, freq="5min"):
    rnd = random.Random(seed)
    idx = pd.date_range(START, periods=n, freq=freq, tz="UTC")
    rows, price = [], p0
    for i in range(n):
        drift = vol * math.sin(i / 25.0) * math.sin(i / 90.0)   # موج‌هایی برای ساختن روند و پولبک
        op = price
        cl = op * (1 + drift + rnd.gauss(0, vol))
        hi = max(op, cl) * (1 + abs(rnd.gauss(0, vol / 2)))
        lo = min(op, cl) * (1 - abs(rnd.gauss(0, vol / 2)))
        rows.append((op, hi, lo, cl))
        price = cl
    return pd.DataFrame(rows, index=idx, columns=["Open", "High", "Low", "Close"])


def to_tf(m1, minutes=5):
    """M1 → تایم‌فریم بالاتر، مثل TradingView (زمان = شروع کندل). کندل ناقص آخر حذف می‌شود."""
    agg = m1.resample(f"{minutes}min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    complete = agg.index + pd.Timedelta(minutes=minutes) <= m1.index[-1] + pd.Timedelta(minutes=1)
    return agg[complete]
