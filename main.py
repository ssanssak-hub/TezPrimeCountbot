import logging
from datetime import datetime
import pytz
import asyncio
import signal
import sys
import threading
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)
import os
from dotenv import load_dotenv

from reminders.reminder_handlers import (
    reminder_menu, handle_reminder_buttons, 
    set_reminder_start, set_reminder_message,
    set_reminder_days, set_reminder_time,
    view_reminders, view_reminder_detail, delete_reminder, cancel_reminder,
    activate_reminder_handler, back_to_main, back_to_notifications,
    REMINDER_MESSAGE, REMINDER_DAYS, REMINDER_TIME
)

from admin.admin_handlers import (
    admin_panel, 
    broadcast_now_start, broadcast_now_message, confirm_broadcast,
    broadcast_scheduled_start, broadcast_scheduled_message, 
    broadcast_scheduled_date, broadcast_scheduled_time, confirm_scheduled_broadcast,
    admin_cancel, 
    admin_stats, admin_bot_status_menu, toggle_bot, delete_all_data, confirm_delete_all,
    manage_admins, add_admin_start, add_admin_execute,
    remove_admin_start, remove_admin_execute, list_admins,
    manage_users, ban_user_start, ban_user_execute,
    unban_user_start, unban_user_execute, banned_list,
    search_user_start, search_user_result, broadcast_date_selection,
    handle_permission_toggle, confirm_add_admin, cancel_add_admin,
    broadcasts_list, broadcast_detail, cancel_broadcast, delete_broadcast_handler,
    save_admin_permissions, admin_server_status,
    edit_admin_start, edit_admin_permissions, back_to_admin,
    BROADCAST_TITLE, BROADCAST_MESSAGE, BROADCAST_DATE, BROADCAST_TIME,
    BAN_USER_ID, ADD_ADMIN_ID, SEARCH_USER_ID
)

from admin.admin_database import init_admin_db

from database import init_db, is_user_admin, is_bot_active, is_user_banned as db_is_banned
from reminders.reminder_database import init_reminder_db, get_all_user_reminders, get_user_reminders
from reminders.reminder_keyboards import main_menu_keyboard, reminder_menu_keyboard

# لود متغیرهای محیطی
load_dotenv()
TOKEN = os.getenv('TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 5000))

# تنظیمات logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app
flask_app = Flask(__name__)

# متغیرهای گلوبال
application: Application = None
bot_loop: asyncio.AbstractEventLoop = None


# ============ هندلرهای اصلی ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /start"""
    user = update.effective_user
    user_id = user.id
    
    from database import save_user
    save_user(user_id, user.username, user.first_name, user.last_name)
    
    keyboard = main_menu_keyboard(user_id=user_id, admin_id=ADMIN_ID)
    
    await update.message.reply_text(
        f"سلام کسخل درس خون {user.first_name}🫶 👋🍑\n"
        f"به ربات TezPrimeCountbot و کنکور کیری خوش اومدی لیوه!\n\n"
        f"این سال تخمی رو با موفقیت تموم کنی لاشی\n\n"
        f"از دکمه‌های زیر میتونی استفاده کن کنکوری:",
        reply_markup=keyboard
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت همه دکمه‌ها"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    logger.info(f"🔘 Button: {data} from user {user_id}")
    
    if data.startswith("perm_") or data in ["admin_confirm_add", "admin_cancel_add", "admin_save_permissions"]:
        await handle_permission_toggle(update, context)
        return
    
    is_admin, _ = is_user_admin(user_id, ADMIN_ID)
    
    if not is_bot_active() and not is_admin:
        await query.edit_message_text("🔴 ربات در حال حاضر غیرفعال است. لطفاً بعداً مراجعه کنید.")
        return
    
    if not is_admin and db_is_banned(user_id):
        await query.edit_message_text("🚫 شما از ربات بن شده‌اید!")
        return
    
    # ---- دکمه‌های اصلی ----
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
    
    # ---- پنل ادمین ----
    elif data == "admin_panel":
        await admin_panel(update, context)
    elif data == "back_to_admin_panel":
        await back_to_admin(update, context)
    
    # ---- Broadcast ها ----
    elif data == "admin_broadcast_now":
        await broadcast_now_start(update, context)
    elif data == "admin_broadcast_scheduled":
        await broadcast_scheduled_start(update, context)
    # ✅ اینا رو اضافه کن:
    elif data.startswith("broadcast_date_"):
        # این دکمه‌ها رو ConversationHandler هندل می‌کنه
        # ولی چون button_handler اول صدا زده میشه، باید ردش کنی
        pass  # بذار ConversationHandler پردازش کنه
    elif data == "broadcast_date_custom":
        pass  # بذار ConversationHandler پردازش کنه
    elif data == "admin_broadcasts_list":
        await broadcasts_list(update, context)
    elif data.startswith("admin_confirm_broadcast_"):
        await confirm_broadcast(update, context)
    elif data.startswith("admin_confirm_scheduled_"):
        await confirm_scheduled_broadcast(update, context)
    elif data.startswith("admin_broadcast_") and not data.startswith("admin_broadcasts_"):
        await broadcast_detail(update, context)
    elif data.startswith("admin_cancel_broadcast_"):
        await cancel_broadcast(update, context)
    elif data.startswith("admin_delete_broadcast_"):
        await delete_broadcast_handler(update, context)
    elif data.startswith("admin_confirm_delete_broadcast_"):
        await delete_broadcast_handler(update, context)
    
    # ---- آمار و وضعیت ----
    elif data == "admin_stats":
        await admin_stats(update, context)
    elif data == "admin_bot_status":
        await admin_bot_status_menu(update, context)
    elif data == "admin_toggle_bot":
        await toggle_bot(update, context)
    elif data == "admin_delete_all_data":
        await delete_all_data(update, context)
    elif data == "admin_confirm_delete":
        await confirm_delete_all(update, context)
    elif data == "admin_server_status":
        await admin_server_status(update, context)
    
    # ---- مدیریت ادمین‌ها ----
    elif data == "admin_manage_admins":
        await manage_admins(update, context)
    elif data == "admin_add_admin":
        await add_admin_start(update, context)
    elif data == "admin_remove_admin":
        await remove_admin_start(update, context)
    elif data.startswith("admin_remove_") and data != "admin_remove_admin":
        await remove_admin_execute(update, context)
    elif data == "admin_edit_admin":
        await edit_admin_start(update, context)
    elif data.startswith("admin_edit_") and data != "admin_edit_admin":
        await edit_admin_permissions(update, context)
    elif data == "admin_list_admins":
        await list_admins(update, context)
    
    # ---- مدیریت کاربران ----
    elif data == "admin_manage_users":
        await manage_users(update, context)
    elif data == "admin_ban_user":
        await ban_user_start(update, context)
    elif data.startswith("admin_ban_"):
        await handle_ban_from_search(update, context)
    elif data == "admin_unban_user":
        await unban_user_start(update, context)
    elif data.startswith("admin_unban_"):
        await unban_user_execute(update, context)
    elif data == "admin_banned_list":
        await banned_list(update, context)
    elif data == "admin_search_user":
        await search_user_start(update, context)
    
    # ---- ریمایندرها ----
    elif data.startswith("view_"):
        await view_reminder_detail(update, context)
    elif data.startswith("delete_"):
        await delete_reminder(update, context)
    elif data.startswith("cancel_"):
        await cancel_reminder(update, context)
    elif data.startswith("activate_"):
        await activate_reminder_handler(update, context)
    
    # ---- بازگشت‌ها ----
    elif data == "back_to_main":
        await back_to_main(update, context)
    elif data == "back_to_notifications":
        await back_to_notifications(update, context)
    
    else:
        logger.warning(f"⚠️ Unknown callback: {data}")


async def handle_ban_from_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بن کردن کاربر از نتایج جستجو"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    from database import check_admin_permission, ban_user as db_ban
    
    if not check_admin_permission(user_id, admin_id, "perm_manage_users"):
        await query.edit_message_text("⛔ شما دسترسی ندارید!")
        return
    
    try:
        user_id_to_ban = int(query.data.split("_")[-1])
        db_ban(user_id_to_ban)
        
        await query.edit_message_text(
            f"🚫 کاربر <code>{user_id_to_ban}</code> بن شد!",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_panel")
            ]])
        )
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        await query.edit_message_text("❌ خطا در بن کردن کاربر!")


async def show_delete_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست حذف ریمایندر"""
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
        text = f"{status} 🗑️ {title[:30]}"
        if len(title) > 30:
            text += "..."
        keyboard.append([InlineKeyboardButton(text, callback_data=f"delete_{r['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_notifications")])
    
    await query.edit_message_text(
        "🗑️ <b>حذف اعلان</b>\n\n"
        "⚠️ با حذف، اعلان کاملاً پاک می‌شود!\n"
        "برای غیرفعال کردن موقت از گزینه لغو استفاده کنید.\n\n"
        "اعلان مورد نظر برای حذف را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode='HTML'
    )


async def show_cancel_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست لغو ریمایندر"""
    query = update.callback_query
    user_id = update.effective_user.id
    reminders = get_user_reminders(user_id)
    
    if not reminders:
        await query.edit_message_text(
            "📭 هیچ اعلان فعالی برای لغو وجود ندارد!", 
            reply_markup=reminder_menu_keyboard()
        )
        return
    
    keyboard = []
    for r in reminders:
        title = r['title'] if r['title'] else 'بدون عنوان'
        text = f"⛔ {title[:30]}"
        if len(title) > 30:
            text += "..."
        keyboard.append([InlineKeyboardButton(text, callback_data=f"cancel_{r['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_notifications")])
    
    await query.edit_message_text(
        "⛔ <b>لغو اعلان</b>\n\n"
        "اعلان غیرفعال می‌شود ولی پاک نمی‌شود.\n"
        "بعداً می‌توانید دوباره فعالش کنید.\n\n"
        "اعلان مورد نظر برای لغو را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode='HTML'
    )


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پاسخ به پیام‌های متنی"""
    user_id = update.effective_user.id
    is_admin, _ = is_user_admin(user_id, ADMIN_ID)
    
    if not is_bot_active() and not is_admin:
        return
    
    if db_is_banned(user_id):
        await update.message.reply_text("🚫 شما از ربات بن شده‌اید!")
        return
    
    if context.user_data.get('awaiting_message'):
        # ✅ برای broadcast ها، ConversationHandler خودش هندل می‌کنه
        broadcast_type = context.user_data.get('broadcast_type')
        if broadcast_type in ['now', 'scheduled']:
            return  # بذار ConversationHandler کارشو بکنه
        
        if context.user_data.get('awaiting_admin'):
            await add_admin_execute(update, context)
            return
        
        if context.user_data.get('awaiting_ban'):
            await ban_user_execute(update, context)
            return
        
        if context.user_data.get('awaiting_search'):
            await search_user_result(update, context)
            return
        
        if context.user_data.get('step') in ['title', 'message']:
            await set_reminder_message(update, context)
            return
    
    await update.message.reply_text(
        "کسکش چی گوهی داری میخوری بزن /start کیری بن میشی کونی."
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت خطاهای کلی و ارسال به ادمین"""
    logger.error(f"❌ Error: {context.error}", exc_info=context.error)
    
    # ✅ ارسال خطا به ادمین در تلگرام
    try:
        if application and application.bot:
            admin_id = int(os.getenv('ADMIN_ID'))
            
            error_text = (
                f"🚨 <b>گزارش خطای ربات</b>\n\n"
                f"<b>نوع خطا:</b> <code>{type(context.error).__name__}</code>\n"
                f"<b>پیام خطا:</b> <code>{str(context.error)[:500]}</code>\n"
            )
            
            # اضافه کردن اطلاعات کاربر اگر موجود باشه
            if update:
                if update.effective_user:
                    user = update.effective_user
                    error_text += (
                        f"\n<b>کاربر:</b> {user.first_name} "
                        f"(<code>{user.id}</code>)"
                    )
                if update.effective_message:
                    error_text += f"\n<b>چت آیدی:</b> <code>{update.effective_chat.id}</code>"
            
            error_text += f"\n\n⏰ <i>{datetime.now(pytz.timezone('Asia/Tehran')).strftime('%Y-%m-%d %H:%M:%S')}</i>"
            
            await application.bot.send_message(
                chat_id=admin_id,
                text=error_text,
                parse_mode='HTML'
            )
            logger.info("📨 Error report sent to admin")
            
    except Exception as e:
        logger.error(f"❌ Failed to send error report to admin: {e}")
    
    # پیام به کاربر
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ خطایی رخ داد! تیم پشتیبانی مطلع شد.\n"
                "لطفاً /start را بزنید."
            )
    except Exception:
        pass


# ============ Webhook Handler (اصلاح‌شده) ============

def process_update(update_json: dict) -> bool:
    """پردازش آپدیت از Webhook - نسخه غیر blocking"""
    global application, bot_loop
    
    try:
        if application is None or application.bot is None:
            logger.error("❌ Application not initialized")
            return False
        
        if bot_loop is None or bot_loop.is_closed():
            logger.error("❌ Bot loop not available")
            return False
        
        update = Update.de_json(update_json, application.bot)
        
        # استفاده از run_coroutine_threadsafe بدون timeout
        # این متد non-blocking هست و سریع برمی‌گرده
        asyncio.run_coroutine_threadsafe(
            application.process_update(update),
            bot_loop
        )
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Webhook processing error: {e}", exc_info=True)
        return False


# ============ Flask Routes ============

@flask_app.route('/', methods=['GET', 'POST'])
def webhook():
    """Endpoint اصلی Webhook"""
    if request.method == 'POST':
        try:
            json_data = request.get_json(force=True)
            
            if not json_data:
                logger.warning("⚠️ Empty request body")
                return jsonify({'status': 'error', 'message': 'Empty body'}), 400
            
            success = process_update(json_data)
            
            if success:
                return jsonify({'status': 'ok'}), 200
            else:
                return jsonify({'status': 'error', 'message': 'Processing failed'}), 500
                
        except Exception as e:
            logger.error(f"❌ Webhook exception: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    return "TezPrimeCountbot is running! 🚀", 200


@flask_app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    status = 'healthy' if application and application.bot else 'initializing'
    return jsonify({
        'status': status,
        'bot': 'TezPrimeCountbot',
        'webhook': WEBHOOK_URL
    }), 200


@flask_app.route('/info', methods=['GET'])
def info():
    """اطلاعات ربات"""
    return jsonify({
        'status': 'running',
        'bot': 'TezPrimeCountbot',
        'webhook': WEBHOOK_URL,
        'admin_id': ADMIN_ID
    }), 200


# ============ راه‌اندازی ============

def setup_handlers():
    """تنظیم همه هندلرها"""
    global application
    
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(broadcast_now_start, pattern="^admin_broadcast_now$"),
            CallbackQueryHandler(broadcast_scheduled_start, pattern="^admin_broadcast_scheduled$"),
            CallbackQueryHandler(ban_user_start, pattern="^admin_ban_user$"),
            CallbackQueryHandler(add_admin_start, pattern="^admin_add_admin$"),
            CallbackQueryHandler(search_user_start, pattern="^admin_search_user$"),
        ],
        states={
            BROADCAST_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_now_message),
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_scheduled_message),
            ],
            BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_now_message),
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_scheduled_message),
            ],
            BROADCAST_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_scheduled_date),
                CallbackQueryHandler(broadcast_date_selection, pattern="^broadcast_date_"),
            ],
            BROADCAST_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_scheduled_time)
            ],
            BAN_USER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ban_user_execute)
            ],
            ADD_ADMIN_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_execute),
                CallbackQueryHandler(handle_permission_toggle, pattern="^perm_"),
                CallbackQueryHandler(confirm_add_admin, pattern="^admin_confirm_add$"),
                CallbackQueryHandler(cancel_add_admin, pattern="^admin_cancel_add$"),
                CallbackQueryHandler(save_admin_permissions, pattern="^admin_save_permissions$"),
            ],
            SEARCH_USER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_user_result)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", admin_cancel),
            CallbackQueryHandler(admin_panel, pattern="^admin_panel$"),
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$"),
        ],
        name="admin_conversation",
        allow_reentry=True
    )
    application.add_handler(admin_conv)
    
    reminder_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(set_reminder_start, pattern="^set_reminder$")
        ],
        states={
            REMINDER_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_reminder_message)
            ],
            REMINDER_DAYS: [
                CallbackQueryHandler(set_reminder_days, pattern="^days_")
            ],
            REMINDER_TIME: [
                CallbackQueryHandler(set_reminder_time, pattern="^time_")
            ],
        },
        fallbacks=[
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$")
        ],
        name="reminder_conversation",
        allow_reentry=True
    )
    application.add_handler(reminder_conv)
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    application.add_error_handler(error_handler)
    
    logger.info("✅ All handlers configured")


def main():
    """تابع اصلی راه‌اندازی"""
    global application, bot_loop
    
    logger.info("🔧 Initializing databases...")
    init_db()
    init_reminder_db()
    init_admin_db()
    logger.info("✅ All databases initialized")
    
    application = Application.builder().token(TOKEN).build()
    
    setup_handlers()
    
    # ساخت event loop اختصاصی برای بات
    bot_loop = asyncio.new_event_loop()
    
    # تنظیم Webhook
    async def setup_webhook():
        await application.bot.set_webhook(WEBHOOK_URL)
        logger.info(f"✅ Webhook set to {WEBHOOK_URL}")
    
    bot_loop.run_until_complete(setup_webhook())
    
    # راه‌اندازی application
    async def start_app():
        await application.initialize()
        await application.start()
        logger.info("✅ Application started")
        
        try:
            from reminders.reminder_scheduler import start_scheduler
            start_scheduler()
            
            from reminders.reminder_scheduler import scheduler
            jobs = scheduler.get_jobs()
            logger.info(f"📋 Active jobs: {len(jobs)}")
            for job in jobs:
                logger.info(f"  - {job.id}: Next run at {job.next_run_time}")
        except Exception as e:
            logger.error(f"⚠️ Scheduler error: {e}")
    
    bot_loop.run_until_complete(start_app())
    
    # اجرای event loop در thread جداگانه
    def run_bot_loop():
        asyncio.set_event_loop(bot_loop)
        bot_loop.run_forever()
    
    bot_thread = threading.Thread(target=run_bot_loop, daemon=True)
    bot_thread.start()
    
    # سیگنال‌های خروج
    def shutdown():
        logger.info("🛑 Shutting down...")
        try:
            if application:
                future = asyncio.run_coroutine_threadsafe(application.stop(), bot_loop)
                future.result(timeout=10)
            if bot_loop and not bot_loop.is_closed():
                bot_loop.call_soon_threadsafe(bot_loop.stop)
        except Exception as e:
            logger.error(f"Shutdown error: {e}")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, lambda s, f: shutdown())
    signal.signal(signal.SIGTERM, lambda s, f: shutdown())
    
    # اجرای Flask
    logger.info(f"🚀 Starting Flask server on port {PORT}")
    flask_app.run(
        host='0.0.0.0',
        port=PORT,
        debug=False,
        threaded=True
    )


if __name__ == "__main__":
    main()
