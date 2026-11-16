"""نقطه‌ی شروع: وب‌سرور Render + ربات تلگرام ساختار.

اجرا:  python -m bot.main
"""
import os
import threading

from flask import Flask

from .telegram_bot import Telegram

app = Flask(__name__)


@app.route("/")
def home():
    return "Goldbot (market structure) is live"


def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))


def main():
    threading.Thread(target=run_web, daemon=True).start()   # اول وب‌سرور، تا Render منتظر نماند
    Telegram(os.environ.get("BOT_TOKEN")).run()


if __name__ == "__main__":
    main()
