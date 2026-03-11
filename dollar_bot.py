"""
بوت تليجرام لمتابعة سعر الدولار في بنك مصر
المصدر: ta3weem.com (تحديث كل 2-3 دقايق)
-----------------------------------------------
pip install python-telegram-bot requests beautifulsoup4
"""

import asyncio
import json
import logging
import os
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# =====================================================
# ⚙️ الإعدادات
# =====================================================
TELEGRAM_TOKEN =    "8554012463:AAEhV7FRk1qeJp1kGi0BH_Z9CNCrt-W8qIs"
ADMIN_CHAT_ID   = int(os.environ.get("ADMIN_CHAT_ID", "0"))

CHECK_INTERVAL_MINUTES = 3
SUBSCRIBERS_FILE       = "subscribers.json"
# =====================================================

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── المشتركين ─────────────────────────────────────

def load_subscribers() -> set:
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE) as f:
            return set(json.load(f))
    return set()

def save_subscribers(subs: set):
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(list(subs), f)

subscribers: set = load_subscribers()

# ── جلب السعر من Ta3weem (بنك مصر) ───────────────

def get_banque_misr_rate() -> dict | None:
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 10) "
                "AppleWebKit/537.36 Chrome/120 Safari/537.36"
            )
        }
        url = "https://ta3weem.com/ar/banks/banque-misr-bm"
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        rows = soup.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            text  = " ".join(c.get_text(strip=True) for c in cells)
            if "USD" in text or "دولار" in text or "Dollar" in text:
                nums = []
                for c in cells:
                    t = c.get_text(strip=True).replace(",", "")
                    try:
                        nums.append(float(t))
                    except ValueError:
                        pass
                if len(nums) >= 2:
                    return {
                        "buy":  nums[0],
                        "sell": nums[1],
                        "time": datetime.now().strftime("%H:%M - %d/%m/%Y")
                    }

        # fallback
        all_nums = []
        for tag in soup.find_all(string=True):
            t = tag.strip().replace(",", "")
            try:
                v = float(t)
                if 40 < v < 70:
                    all_nums.append(v)
            except ValueError:
                pass

        if len(all_nums) >= 2:
            return {
                "buy":  all_nums[0],
                "sell": all_nums[1],
                "time": datetime.now().strftime("%H:%M - %d/%m/%Y")
            }

    except Exception as e:
        logger.error(f"خطأ في جلب السعر: {e}")
    return None

# ── أوامر البوت ────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in subscribers:
        await update.message.reply_text("✅ أنت مشترك بالفعل.")
        return

    subscribers.add(chat_id)
    save_subscribers(subscribers)

    data = get_banque_misr_rate()
    rate_text = (
        f"السعر الحالي في *بنك مصر*:\n"
        f"شراء: *{data['buy']} EGP* | بيع: *{data['sell']} EGP*"
        if data else ""
    )

    await update.message.reply_text(
        f"🎉 *تم الاشتراك بنجاح!*\n"
        f"هتوصلك رسالة كل ما سعر الدولار في بنك مصر يتغير.\n\n"
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
    data = get_banque_misr_rate()
    if data:
        await update.message.reply_text(
            f"🏦 *سعر الدولار - بنك مصر*\n\n"
            f"🟢 شراء: *{data['buy']} EGP*\n"
            f"🔴 بيع:  *{data['sell']} EGP*\n\n"
            f"🕐 {data['time']}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ مش قادر أجيب السعر دلوقتي.")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ADMIN_CHAT_ID and update.effective_chat.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ للأدمن بس.")
        return
    data = get_banque_misr_rate()
    rate_text = f"شراء {data['buy']} | بيع {data['sell']}" if data else "غير متاح"
    await update.message.reply_text(
        f"📊 *إحصائيات البوت*\n\n"
        f"👥 المشتركين: {len(subscribers)}\n"
        f"💵 السعر الحالي: {rate_text}\n"
        f"🔄 التحقق كل: {CHECK_INTERVAL_MINUTES} دقايق\n"
        f"🏦 المصدر: Ta3weem / بنك مصر",
        parse_mode="Markdown"
    )

# ── مراقبة السعر في الخلفية ────────────────────────

async def monitor_rate(app: Application):
    last_sell = None
    logger.info("✅ بدأت مراقبة سعر بنك مصر...")

    while True:
        await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)

        data = get_banque_misr_rate()
        if not data:
            continue

        current_sell = data["sell"]

        if last_sell is not None and current_sell != last_sell:
            direction = "📈" if current_sell > last_sell else "📉"
            diff = round(abs(current_sell - last_sell), 4)
            sign = "+" if current_sell > last_sell else "-"

            message = (
                f"{direction} *تغيّر سعر الدولار في بنك مصر!*\n\n"
                f"🟢 شراء: *{data['buy']} EGP*\n"
                f"🔴 بيع:  *{data['sell']} EGP*\n\n"
                f"التغيير: *{sign}{diff} جنيه*\n"
                f"🕐 {data['time']}"
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

            logger.info(f"تنبيه: بيع {last_sell} ← {current_sell} | {len(subscribers)} مشترك")

        last_sell = current_sell

async def post_init(app: Application):
    asyncio.create_task(monitor_rate(app))

def main():
    print("🤖 بوت سعر الدولار (بنك مصر) شغال...")
    print(f"🔄 التحقق كل {CHECK_INTERVAL_MINUTES} دقايق")

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
