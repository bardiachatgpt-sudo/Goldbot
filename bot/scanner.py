"""حلقه‌ی اسکن زنده.

هر دقیقه برای هر نماد:
  - M5 (زمینه): چرخه‌ی بازار. هر تغییر برای فالوکننده‌ها؛ «🚀 اسپایک، منتظر پولبک» برای همه.
    هشدارهای اطلاعاتی M5 (H2/L2، پین‌بار، وج) فقط اگر در ALERT_SETUPS روشن شده باشند.
  - M1 (ماشه): ستاپ ورود، ورود، حد سود/ضرر (trades.py) برای همه.
قیمت زنده (live.py) فقط برای نمادهایی که سفارش رنج یا معامله‌ی باز دارند.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .alert_chart import m5_alert_chart, trade_chart
from .config import (ALERT_CHARTS, ALERT_SETUPS, BARS, CONTEXT_TF, LIVE_PRICES, MIN_BARS, SYMBOLS,
                     TRIGGER_BARS, TRIGGER_TF, WORKERS)
from .cycle import RANGE, SPIKE, CycleEngine
from .data import get_closed_candles, source
from .messages import build_alert, build_cycle_alert, build_spike_alert, build_trade_alert
from .strategy import analyze, new_events
from .trades import TradeManager


def _chart(make, *args):
    """عکس هشدار؛ اگر رسم نشد، هشدار بدون عکس می‌رود."""
    if not ALERT_CHARTS or args[1] is None:
        return None
    try:
        return make(*args)
    except Exception as e:
        print("alert chart error:", e)
        return None


class Scanner:
    def __init__(self, send, send_followers=None):
        self.send = send                                  # همه‌ی کاربران + کانال: send(text, photo)
        self.send_followers = send_followers or (lambda sym, text, photo=None: None)
        self.seen = {}                                    # نماد → آخرین کندل M5 پردازش‌شده
        self.cycles = {}                                  # نماد → موتور چرخه‌ی زنده
        self.trades = {s: TradeManager(s) for s in SYMBOLS}
        self.m1_res = {}                                  # آخرین تحلیل M1 هر نماد (برای عکس هشدار زنده)
        self.lock = threading.RLock()                     # تلگرام و قیمت زنده هم این‌ها را می‌خوانند
        self.stream = None

    # ------------------------------------------------------------ قیمت زنده
    def attach_stream(self, stream):
        self.stream = stream

    def on_price(self, sym, price, ts):
        with self.lock:
            for ev in self.trades[sym].on_price(price, ts):
                self.send(build_trade_alert(ev), _chart(trade_chart, sym, self.m1_res.get(sym), ev))
            self._update_stream()

    def on_live_up(self, sym, ts):
        with self.lock:
            self.trades[sym].live_started(ts)

    def on_live_down(self, sym):
        with self.lock:
            self.trades[sym].live_stopped()

    def _update_stream(self):
        if self.stream is not None:
            self.stream.want({s: source(s) for s, tm in self.trades.items() if tm.needs_live()})

    # ------------------------------------------------------------ هر دقیقه
    def _fetch(self, sym):
        m5 = get_closed_candles(sym, BARS, MIN_BARS, CONTEXT_TF)
        m1 = get_closed_candles(sym, TRIGGER_BARS, MIN_BARS, TRIGGER_TF) if "TRADE" in ALERT_SETUPS else None
        return sym, m5, m1

    def scan_once(self, pool=None):
        results = pool.map(self._fetch, list(SYMBOLS)) if pool else map(self._fetch, list(SYMBOLS))
        for sym, m5, m1 in results:
            if m5 is None:
                continue
            with self.lock:
                self._trades(sym, m1)                     # اول M1، با چرخه‌ی M5 تا آخرین کندل بسته‌شده
                self._cycle(sym, m5)
                self._m5_setups(sym, m5)
            with self.lock:
                self._update_stream()

    def _trades(self, sym, m1):
        if "TRADE" not in ALERT_SETUPS or m1 is None or len(m1) < MIN_BARS:
            return
        res = analyze(m1, cycle=False)
        self.m1_res[sym] = res
        eng = self.cycles.get(sym)
        ctx = eng.snapshot() if eng is not None else None
        for ev in self.trades[sym].process(res["df"], ctx):
            self.send(build_trade_alert(ev), _chart(trade_chart, sym, res, ev))

    def _cycle(self, sym, df):
        eng = self.cycles.get(sym)
        if eng is None or df.index[0] > eng.t[-1]:        # اولین اجرا یا شکاف در داده: بازسازی بی‌صدا
            eng = CycleEngine(sym)
            eng.feed(df)
            self.cycles[sym] = eng
            return
        events = eng.feed(df)
        if not events:
            return
        res = analyze(df, engine=eng) if ALERT_CHARTS else None
        for ev in events:
            photo = _chart(m5_alert_chart, sym, res, ev)
            self.send_followers(sym, build_cycle_alert(ev), photo)
            # اسپایکی که از رنج بیرون زده: برای همه، چون ستاپ اولین پولبک از همین‌جا شروع می‌شود
            if "SPIKE" in ALERT_SETUPS and ev["from"][0] == RANGE and ev["to"][0] == SPIKE \
                    and ev["snap"].get("broken") is not None:
                self.send(build_spike_alert(ev), photo)

    def _m5_setups(self, sym, df):
        """هشدارهای اطلاعاتی M5 (پیش‌فرض خاموش)."""
        newest = df.index[-1]
        if sym not in self.seen:                          # اولین اجرا: فقط نقطه‌ی شروع را ثبت کن
            self.seen[sym] = newest
            print(f"[{sym}] ready, bars={len(df)}, last={newest}")
            return
        if newest <= self.seen[sym]:
            return
        wanted = ALERT_SETUPS & {"H1", "H2", "L1", "L2", "WEDGE", "PIN", "WEDGE_BO", "RANGE_BO"}
        if wanted:
            res = analyze(df, engine=self.cycles.get(sym))
            for ev in new_events(sym, res, self.seen[sym]):
                if ev["setup"] in wanted:
                    self.send(build_alert(ev), _chart(m5_alert_chart, sym, res, ev))
        self.seen[sym] = newest

    def engine(self, sym):
        return self.cycles.get(sym)


def run_scanner(scanner):
    if LIVE_PRICES:
        from .live import PriceStream
        stream = PriceStream(scanner.on_price, scanner.on_live_up, scanner.on_live_down)
        scanner.attach_stream(stream)
        stream.start()
    pool = ThreadPoolExecutor(max_workers=WORKERS)        # دریافت هم‌زمان نمادها
    while True:
        try:
            scanner.scan_once(pool)
        except Exception as e:
            print("scanner error:", e)
        time.sleep(60 - (time.time() % 60) + 4)
