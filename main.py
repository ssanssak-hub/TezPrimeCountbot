import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
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
    search_user_start, search_user_result,
    handle_permission_toggle, confirm_add_admin, cancel_add_admin,
    broadcasts_list, broadcast_detail, cancel_broadcast, delete_broadcast_handler,
    save_admin_permissions, 
    edit_admin_start, edit_admin_permissions, 
    BROADCAST_TITLE, BROADCAST_MESSAGE, BROADCAST_DATE, BROADCAST_TIME,
    BAN_USER_ID, ADD_ADMIN_ID, SEARCH_USER_ID
)

from admin.admin_database import init_admin_db

from database import init_db, is_user_admin, is_bot_active, is_user_banned as db_is_banned
from reminders.reminder_database import init_reminder_db, get_all_user_reminders, get_user_reminders
from reminders.reminder_keyboards import main_menu_keyboard, reminder_menu_keyboard

load_dotenv()
TOKEN = os.getenv('TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)
application = None
loop = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    from database import save_user
    save_user(user_id, user.username, user.first_name, user.last_name)
    
    keyboard = main_menu_keyboard(user_id=user_id, admin_id=ADMIN_ID)
    
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
    
    # ⚠️ perm_ها و confirm/cancel ادمین
    if data.startswith("perm_"):
        await handle_permission_toggle(update, context)
        return
    
    if data == "admin_confirm_add":
        await confirm_add_admin(update, context)
        return
    
    if data == "admin_cancel_add":
        await cancel_add_admin(update, context)
        return
    
    user_id = update.effective_user.id
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
    elif data == "admin_broadcast_now":
        await broadcast_now_start(update, context)
    elif data == "admin_broadcast_scheduled":
        await broadcast_scheduled_start(update, context)
    elif data == "admin_broadcasts_list":
        await broadcasts_list(update, context)
    elif data.startswith("admin_confirm_scheduled_"):
        await confirm_scheduled_broadcast(update, context)
    elif data.startswith("admin_cancel_broadcast_"):
        await cancel_broadcast(update, context)
    elif data.startswith("admin_delete_broadcast_"):
        await delete_broadcast_handler(update, context)
    elif data.startswith("admin_confirm_broadcast_"):
        await confirm_broadcast(update, context)
    elif data.startswith("admin_broadcast_") and not data.startswith("admin_broadcasts_"):
        await broadcast_detail(update, context)
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
    elif data == "admin_save_permissions":
        await save_admin_permissions(update, context)
    elif data == "admin_list_admins":
        await list_admins(update, context)
    elif data == "admin_manage_users":
        await manage_users(update, context)
    elif data == "admin_ban_user":
        await ban_user_start(update, context)
    elif data.startswith("admin_ban_"):
        try:
            user_id_to_ban = int(data.split("_")[-1])
            from database import ban_user as db_ban
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
    elif data == "admin_unban_user":
        await unban_user_start(update, context)
    elif data.startswith("admin_unban_"):
        await unban_user_execute(update, context)
    elif data == "admin_banned_list":
        await banned_list(update, context)
    elif data == "admin_search_user":
        await search_user_start(update, context)
    
    # ---- دکمه‌های اعلان ----
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
    query = update.callback_query
    user_id = update.effective_user.id
    reminders = get_all_user_reminders(user_id)
    
    if not reminders:
        await query.edit_message_text("📭 هیچ اعلانی برای حذف وجود ندارد!", reply_markup=reminder_menu_keyboard())
        return
    
    keyboard = []
    for r in reminders:
        title = r['title'] if r['title'] else 'بدون عنوان'
        status = "✅" if r['is_active'] else "⛔"
        text = f"{status} 🗑️ {title[:25]}..."
        keyboard.append([InlineKeyboardButton(text, callback_data=f"delete_{r['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_notifications")])
    
    await query.edit_message_text(
        "🗑️ <b>حذف اعلان</b>\n\n⚠️ با حذف، اعلان کاملاً پاک می‌شود!\nبرای غیرفعال کردن موقت از گزینه لغو استفاده کنید.\n\nاعلان مورد نظر برای حذف را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML'
    )

async def show_cancel_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    reminders = get_user_reminders(user_id)
    
    if not reminders:
        await query.edit_message_text("📭 هیچ اعلان فعالی برای لغو وجود ندارد!", reply_markup=reminder_menu_keyboard())
        return
    
    keyboard = []
    for r in reminders:
        title = r['title'] if r['title'] else 'بدون عنوان'
        text = f"⛔ {title[:25]}..."
        keyboard.append([InlineKeyboardButton(text, callback_data=f"cancel_{r['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_notifications")])
    
    await query.edit_message_text(
        "⛔ <b>لغو اعلان</b>\n\nاعلان غیرفعال می‌شود ولی پاک نمی‌شود.\nبعداً می‌توانید دوباره فعالش کنید.\n\nاعلان مورد نظر برای لغو را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML'
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin, _ = is_user_admin(user_id, ADMIN_ID)
    
    if not is_bot_active() and not is_admin:
        return
    
    if db_is_banned(user_id):
        await update.message.reply_text("🚫 شما از ربات بن شده‌اید!")
        return
    
    # ====== افزودن ادمین ======
    if context.user_data.get('awaiting_message') and context.user_data.get('awaiting_admin'):
        await add_admin_execute(update, context)
        return
    
    # ====== بن کاربر ======
    if context.user_data.get('awaiting_message') and context.user_data.get('awaiting_ban'):
        await ban_user_execute(update, context)
        return
    
    # ====== جستجوی کاربر ======
    if context.user_data.get('awaiting_message') and context.user_data.get('awaiting_search'):
        await search_user_result(update, context)
        return
    
    # ====== ریمایندر ======
    if context.user_data.get('awaiting_message') and context.user_data.get('step') in ['title', 'message']:
        await set_reminder_message(update, context)
        return
    
    # ====== هیچکدوم نبود ======
    await update.message.reply_text("لطفاً از دکمه‌های منو استفاده کنید یا /start را بزنید.")
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}", exc_info=context.error)
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("❌ خطایی رخ داد! لطفاً /start را بزنید.")
        except:
            pass

def process_update(update_json):
    global application, loop
    try:
        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        update = Update.de_json(update_json, application.bot)
        future = asyncio.run_coroutine_threadsafe(application.process_update(update), loop)
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
            if not json_data: return jsonify({'status': 'error'}), 400
            success = process_update(json_data)
            return jsonify({'status': 'ok' if success else 'error'}), 200 if success else 500
        except Exception as e:
            logger.error(f"Webhook exception: {e}")
            return jsonify({'status': 'error'}), 500
    return "TezPrimeCountbot is running! 🚀", 200

@flask_app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'}), 200

@flask_app.route('/info', methods=['GET'])
def info():
    return jsonify({'status': 'running', 'bot': 'TezPrimeCountbot', 'webhook': WEBHOOK_URL}), 200

def main():
    global application, loop
    
    init_db()
    init_reminder_db()
    init_admin_db()
    
    application = Application.builder().token(TOKEN).build()
    
    # ⚠️ admin_conv با states کامل

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
            BROADCAST_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_scheduled_date)],
            BROADCAST_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_scheduled_time)],
            BAN_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_user_execute)],
            ADD_ADMIN_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_execute),
                CallbackQueryHandler(handle_permission_toggle, pattern="^perm_"),
                CallbackQueryHandler(confirm_add_admin, pattern="^admin_confirm_add$"),
                CallbackQueryHandler(cancel_add_admin, pattern="^admin_cancel_add$"),
                CallbackQueryHandler(save_admin_permissions, pattern="^admin_save_permissions$"),  # ⚠️ اینجا
            ],
            SEARCH_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_user_result)],
        },
        fallbacks=[
            CommandHandler("cancel", admin_cancel),
            CallbackQueryHandler(admin_panel, pattern="^admin_panel$"),
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$"),
        ],
        name="admin_conversation",
        per_message=True,
        allow_reentry=True
    )
    application.add_handler(admin_conv)    
    
    reminder_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_reminder_start, pattern="^set_reminder$")],
        states={
            REMINDER_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_reminder_message)],
            REMINDER_DAYS: [CallbackQueryHandler(set_reminder_days, pattern="^days_")],
            REMINDER_TIME: [CallbackQueryHandler(set_reminder_time, pattern="^time_")],
        },
        fallbacks=[CallbackQueryHandler(back_to_main, pattern="^back_to_main$")],
        name="reminder_conversation",
        per_message=True,
        allow_reentry=True
    )
    application.add_handler(reminder_conv)
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    application.add_error_handler(error_handler)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def setup_webhook():
        await application.bot.set_webhook(WEBHOOK_URL)
        logger.info(f"✅ Webhook set to {WEBHOOK_URL}")
    
    loop.run_until_complete(setup_webhook())
    
    async def run_application():
        await application.initialize()
        await application.start()
        logger.info("✅ Application started")
        
        from reminders.reminder_scheduler import start_scheduler
        start_scheduler()
        
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
