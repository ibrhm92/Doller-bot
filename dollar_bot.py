"""
بوت تليجرام لمتابعة سعر الدولار مقابل الجنيه المصري
-------------------------------------------------------
المتطلبات:
    pip install python-telegram-bot requests

الإعداد:
    1. اعمل بوت من @BotFather واحصل على TOKEN
    2. اعمل حساب مجاني على https://app.exchangerate-api.com وخد API KEY
    3. حط القيم في المتغيرات أدناه وشغّل

الأوامر:
    /start   — الاشتراك في التنبيهات
    /stop    — إلغاء الاشتراك
    /rate    — معرفة السعر الحالي فوراً
    /status  — عدد المشتركين (للأدمن)
"""

import asyncio
import json
import logging
import os
from datetime import datetime

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# =====================================================
# ⚙️ الإعدادات — عدّل هنا فقط
# =====================================================
TELEGRAM_TOKEN =    "8554012463:AAEhV7FRk1qeJp1kGi0BH_Z9CNCrt-W8qIs"
EXCHANGE_API_KEY ="8f9ff728280cb3a5ca050def"
ADMIN_CHAT_ID = 123456789                       # chat_id بتاعك عشان تستقبل /status

CHECK_INTERVAL_MINUTES = 5                      # كل كام دقيقة يتحقق من السعر
SUBSCRIBERS_FILE = "subscribers.json"           # ملف لحفظ المشتركين
# =====================================================

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── حفظ وتحميل المشتركين ──────────────────────────

def load_subscribers() -> set:
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_subscribers(subs: set):
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(list(subs), f)

subscribers: set = load_subscribers()

# ── جلب سعر الدولار ───────────────────────────────

def get_usd_egp() -> float | None:
    try:
        url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/pair/USD/EGP"
        res = requests.get(url, timeout=10)
        data = res.json()
        if data.get("result") == "success":
            return round(data["conversion_rate"], 2)
    except Exception as e:
        logger.error(f"خطأ في جلب السعر: {e}")
    return None

# ── أوامر البوت ────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in subscribers:
        await update.message.reply_text("✅ أنت مشترك بالفعل في تنبيهات سعر الدولار.")
        return

    subscribers.add(chat_id)
    save_subscribers(subscribers)

    rate = get_usd_egp()
    rate_text = f"السعر الحالي: *{rate} جنيه*" if rate else ""

    await update.message.reply_text(
        f"🎉 *تم الاشتراك بنجاح!*\n"
        f"هتوصلك رسالة كل ما سعر الدولار يتغير.\n\n"
        f"{rate_text}\n\n"
        f"لإلغاء الاشتراك: /stop\n"
        f"لمعرفة السعر الآن: /rate",
        parse_mode="Markdown"
    )
    logger.info(f"مشترك جديد: {chat_id} — إجمالي: {len(subscribers)}")

async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in subscribers:
        await update.message.reply_text("⚠️ أنت مش مشترك أصلاً.")
        return

    subscribers.discard(chat_id)
    save_subscribers(subscribers)
    await update.message.reply_text("🔕 تم إلغاء اشتراكك. مش هتوصلك تنبيهات.\nللاشتراك مجدداً: /start")
    logger.info(f"إلغاء اشتراك: {chat_id} — إجمالي: {len(subscribers)}")

async def cmd_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rate = get_usd_egp()
    now = datetime.now().strftime("%H:%M - %d/%m/%Y")
    if rate:
        await update.message.reply_text(
            f"💵 *سعر الدولار الآن*\n\n"
            f"1 USD = *{rate} EGP*\n\n"
            f"🕐 {now}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ مش قادر أجيب السعر دلوقتي، حاول بعد شوية.")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ الأمر ده للأدمن بس.")
        return
    rate = get_usd_egp()
    await update.message.reply_text(
        f"📊 *إحصائيات البوت*\n\n"
        f"👥 المشتركين: {len(subscribers)}\n"
        f"💵 السعر الحالي: {rate} EGP\n"
        f"🔄 التحقق كل: {CHECK_INTERVAL_MINUTES} دقيقة",
        parse_mode="Markdown"
    )

# ── مهمة المراقبة في الخلفية ───────────────────────

async def monitor_rate(app: Application):
    """تشتغل في الخلفية وتتحقق من السعر كل فترة"""
    last_rate = None
    logger.info("✅ بدأت مراقبة سعر الدولار...")

    while True:
        await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)

        rate = get_usd_egp()
        if rate is None:
            continue

        if last_rate is not None and rate != last_rate:
            direction = "📈" if rate > last_rate else "📉"
            diff = round(abs(rate - last_rate), 2)
            now = datetime.now().strftime("%H:%M - %d/%m/%Y")

            message = (
                f"{direction} *تغيّر سعر الدولار!*\n\n"
                f"السعر الجديد: *{rate} EGP*\n"
                f"السعر السابق: {last_rate} EGP\n"
                f"الفرق: {'+' if rate > last_rate else '-'}{diff} جنيه\n\n"
                f"🕐 {now}"
            )

            dead_subs = set()
            for chat_id in list(subscribers):
                try:
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"فشل إرسال لـ {chat_id}: {e}")
                    # لو البوت اتحذف من المحادثة، شيل المشترك
                    if "blocked" in str(e).lower() or "not found" in str(e).lower():
                        dead_subs.add(chat_id)

            if dead_subs:
                subscribers.difference_update(dead_subs)
                save_subscribers(subscribers)
                logger.info(f"تم حذف {len(dead_subs)} مشترك غير نشط")

            logger.info(f"تم إرسال التنبيه: {last_rate} ← {rate} لـ {len(subscribers)} مشترك")

        last_rate = rate

# ── التشغيل ────────────────────────────────────────

async def post_init(app: Application):
    asyncio.create_task(monitor_rate(app))

def main():
    print("🤖 بوت سعر الدولار شغّال...")
    print(f"👥 المشتركين الحاليين: {len(subscribers)}")
    print(f"🔄 التحقق كل {CHECK_INTERVAL_MINUTES} دقيقة")
    print("اضغط Ctrl+C للإيقاف\n")

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("rate", cmd_rate))
    app.add_handler(CommandHandler("status", cmd_status))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
