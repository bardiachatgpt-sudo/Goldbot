# Stem Splitter Bot 🎶

ربات تلگرامی که آهنگ رو می‌گیره و لاین‌هاش رو جدا برمی‌گردونه:
🎤 وکال · 🥁 درامز · 🎸 بیس · 🎹 سایر سازها

جداسازی با مدل **Demucs** روی [Replicate](https://replicate.com) انجام می‌شه، پس ربات روی پلن رایگان Render هم اجرا می‌شه.

## راه‌اندازی

1. **توکن تلگرام:** از [@BotFather](https://t.me/BotFather) یه ربات بساز و توکنش رو بگیر.
2. **توکن Replicate:** توی replicate.com ثبت‌نام کن، در بخش Billing کارت اضافه کن (هزینه به ازای هر آهنگه) و از Account → API tokens یه توکن بساز.
3. **Render:** New → Web Service → همین ریپو. Render خودش Dockerfile رو تشخیص می‌ده.
4. در Environment این دو متغیر رو اضافه کن:

| متغیر | مقدار |
|---|---|
| `BOT_TOKEN` | توکن BotFather |
| `REPLICATE_API_TOKEN` | توکن Replicate |

ربات خودش webhook رو روی آدرس Render تنظیم می‌کنه. لازم نیست کار دیگه‌ای بکنی.

### متغیرهای اختیاری
- `REPLICATE_VERSION`: نسخهٔ خاصی از مدل رو قفل می‌کنه (پیش‌فرض: آخرین نسخه)
- `MP3_BITRATE`: کیفیت خروجی (پیش‌فرض `192k`)

## اجرای محلی
```bash
pip install -r requirements.txt   # ffmpeg هم باید نصب باشه
export BOT_TOKEN=... REPLICATE_API_TOKEN=...
python app.py                     # بدون RENDER_EXTERNAL_URL در حالت polling اجرا می‌شه
```

## محدودیت‌ها
- حداکثر حجم فایل ورودی ۲۰ مگابایته (محدودیت تلگرام برای ربات‌ها).
- روی پلن رایگان Render، سرویس بعد از ۱۵ دقیقه بی‌کاری می‌خوابه. اولین پیام بعدش ممکنه حدود یک دقیقه طول بکشه تا جواب بیاد.

⚠️ این ریپو public هست. هیچ‌وقت توکن‌ها رو توی کد نذار.
