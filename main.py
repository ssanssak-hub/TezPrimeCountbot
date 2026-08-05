import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import os
from dotenv import load_dotenv

# Import ماژول‌های اعلان
from reminders.reminder_handlers import (
    reminder_menu, handle_reminder_buttons, 
    set_reminder_start, set_reminder_message,
    set_reminder_days, set_reminder_time,
    view_reminders, view_reminder_detail, delete_reminder, cancel_reminder,
    activate_reminder_handler, back_to_main, back_to_notifications,
    REMINDER_MESSAGE, REMINDER_DAYS, REMINDER_TIME
)

# Import دیتابیس
from database import init_db
from reminders.reminder_database import init_reminder_db, get_all_user_reminders, get_user_reminders
from reminders.reminder_keyboards import main_menu_keyboard, reminder_menu_keyboard

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
    
    from database import save_user
    save_user(user_id, user.username, user.first_name, user.last_name)
    
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
    logger.info(f"Button handler received: {data}")
    
    if data == "notifications":
        await reminder_menu(update, context)
    elif data == "set_reminder":
        await set_reminder_start(update, context)
    elif data == "view_reminders":
        await view_reminders(update, context)
    elif data == "delete_reminder":
        await show_delete_list(update, context)
    elif data == "cancel_reminder":
        await show_cancel_list(update, context)
    elif data.startswith("view_"):
        try:
            reminder_id = int(data.split("_")[1])
            await view_reminder_detail(update, context)
        except (IndexError, ValueError) as e:
            logger.error(f"Invalid view callback: {data}, error: {e}")
            await query.edit_message_text("❌ خطا در نمایش اعلان!")
    elif data.startswith("delete_"):
        try:
            reminder_id = int(data.split("_")[1])
            await delete_reminder(update, context)
        except (IndexError, ValueError) as e:
            logger.error(f"Invalid delete callback: {data}, error: {e}")
            await query.edit_message_text("❌ خطا در حذف اعلان!")
    elif data.startswith("cancel_"):
        try:
            reminder_id = int(data.split("_")[1])
            await cancel_reminder(update, context)
        except (IndexError, ValueError) as e:
            logger.error(f"Invalid cancel callback: {data}, error: {e}")
            await query.edit_message_text("❌ خطا در لغو اعلان!")
    elif data.startswith("activate_"):
        try:
            reminder_id = int(data.split("_")[1])
            await activate_reminder_handler(update, context)
        except (IndexError, ValueError) as e:
            logger.error(f"Invalid activate callback: {data}, error: {e}")
            await query.edit_message_text("❌ خطا در فعال‌سازی اعلان!")
    elif data == "back_to_main":
        await back_to_main(update, context)
    elif data == "back_to_notifications":
        await back_to_notifications(update, context)
    else:
        logger.warning(f"Unknown callback data: {data}")

async def show_delete_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست اعلان‌ها برای حذف"""
    query = update.callback_query
    user_id = update.effective_user.id
    reminders = get_all_user_reminders(user_id)
    
    if not reminders:
        await query.edit_message_text(
            "📭 هیچ اعلانی برای حذف وجود ندارد!",
            reply_markup=reminder_menu_keyboard()
        )
        return
    
    keyboard = []
    for r in reminders:
        title = r['title'] if r['title'] else 'بدون عنوان'
        status = "✅" if r['is_active'] else "⛔"
        text = f"{status} 🗑️ {title[:25]}..."
        keyboard.append([InlineKeyboardButton(text, callback_data=f"delete_{r['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_notifications")])
    
    await query.edit_message_text(
        "🗑️ **حذف اعلان**\n\n"
        "⚠️ با حذف، اعلان کاملاً پاک می‌شود!\n"
        "برای غیرفعال کردن موقت از گزینه لغو استفاده کنید.\n\n"
        "اعلان مورد نظر برای حذف را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_cancel_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست اعلان‌های فعال برای لغو"""
    query = update.callback_query
    user_id = update.effective_user.id
    reminders = get_user_reminders(user_id)  # فقط فعال‌ها
    
    if not reminders:
        await query.edit_message_text(
            "📭 هیچ اعلان فعالی برای لغو وجود ندارد!",
            reply_markup=reminder_menu_keyboard()
        )
        return
    
    keyboard = []
    for r in reminders:
        title = r['title'] if r['title'] else 'بدون عنوان'
        text = f"⛔ {title[:25]}..."
        keyboard.append([InlineKeyboardButton(text, callback_data=f"cancel_{r['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_notifications")])
    
    await query.edit_message_text(
        "⛔ **لغو اعلان**\n\n"
        "اعلان غیرفعال می‌شود ولی پاک نمی‌شود.\n"
        "بعداً می‌توانید دوباره فعالش کنید.\n\n"
        "اعلان مورد نظر برای لغو را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_message'):
        await set_reminder_message(update, context)
    else:
        await update.message.reply_text("لطفاً از دکمه‌های منو استفاده کنید یا /start را بزنید.")

def process_update(update_json):
    global application, loop
    
    try:
        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        update = Update.de_json(update_json, application.bot)
        
        future = asyncio.run_coroutine_threadsafe(
            application.process_update(update),
            loop
        )
        future.result(timeout=10)
        
        return True
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return False

@flask_app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'POST':
        try:
            json_data = request.get_json(force=True)
            if not json_data:
                return jsonify({'status': 'error', 'message': 'No data'}), 400
            
            success = process_update(json_data)
            if success:
                return jsonify({'status': 'ok'}), 200
            else:
                return jsonify({'status': 'error'}), 500
                
        except Exception as e:
            logger.error(f"Webhook exception: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
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
    
    init_db()
    init_reminder_db()
    
    application = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_reminder_start, pattern="^set_reminder$")],
        states={
            REMINDER_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_reminder_message)],
            REMINDER_DAYS: [CallbackQueryHandler(set_reminder_days, pattern="^days_")],
            REMINDER_TIME: [CallbackQueryHandler(set_reminder_time, pattern="^time_")],
        },
        fallbacks=[CallbackQueryHandler(back_to_main, pattern="^back_to_main$")],
        name="reminder_conversation",
        per_message=False,
        allow_reentry=True
    )
    application.add_handler(conv_handler)
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def setup_webhook():
        await application.bot.set_webhook(WEBHOOK_URL)
        logger.info(f"✅ Webhook set to {WEBHOOK_URL}")
        return True
    
    success = loop.run_until_complete(setup_webhook())
    if not success:
        logger.error("❌ Failed to set webhook")
    
    async def run_application():
        await application.initialize()
        await application.start()
        logger.info("✅ Application started")
        
        # راه‌اندازی Scheduler
        from reminders.reminder_scheduler import start_scheduler
        start_scheduler()
        
        # پرینت jobهای فعال
        from reminders.reminder_scheduler import scheduler
        jobs = scheduler.get_jobs()
        logger.info(f"📋 Active jobs: {len(jobs)}")
        for job in jobs:
            logger.info(f"  - Job: {job.id}, Next run: {job.next_run_time}")
        
        await asyncio.Event().wait()
    
    import threading
    def run_bot():
        loop.run_until_complete(run_application())
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    logger.info("✅ Bot is ready to receive updates")
    
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Starting Flask server on port {port}")
    
    flask_app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    
if __name__ == "__main__":
    main()
