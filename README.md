# Goldbot 🥇

ربات تلگرامی که طلا، ماژورهای فارکس و بیت‌کوین را به روش **پرایس اکشن ال بروکس** (Al Brooks) تحلیل می‌کند و ستاپ‌ها را به تلگرام می‌فرستد.

- **منطق تشخیص:** از ریپازیتوری `price-action-skills-albrooks`
- **اتصال به داده:** وب‌سوکت TradingView، همان روشی که در `BardiaqTradingbot` استفاده شده است (OANDA → FOREXCOM → FX_IDC)

## نمادها
🥇 XAUUSD · 🇪🇺 EURUSD · 🇬🇧 GBPUSD · 🇯🇵 USDJPY · 🇨🇭 USDCHF · 🇨🇦 USDCAD · 🇦🇺 AUDUSD · 🇳🇿 NZDUSD · ₿ BTCUSD

برای اضافه یا حذف کردن نماد، فهرست `SYMBOLS` در `bot/config.py` را ویرایش کنید.

## چه چیزهایی را تشخیص می‌دهد
| مورد | توضیح |
|---|---|
| فاز بازار | Bull Trend / Bear Trend / Trading Range، از روی ۱۵ کندل آخر نسبت به EMA 20 |
| نوع کندل | Trend bar (بدنه ≥ ۴۵٪)، Doji (بدنه < ۲۵٪)، Trading Range |
| H1 / H2 | پولبک اول و دوم در روند صعودی (بالای EMA 20) |
| L1 / L2 | پولبک اول و دوم در روند نزولی (زیر EMA 20) |
| سوئینگ‌ها | Swing High / Swing Low با ۳ کندل در هر طرف، که سطوح حمایت و مقاومت را می‌سازند |
| Wedge | سه فشار: Wedge Bottom (احتمال برگشت صعودی) و Wedge Top (احتمال برگشت نزولی) |

## در تلگرام
- `/start`: ثبت‌نام برای دریافت هشدارها
- `/analyze EURUSD` یا دکمه‌ی نماد: گزارش کامل وضعیت فعلی همراه با نمودار (بدون نام نماد: XAUUSD)
- هشدار زنده: بعد از بسته شدن هر کندل، اگر ستاپ تازه‌ای (پیش‌فرض: H2، L2 و Wedge) تشکیل شده باشد

## ساختار
| فایل | کاربرد |
|---|---|
| `bot/data.py` | دریافت کندل از TradingView |
| `bot/strategy.py` | منطق تشخیص ال بروکس |
| `bot/chart.py` | رسم نمودار با علامت‌گذاری ستاپ‌ها |
| `bot/messages.py` | متن پیام‌ها |
| `bot/scanner.py` | حلقه‌ی اسکن زنده |
| `bot/telegram_bot.py` | دستورها و ارسال پیام |
| `bot/storage.py` | کاربران: Postgres اگر `DATABASE_URL` باشد، وگرنه `bot_state.json` |
| `bot/main.py` | نقطه‌ی شروع (وب‌سرور + اسکنر + تلگرام) |

## متغیرهای محیطی (Render → Environment)
| متغیر | توضیح |
|---|---|
| `BOT_TOKEN` | توکن ربات از BotFather (ضروری) |
| `CHANNEL_ID` | اختیاری: کانال یا گروهی که هشدارها به آن هم ارسال شود، مثلاً `@mychannel`. ربات باید در کانال ادمین باشد |
| `TIMEFRAME` | تایم‌فریم: `1`، `5`، `15`، `60`، `240`، `D` (پیش‌فرض `5`) |
| `ALERT_SETUPS` | ستاپ‌هایی که هشدار می‌دهند (پیش‌فرض `H2,L2,WEDGE`) |
| `BARS` | تعداد کندل برای هر تحلیل (پیش‌فرض `500`) |
| `DATABASE_URL` | اختیاری: Postgres تا لیست کاربران با هر دیپلوی پاک نشود |

`REPLICATE_API_TOKEN` دیگر لازم نیست و می‌شود از Render پاکش کرد.

## اجرا
```bash
pip install -r requirements.txt
BOT_TOKEN=... python -m bot.main
```

## تست
```bash
python -m unittest discover -s tests -v
```

⚠️ این ابزار فقط برای آموزش و پژوهش است و توصیه‌ی مالی نیست.
⚠️ این ریپو public است. هیچ‌وقت توکن‌ها را داخل کد نگذارید.
