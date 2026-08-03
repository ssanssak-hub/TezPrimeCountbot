import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import os
from dotenv import load_dotenv

# Import ماژول‌های اعلان
from reminders.reminder_handlers import (
    reminder_menu, handle_reminder_buttons, 
    set_reminder_start, set_reminder_message,
    set_reminder_days, set_reminder_time,
    view_reminders, delete_reminder, cancel_reminder,
    back_to_main, REMINDER_MESSAGE, REMINDER_DAYS, REMINDER_TIME
)

# Import دیتابیس
from database import init_db

# Load environment variables
load_dotenv()
TOKEN = os.getenv('TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app برای Webhook
flask_app = Flask(__name__)

# Telegram Application
application = None
loop = None

# دکمه‌های منوی اصلی
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # ذخیره کاربر در دیتابیس
    from database import save_user
    save_user(user_id, user.username, user.first_name, user.last_name)
    
    # ساخت کیبورد منوی اصلی
    from reminders.reminder_keyboards import main_menu_keyboard
    keyboard = main_menu_keyboard()
    
    await update.message.reply_text(
        f"سلام {user.first_name}! 👋\n"
        f"به ربات TezPrimeCountbot خوش اومدی!\n\n"
        f"از دکمه‌های زیر استفاده کن:",
        reply_markup=keyboard
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "notifications":
        await reminder_menu(update, context)
    elif data.startswith("reminder_"):
        await handle_reminder_buttons(update, context)
    elif data == "back_to_main":
        await back_to_main(update, context)
    elif data == "view_reminders":
        await view_reminders(update, context)
    elif data.startswith("delete_"):
        await delete_reminder(update, context)
    elif data.startswith("cancel_"):
        await cancel_reminder(update, context)

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # برای دریافت پیام متنی در طول تنظیم اعلان
    if context.user_data.get('awaiting_message'):
        await set_reminder_message(update, context)

# 🔥 **تابع پردازش Webhook با مدیریت Event Loop**
def process_update(update_json):
    global application, loop
    
    try:
        # اگر loop وجود نداره، یک loop جدید بساز
        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # ایجاد آبجکت Update
        update = Update.de_json(update_json, application.bot)
        
        # اجرای پردازش در event loop
        future = asyncio.run_coroutine_threadsafe(
            application.process_update(update),
            loop
        )
        future.result(timeout=10)  # منتظر حداکثر ۱۰ ثانیه
        
        return True
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return False

# 🔥 **مسیر اصلی Webhook**
@flask_app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'POST':
        try:
            # دریافت داده JSON
            json_data = request.get_json(force=True)
            if not json_data:
                return jsonify({'status': 'error', 'message': 'No data'}), 400
            
            # پردازش درخواست
            success = process_update(json_data)
            if success:
                return jsonify({'status': 'ok'}), 200
            else:
                return jsonify({'status': 'error'}), 500
                
        except Exception as e:
            logger.error(f"Webhook exception: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    # پاسخ به درخواست GET
    return "TezPrimeCountbot is running! 🚀", 200

@flask_app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'}), 200

@flask_app.route('/info', methods=['GET'])
def info():
    return jsonify({
        'status': 'running',
        'bot': 'TezPrimeCountbot',
        'webhook': WEBHOOK_URL
    }), 200

def main():
    global application, loop
    
    # مقداردهی اولیه دیتابیس
    init_db()
    
    # ساخت اپلیکیشن
    application = Application.builder().token(TOKEN).build()
    
    # هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # هندلر تنظیم اعلان (Conversation)
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_reminder_start, pattern="^set_reminder$")],
        states={
            REMINDER_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_reminder_message)],
            REMINDER_DAYS: [CallbackQueryHandler(set_reminder_days, pattern="^days_")],
            REMINDER_TIME: [CallbackQueryHandler(set_reminder_time, pattern="^time_")],
        },
        fallbacks=[CallbackQueryHandler(back_to_main, pattern="^back_to_main$")],
        name="reminder_conversation",
        per_message=False
    )
    application.add_handler(conv_handler)
    
    # هندلر پیش‌فرض
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    # 🚀 **راه‌اندازی Event Loop جدید**
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # تنظیم Webhook
    async def setup_webhook():
        await application.bot.set_webhook(WEBHOOK_URL)
        logger.info(f"✅ Webhook set to {WEBHOOK_URL}")
        return True
    
    # اجرای تنظیم Webhook
    success = loop.run_until_complete(setup_webhook())
    if not success:
        logger.error("❌ Failed to set webhook")
    
    # 🔥 **مهم: شروع به کار Application در پس‌زمینه**
    async def run_application():
        await application.initialize()
        await application.start()
        logger.info("✅ Application started")
        # نگه داشتن application در حالت آماده‌باش
        await asyncio.Event().wait()  # اینجا منتظر می‌مونه تا forever
    
    # اجرای Application در پس‌زمینه
    import threading
    def run_bot():
        loop.run_until_complete(run_application())
    
    # اجرا در یک ترد جداگانه
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    logger.info("✅ Bot is ready to receive updates")
    
    # راه‌اندازی Flask
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Starting Flask server on port {port}")
    
    # اجرای Flask (این تابع بلاک می‌شه و منتظر می‌مونه)
    flask_app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

if __name__ == "__main__":
    main()
