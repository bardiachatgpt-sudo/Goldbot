import os
import time
import threading
from datetime import datetime
import pytz
from flask import Flask
import telebot
import yfinance as yf
import pandas as pd
import numpy as np

# ۱. وب‌سرور برای روشن ماندن ۲۴ ساعته در Hugging Face
app = Flask(__name__)

@app.route('/')
def home():
    return "Al Brooks M5 Price Action Engine (XAU/USD) is Running 24/7!"

def run_web():
    app.run(host="0.0.0.0", port=7860)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

subscribed_users = set()
active_trade = None       # معامله فعال یا سفارش Stop در انتظار فعال‌سازی
stats = {"wins": 0, "losses": 0, "cancelled": 0}
last_pre_alert_time = None
last_signal_time = None

# ۲. دریافت دیتای ۵ دقیقه طلا و محاسبه EMA 20 (تنها ابزار ال بروکس)
def get_al_brooks_data():
    df = yf.download("GC=F", period="5d", interval="5m", progress=False)
    if df.empty or len(df) < 50:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # تنها اندیکاتور ال بروکس: EMA 20
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()

    # محاسبه ATR صرفاً برای سنجش مقیاس کندل‌ها در طلا (جلوگیری از کندل‌های میکروسکوپی)
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    true_range = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1)
    df['ATR'] = true_range.rolling(14).mean()

    return df

# ۳. رادار تشخیص «سیم خاردار» (Barb Wire) و تریدینگ رنج تنگ به سبک ال بروکس
def is_barb_wire(df_slice):
    """
    بررسی ۵ کندل اخیر: اگر کندل‌ها مدام EMA20 را قطع کرده‌اند، همپوشانی شدید دارند
    و بیش از ۲ کندل دوجی (بدنه کوچک) وجود دارد -> سیم خاردار است (معامله ممنوع!)
    """
    last5 = df_slice.iloc[-5:]
    doji_count = 0
    ema_crosses = 0

    for _, row in last5.iterrows():
        rng = float(row['High'] - row['Low'])
        body = abs(float(row['Close'] - row['Open']))
        ema = float(row['EMA20'])

        if rng > 0 and (body / rng) < 0.30:
            doji_count += 1
        if float(row['Low']) <= ema <= float(row['High']):
            ema_crosses += 1

    # اگر حداقل ۴ کندل از ۵ کندل روی EMA20 گیر کرده‌اند و حداقل ۲ دوجی داریم = سیم خاردار!
    if ema_crosses >= 4 and doji_count >= 2:
        return True
    return False

# ۴. تشخیص چرخه بازار ال بروکس: Always In Long یا Always In Short
def get_market_cycle(df_slice):
    """
    بررسی ۱۵ کندل اخیر برای تشخیص روند قطعی (Spike & Channel)
    """
    if is_barb_wire(df_slice):
        return "BARB_WIRE (سیم خاردار - رنج خطرناک)"

    last15 = df_slice.iloc[-15:]
    above_ema = sum(last15['Close'] > last15['EMA20'])
    below_ema = sum(last15['Close'] < last15['EMA20'])

    ema_now = float(last15['EMA20'].iloc[-1])
    ema_prev = float(last15['EMA20'].iloc[-6])
    ema_slope = ema_now - ema_prev

    if above_ema >= 11 and ema_slope > 0.5:
        return "ALWAYS_IN_LONG"
    elif below_ema >= 11 and ema_slope < -0.5:
        return "ALWAYS_IN_SHORT"
    else:
        return "TRADING_RANGE"

# ۵. شمارش لگ‌ها (H1 / H2 برای خرید و L1 / L2 برای فروش) + کالبدشکافی کندل سیگنال
def analyze_al_brooks_setup(df_closed):
    """
    df_closed دیتافریمی است که آخرین ردیف آن، کندل ۵ دقیقه‌ای است که همین الان بسته شده (Signal Bar).
    """
    cycle = get_market_cycle(df_closed)
    sb = df_closed.iloc[-1]       # Signal Bar (کندل سیگنال)
    prev1 = df_closed.iloc[-2]    # کندل قبل از سیگنال
    prev2 = df_closed.iloc[-3]
    prev3 = df_closed.iloc[-4]
    prev4 = df_closed.iloc[-5]

    sb_high = float(sb['High'])
    sb_low = float(sb['Low'])
    sb_open = float(sb['Open'])
    sb_close = float(sb['Close'])
    sb_ema = float(sb['EMA20'])
    sb_atr = float(sb['ATR'])

    sb_range = sb_high - sb_low
    if sb_range < (sb_atr * 0.4) or sb_range > (sb_atr * 2.8):
        # کندل نباید بیش از حد ریز (بی‌جان) یا بیش از حد غول‌پیکر (Exhaustion/Climactic) باشد
        return None

    # موقعیت بسته شدن کندل (۰ یعنی کفِ کندل، ۱ یعنی سقفِ کندل)
    close_position = (sb_close - sb_low) / sb_range

    # -------------------------------------------------------------------------
    # الف) بررسی ستاپ خرید ال بروکس: Always In Long + Pullback to EMA20 (H1/H2)
    # -------------------------------------------------------------------------
    if cycle == "ALWAYS_IN_LONG":
        # ۱. آیا قیمت به EMA 20 پولبک زده و آن را لمس/تست کرده است؟
        touched_ema = (sb_low <= sb_ema + (sb_atr * 0.25)) or (float(prev1['Low']) <= float(prev1['EMA20']) + (sb_atr * 0.2))

        # ۲. آیا کندل قبل یا خود کندل سیگنال یک اصلاح (کف پایین‌تر از کندل‌های قبلی) ایجاد کرده؟
        is_pullback = (sb_low < float(prev2['Low'])) or (float(prev1['Low']) < float(prev3['Low']))

        # ۳. آناتومی کندل سیگنال صعودی ال بروکس:
        # باید بالای EMA20 بسته شود و کلوز آن در ۳۵٪ بالایی کندل باشد (کندل روند صعودی یا پین‌بار صعودی قوی)
        valid_bull_sb = (sb_close > sb_ema) and (close_position >= 0.65) and (sb_close >= sb_open)

        if touched_ema and is_pullback and valid_bull_sb:
            # تشخیص اینکه ستاپ H1 است یا ستاپ طلایی H2 (دو لگ اصلاحی)
            leg_type = "H1 (اولین پولبک به EMA20)"
            if float(prev2['High']) > float(prev3['High']) and float(prev1['Low']) < float(prev2['Low']):
                leg_type = "H2 (ستاپ طلایی دو لِگه - High 2 Bull Flag) ⭐"

            # فرمول سفارش‌گذاری ال بروکس:
            # ورود: ۲۰ سنت (۲ پیپ) بالاتر از سقف کندل سیگنال (Buy Stop)
            # استاپ: ۲۰ سنت پایین‌تر از کف کندل سیگنال یا کف کندل قبلی (هر کدام پایین‌تر بود)
            entry_stop = sb_high + 0.20
            swing_low = min(sb_low, float(prev1['Low'])) - 0.20
            risk = max(entry_stop - swing_low, max(sb_atr * 1.2, 2.0)) # حداقل ۲ دلار استاپ برای جلوگیری از شدو
            sl = entry_stop - risk
            tp = entry_stop + (risk * 2.0) # ریوارد دقیق ۱ به ۲ (Measured Move)

            return {
                "type": "BUY_STOP",
                "setup_name": leg_type,
                "signal_bar_high": sb_high,
                "signal_bar_low": sb_low,
                "entry": entry_stop,
                "sl": sl,
                "tp": tp,
                "risk": risk,
                "reward": risk * 2.0,
                "candles_waited": 0
            }

    # -------------------------------------------------------------------------
    # ب) بررسی ستاپ فروش ال بروکس: Always In Short + Pullback to EMA20 (L1/L2)
    # -------------------------------------------------------------------------
    elif cycle == "ALWAYS_IN_SHORT":
        # ۱. آیا قیمت در اصلاح رو به بالا به EMA 20 رسیده است؟
        touched_ema = (sb_high >= sb_ema - (sb_atr * 0.25)) or (float(prev1['High']) >= float(prev1['EMA20']) - (sb_atr * 0.2))

        # ۲. آیا یک اصلاح رو به بالا (سقف بالاتر نسبت به کندل‌های قبل) شکل گرفته؟
        is_pullback = (sb_high > float(prev2['High'])) or (float(prev1['High']) > float(prev3['High']))

        # ۳. آناتومی کندل سیگنال نزولی ال بروکس:
        # باید زیر EMA20 بسته شود و کلوز آن در ۳۵٪ پایینی کندل باشد (کندل روند نزولی یا ریورسال بار نزولی)
        valid_bear_sb = (sb_close < sb_ema) and (close_position <= 0.35) and (sb_close <= sb_open)

        if touched_ema and is_pullback and valid_bear_sb:
            leg_type = "L1 (اولین پولبک به EMA20)"
            if float(prev2['Low']) < float(prev3['Low']) and float(prev1['High']) > float(prev2['High']):
                leg_type = "L2 (ستاپ طلایی دو لِگه - Low 2 Bear Flag) ⭐"

            entry_stop = sb_low - 0.20
            swing_high = max(sb_high, float(prev1['High'])) + 0.20
            risk = max(swing_high - entry_stop, max(sb_atr * 1.2, 2.0))
            sl = entry_stop + risk
            tp = entry_stop - (risk * 2.0)

            return {
                "type": "SELL_STOP",
                "setup_name": leg_type,
                "signal_bar_high": sb_high,
                "signal_bar_low": sb_low,
                "entry": entry_stop,
                "sl": sl,
                "tp": tp,
                "risk": risk,
                "reward": risk * 2.0,
                "candles_waited": 0
            }

    return None

def broadcast(text):
    if not bot:
        return
    for chat_id in list(subscribed_users):
        try:
            bot.send_message(chat_id, text, parse_mode="Markdown")
        except Exception as e:
            print(f"Telegram error: {e}")

# ۶. حلقه اصلی اسکنر ۲۴ ساعته بازار طلا
def al_brooks_scanner():
    global active_trade, last_pre_alert_time, last_signal_time, stats

    while True:
        try:
            if not subscribed_users:
                time.sleep(10)
                continue

            now_utc = datetime.now(pytz.utc)
            df = get_al_brooks_data()
            if df is None:
                time.sleep(15)
                continue

            live_bar = df.iloc[-1]       # کندل زنده در حال حرکت
            closed_df = df.iloc[:-1]     # دیتافریم کندل‌های بسته شده قطعی
            live_time = df.index[-1]
            closed_time = closed_df.index[-1]

            live_high = float(live_bar['High'])
            live_low = float(live_bar['Low'])
            live_close = float(live_bar['Close'])

            # -----------------------------------------------------------------
            # بخش اول: مدیریت سفارش‌های شرطی (Buy Stop / Sell Stop) و معاملات باز
            # -----------------------------------------------------------------
            if active_trade:
                status = active_trade['type']

                # ۱. اگر سفارش هنوز در حالت انتظار شکست سقف/کف کندل سیگنال است (Pending Stop)
                if status == "BUY_STOP":
                    if live_high >= active_trade['entry']:
                        active_trade['type'] = "BUY_ACTIVE"
                        broadcast(
                            f"⚡ **سقف کندل سیگنال شکسته شد! (ورود به BUY فعال شد - Entry Bar)** 🟢\n"
                            f"حالا معامله با ریسک به ریوارد ۱ به ۲ در جریان است..."
                        )
                    elif live_low < active_trade['signal_bar_low'] or (closed_time != active_trade.get('signal_time')):
                        # قانون ال بروکس: اگر کندل بعدی سقف کندل سیگنال را نشکند، سفارش باطل می‌شود!
                        stats['cancelled'] += 1
                        broadcast(
                            f"🚫 **سفارش Buy Stop باطل شد (قانون ال بروکس)!**\n"
                            f"کندل بعدی موفق نشد سقف کندل سیگنال را بشکند. به لطف ورود شرطی ال بروکس، از ورود به یک معامله ضعیف محافظت شدیم! 🛡️"
                        )
                        active_trade = None

                elif status == "SELL_STOP":
                    if live_low <= active_trade['entry']:
                        active_trade['type'] = "SELL_ACTIVE"
                        broadcast(
                            f"⚡ **کف کندل سیگنال شکسته شد! (ورود به SELL فعال شد - Entry Bar)** 🔴\n"
                            f"حالا معامله با ریسک به ریوارد ۱ به ۲ در جریان است..."
                        )
                    elif live_high > active_trade['signal_bar_high'] or (closed_time != active_trade.get('signal_time')):
                        stats['cancelled'] += 1
                        broadcast(
                            f"🚫 **سفارش Sell Stop باطل شد (قانون ال بروکس)!**\n"
                            f"کندل بعدی موفق نشد کف کندل سیگنال را بشکند. سفارش Pending را حذف کنید! 🛡️"
                        )
                        active_trade = None

                # ۲. اگر معامله فعال شده است، بررسی برخورد به TP (ریوارد ۲) یا SL
                elif status == "BUY_ACTIVE":
                    if live_high >= active_trade['tp']:
                        stats['wins'] += 1
                        tot = stats['wins'] + stats['losses']
                        wr = (stats['wins'] / tot) * 100
                        broadcast(f"🎯 **تارگت ۱ به ۲ ال بروکس زده شد! (+2R سود خالص)** ✅\n🏆 وین‌ریت فعلی: **{wr:.1f}%** ({stats['wins']} برد / {stats['losses']} باخت)")
                        active_trade = None
                    elif live_low <= active_trade['sl']:
                        stats['losses'] += 1
                        tot = stats['wins'] + stats['losses']
                        wr = (stats['wins'] / tot) * 100
                        broadcast(f"🛑 **استاپ‌لاس زیر کندل سیگنال فعال شد (-1R).**\n🏆 وین‌ریت فعلی: **{wr:.1f}%** ({stats['wins']} برد / {stats['losses']} باخت)")
                        active_trade = None

                elif status == "SELL_ACTIVE":
                    if live_low <= active_trade['tp']:
                        stats['wins'] += 1
                        tot = stats['wins'] + stats['losses']
                        wr = (stats['wins'] / tot) * 100
                        broadcast(f"🎯 **تارگت ۱ به ۲ ال بروکس زده شد! (+2R سود خالص)** ✅\n🏆 وین‌ریت فعلی: **{wr:.1f}%** ({stats['wins']} برد / {stats['losses']} باخت)")
                        active_trade = None
                    elif live_high >= active_trade['sl']:
                        stats['losses'] += 1
                        tot = stats['wins'] + stats['losses']
                        wr = (stats['wins'] / tot) * 100
                        broadcast(f"🛑 **استاپ‌لاس بالای کندل سیگنال فعال شد (-1R).**\n🏆 وین‌ریت فعلی: **{wr:.1f}%** ({stats['wins']} برد / {stats['losses']} باخت)")
                        active_trade = None

            # -----------------------------------------------------------------
            # بخش دوم: شکار ستاپ جدید ال بروکس (اگر معامله‌ای باز نیست)
            # -----------------------------------------------------------------
            if active_trade is None:
                minute_mod = now_utc.minute % 5

                # الف) آژیر آماده‌باش ۲ دقیقه قبل از بسته شدن کندل ۵ دقیقه (دقیقه ۳)
                if minute_mod == 3 and last_pre_alert_time != live_time:
                    cycle = get_market_cycle(closed_df)
                    ema20 = float(live_bar['EMA20'])
                    atr = float(live_bar['ATR'])

                    if cycle == "ALWAYS_IN_LONG" and abs(live_low - ema20) <= (atr * 0.4):
                        last_pre_alert_time = live_time
                        broadcast(
                            f"⚠️ **آژیر ۲ دقیقه‌ای ال بروکس (XAU/USD - M5)**\n\n"
                            f"📈 وضعیت بازار: **Always In Long (روند صعودی قوی)**\n"
                            f"🧲 قیمت طلا در حال تست میانگین **EMA 20** و تشکیل کندل سیگنال (H1/H2) است!\n"
                            f"📱 **همین الان متاتریدر را باز کن!** اگر ۲ دقیقه دیگر این کندل در یک‌سوم بالایی بسته شود، دستور **Buy Stop** صادر می‌شود."
                        )
                    elif cycle == "ALWAYS_IN_SHORT" and abs(live_high - ema20) <= (atr * 0.4):
                        last_pre_alert_time = live_time
                        broadcast(
                            f"⚠️ **آژیر ۲ دقیقه‌ای ال بروکس (XAU/USD - M5)**\n\n"
                            f"📉 وضعیت بازار: **Always In Short (روند نزولی قوی)**\n"
                            f"🧲 قیمت طلا در حال تست میانگین **EMA 20** و تشکیل کندل سیگنال (L1/L2) است!\n"
                            f"📱 **همین الان متاتریدر را باز کن!** اگر ۲ دقیقه دیگر این کندل در یک‌سوم پایینی بسته شود، دستور **Sell Stop** صادر می‌شود."
                        )

                # ب) بررسی قطعی کندل سیگنال دقیقاً در لحظه بسته شدن کندل ۵ دقیقه (دقیقه ۰ و ۵)
                if minute_mod == 0 and last_signal_time != closed_time:
                    setup = analyze_al_brooks_setup(closed_df)
                    last_signal_time = closed_time

                    if setup:
                        setup['signal_time'] = closed_time
                        active_trade = setup
                        risk_d = setup['risk']
                        rew_d = setup['reward']

                        if setup['type'] == "BUY_STOP":
                            broadcast(
                                f"🟢 **سیگنال پرایس اکشن ال بروکس (BUY STOP - طلا ۵ دقیقه)** 🟢\n\n"
                                f"📚 **ستاپ تشخیص داده شده:** `{setup['setup_name']}`\n"
                                f"✅ کندل سیگنال روی EMA 20 با کلوز قوی در یک‌سوم بالایی بسته شد!\n\n"
                                f"🛠️ **نحوه ورود دقیق به سبک ال بروکس:**\n"
                                f"۱. سفارش **Buy Stop** خود را **۲۰ سنت (۲ پیپ) بالاتر از سقف کندلی که همین الان بسته شد** قرار دهید (یا به محض شکستن سقف کندل قبلی وارد شوید).\n"
                                f"۲. 🛑 **فاصله حد ضرر (SL):** `${risk_d:.2f}-` ({risk_d*10:.0f} پیپ پایین‌تر از نقطه ورود - زیر کف کندل سیگنال)\n"
                                f"۳. 🎯 **فاصله حد سود (TP - 1:2):** `${rew_d:.2f}+` ({rew_d*10:.0f} پیپ بالاتر از نقطه ورود)\n\n"
                                f"⚠️ *قانون طلایی بروکس: اگر کندل ۵ دقیقه جدید تمام شد و سقف کندل سیگنال را نشکست، وارد نشوید و سفارش را حذف کنید!*"
                            )
                        elif setup['type'] == "SELL_STOP":
                            broadcast(
                                f"🔴 **سیگنال پرایس اکشن ال بروکس (SELL STOP - طلا ۵ دقیقه)** 🔴\n\n"
                                f"📚 **ستاپ تشخیص داده شده:** `{setup['setup_name']}`\n"
                                f"✅ کندل سیگنال زیر EMA 20 با کلوز قوی در یک‌سوم پایینی بسته شد!\n\n"
                                f"🛠️ **نحوه ورود دقیق به سبک ال بروکس:**\n"
                                f"۱. سفارش **Sell Stop** خود را **۲۰ سنت (۲ پیپ) پایین‌تر از کف کندلی که همین الان بسته شد** قرار دهید (یا به محض شکستن کف کندل قبلی وارد شوید).\n"
                                f"۲. 🛑 **فاصله حد ضرر (SL):** `${risk_d:.2f}+` ({risk_d*10:.0f} پیپ بالاتر از نقطه ورود - بالای سقف کندل سیگنال)\n"
                                f"۳. 🎯 **فاصله حد سود (TP - 1:2):** `${rew_d:.2f}-` ({rew_d*10:.0f} پیپ پایین‌تر از نقطه ورود)\n\n"
                                f"⚠️ *قانون طلایی بروکس: اگر کندل ۵ دقیقه جدید تمام شد و کف کندل سیگنال را نشکست، وارد نشوید و سفارش را حذف کنید!*"
                            )

        except Exception as e:
            print(f"Al Brooks Engine Error: {e}")

        time.sleep(15)

# ۷. دستورات تلگرام برای گزارش لحظه‌ای پرایس اکشن
if bot:
    @bot.message_handler(commands=['start'])
    def start_cmd(message):
        subscribed_users.add(message.chat.id)
        bot.reply_to(
            message,
            "👨‍🏫 **موتور پرایس اکشن ال بروکس (XAU/USD - تایم ۵ دقیقه) فعال شد!**\n\n"
            "📌 **قوانین فعال در هسته ربات:**\n"
            "1️⃣ تنها اندیکاتور: **EMA 20** (بدون هیچ اندیکاتور اضافی)\n"
            "2️⃣ تشخیص چرخه بازار: **Always In Long / Short**\n"
            "3️⃣ فیلتر هوشمند **Barb Wire (سیم خاردار)**: قفل کردن ربات در بازارهای رنج و دوجی\n"
            "4️⃣ شکار ستاپ‌های **H1 / H2** و **L1 / L2** با بررسی آناتومی کندل سیگنال (بسته شدن در ۱/۳ بالایی یا پایینی)\n"
            "5️⃣ ورود شرطی (**Buy Stop / Sell Stop** بالای سقف/کف کندل سیگنال) با ریوارد دقیق **۱ به ۲**\n\n"
            "برای دیدن تحلیل لحظه‌ای چارت ۵ دقیقه طلا به سبک ال بروکس، دستور `/status` را بزنید.",
            parse_mode="Markdown"
        )

    @bot.message_handler(commands=['status'])
    def status_cmd(message):
        df = get_al_brooks_data()
        if df is None:
            bot.reply_to(message, "⏳ در حال دریافت کندل‌های ۵ دقیقه طلا...")
            return

        closed_df = df.iloc[:-1]
        cycle = get_market_cycle(closed_df)
        last_bar = closed_df.iloc[-1]
        tot = stats['wins'] + stats['losses']
        wr = (stats['wins'] / tot * 100) if tot > 0 else 0.0

        cycle_fa = {
            "ALWAYS_IN_LONG": "🟢 Always In Long (اسپایک/کانال صعودی - فقط شکار H1/H2)",
            "ALWAYS_IN_SHORT": "🔴 Always In Short (اسپایک/کانال نزولی - فقط شکار L1/L2)",
            "TRADING_RANGE": "🟡 Trading Range (در حال نوسان - منتظر شفاف شدن روند)",
            "BARB_WIRE (سیم خاردار - رنج خطرناک)": "⛔ Barb Wire (سیم خاردار تشخیص داده شد! ترید مطلقاً ممنوع)"
        }.get(cycle, cycle)

        bot.reply_to(
            message,
            f"📊 **خوانش لحظه‌ای چارت ۵ دقیقه طلا از دید ال بروکس:**\n\n"
            f"🧭 **چرخه فعلی بازار:**\n{cycle_fa}\n\n"
            f"🧲 فاصله قیمت از EMA 20: **${abs(float(last_bar['Close'] - last_bar['EMA20'])):.2f}**\n"
            f"📏 میانگین قد کندل‌ها (ATR): **${float(last_bar['ATR']):.2f}**\n\n"
            f"🏆 **کارنامه پرایس اکشن ال بروکس:**\n"
            f"✅ تارگت (1:2): `{stats['wins']}` | ❌ استاپ: `{stats['losses']}`\n"
            f"🛡️ سفارش‌های باطل‌شده (نجات از ضرر به لطف Stop Order): `{stats['cancelled']}`\n"
            f"📈 وین‌ریت خالص: **{wr:.1f}%**",
            parse_mode="Markdown"
        )

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    threading.Thread(target=al_brooks_scanner, daemon=True).start()

    if bot:
        print("🤖 Al Brooks Price Action Bot Started!")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
