"""چت‌هایی که هشدار گپ طلا را روشن کرده‌اند — طوری که با دیپلوی و ری‌استارت پاک نشوند.

- اگر DATABASE_URL (Postgres، مثلاً Neon) تنظیم شده باشد: جدول goldbot_alert_subs (همیشه می‌ماند).
- وگرنه فایل alert_subs.json (با هر دیپلوی روی Render پاک می‌شود).
- ALERT_CHAT_IDS (فهرست با کاما) همیشه هم اضافه می‌شود.
هر کسی یک بار دکمه را بزند، تا وقتی خودش خاموش نکند هشدار می‌گیرد.
"""
import json
import os
import threading

ALERT_FILE = "alert_subs.json"


class AlertSubs:
    def __init__(self, path=ALERT_FILE, url=None):
        self.path = path
        self.lock = threading.Lock()
        self.url = None
        self.chats = {int(x) for x in os.environ.get("ALERT_CHAT_IDS", "").replace(" ", "").split(",") if x}
        url = os.environ.get("DATABASE_URL") if url is None else url
        if url:
            try:
                import psycopg
                with psycopg.connect(url, autocommit=True, connect_timeout=15) as conn:
                    conn.execute("CREATE TABLE IF NOT EXISTS goldbot_alert_subs (chat_id BIGINT PRIMARY KEY)")
                    self.chats |= {r[0] for r in conn.execute("SELECT chat_id FROM goldbot_alert_subs")}
                self.url = url
                print(f"alert subscribers from Postgres: {len(self.chats)}")
                return
            except Exception as e:
                print("Postgres unavailable for alert subscribers, using the file:", e)
        try:
            with open(self.path) as f:
                self.chats |= {int(x) for x in json.load(f)}
        except Exception:
            pass

    def where(self):
        return "database" if self.url else "file"

    def __contains__(self, chat_id):
        return chat_id in self.chats

    def __iter__(self):
        return iter(list(self.chats))

    def __len__(self):
        return len(self.chats)

    def set(self, chat_id, on):
        (self.chats.add if on else self.chats.discard)(chat_id)
        if self.url:                                      # هر بار اتصال تازه (Neon اتصال‌های بی‌کار را می‌بندد)
            try:
                import psycopg
                with self.lock, psycopg.connect(self.url, autocommit=True, connect_timeout=15) as conn:
                    if on:
                        conn.execute("INSERT INTO goldbot_alert_subs VALUES (%s) ON CONFLICT DO NOTHING",
                                          (chat_id,))
                    else:
                        conn.execute("DELETE FROM goldbot_alert_subs WHERE chat_id=%s", (chat_id,))
                return
            except Exception as e:
                print("alert subscribers db error:", e)
        try:
            with open(self.path, "w") as f:
                json.dump(sorted(self.chats), f)
        except Exception as e:
            print("alert file error:", e)
