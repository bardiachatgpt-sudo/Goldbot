# راه‌اندازی ربات روی Render (برای اینکه تنظیمات گم نشود)

## متغیرهای Render (سرویس ربات ← Environment)
| کلید | لازم؟ | چیست |
|---|---|---|
| `BOT_TOKEN` | **بله** | توکن ربات تلگرام از BotFather |
| `DATABASE_URL` | پیشنهادی | آدرس دیتابیس Neon (`postgresql://...neon.tech/...`). با آن، هر کسی یک بار دکمه‌ی «🔔 Gold gap alerts» را بزند، هشدار برایش با هر دیپلوی روشن می‌ماند (جدول `goldbot_alert_subs`). بدون آن، با هر دیپلوی هشدارها خاموش می‌شوند |
| `ALERT_CHAT_IDS` | اختیاری | شماره‌ی چت‌هایی که همیشه هشدار طلا بگیرند (با کاما جدا). شماره‌ی چت از ربات `@userinfobot` در تلگرام |
| `STRUCTURE_PAIRS` | اختیاری | فقط اگر بخواهید جفت‌ارزها فرق کند (پیش‌فرض `XAUUSD,USDJPY,EURUSD`) |

## آدرس دیتابیس Neon را از کجا بیاورم؟
console.neon.tech ← پروژه ← دکمه‌ی **Connect** ← آدرس اتصال را کپی کنید ← در Render به‌عنوان `DATABASE_URL` بگذارید ← **Save**.

## بعد از هر دیپلوی چه ببینم؟ (Render ← Logs)
- `alert subscribers from Postgres: N` ← به دیتابیس وصل است و N نفر هشدار طلا را روشن دارند.
- `Postgres unavailable for alert subscribers…` ← وصل نیست؛ `DATABASE_URL` را چک کنید.
- چند خط `409 Conflict` هنگام دیپلوی عادی است.

## دیدن کاربرها در Neon
SQL Editor:
- `SELECT * FROM goldbot_alert_subs;` ← کسانی که هشدار طلا روشن دارند
- `SELECT count(*) FROM goldbot_users;` ← کاربرهای ربات قدیمی (تا ۱۶ نوامبر)

## دیپلوی
Render خودش از شاخه‌ی `main` گیت‌هاب دیپلوی می‌کند (۳ تا ۵ دقیقه).
