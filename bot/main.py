"""نقطه‌ی شروع: وب‌سرور Render + اسکنر + ربات تلگرام.

اجرا:  python -m bot.main
"""
import os
import threading

from flask import Flask

from .config import STATE_FILE
from .scanner import Scanner, run_scanner
from .storage import open_state
from .telegram_bot import Telegram

app = Flask(__name__)


@app.route("/")
def home():
    return "Goldbot (Al Brooks price action) is live"


def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))


def main():
    threading.Thread(target=run_web, daemon=True).start()   # اول وب‌سرور، تا Render منتظر نماند
    state = open_state(STATE_FILE)
    print(f"storage: {state.describe()}, users={len(state.users)}")
    tg = Telegram(os.environ.get("BOT_TOKEN"), state)
    scanner = Scanner(tg.broadcast, tg.notify_followers)
    tg.scanner = scanner                                    # دکمه‌ها همان وضعیت چرخه‌ی هشدارها را نشان می‌دهند
    threading.Thread(target=run_scanner, args=(scanner,), daemon=True).start()
    tg.run()


if __name__ == "__main__":
    main()
