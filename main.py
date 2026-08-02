import os
import logging
from flask import Flask, request
import telegram

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 7703672187))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

bot = telegram.Bot(token=TOKEN)
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "🤖 Bot is running!"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    try:
        update = telegram.Update.de_json(request.get_json(force=True), bot)
        
        if update.message:
            chat_id = update.message.chat_id
            text = update.message.text

            if text == "/setwebhook" and chat_id == ADMIN_ID:
                bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
                bot.send_message(chat_id, "✅ Webhook تنظیم شد.")
                return "ok"

            if text == "/start":
                bot.send_message(chat_id, "👋 سلام! به ربات خوش اومدی.")
                return "ok"

            bot.send_message(chat_id, f"📩 پیام شما: {text}")
            
        return "ok"
        
    except Exception as e:
        logging.error(f"خطا: {e}")
        return "error", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
