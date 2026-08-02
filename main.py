import os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application
from dotenv import load_dotenv
from handlers import start, handle_message
from scheduler import start_async_scheduler, bot

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not TOKEN:
    raise ValueError("TOKEN is required!")

app = Flask(__name__)

# ایجاد event loop اصلی
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# متغیر global برای scheduler
scheduler = None

async def init_bot():
    """راه‌اندازی ربات و scheduler"""
    global scheduler
    
    # راه‌اندازی scheduler
    scheduler = await start_async_scheduler()
    logger.info("✅ Bot and scheduler initialized")

# اجرای راه‌اندازی
loop.run_until_complete(init_bot())

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "bot": "active",
        "webhook": WEBHOOK_URL
    })

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        
        if not update.message or not update.message.text:
            return "ok", 200
        
        async def process_update():
            if update.message.text == "/start":
                await start(update, None)
            else:
                await handle_message(update, None)
        
        # اجرای async در event loop
        future = asyncio.run_coroutine_threadsafe(process_update(), loop)
        future.result(timeout=30)
        
        return "ok", 200
        
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
        return "error", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting bot on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=False)  # threaded=False
