"""حلقه‌ی اسکن زنده.

هر دقیقه برای هر نماد:
  - کندل‌های M5 (زمینه):
      * چرخه‌ی بازار (رنج/اسپایک/کانال/تست): هر تغییر برای کسانی که نماد را فالو کرده‌اند
      * بعد از بسته شدن هر کندل، ستاپ‌های تازه (H2/L2، Wedge، پین‌بار ...) برای همه
  - کندل‌های M1 (ماشه): بریک‌اوت از سطح‌های M5 → آماده باش / تأیید شد / شکست خورد، برای همه
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .config import (ALERT_SETUPS, BARS, CONTEXT_TF, MIN_BARS, SYMBOLS, TRIGGER_BARS,
                     TRIGGER_TF, WORKERS)
from .cycle import CycleEngine
from .data import get_closed_candles
from .messages import build_alert, build_cycle_alert
from .mtf import BreakoutWatcher
from .strategy import analyze, new_events


class Scanner:
    def __init__(self, send, send_followers=None):
        self.send = send                                  # همه‌ی کاربران + کانال
        self.send_followers = send_followers or (lambda sym, text: None)
        self.seen = {}                                    # نماد → آخرین کندل M5 پردازش‌شده
        self.watchers = {s: BreakoutWatcher(s) for s in SYMBOLS}
        self.cycles = {}                                  # نماد → موتور چرخه‌ی زنده
        self.lock = threading.RLock()                     # ربات تلگرام هم موتورها را می‌خواند

    def _fetch(self, sym):
        m5 = get_closed_candles(sym, BARS, MIN_BARS, CONTEXT_TF)
        m1 = get_closed_candles(sym, TRIGGER_BARS, MIN_BARS, TRIGGER_TF) if "MTF_BO" in ALERT_SETUPS else None
        return sym, m5, m1

    def scan_once(self, pool=None):
        results = pool.map(self._fetch, list(SYMBOLS)) if pool else map(self._fetch, list(SYMBOLS))
        for sym, m5, m1 in results:
            if m5 is None:
                continue
            with self.lock:
                for ev in self.watchers[sym].process(m5, m1):     # اول M1، با زمینه‌ی M5 همان لحظه
                    self.send(build_alert(ev))
                self._cycle(sym, m5)
                self._m5_setups(sym, m5)

    def _cycle(self, sym, df):
        eng = self.cycles.get(sym)
        if eng is None or df.index[0] > eng.t[-1]:        # اولین اجرا یا شکاف در داده: بازسازی بی‌صدا
            eng = CycleEngine(sym)
            eng.feed(df)
            self.cycles[sym] = eng
            return
        for ev in eng.feed(df):
            self.send_followers(sym, build_cycle_alert(ev))

    def _m5_setups(self, sym, df):
        newest = df.index[-1]
        if sym not in self.seen:                          # اولین اجرا: فقط نقطه‌ی شروع را ثبت کن
            self.seen[sym] = newest
            print(f"[{sym}] ready, bars={len(df)}, last={newest}")
            return
        if newest <= self.seen[sym]:
            return
        res = analyze(df, engine=self.cycles.get(sym))
        for ev in new_events(sym, res, self.seen[sym]):
            if ev["setup"] in ALERT_SETUPS:
                self.send(build_alert(ev))
        self.seen[sym] = newest

    def engine(self, sym):
        return self.cycles.get(sym)


def run_scanner(scanner):
    pool = ThreadPoolExecutor(max_workers=WORKERS)        # دریافت هم‌زمان نمادها
    while True:
        try:
            scanner.scan_once(pool)
        except Exception as e:
            print("scanner error:", e)
        time.sleep(60 - (time.time() % 60) + 4)
