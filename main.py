import os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Bot, Update
from dotenv import load_dotenv

# اضافه کردن ایمپورت‌های جدید
import handlers
from keyboards import get_main_menu

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
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not TOKEN:
    raise ValueError("TOKEN is required!")
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
    try:
        loop.run_until_complete(bot.initialize())
        logger.info("✅ Bot initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Bot initialization failed: {e}")
        return False

if not initialize_bot():
    logger.error("Failed to initialize bot! Exiting...")
    exit(1)

def send_message_sync(chat_id, text, reply_markup=None):
    """ارسال پیام به صورت sync"""
    try:
        if reply_markup:
            loop.run_until_complete(bot.send_message(
                chat_id=chat_id, 
                text=text, 
                reply_markup=reply_markup
            ))
        else:
            loop.run_until_complete(bot.send_message(chat_id=chat_id, text=text))
        logger.info(f"Message sent to {chat_id}")
    except Exception as e:
        logger.error(f"Error sending message: {e}")

@app.route("/", methods=["GET"])
def home():
    try:
        bot_info = loop.run_until_complete(bot.get_me())
        return jsonify({
            "status": "running",
            "bot": f"@{bot_info.username}" if bot_info.username else "unknown",
            "webhook": WEBHOOK_URL
        })
    except Exception as e:
        logger.error(f"Error in home: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        
        if not update.message:
            return "ok", 200
            
        chat_id = update.message.chat_id
        text = update.message.text
        
        if not text:
            return "ok", 200
        
        # ایجاد یک تابع async برای پردازش پیام
        async def process_update():
            # اگر پیام /start بود
            if text == "/start":
                await handlers.start(update, None)
            # در غیر این صورت به handlers ارسال کن
            else:
                await handlers.handle_message(update, None)
        
        # اجرای تابع async
        loop.run_until_complete(process_update())
        
        return "ok", 200
        
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
        return "error", 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {error}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting bot on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
