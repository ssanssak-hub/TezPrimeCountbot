import os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Bot, Update
from dotenv import load_dotenv

# بارگذاری متغیرهای محیطی
load_dotenv()

# تنظیم لاگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# خواندن متغیرها
TOKEN = os.environ.get("TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not TOKEN:
    raise ValueError("TOKEN is required!")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID is required!")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is required!")

# ایجاد ربات
bot = Bot(token=TOKEN)
app = Flask(__name__)

# حلقه رویداد برای async
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# مقداردهی اولیه ربات
def initialize_bot():
    """مقداردهی اولیه ربات"""
    try:
        loop.run_until_complete(bot.initialize())
        logger.info("✅ Bot initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Bot initialization failed: {e}")
        return False

# مقداردهی اولیه در زمان اجرا
if not initialize_bot():
    logger.error("Failed to initialize bot! Exiting...")
    exit(1)

def send_message_sync(chat_id, text):
    """ارسال پیام به صورت sync (با استفاده از loop)"""
    try:
        loop.run_until_complete(bot.send_message(chat_id=chat_id, text=text))
        logger.info(f"Message sent to {chat_id}")
    except Exception as e:
        logger.error(f"Error sending message: {e}")

def set_webhook_sync():
    """تنظیم وب‌هوک به صورت sync"""
    try:
        loop.run_until_complete(bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}"))
        logger.info("Webhook set successfully")
        return True
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
        return False

@app.route("/", methods=["GET"])
def home():
    """صفحه اصلی"""
    try:
        # دریافت اطلاعات ربات
        bot_info = loop.run_until_complete(bot.get_me())
        bot_username = f"@{bot_info.username}" if bot_info.username else "unknown"
        
        return jsonify({
            "status": "running",
            "bot": bot_username,
            "webhook": WEBHOOK_URL,
            "admin_id": ADMIN_ID
        })
    except Exception as e:
        logger.error(f"Error in home: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    """دریافت آپدیت از تلگرام"""
    try:
        # دریافت داده
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        
        if not update.message:
            return "ok", 200
            
        chat_id = update.message.chat_id
        text = update.message.text
        
        # بررسی دستورات
        if not text:
            return "ok", 200
            
        # دستور /start
        if text == "/start":
            message = (
                "👋 سلام! به ربات خوش اومدی.\n\n"
                "📌 این یک ربات نمونه است.\n"
                "🔹 هر پیامی بفرستی، برمی‌گردونه.\n"
                "🔹 دستور /help برای راهنما."
            )
            send_message_sync(chat_id, message)
            
        # دستور /help
        elif text == "/help":
            message = (
                "📖 راهنمای ربات:\n\n"
                "/start - شروع کار\n"
                "/help - راهنما\n"
                "/setwebhook - تنظیم وب‌هوک (فقط ادمین)\n"
                "/info - اطلاعات ربات (فقط ادمین)"
            )
            send_message_sync(chat_id, message)
            
        # دستور /setwebhook (فقط ادمین)
        elif text == "/setwebhook" and chat_id == ADMIN_ID:
            result = set_webhook_sync()
            if result:
                send_message_sync(chat_id, "✅ Webhook با موفقیت تنظیم شد!")
            else:
                send_message_sync(chat_id, "❌ خطا در تنظیم Webhook!")
                
        # دستور /info (فقط ادمین)
        elif text == "/info" and chat_id == ADMIN_ID:
            try:
                bot_info = loop.run_until_complete(bot.get_me())
                info = (
                    f"📊 اطلاعات ربات:\n"
                    f"🔹 نام: {bot_info.first_name}\n"
                    f"🔹 یوزرنیم: @{bot_info.username if bot_info.username else 'ندارد'}\n"
                    f"🔹 توکن: {TOKEN[:10]}...\n"
                    f"🔹 ادمین: {ADMIN_ID}\n"
                    f"🔹 وب‌هوک: {WEBHOOK_URL}\n"
                    f"🔹 وضعیت: فعال ✅"
                )
                send_message_sync(chat_id, info)
            except Exception as e:
                logger.error(f"Error getting bot info: {e}")
                send_message_sync(chat_id, "❌ خطا در دریافت اطلاعات!")
            
        # دستورات غیرمجاز برای ادمین
        elif chat_id == ADMIN_ID and text.startswith("/"):
            send_message_sync(chat_id, "⚠️ دستور نامعتبر! برای راهنما /help را بفرست.")
            
        # اکو پیام (برای کاربران عادی)
        else:
            send_message_sync(chat_id, f"📩 پیام شما: {text}")
            
        return "ok", 200
        
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
        return "error", 500

@app.errorhandler(404)
def not_found(error):
    """خطای 404"""
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    """خطای 500"""
    logger.error(f"Internal error: {error}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    logger.info(f"🚀 Starting bot on port {port}")
    logger.info(f"🤖 Bot token: {TOKEN[:10]}...")
    logger.info(f"👤 Admin ID: {ADMIN_ID}")
    logger.info(f"🔗 Webhook URL: {WEBHOOK_URL}")
    
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
