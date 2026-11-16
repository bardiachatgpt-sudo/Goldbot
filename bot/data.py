"""دریافت کندل از وب‌سوکت TradingView."""
import json
import random
import re
import string
import time

import pandas as pd
import websocket

from .config import ALL_SYMBOLS as SYMBOLS, TIMEFRAME


def _send(ws, func, params):
    payload = json.dumps({"m": func, "p": params}, separators=(",", ":"))
    ws.send(f"~m~{len(payload)}~m~{payload}")


def fetch_candles(tv_symbol, interval="1", n_bars=1000, timeout=20):
    ws = None
    try:
        ws = websocket.create_connection(
            "wss://data.tradingview.com/socket.io/websocket?from=chart%2F",
            headers={
                "Origin": "https://www.tradingview.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
            timeout=12,
        )
        cs = "cs_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
        _send(ws, "set_auth_token", ["unauthorized_user_token"])
        _send(ws, "chart_create_session", [cs, ""])
        sym = json.dumps({"symbol": tv_symbol, "adjustment": "splits"}, separators=(",", ":"))
        _send(ws, "resolve_symbol", [cs, "sds_sym_1", f"={sym}"])
        _send(ws, "create_series", [cs, "sds_1", "s1", "sds_sym_1", str(interval), n_bars, ""])

        bars = {}
        t0 = time.time()
        done = False
        while time.time() - t0 < timeout and not done:
            raw = ws.recv()
            if not raw:
                break
            if re.fullmatch(r"~m~\d+~m~~h~\d+", raw):
                ws.send(raw)
                continue
            for part in re.split(r"~m~\d+~m~", raw):
                if not part.strip() or part.startswith("~h~"):
                    continue
                try:
                    msg = json.loads(part)
                except Exception:
                    continue
                m = msg.get("m")
                if m in ("timescale_update", "du"):
                    p = msg.get("p", [])
                    if len(p) >= 2 and isinstance(p[1], dict):
                        for item in p[1].get("sds_1", {}).get("s", []):
                            v = item.get("v", [])
                            if len(v) >= 5:
                                bars[int(v[0])] = (float(v[1]), float(v[2]), float(v[3]), float(v[4]))
                elif m == "series_completed":
                    done = True
        ws.close()
        if not bars:
            return None, f"{tv_symbol}: no bars"
        df = pd.DataFrame.from_dict(
            bars, orient="index", columns=["Open", "High", "Low", "Close"]
        ).sort_index()
        df.index = pd.to_datetime(df.index, unit="s", utc=True)
        return df, None
    except Exception as e:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        return None, f"{tv_symbol}: {str(e)[:80]}"


LAST_SOURCE = {}   # نماد → منبع TradingView که آخرین بار داده داد (برای قیمت زنده)


def source(name):
    return LAST_SOURCE.get(name, SYMBOLS[name][0])


def get_closed_candles(name, n_bars, min_bars, interval=None):
    """فقط کندل‌های بسته‌شده؛ ردیف آخر (کندل در حال تشکیل) حذف می‌شود."""
    errors = []
    for tv_symbol in SYMBOLS[name]:
        df, err = fetch_candles(tv_symbol, interval or TIMEFRAME, n_bars)
        if df is not None and len(df) > min_bars:
            LAST_SOURCE[name] = tv_symbol
            return df.iloc[:-1]
        errors.append(err or f"{tv_symbol}: too few bars")
    print(f"[{name}] fetch failed: {' | '.join(errors)}")
    return None
