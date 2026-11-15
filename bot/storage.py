"""ذخیره‌ی کاربران ثبت‌شده و نمادهایی که هر کاربر فالو کرده.

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
        self.follows = {}                     # chat_id → مجموعه‌ی نمادها
        try:
            if os.path.exists(path):
                with open(path) as f:
                    d = json.load(f)
                self.users = set(d.get("users", []))
                self.follows = {int(k): set(v) for k, v in d.get("follows", {}).items()}
        except Exception as e:
            print("load_state error:", e)

    def describe(self):
        return f"JSON file ({self.path})"

    def _save(self):
        try:
            with self.lock, open(self.path, "w") as f:
                json.dump({"users": list(self.users),
                           "follows": {str(k): sorted(v) for k, v in self.follows.items()}}, f)
        except Exception as e:
            print("save_state error:", e)

    def add_user(self, chat_id):
        if chat_id in self.users:
            return
        self.users.add(chat_id)
        self._save()

    def set_follow(self, chat_id, sym, on):
        cur = self.follows.setdefault(chat_id, set())
        (cur.add if on else cur.discard)(sym)
        self._save()


class PgState:
    def __init__(self, url):
        import psycopg
        self.conn = psycopg.connect(url, autocommit=True)
        self.lock = threading.Lock()
        with self.lock:
            self.conn.execute("CREATE TABLE IF NOT EXISTS goldbot_users (chat_id BIGINT PRIMARY KEY)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS goldbot_follows "
                              "(chat_id BIGINT, sym TEXT, PRIMARY KEY (chat_id, sym))")
            self.users = {r[0] for r in self.conn.execute("SELECT chat_id FROM goldbot_users")}
            self.follows = {}
            for chat_id, sym in self.conn.execute("SELECT chat_id, sym FROM goldbot_follows"):
                self.follows.setdefault(chat_id, set()).add(sym)

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

    def set_follow(self, chat_id, sym, on):
        cur = self.follows.setdefault(chat_id, set())
        (cur.add if on else cur.discard)(sym)
        try:
            with self.lock:
                if on:
                    self.conn.execute("INSERT INTO goldbot_follows VALUES (%s, %s) ON CONFLICT DO NOTHING",
                                      (chat_id, sym))
                else:
                    self.conn.execute("DELETE FROM goldbot_follows WHERE chat_id=%s AND sym=%s", (chat_id, sym))
        except Exception as e:
            print("db error:", e)


def followers(state, sym):
    return [cid for cid, syms in list(state.follows.items()) if sym in syms]


def is_following(state, chat_id, sym):
    return sym in state.follows.get(chat_id, ())


def open_state(path):
    url = os.environ.get("DATABASE_URL")
    if url:
        try:
            return PgState(url)
        except Exception as e:
            print("Postgres unavailable, falling back to JSON:", e)
    return JsonState(path)
