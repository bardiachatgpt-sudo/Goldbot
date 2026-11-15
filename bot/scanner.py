"""حلقه‌ی اسکن زنده.

هر دقیقه برای هر نماد:
  - کندل‌های M5 (زمینه): بعد از بسته شدن هر کندل، ستاپ‌های تازه (H2/L2، Wedge، پین‌بار ...)
  - کندل‌های M1 (ماشه): بریک‌اوت از سطح‌های M5 → آماده باش / تأیید شد / شکست خورد
"""
import time
from concurrent.futures import ThreadPoolExecutor

from .config import (ALERT_SETUPS, BARS, CONTEXT_TF, MIN_BARS, SYMBOLS, TRIGGER_BARS,
                     TRIGGER_TF, WORKERS)
from .data import get_closed_candles
from .messages import build_alert
from .mtf import BreakoutWatcher
from .strategy import analyze, new_events


class Scanner:
    def __init__(self, send):
        self.send = send
        self.seen = {}                                   # نماد → آخرین کندل M5 پردازش‌شده
        self.watchers = {s: BreakoutWatcher(s) for s in SYMBOLS}

    def _fetch(self, sym):
        m5 = get_closed_candles(sym, BARS, MIN_BARS, CONTEXT_TF)
        m1 = get_closed_candles(sym, TRIGGER_BARS, MIN_BARS, TRIGGER_TF) if "MTF_BO" in ALERT_SETUPS else None
        return sym, m5, m1

    def scan_once(self, pool=None):
        results = pool.map(self._fetch, list(SYMBOLS)) if pool else map(self._fetch, list(SYMBOLS))
        for sym, m5, m1 in results:
            if m5 is None:
                continue
            for ev in self.watchers[sym].process(m5, m1):     # اول M1، با زمینه‌ی M5 همان لحظه
                self.send(build_alert(ev))
            self._m5_setups(sym, m5)

    def _m5_setups(self, sym, df):
        newest = df.index[-1]
        if sym not in self.seen:                         # اولین اجرا: فقط نقطه‌ی شروع را ثبت کن
            self.seen[sym] = newest
            print(f"[{sym}] ready, bars={len(df)}, last={newest}")
            return
        if newest <= self.seen[sym]:
            return
        res = analyze(df)
        for ev in new_events(sym, res, self.seen[sym]):
            if ev["setup"] in ALERT_SETUPS:
                self.send(build_alert(ev))
        self.seen[sym] = newest


def run_scanner(send):
    scanner = Scanner(send)
    pool = ThreadPoolExecutor(max_workers=WORKERS)       # دریافت هم‌زمان نمادها
    while True:
        try:
            scanner.scan_once(pool)
        except Exception as e:
            print("scanner error:", e)
        time.sleep(60 - (time.time() % 60) + 4)
