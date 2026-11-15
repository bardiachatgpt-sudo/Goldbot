"""حلقه‌ی اسکن زنده: بعد از بسته شدن هر کندل، تحلیل را تکرار و ستاپ‌های تازه را ارسال می‌کند."""
import time
from concurrent.futures import ThreadPoolExecutor

from .config import ALERT_SETUPS, BARS, MIN_BARS, SYMBOLS, WORKERS
from .data import get_closed_candles
from .messages import build_alert
from .strategy import analyze, new_events


def scan_once(last_seen, send, pool=None):
    """یک دور بررسی برای همه‌ی نمادها. last_seen: {نماد: زمان آخرین کندل پردازش‌شده}."""
    fetch = lambda sym: (sym, get_closed_candles(sym, BARS, MIN_BARS))
    results = pool.map(fetch, list(SYMBOLS)) if pool else map(fetch, list(SYMBOLS))
    for sym, df in results:
        if df is None:
            continue
        newest = df.index[-1]
        if sym not in last_seen:                 # اولین اجرا: فقط نقطه‌ی شروع را ثبت کن
            last_seen[sym] = newest
            print(f"[{sym}] ready, bars={len(df)}, last={newest}")
            continue
        if newest <= last_seen[sym]:
            continue
        res = analyze(df)
        for ev in new_events(sym, res, last_seen[sym]):
            if ev["setup"] in ALERT_SETUPS:
                send(build_alert(ev))
        last_seen[sym] = newest


def run_scanner(send):
    last_seen = {}
    pool = ThreadPoolExecutor(max_workers=WORKERS)   # دریافت هم‌زمان نمادها
    while True:
        try:
            scan_once(last_seen, send, pool)
        except Exception as e:
            print("scanner error:", e)
        time.sleep(60 - (time.time() % 60) + 4)
