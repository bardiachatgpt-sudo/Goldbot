"""
Stem Splitter Telegram Bot
--------------------------
Send a song -> get back separate tracks: vocals, drums, bass, other instruments.

Separation runs on Replicate (Demucs model) so the bot itself stays light
enough for Render's free plan. ffmpeg (installed in the Docker image) converts
stems to MP3 so they fit Telegram's upload limits.

Environment variables:
  BOT_TOKEN            - Telegram bot token from @BotFather (required)
  REPLICATE_API_TOKEN  - Replicate API token (required)
  REPLICATE_MODEL      - optional, default "ryan5453/demucs"
  REPLICATE_VERSION    - optional, pin a model version id (default: latest)
  MP3_BITRATE          - optional, default "192k"
  RENDER_EXTERNAL_URL  - set automatically by Render; enables webhook mode
  PORT                 - set automatically by Render
"""

import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
import time

import requests
import telebot
from flask import Flask, abort, request

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")
REPLICATE_MODEL = os.environ.get("REPLICATE_MODEL", "ryan5453/demucs")
REPLICATE_VERSION = os.environ.get("REPLICATE_VERSION", "")
MP3_BITRATE = os.environ.get("MP3_BITRATE", "192k")
PUBLIC_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
PORT = int(os.environ.get("PORT", 10000))

TELEGRAM_DOWNLOAD_LIMIT = 20 * 1024 * 1024  # bots can only download files up to 20 MB
TELEGRAM_UPLOAD_LIMIT = 49 * 1024 * 1024    # bots can upload files up to 50 MB
PREDICTION_TIMEOUT = 15 * 60                 # seconds
MAX_JOBS_PER_USER = 1

REPLICATE_API = "https://api.replicate.com/v1"

# Display order and Persian labels for the stems we know about.
STEM_LABELS = {
    "vocals": "🎤 وکال",
    "drums": "🥁 درامز",
    "bass": "🎸 بیس",
    "other": "🎹 سایر سازها",
    "guitar": "🎸 گیتار",
    "piano": "🎹 پیانو",
}

bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=4) if BOT_TOKEN else None
app = Flask(__name__)

# Secret that Telegram sends back with every webhook call, so random POSTs are rejected.
WEBHOOK_SECRET = hashlib.sha256(BOT_TOKEN.encode()).hexdigest()[:32] if BOT_TOKEN else ""
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET[:16]}"

_active_jobs = {}
_jobs_lock = threading.Lock()


# --------------------------------------------------------------------------
# Replicate
# --------------------------------------------------------------------------
def _rep_headers():
    return {"Authorization": f"Bearer {REPLICATE_API_TOKEN}"}


_cached_version = None


def get_model_version():
    global _cached_version
    if REPLICATE_VERSION:
        return REPLICATE_VERSION
    if _cached_version:
        return _cached_version
    r = requests.get(f"{REPLICATE_API}/models/{REPLICATE_MODEL}", headers=_rep_headers(), timeout=30)
    r.raise_for_status()
    _cached_version = r.json()["latest_version"]["id"]
    return _cached_version


def upload_to_replicate(path):
    with open(path, "rb") as f:
        r = requests.post(
            f"{REPLICATE_API}/files",
            headers=_rep_headers(),
            files={"content": (os.path.basename(path), f, "application/octet-stream")},
            timeout=300,
        )
    r.raise_for_status()
    return r.json()["urls"]["get"]


def run_separation(audio_url):
    r = requests.post(
        f"{REPLICATE_API}/predictions",
        headers={**_rep_headers(), "Content-Type": "application/json"},
        json={"version": get_model_version(), "input": {"audio": audio_url}},
        timeout=60,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Replicate error {r.status_code}: {r.text[:300]}")
    pred = r.json()
    poll_url = pred["urls"]["get"]

    deadline = time.time() + PREDICTION_TIMEOUT
    while pred.get("status") not in ("succeeded", "failed", "canceled"):
        if time.time() > deadline:
            requests.post(pred["urls"]["cancel"], headers=_rep_headers(), timeout=30)
            raise RuntimeError("Separation timed out")
        time.sleep(3)
        pred = requests.get(poll_url, headers=_rep_headers(), timeout=30).json()

    if pred["status"] != "succeeded":
        raise RuntimeError(f"Separation {pred['status']}: {str(pred.get('error'))[:300]}")
    return normalize_output(pred.get("output"))


def normalize_output(output):
    """Different Demucs versions on Replicate return different shapes.
    Turn all of them into {stem_name: url}."""
    stems = {}
    if isinstance(output, dict) and isinstance(output.get("stems"), list):
        output = output["stems"]
    if isinstance(output, dict):
        for name, url in output.items():
            if isinstance(url, str) and url.startswith("http"):
                stems[name] = url
    elif isinstance(output, list):
        for i, item in enumerate(output):
            if isinstance(item, dict) and item.get("audio"):
                stems[item.get("name", f"stem{i}")] = item["audio"]
            elif isinstance(item, str) and item.startswith("http"):
                name = os.path.splitext(os.path.basename(item.split("?")[0]))[0]
                stems[name or f"stem{i}"] = item
    # Skip "no_vocals"-style complements; we only want the individual lines.
    stems = {k: v for k, v in stems.items() if not k.startswith("no_")}
    if not stems:
        raise RuntimeError(f"Unexpected model output: {str(output)[:300]}")
    return stems


# --------------------------------------------------------------------------
# Audio helpers
# --------------------------------------------------------------------------
def download(url, dest):
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return dest


def to_mp3(src, dest, bitrate=MP3_BITRATE):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-b:a", bitrate, dest],
        check=True,
        timeout=300,
    )
    return dest


def ordered(stems):
    known = [s for s in STEM_LABELS if s in stems]
    rest = sorted(s for s in stems if s not in STEM_LABELS)
    return known + rest


# --------------------------------------------------------------------------
# Telegram handlers
# --------------------------------------------------------------------------
WELCOME = (
    "سلام! 🎶\n\n"
    "یه آهنگ برام بفرست تا جداش کنم به:\n"
    "🎤 وکال\n🥁 درامز\n🎸 بیس\n🎹 سایر سازها\n\n"
    "فایل صوتی (mp3, wav, m4a, flac…) یا ویس بفرست. حداکثر حجم ۲۰ مگابایت.\n"
    "پردازش هر آهنگ معمولاً ۱ تا ۳ دقیقه طول می‌کشه."
)


def get_audio_info(message):
    """Return (file_id, file_size, base_name) or None if the message has no audio."""
    if message.audio:
        a = message.audio
        name = a.file_name or " - ".join(x for x in (a.performer, a.title) if x) or "song"
        return a.file_id, a.file_size, name
    if message.voice:
        return message.voice.file_id, message.voice.file_size, "voice"
    if message.document:
        d = message.document
        mime = d.mime_type or ""
        ext = os.path.splitext(d.file_name or "")[1].lower()
        if mime.startswith("audio/") or mime.startswith("video/") or ext in (
            ".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus", ".aac", ".wma", ".aiff", ".aif", ".mp4",
        ):
            return d.file_id, d.file_size, d.file_name or "song"
    if message.video:
        return message.video.file_id, message.video.file_size, message.video.file_name or "video"
    return None


if bot:

    @bot.message_handler(commands=["start", "help"])
    def cmd_start(message):
        bot.reply_to(message, WELCOME)

    @bot.message_handler(content_types=["audio", "voice", "document", "video"])
    def on_audio(message):
        info = get_audio_info(message)
        if not info:
            bot.reply_to(message, "این فایل صوتی نیست. لطفاً یه آهنگ بفرست 🎵")
            return
        file_id, file_size, name = info

        if file_size and file_size > TELEGRAM_DOWNLOAD_LIMIT:
            bot.reply_to(message, "❌ حجم فایل بیشتر از ۲۰ مگابایته (محدودیت تلگرام برای ربات‌ها). یه نسخهٔ کم‌حجم‌تر بفرست.")
            return

        user_id = message.from_user.id
        with _jobs_lock:
            if _active_jobs.get(user_id, 0) >= MAX_JOBS_PER_USER:
                bot.reply_to(message, "⏳ یه آهنگ دیگه‌ت هنوز در حال پردازشه. صبر کن تموم بشه.")
                return
            _active_jobs[user_id] = _active_jobs.get(user_id, 0) + 1

        try:
            process_song(message, file_id, name)
        finally:
            with _jobs_lock:
                _active_jobs[user_id] -= 1

    @bot.message_handler(func=lambda m: True, content_types=["text", "photo", "sticker"])
    def on_other(message):
        bot.reply_to(message, "یه آهنگ بفرست تا لاین‌هاش رو جدا کنم 🎵\n/help")


def process_song(message, file_id, name):
    chat_id = message.chat.id
    status = bot.reply_to(message, "📥 دریافت فایل…")

    def update(text):
        try:
            bot.edit_message_text(text, chat_id, status.message_id)
        except Exception:
            pass

    workdir = tempfile.mkdtemp(prefix="stems_")
    try:
        tg_file = bot.get_file(file_id)
        ext = os.path.splitext(tg_file.file_path or "")[1] or ".mp3"
        src = os.path.join(workdir, "input" + ext)
        with open(src, "wb") as f:
            f.write(bot.download_file(tg_file.file_path))

        update("⬆️ آپلود برای پردازش…")
        audio_url = upload_to_replicate(src)

        update("🎛 در حال جدا کردن لاین‌ها… (۱ تا ۳ دقیقه)")
        stems = run_separation(audio_url)

        update("📤 ارسال فایل‌ها…")
        base = os.path.splitext(name)[0][:60] or "song"
        bot.send_chat_action(chat_id, "upload_audio")
        sent = 0
        for stem in ordered(stems):
            label = STEM_LABELS.get(stem, stem)
            raw = download(stems[stem], os.path.join(workdir, f"{stem}_raw"))
            mp3 = to_mp3(raw, os.path.join(workdir, f"{base} - {stem}.mp3"))
            if os.path.getsize(mp3) > TELEGRAM_UPLOAD_LIMIT:
                mp3 = to_mp3(raw, mp3, bitrate="96k")
            with open(mp3, "rb") as f:
                bot.send_audio(
                    chat_id,
                    f,
                    caption=label,
                    title=f"{base} ({stem})",
                    performer="Stem Splitter",
                    reply_to_message_id=message.message_id,
                )
            sent += 1

        update(f"✅ تموم شد! {sent} لاین جدا شد.")
    except Exception as e:
        print(f"[error] chat={chat_id}: {e}", flush=True)
        update("❌ یه مشکلی پیش اومد و پردازش انجام نشد. دوباره امتحان کن.")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# --------------------------------------------------------------------------
# Web server (Render needs an open port; Telegram talks to us via webhook)
# --------------------------------------------------------------------------
@app.route("/")
def health():
    return "Stem Splitter Bot is running."


@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        abort(403)
    update = telebot.types.Update.de_json(request.get_data(as_text=True))
    bot.process_new_updates([update])  # handlers run in bot's worker threads
    return "OK", 200


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set")
    if not REPLICATE_API_TOKEN:
        raise SystemExit("REPLICATE_API_TOKEN is not set")
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is not installed")

    if PUBLIC_URL:
        bot.remove_webhook()
        bot.set_webhook(url=PUBLIC_URL + WEBHOOK_PATH, secret_token=WEBHOOK_SECRET)
        print(f"Webhook mode: {PUBLIC_URL}{WEBHOOK_PATH[:10]}…", flush=True)
        app.run(host="0.0.0.0", port=PORT, threaded=True)
    else:
        # Local run: no public URL, so poll Telegram instead.
        bot.remove_webhook()
        print("Polling mode", flush=True)
        bot.infinity_polling(timeout=30, long_polling_timeout=30)


if __name__ == "__main__":
    main()
