"""
بوت تليجرام لمتابعة سعر الدولار (فوركس - لحظي)
المصدر: exchangerate-api.com (مجاني - تحديث كل 30 ثانية)
-----------------------------------------------
pip install python-telegram-bot requests
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
TELEGRAM_TOKEN         ="8554012463:AAEhV7FRk1qeJp1kGi0BH_Z9CNCrt-W8qIs"
EXCHANGE_API_KEY       = "06676dfc06882d45737efeca"
ADMIN_CHAT_ID          = int(os.environ.get("ADMIN_CHAT_ID", "0"))
CHECK_INTERVAL_SECONDS = 15         # كل 30 ثانية
MIN_CHANGE             = 0.001       # أقل تغيير يستحق تنبيه (5 قروش)
SUBSCRIBERS_FILE       = "subscribers.json"
# =====================================================

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ── المشتركين ──────────────────────────────────────

def load_subscribers() -> set:
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE) as f:
            return set(json.load(f))
    return set()

def save_subscribers(subs: set):
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(list(subs), f)

subscribers: set = load_subscribers()

# ── جلب السعر من الفوركس ───────────────────────────

def get_forex_rate() -> float | None:
    try:
        url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/pair/USD/EGP"
        res  = requests.get(url, timeout=10)
        data = res.json()
        if data.get("result") == "success":
            return round(data["conversion_rate"], 4)
    except Exception as e:
        logger.error(f"خطأ: {e}")
    return None

# ── أوامر البوت ────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in subscribers:
        await update.message.reply_text("✅ أنت مشترك بالفعل.")
        return

    subscribers.add(chat_id)
    save_subscribers(subscribers)

    rate = get_forex_rate()
    rate_text = f"السعر الحالي: *{rate} EGP*" if rate else ""

    await update.message.reply_text(
        f"🎉 *تم الاشتراك بنجاح!*\n"
        f"هتوصلك تنبيه فور ما السعر يتغير أكتر من {MIN_CHANGE} جنيه.\n\n"
        f"{rate_text}\n\n"
        f"إلغاء الاشتراك: /stop\n"
        f"السعر الآن: /rate",
        parse_mode="Markdown"
    )
    logger.info(f"مشترك جديد: {chat_id}")

async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in subscribers:
        await update.message.reply_text("⚠️ أنت مش مشترك أصلاً.")
        return
    subscribers.discard(chat_id)
    save_subscribers(subscribers)
    await update.message.reply_text("🔕 تم إلغاء اشتراكك.")

async def cmd_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rate = get_forex_rate()
    if rate:
        now = datetime.now().strftime("%H:%M - %d/%m/%Y")
        await update.message.reply_text(
            f"💵 *سعر الدولار - فوركس لحظي*\n\n"
            f"1 USD = *{rate} EGP*\n\n"
            f"🕐 {now}\n"
            f"⚡ مصدر لحظي — قد يختلف قليلاً عن البنوك",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ مش قادر أجيب السعر دلوقتي.")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ADMIN_CHAT_ID and update.effective_chat.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ للأدمن بس.")
        return
    rate = get_forex_rate()
    await update.message.reply_text(
        f"📊 *إحصائيات البوت*\n\n"
        f"👥 المشتركين: {len(subscribers)}\n"
        f"💵 السعر الحالي: {rate} EGP\n"
        f"🔄 التحقق كل: {CHECK_INTERVAL_SECONDS} ثانية\n"
        f"📏 أقل تغيير للتنبيه: {MIN_CHANGE} جنيه\n"
        f"⚡ المصدر: فوركس لحظي",
        parse_mode="Markdown"
    )

# ── مراقبة السعر في الخلفية ────────────────────────

async def monitor_rate(app: Application):
    last_rate = None
    logger.info("✅ بدأت مراقبة سعر الفوركس (كل 30 ثانية)...")

    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

        rate = get_forex_rate()
        if rate is None:
            continue

        if last_rate is not None:
            diff = round(abs(rate - last_rate), 4)

            # بس لو التغيير أكبر من الحد الأدنى
            if diff >= MIN_CHANGE:
                direction = "📈" if rate > last_rate else "📉"
                sign      = "+" if rate > last_rate else "-"
                now       = datetime.now().strftime("%H:%M - %d/%m/%Y")

                message = (
                    f"{direction} *تحرّك سعر الدولار!*\n\n"
                    f"السعر الجديد: *{rate} EGP*\n"
                    f"السعر السابق: {last_rate} EGP\n"
                    f"التغيير: *{sign}{diff} جنيه*\n\n"
                    f"🕐 {now}\n"
                    f"⚡ مصدر لحظي — قد يختلف قليلاً عن البنوك"
                )

                dead = set()
                for cid in list(subscribers):
                    try:
                        await app.bot.send_message(cid, message, parse_mode="Markdown")
                    except Exception as e:
                        if "blocked" in str(e).lower() or "not found" in str(e).lower():
                            dead.add(cid)

                if dead:
                    subscribers.difference_update(dead)
                    save_subscribers(subscribers)

                logger.info(f"تنبيه: {last_rate} ← {rate} | فرق {diff} | {len(subscribers)} مشترك")
                last_rate = rate
        else:
            last_rate = rate

async def post_init(app: Application):
    asyncio.create_task(monitor_rate(app))

def main():
    print("🤖 بوت سعر الدولار (فوركس لحظي) شغال...")
    print(f"⚡ التحقق كل {CHECK_INTERVAL_SECONDS} ثانية")
    print(f"📏 أقل تغيير للتنبيه: {MIN_CHANGE} جنيه")

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("stop",   cmd_stop))
    app.add_handler(CommandHandler("rate",   cmd_rate))
    app.add_handler(CommandHandler("status", cmd_status))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
