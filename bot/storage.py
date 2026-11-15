"""ذخیره‌ی کاربران ثبت‌شده.

  - اگر DATABASE_URL تنظیم شده باشد: Postgres (با دیپلوی پاک نمی‌شود)
  - در غیر این صورت: فایل JSON محلی (روی Render با هر دیپلوی پاک می‌شود)
"""
import json
import os
import threading


class JsonState:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.users = set()
        try:
            if os.path.exists(path):
                with open(path) as f:
                    self.users = set(json.load(f).get("users", []))
        except Exception as e:
            print("load_state error:", e)

    def describe(self):
        return f"JSON file ({self.path})"

    def add_user(self, chat_id):
        if chat_id in self.users:
            return
        self.users.add(chat_id)
        try:
            with self.lock, open(self.path, "w") as f:
                json.dump({"users": list(self.users)}, f)
        except Exception as e:
            print("save_state error:", e)


class PgState:
    def __init__(self, url):
        import psycopg
        self.conn = psycopg.connect(url, autocommit=True)
        self.lock = threading.Lock()
        with self.lock:
            self.conn.execute("CREATE TABLE IF NOT EXISTS goldbot_users (chat_id BIGINT PRIMARY KEY)")
            self.users = {r[0] for r in self.conn.execute("SELECT chat_id FROM goldbot_users")}

    def describe(self):
        return "Postgres"

    def add_user(self, chat_id):
        if chat_id in self.users:
            return
        self.users.add(chat_id)
        try:
            with self.lock:
                self.conn.execute("INSERT INTO goldbot_users VALUES (%s) ON CONFLICT DO NOTHING", (chat_id,))
        except Exception as e:
            print("db error:", e)


def open_state(path):
    url = os.environ.get("DATABASE_URL")
    if url:
        try:
            return PgState(url)
        except Exception as e:
            print("Postgres unavailable, falling back to JSON:", e)
    return JsonState(path)
