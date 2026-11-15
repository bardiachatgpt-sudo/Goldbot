"""قیمت زنده از وب‌سوکت TradingView (quote session).

فقط برای نمادهایی که سفارش رنج یا معامله‌ی باز دارند به قیمت لحظه‌ای گوش می‌دهد، تا ترتیب واقعی
رسیدن قیمت به ورود / سایه‌ی پین‌بار / حد ضرر / حد سود معلوم شود و پیام همان لحظه برود.
اگر اتصال قطع شود، آن دقیقه‌ها از روی شکل کندل M1 تصمیم‌گیری می‌شوند (trades.py).
"""
import json
import random
import re
import string
import threading
import time

import pandas as pd
import websocket

URL = "wss://data.tradingview.com/socket.io/websocket?from=chart%2F"
HEADERS = {"Origin": "https://www.tradingview.com",
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def frame(func, params):
    payload = json.dumps({"m": func, "p": params}, separators=(",", ":"))
    return f"~m~{len(payload)}~m~{payload}"


def parse(raw):
    """یک پیام خام وب‌سوکت → (heartbeat یا None, فهرست (نماد TradingView، قیمت))."""
    if re.fullmatch(r"~m~\d+~m~~h~\d+", raw):
        return raw, []
    prices = []
    for part in re.split(r"~m~\d+~m~", raw):
        if not part.strip() or part.startswith("~h~"):
            continue
        try:
            msg = json.loads(part)
        except Exception:
            continue
        if msg.get("m") != "qsd":
            continue
        p = msg.get("p", [])
        if len(p) < 2 or not isinstance(p[1], dict):
            continue
        v = p[1].get("v", {})
        price = v.get("bid", v.get("lp"))                  # نمودار TradingView معمولاً Bid است
        if price is not None:
            prices.append((p[1].get("n"), float(price)))
    return None, prices


class PriceStream:
    """یک اتصال برای همه‌ی نمادها؛ اشتراک‌ها هر دقیقه با want() به‌روز می‌شوند."""

    def __init__(self, on_price, on_up, on_down):
        self.on_price = on_price          # (name, price, ts)
        self.on_up = on_up                # (name, ts): از این لحظه قیمت زنده داریم
        self.on_down = on_down            # (name): اتصال قطع شد
        self.wanted = {}                  # name → نماد TradingView
        self.subscribed = {}
        self.lock = threading.Lock()
        self.ws = None

    def want(self, mapping):
        with self.lock:
            self.wanted = dict(mapping)

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        backoff = 2
        while True:
            with self.lock:
                need = bool(self.wanted)
            if not need:
                time.sleep(1)
                continue
            try:
                self._session()
                backoff = 2
            except Exception as e:
                print("live price error:", str(e)[:100])
            for name in list(self.subscribed):
                self.on_down(name)
            self.subscribed = {}
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)

    def _session(self):
        ws = websocket.create_connection(URL, headers=HEADERS, timeout=12)
        ws.settimeout(1)
        qs = "qs_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
        ws.send(frame("set_auth_token", ["unauthorized_user_token"]))
        ws.send(frame("quote_create_session", [qs]))
        ws.send(frame("quote_set_fields", [qs, "lp", "bid", "ask"]))
        by_tv = {}
        try:
            while True:
                with self.lock:
                    wanted = dict(self.wanted)
                if not wanted:
                    return
                for name, tv in wanted.items():          # اشتراک‌های تازه
                    if self.subscribed.get(name) != tv:
                        ws.send(frame("quote_add_symbols", [qs, tv]))
                        self.subscribed[name] = tv
                        by_tv[tv] = name
                        self.on_up(name, pd.Timestamp.now(tz="UTC"))
                for name in list(self.subscribed):        # اشتراک‌های قدیمی
                    if name not in wanted:
                        tv = self.subscribed.pop(name)
                        ws.send(frame("quote_remove_symbols", [qs, tv]))
                        by_tv.pop(tv, None)
                        self.on_down(name)
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not raw:
                    raise ConnectionError("closed")
                hb, prices = parse(raw)
                if hb:
                    ws.send(hb)
                now = pd.Timestamp.now(tz="UTC")
                for tv, price in prices:
                    name = by_tv.get(tv)
                    if name:
                        self.on_price(name, price, now)
        finally:
            try:
                ws.close()
            except Exception:
                pass
