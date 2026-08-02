import os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Bot, Update
from dotenv import load_dotenv
from handlers import start, handle_message
from scheduler import start_scheduler

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
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is required!")

bot = Bot(token=TOKEN)
app = Flask(__name__)

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

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

try:
    scheduler = start_scheduler()
    logger.info("✅ Scheduler started successfully")
except Exception as e:
    logger.error(f"❌ Failed to start scheduler: {e}")

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
            
        text = update.message.text
        
        if not text:
            return "ok", 200
        
        async def process_update():
            if text == "/start":
                await start(update, None)
            else:
                await handle_message(update, None)
        
        loop.run_until_complete(process_update())
        return "ok", 200
        
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
        return "error", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting bot on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
