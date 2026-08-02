import os
import logging
from flask import Flask, request
from telegram import Bot, Update
from dotenv import load_dotenv

# بارگذاری متغیرهای محیطی از فایل .env (برای لوکال)
load_dotenv()

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 7703672187))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not TOKEN:
    raise ValueError("TOKEN not found in environment variables!")

bot = Bot(token=TOKEN)
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "🤖 Bot is running!"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        
        if update.message:
            chat_id = update.message.chat_id
            text = update.message.text

            # دستور /setwebhook فقط برای ادمین
            if text == "/setwebhook" and chat_id == ADMIN_ID:
                bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
                bot.send_message(chat_id, "✅ Webhook تنظیم شد.")
                return "ok"

            # دستور /start
            if text == "/start":
                await bot.send_message(chat_id, "👋 سلام! به ربات خوش اومدی.")
                return "ok"

            # اکو پیام
            await bot.send_message(chat_id, f"📩 پیام شما: {text}")
            
        return "ok"
        
    except Exception as e:
        logging.error(f"خطا: {e}")
        return "error", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
