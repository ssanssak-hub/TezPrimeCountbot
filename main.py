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
    broadcast_stats,
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

import time
processed_updates = {}  # دیکشنری برای ذخیره update_id های پردازش شده

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

async def handle_send_now_from_scheduled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال فوری یه پیام زمان‌بندی شده"""
    query = update.callback_query
    await query.answer()
    
    from admin.admin_keyboards import back_to_admin_keyboard
    from admin.admin_database import get_broadcast_by_id
    
    broadcast_id = int(query.data.split("_")[-1])
    broadcast = get_broadcast_by_id(broadcast_id)
    
    if not broadcast:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())
        return
    
    b = dict(broadcast)
    
    # ✅ حذف زمان‌بندی (اگه job داره)
    try:
        from reminders.reminder_scheduler import scheduler
        job_id = f"broadcast_{broadcast_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    except:
        pass
    
    # ✅ تغییر وضعیت به pending و حذف تاریخ
    from admin.admin_database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE broadcasts 
        SET send_date = NULL, send_time = NULL, status = 'pending', job_id = NULL
        WHERE id = ?
    ''', (broadcast_id,))
    conn.commit()
    conn.close()
    
    # ✅ ارسال فوری با تابع پیشرفته
    from admin.admin_broadcast import send_broadcast_advanced
    
    progress_msg = await query.edit_message_text("⏳ در حال ارسال...", parse_mode='HTML')
    
    try:
        sent, failed, total = await send_broadcast_advanced(broadcast_id, b['admin_id'], b)
        
        from admin.admin_broadcast import send_broadcast_report
        await send_broadcast_report(update.effective_user.id, b['title'], sent, failed, total)
        
        await progress_msg.edit_text(
            f"✅ ارسال به پایان رسید!\n\n{sent}/{total} موفق",
            reply_markup=back_to_admin_keyboard()
        )
    except Exception as e:
        await progress_msg.edit_text(f"❌ خطا: {str(e)[:200]}", reply_markup=back_to_admin_keyboard())

async def show_broadcast_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش جزئیات کامل یک پیام همگانی"""
    query = update.callback_query
    await query.answer("🔍 در حال دریافت جزئیات...")
    
    from admin.admin_database import get_broadcast_by_id
    from database import get_user_info
    import json
    
    broadcast_id = int(query.data.split("_")[-1])
    broadcast = get_broadcast_by_id(broadcast_id)
    
    if not broadcast:
        await query.message.reply_text("❌ پیام یافت نشد!")
        return
    
    b = dict(broadcast)
    
    content_type = b.get('content_type', 'text')
    title = b.get('title', 'بدون عنوان') or 'بدون عنوان'
    message = b.get('message') or ''
    status = b.get('status', 'unknown')
    file_id = b.get('file_id')
    file_caption = b.get('file_caption') or ''
    
    status_emoji = {
        'pending': '⏰ در انتظار', 'sending': '📤 در حال ارسال',
        'completed': '✅ تکمیل شده', 'failed': '❌ ناموفق',
        'stopped': '🛑 متوقف شده', 'cancelled': '⛔ لغو شده'
    }
    status_text = status_emoji.get(status, status)
    
    content_emoji = {
        'text': '📝 متن', 'photo': '🖼 عکس', 'video': '🎥 فیلم',
        'document': '📄 فایل', 'audio': '🎵 صدا/ویس'
    }
    content_text = content_emoji.get(content_type, content_type)
    
    # ✅ تبدیل sqlite3.Row به dict
    admin_info = get_user_info(b.get('admin_id'))
    if admin_info:
        admin_info = dict(admin_info)
        admin_name = admin_info.get('first_name', 'ناشناس')
        admin_username = admin_info.get('username', '')
    else:
        admin_name = 'ناشناس'
        admin_username = ''
    
    total_users = b.get('total_users', 0) or 0
    sent_count = b.get('sent_count', 0) or 0
    failed_count = b.get('failed_count', 0) or 0
    blocked_count = b.get('blocked_count', 0) or 0
    success_rate = round(sent_count / total_users * 100, 1) if total_users > 0 else 0
    
    # ✅ دکمه‌های شیشه‌ای با جزئیات کامل
    inline_buttons = b.get('inline_buttons')
    buttons_text = ""
    buttons_count = 0
    if inline_buttons:
        try:
            buttons_data = json.loads(inline_buttons) if isinstance(inline_buttons, str) else inline_buttons
            buttons_count = len(buttons_data)
            for i, btn in enumerate(buttons_data, 1):
                if isinstance(btn, dict):
                    btn_text = btn.get('text', 'بدون متن')
                    btn_type = btn.get('type', '')
                    if btn_type == 'url':
                        url = btn.get('url', '')
                        buttons_text += f"  {i}. 🔗 {btn_text}\n     لینک: {url[:60]}{'...' if len(url) > 60 else ''}\n"
                    elif btn_type == 'callback':
                        msg = btn.get('message', 'بدون پیام')
                        buttons_text += f"  {i}. 🔘 {btn_text}\n     پیام: {msg[:60]}{'...' if len(msg) > 60 else ''}\n"
                elif isinstance(btn, list):
                    if len(btn) == 2:
                        buttons_text += f"  {i}. 🔗 {btn[0]}\n     لینک: {btn[1][:60]}\n"
                    elif len(btn) >= 3:
                        buttons_text += f"  {i}. 🔘 {btn[0]}\n     پیام: {btn[2][:60]}\n"
        except:
            buttons_text = "  ⚠️ خطا در خواندن دکمه‌ها\n"
    
    created_at = str(b.get('created_at', '؟'))[:19]
    send_date = b.get('send_date', '')
    send_time = b.get('send_time', '')
    
    # ✅ ساخت متن
    text = f"🔍 جزئیات پیام #{broadcast_id}\n"
    text += f"━━━━━━━━━━━━━━━━\n"
    text += f"📌 عنوان: {title[:50]}\n"
    text += f"📎 نوع: {content_text}\n"
    text += f"📊 وضعیت: {status_text}\n"
    text += f"━━━━━━━━━━━━━━━━\n"
    text += f"👤 ارسال‌کننده: {admin_name}"
    if admin_username:
        text += f" (@{admin_username})"
    text += f"\n🆔 شناسه: {b.get('admin_id')}\n"
    text += f"━━━━━━━━━━━━━━━━\n"
    
    if content_type == 'text' and message:
        text += f"📝 متن پیام:\n{message[:300]}{'...' if len(message) > 300 else ''}\n"
        text += f"📏 طول: {len(message)} کاراکتر\n"
    elif content_type != 'text':
        text += f"📎 فایل: {content_text}\n"
        if file_caption:
            text += f"📝 کپشن: {file_caption[:200]}{'...' if len(file_caption) > 200 else ''}\n"
        text += f"🆔 FileID: {file_id[:30] if file_id else '؟'}...\n"
    
    text += f"━━━━━━━━━━━━━━━━\n"
    
    # ✅ دکمه‌ها
    text += f"🔘 دکمه‌های شیشه‌ای: {buttons_count} عدد\n"
    if buttons_text:
        text += buttons_text
    else:
        text += "  ❌ بدون دکمه\n"
    
    text += f"━━━━━━━━━━━━━━━━\n"
    text += f"📊 آمار ارسال:\n"
    text += f"  👥 کل: {total_users} | ✅ موفق: {sent_count} ({success_rate}%)\n"
    text += f"  ❌ ناموفق: {failed_count} | 🚫 بلاک: {blocked_count}\n"
    text += f"━━━━━━━━━━━━━━━━\n"
    text += f"📅 ایجاد: {created_at}\n"
    if send_date and send_time:
        text += f"⏰ زمان‌بندی: {send_date} ساعت {send_time}\n"
    else:
        text += f"⚡ ارسال فوری\n"
    
    # ✅ ارسال به صورت پیام جدید
    await query.message.reply_text(text)
    
    # ✅ ارسال فایل اصلی
    if content_type != 'text' and file_id:
        try:
            admin_chat_id = update.effective_user.id
            caption_text = f"📎 فایل پیام #{broadcast_id}: {title[:50]}"
            
            if content_type == 'photo':
                await context.bot.send_photo(admin_chat_id, file_id, caption=caption_text)
            elif content_type == 'video':
                await context.bot.send_video(admin_chat_id, file_id, caption=caption_text)
            elif content_type == 'document':
                await context.bot.send_document(admin_chat_id, file_id, caption=caption_text)
            elif content_type == 'audio':
                await context.bot.send_audio(admin_chat_id, file_id, caption=caption_text)
        except Exception as e:
            logger.warning(f"Could not send file: {e}")
        
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت همه دکمه‌ها"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    logger.info(f"🔘 Button: {data} from user {user_id}")
    
    # ============ ✅ دکمه‌های ارسال پیشرفته (اولویت اول) ============
    
    # دکمه‌های مدیریت دکمه‌های شیشه‌ای (افزودن/حذف/تأیید/رد)
    if data.startswith("ib_"):
        from admin.admin_handlers import handle_inline_buttons
        await handle_inline_buttons(update, context)
        return
    
    # دکمه تأیید نهایی ارسال پیشرفته
    if data.startswith("confirm_adv_broadcast_"):
        from admin.admin_handlers import confirm_advanced_broadcast
        await confirm_advanced_broadcast(update, context)
        return
    
    # دکمه ویرایش دکمه‌های شیشه‌ای
    if data.startswith("broadcast_edit_buttons_"):
        from admin.admin_handlers import edit_broadcast_buttons
        await edit_broadcast_buttons(update, context)
        return

    # ============ ✅ این بخش رو اضافه کن ============
    # دکمه‌های شیشه‌ای پیام‌های همگانی (کلیک کاربران)
    if data.startswith("bc_btn_"):
        await handle_broadcast_button_click(update, context)
        return 

    if data.startswith("bc_"):
        await handle_broadcast_button_click(update, context)
        return
    
    # ✅ اضافه کردن شرط برای دکمه‌های تاریخ (مرحله ۳)
    if data.startswith("broadcast_date_"):
        await broadcast_date_selection(update, context)
        return
    
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
    elif data == "admin_broadcasts_list":
        await broadcasts_list(update, context)
    elif data.startswith("admin_confirm_broadcast_"):
        await confirm_broadcast(update, context)
    elif data.startswith("admin_confirm_scheduled_"):
        await confirm_scheduled_broadcast(update, context)
    elif data.startswith("admin_broadcast_details_"):
        await show_broadcast_details(update, context)
        return
    elif data.startswith("admin_broadcast_stats_"):
        await broadcast_stats(update, context)
        return
    elif data.startswith("admin_broadcast_") and not data.startswith("admin_broadcasts_"):
        await broadcast_detail(update, context)
    elif data.startswith("admin_cancel_broadcast_"):
        await cancel_broadcast(update, context)
    elif data.startswith("admin_delete_broadcast_"):
        await delete_broadcast_handler(update, context)
    elif data.startswith("admin_confirm_delete_broadcast_"):
        await delete_broadcast_handler(update, context)
    elif data.startswith("admin_send_now_"):
        await handle_send_now_from_scheduled(update, context)
        return
    
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
    
    # ✅ چک کن awaiting_message ولی broadcast نباشه
    if context.user_data.get('awaiting_message'):
        broadcast_type = context.user_data.get('broadcast_type')
        
        # ⚠️ برای broadcast ها هیچ کاری نکن - بذار ConversationHandler هندل کنه
        if broadcast_type in ['now', 'scheduled']:
            return  # اما این بار return خالی، چون ConversationHandler قبلاً ثبت شده
        
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

async def handle_broadcast_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    مدیریت کلیک کاربران روی دکمه‌های شیشه‌ای پیام همگانی
    
    فرمت callback_data: bc_{button_id}
    پیام از جدول button_messages خونده میشه
    """
    query = update.callback_query
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or 'کاربر'
    
    data = query.data
    logger.info(f"📣 Broadcast button clicked: {data} by {user_name} ({user_id})")
    
    # ✅ استخراج button_id و دریافت پیام
    button_id = None
    message_to_show = "✅ با تشکر از شما! ❤️"
    
    try:
        if data.startswith("bc_"):
            button_id = data[3:]  # حذف "bc_" از ابتدا
            
            if button_id:
                # ✅ دریافت پیام از دیتابیس
                from admin.admin_database import get_button_message
                stored_message = get_button_message(button_id)
                if stored_message:
                    message_to_show = stored_message
                    logger.info(f"📝 Message loaded for button {button_id}: {message_to_show[:80]}...")
                else:
                    logger.warning(f"⚠️ No message found for button_id: {button_id}")
            else:
                logger.warning(f"⚠️ Empty button_id in callback_data: {data}")
        else:
            logger.warning(f"⚠️ Invalid callback_data format: {data}")
            
    except Exception as e:
        logger.error(f"❌ Error loading button message: {e}", exc_info=True)
    
    # ✅ جایگزینی {name} با اسم کاربر
    message_to_show = message_to_show.replace('{name}', user_name)
    
    # ✅ نمایش پیام به کاربر - روش ترکیبی (Toast + Reply)
    try:
        # ۱. همیشه یه Toast نشون بده (تأیید کلیک)
        if len(message_to_show) <= 100:
            await query.answer(text=message_to_show, show_alert=False)
        else:
            await query.answer(text=message_to_show[:100] + "...", show_alert=False)
        
        # ۲. پیام کامل رو به صورت Reply بفرست (کاربر حتماً ببینه)
        sent_msg = await query.message.reply_text(
            f"💬 {message_to_show}",
            reply_to_message_id=query.message.message_id
        )
        
        # ۳. پاک کردن خودکار پیام Reply بعد از ۱۵ ثانیه (اختیاری)
        asyncio.create_task(delete_message_later(sent_msg, 15))
        
        logger.info(f"✅ Message sent to {user_name}: {message_to_show[:50]}...")
        
    except Exception as e:
        logger.error(f"❌ Error showing message: {e}")
        # تلاش آخر - فقط Alert
        try:
            await query.answer(text=message_to_show[:200], show_alert=True)
        except:
            try:
                await query.answer(text="✅ دریافت شد!", show_alert=False)
            except:
                pass
    
    # ✅ ذخیره آمار کلیک (فقط اگه button_id معتبر باشه)
    if button_id:
        try:
            from database import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # ایجاد جدول اگه وجود نداشته باشه
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS button_clicks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    button_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    user_name TEXT,
                    clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # ذخیره کلیک
            cursor.execute('''
                INSERT INTO button_clicks (button_id, user_id, user_name)
                VALUES (?, ?, ?)
            ''', (button_id, user_id, user_name))
            
            conn.commit()
            
            # لاگ آمار
            cursor.execute('''
                SELECT COUNT(DISTINCT user_id) as unique_clicks
                FROM button_clicks
                WHERE button_id = ?
            ''', (button_id,))
            stats = cursor.fetchone()
            conn.close()
            
            unique_clicks = stats['unique_clicks'] if stats else 1
            logger.info(f"📊 Button {button_id}: {unique_clicks} unique clicks")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not save click stats: {e}")
    else:
        logger.warning("⚠️ Click not saved - no valid button_id")
    
    logger.info(f"✅ Button handled: button_id={button_id}, user={user_name}")

async def delete_message_later(message, delay=10):
    """پاک کردن پیام بعد از delay ثانیه"""
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except:
        pass

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
                "❌ عملیات کیر شد! خیالت تخت به سنس اطلاع داده شد از توت درش بیاره.\n"
                "پفیوز این /start رو بمال روش."
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
            
            # ✅ جلوگیری از پردازش تکراری
            update_id = json_data.get('update_id')
            if update_id and update_id in processed_updates:
                logger.warning(f"⚠️ Duplicate update {update_id}, skipping...")
                return jsonify({'status': 'ok', 'message': 'duplicate'}), 200
            
            if update_id:
                processed_updates[update_id] = time.time()
            
            # پاکسازی update_id های قدیمی (بیشتر از ۶۰ ثانیه)
            now = time.time()
            for uid in list(processed_updates.keys()):
                if now - processed_updates[uid] > 60:
                    del processed_updates[uid]
            
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

    # import های جدید
    from admin.admin_handlers import (
        BROADCAST_CONTENT_TYPE, BROADCAST_BUTTONS,
        handle_content_type, handle_file_receive,
        handle_inline_buttons, handle_button_text_input,
        show_final_preview, confirm_advanced_broadcast,
        edit_broadcast_buttons
    )    
    
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(broadcast_now_start, pattern="^admin_broadcast_now$"),
            CallbackQueryHandler(broadcast_scheduled_start, pattern="^admin_broadcast_scheduled$"),
            CallbackQueryHandler(ban_user_start, pattern="^admin_ban_user$"),
            CallbackQueryHandler(add_admin_start, pattern="^admin_add_admin$"),
            CallbackQueryHandler(search_user_start, pattern="^admin_search_user$"),
        ],
        states={
            BROADCAST_CONTENT_TYPE: [
                CallbackQueryHandler(handle_content_type, pattern="^content_type_"),
            ],            
            BROADCAST_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_now_message),
                MessageHandler(filters.PHOTO, handle_file_receive),
                MessageHandler(filters.VIDEO, handle_file_receive),
                MessageHandler(filters.Document.ALL, handle_file_receive),
                MessageHandler(filters.AUDIO, handle_file_receive),
                MessageHandler(filters.VOICE, handle_file_receive),
            ],
            BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_now_message),
            ],
            BROADCAST_BUTTONS: [
                # ✅ دکمه‌های مدیریت دکمه‌های شیشه‌ای (افزودن/حذف/تأیید/رد)
                CallbackQueryHandler(handle_inline_buttons, pattern="^ib_"),
                # ✅ تأیید نهایی ارسال پیشرفته (هم برای فوری و هم زمان‌بندی)
                CallbackQueryHandler(confirm_advanced_broadcast, pattern="^confirm_adv_broadcast_"),
                # ✅ ویرایش دکمه‌های یک broadcast ذخیره شده
                CallbackQueryHandler(edit_broadcast_buttons, pattern="^broadcast_edit_buttons_"),
                # ✅ دریافت متن/لینک دکمه جدید
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button_text_input),
            ],            
            BROADCAST_DATE: [
                CallbackQueryHandler(broadcast_date_selection, pattern="^broadcast_date_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_scheduled_date),
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
