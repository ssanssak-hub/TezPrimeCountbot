import logging
import os
import psutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import (
    get_all_users, get_all_active_users, get_total_users_count,
    ban_user as db_ban_user, unban_user as db_unban_user,
    get_banned_users, is_user_banned, get_user_info,
    add_admin as db_add_admin, remove_admin as db_remove_admin,
    get_all_admins, get_bot_status, toggle_bot_status,
    delete_all_user_data, is_user_admin
)
from reminders.reminder_database import get_all_user_reminders
from admin.admin_keyboards import (
    admin_panel_keyboard, admin_manage_admins_keyboard,
    admin_manage_users_keyboard, admin_bot_status_keyboard,
    admin_broadcasts_list_keyboard, broadcast_action_keyboard,
    back_to_admin_keyboard
)
from admin.admin_database import (
    init_admin_db, save_broadcast, get_all_broadcasts,
    mark_broadcast_cancelled, delete_broadcast, get_broadcast_stats,
    get_broadcast_progress
)
from admin.admin_broadcast import send_broadcast_now, get_broadcast_progress_text
from reminders.reminder_utils import get_weekday_name, get_persian_datetime

logger = logging.getLogger(__name__)

# حالت‌های Conversation
(BROADCAST_TITLE, BROADCAST_MESSAGE, BROADCAST_DATE, BROADCAST_TIME,
 BAN_USER_ID, UNBAN_USER_ID, ADD_ADMIN_ID, REMOVE_ADMIN_ID, SEARCH_USER_ID) = range(9)

# ---------- منوی اصلی پنل ----------

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش پنل مدیریت"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    is_admin, admin_type = is_user_admin(user_id, admin_id)
    
    if not is_admin:
        if query:
            await query.edit_message_text("⛔ شما دسترسی به پنل مدیریت ندارید!")
        return
    
    context.user_data.clear()
    
    text = (
        f"👑 **پنل مدیریت**\n\n"
        f"🎭 سطح دسترسی: {'ادمین اصلی' if admin_type == 'main_admin' else 'ادمین فرعی'}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"از منوی زیر استفاده کنید:"
    )
    
    if query:
        await query.edit_message_text(text, reply_markup=admin_panel_keyboard(), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=admin_panel_keyboard(), parse_mode='Markdown')

# ---------- ارسال پیام همگانی فوری ----------

async def broadcast_now_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ارسال فوری"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    if user_id != admin_id:
        await query.edit_message_text("⛔ فقط ادمین اصلی!")
        return ConversationHandler.END
    
    context.user_data['broadcast'] = {}
    context.user_data['broadcast_step'] = 'title'
    context.user_data['awaiting_message'] = True
    
    await query.edit_message_text(
        "📝 **ارسال پیام همگانی فوری**\n\nلطفاً **عنوان** پیام را ارسال کنید:",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='Markdown'
    )
    return BROADCAST_TITLE

async def broadcast_now_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت عنوان و پیام"""
    if not context.user_data.get('awaiting_message'):
        return ConversationHandler.END
    
    message = update.message.text
    step = context.user_data.get('broadcast_step', 'title')
    
    if step == 'title':
        context.user_data['broadcast']['title'] = message
        context.user_data['broadcast_step'] = 'message'
        
        await update.message.reply_text(
            f"📝 عنوان: **{message}**\n\nحالا **متن پیام** را ارسال کنید:\n\n⚠️ این پیام به **همه کاربران** ارسال خواهد شد!",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='Markdown'
        )
        return BROADCAST_MESSAGE
    
    elif step == 'message':
        title = context.user_data['broadcast']['title']
        broadcast_id = save_broadcast(update.effective_user.id, title, message)
        users_count = get_total_users_count()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تایید ارسال", callback_data=f"admin_confirm_broadcast_{broadcast_id}")],
            [InlineKeyboardButton("❌ لغو", callback_data="admin_panel")]
        ])
        
        await update.message.reply_text(
            f"📢 **تایید نهایی**\n\n📌 عنوان: **{title}**\n📝 پیام: {message[:100]}...\n👥 گیرندگان: **{users_count}** کاربر\n\nآیا از ارسال اطمینان دارید؟",
            reply_markup=keyboard, parse_mode='Markdown'
        )
        
        context.user_data.clear()
        return ConversationHandler.END

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تایید و ارسال"""
    query = update.callback_query
    await query.answer()
    
    broadcast_id = int(query.data.split("_")[-1])
    
    broadcasts = get_all_broadcasts()
    broadcast = None
    for b in broadcasts:
        if b['id'] == broadcast_id:
            broadcast = b
            break
    
    if not broadcast:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())
        return
    
    await query.edit_message_text("⏳ **در حال ارسال پیام همگانی...**", parse_mode='Markdown')
    
    import asyncio
    asyncio.create_task(
        send_broadcast_now(broadcast_id, broadcast['admin_id'], broadcast['title'], broadcast['message'])
    )
    
    await asyncio.sleep(2)
    progress_text = get_broadcast_progress_text(broadcast_id)
    await query.edit_message_text(progress_text, reply_markup=back_to_admin_keyboard(), parse_mode='Markdown')

# ---------- پیام همگانی زمان‌بندی شده ----------

async def broadcast_scheduled_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع پیام همگانی زمان‌بندی شده - مرحله عنوان"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    if user_id != admin_id:
        await query.edit_message_text("⛔ فقط ادمین اصلی!")
        return ConversationHandler.END
    
    context.user_data['broadcast'] = {}
    context.user_data['broadcast_type'] = 'scheduled'
    context.user_data['broadcast_step'] = 'title'
    context.user_data['awaiting_message'] = True
    
    await query.edit_message_text(
        "📝 **پیام همگانی زمان‌بندی شده - مرحله ۱/۴**\n\n"
        "لطفاً **عنوان** پیام را ارسال کنید:\n"
        "(مثلاً: اطلاعیه مهم، تخفیف ویژه)",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='Markdown'
    )
    return BROADCAST_TITLE


async def broadcast_scheduled_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت عنوان و پیام برای زمان‌بندی"""
    if not context.user_data.get('awaiting_message'):
        return ConversationHandler.END
    
    message = update.message.text
    step = context.user_data.get('broadcast_step', 'title')
    
    if step == 'title':
        context.user_data['broadcast']['title'] = message
        context.user_data['broadcast_step'] = 'message'
        
        await update.message.reply_text(
            f"📝 **مرحله ۲/۴**\n\n"
            f"عنوان: **{message}**\n\n"
            f"حالا لطفاً **متن پیام** را ارسال کنید:",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='Markdown'
        )
        return BROADCAST_MESSAGE
    
    elif step == 'message':
        context.user_data['broadcast']['message'] = message
        context.user_data['broadcast_step'] = 'date'
        
        # کیبورد انتخاب تاریخ (فردا تا ۷ روز آینده)
        from datetime import datetime, timedelta
        keyboard = []
        today = datetime.now()
        
        for i in range(1, 8):
            date = today + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            persian_date = get_persian_datetime()  # از utils خودت استفاده کن
            keyboard.append([InlineKeyboardButton(
                f"📅 {date_str}",
                callback_data=f"broadcast_date_{date_str}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")])
        
        await update.message.reply_text(
            f"📅 **مرحله ۳/۴ - انتخاب تاریخ**\n\n"
            f"عنوان: **{context.user_data['broadcast']['title']}**\n"
            f"پیام: {message[:50]}...\n\n"
            f"تاریخ ارسال را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return BROADCAST_DATE


async def broadcast_scheduled_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب تاریخ و رفتن به انتخاب ساعت"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "admin_panel":
        context.user_data.clear()
        return ConversationHandler.END
    
    date_str = query.data.split("_")[-1]  # مثلاً 2026-08-06
    context.user_data['broadcast']['date'] = date_str
    context.user_data['broadcast_step'] = 'time'
    
    # کیبورد انتخاب ساعت (۰ تا ۲۳)
    keyboard = []
    hour_row = []
    for h in range(24):
        hour_row.append(InlineKeyboardButton(f"{h:02d}", callback_data=f"broadcast_hour_{h}"))
        if len(hour_row) == 6:
            keyboard.append(hour_row)
            hour_row = []
    if hour_row:
        keyboard.append(hour_row)
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")])
    
    await query.edit_message_text(
        f"🕐 **مرحله ۴/۴ - انتخاب ساعت**\n\n"
        f"📅 تاریخ: **{date_str}**\n\n"
        f"لطفاً **ساعت** ارسال را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return BROADCAST_TIME


async def broadcast_scheduled_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب ساعت و دقیقه و ثبت نهایی"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "admin_panel":
        context.user_data.clear()
        return ConversationHandler.END
    
    data = query.data
    
    if data.startswith("broadcast_hour_"):
        hour = int(data.split("_")[-1])
        context.user_data['broadcast']['hour'] = hour
        
        # کیبورد انتخاب دقیقه (۰ تا ۵۵ با گام ۵)
        keyboard = []
        minute_row = []
        for m in range(0, 60, 5):
            minute_row.append(InlineKeyboardButton(f"{m:02d}", callback_data=f"broadcast_minute_{m}"))
            if len(minute_row) == 6:
                keyboard.append(minute_row)
                minute_row = []
        if minute_row:
            keyboard.append(minute_row)
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به انتخاب ساعت", callback_data="broadcast_back_to_hour")])
        
        await query.edit_message_text(
            f"🕐 **انتخاب دقیقه**\n\n"
            f"ساعت انتخاب شده: **{hour:02d}**\n\n"
            f"لطفاً **دقیقه** را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return BROADCAST_TIME
    
    elif data.startswith("broadcast_minute_"):
        minute = int(data.split("_")[-1])
        
        title = context.user_data['broadcast']['title']
        message = context.user_data['broadcast']['message']
        date = context.user_data['broadcast']['date']
        hour = context.user_data['broadcast']['hour']
        
        # ذخیره در دیتابیس
        broadcast_id = save_broadcast(update.effective_user.id, title, message, date, f"{hour:02d}:{minute:02d}")
        
        # زمان‌بندی
        from apscheduler.triggers.date import DateTrigger
        from datetime import datetime
        from reminders.reminder_scheduler import scheduler
        
        run_date = datetime.strptime(f"{date} {hour:02d}:{minute:02d}:00", "%Y-%m-%d %H:%M:%S")
        
        scheduler.add_job(
            lambda: None,  # جایگزین با تابع ارسال
            trigger=DateTrigger(run_date=run_date),
            id=f"broadcast_{broadcast_id}",
            replace_existing=True
        )
        
        # تایید نهایی
        total_users = get_total_users_count()
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تایید و برنامه‌ریزی", callback_data=f"admin_confirm_scheduled_{broadcast_id}")],
            [InlineKeyboardButton("❌ لغو", callback_data="admin_panel")]
        ])
        
        await query.edit_message_text(
            f"📢 **تایید نهایی**\n\n"
            f"📌 عنوان: **{title}**\n"
            f"📝 پیام: {message[:100]}...\n"
            f"📅 تاریخ: **{date}**\n"
            f"🕐 ساعت: **{hour:02d}:{minute:02d}**\n"
            f"👥 گیرندگان: **{total_users}** کاربر\n\n"
            f"آیا تأیید می‌کنید؟",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    elif data == "broadcast_back_to_hour":
        # برگشت به انتخاب ساعت
        keyboard = []
        hour_row = []
        for h in range(24):
            hour_row.append(InlineKeyboardButton(f"{h:02d}", callback_data=f"broadcast_hour_{h}"))
            if len(hour_row) == 6:
                keyboard.append(hour_row)
                hour_row = []
        if hour_row:
            keyboard.append(hour_row)
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")])
        
        await query.edit_message_text(
            "🕐 **انتخاب ساعت**\n\nلطفاً ساعت ارسال را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return BROADCAST_TIME


async def confirm_scheduled_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تایید نهایی پیام زمان‌بندی شده"""
    query = update.callback_query
    await query.answer()
    
    broadcast_id = int(query.data.split("_")[-1])
    
    broadcasts = get_all_broadcasts()
    broadcast = None
    for b in broadcasts:
        if b['id'] == broadcast_id:
            broadcast = b
            break
    
    if not broadcast:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())
        return
    
    # برنامه‌ریزی واقعی ارسال
    from reminders.reminder_scheduler import scheduler
    from apscheduler.triggers.date import DateTrigger
    from datetime import datetime
    
    run_date = datetime.strptime(
        f"{broadcast['send_date']} {broadcast['send_time']}:00",
        "%Y-%m-%d %H:%M:%S"
    )
    
    async def send_scheduled_broadcast():
        await send_broadcast_now(broadcast_id, broadcast['admin_id'], broadcast['title'], broadcast['message'])
    
    scheduler.add_job(
        send_scheduled_broadcast,
        trigger=DateTrigger(run_date=run_date),
        id=f"broadcast_{broadcast_id}",
        replace_existing=True
    )
    
    await query.edit_message_text(
        f"✅ **پیام همگانی برنامه‌ریزی شد!**\n\n"
        f"📌 عنوان: **{broadcast['title']}**\n"
        f"📅 تاریخ: **{broadcast['send_date']}**\n"
        f"🕐 ساعت: **{broadcast['send_time']}**\n\n"
        f"پیام در تاریخ مشخص شده به همه کاربران ارسال خواهد شد.",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='Markdown'
    )

# ---------- لیست پیام‌های همگانی ----------

async def broadcasts_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست پیام‌ها"""
    query = update.callback_query
    await query.answer()
    
    broadcasts = get_all_broadcasts()
    if not broadcasts:
        await query.edit_message_text("📭 هیچ پیام همگانی وجود ندارد!", reply_markup=back_to_admin_keyboard())
        return
    
    await query.edit_message_text("📋 **پیام‌های همگانی**", reply_markup=admin_broadcasts_list_keyboard(broadcasts), parse_mode='Markdown')

async def broadcast_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """جزئیات پیام"""
    query = update.callback_query
    await query.answer()
    
    broadcast_id = int(query.data.split("_")[-1])
    progress_text = get_broadcast_progress_text(broadcast_id)
    
    broadcasts = get_all_broadcasts()
    broadcast = None
    for b in broadcasts:
        if b['id'] == broadcast_id:
            broadcast = b
            break
    
    if broadcast:
        await query.edit_message_text(progress_text, reply_markup=broadcast_action_keyboard(broadcast_id, broadcast['is_sent'], broadcast['is_cancelled']), parse_mode='Markdown')

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو پیام"""
    query = update.callback_query
    await query.answer()
    
    broadcast_id = int(query.data.split("_")[-1])
    mark_broadcast_cancelled(broadcast_id)
    await query.edit_message_text("⛔ پیام همگانی لغو شد!", reply_markup=back_to_admin_keyboard())

async def delete_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف پیام"""
    query = update.callback_query
    await query.answer()
    
    broadcast_id = int(query.data.split("_")[-1])
    delete_broadcast(broadcast_id)
    await query.edit_message_text("🗑️ پیام همگانی حذف شد!", reply_markup=back_to_admin_keyboard())

# ---------- آمار ----------

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آمار و گزارشات"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    if user_id != admin_id:
        await query.edit_message_text("⛔ فقط ادمین اصلی!")
        return
    
    total_users = get_total_users_count()
    active_users = len(get_all_active_users())
    banned_users = len(get_banned_users())
    sub_admins = get_all_admins()
    broadcasts = get_all_broadcasts()
    pending = len([b for b in broadcasts if not b['is_sent'] and not b['is_cancelled']])
    
    text = (
        f"📊 **آمار و گزارشات**\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"👑 **ادمین‌ها:**\n"
        f"   🔸 ادمین اصلی: ۱\n"
        f"   🔹 ادمین فرعی: {len(sub_admins)}\n\n"
        f"👥 **کاربران:**\n"
        f"   کل: {total_users}\n"
        f"   فعال: {active_users}\n"
        f"   بن شده: {banned_users}\n\n"
        f"📢 **پیام‌های همگانی:**\n"
        f"   کل: {len(broadcasts)}\n"
        f"   در انتظار: {pending}\n"
    )
    
    await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode='Markdown')

# ---------- وضعیت ربات ----------

async def admin_bot_status_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وضعیت ربات"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    if user_id != admin_id:
        await query.edit_message_text("⛔ فقط ادمین اصلی!")
        return
    
    status = get_bot_status()
    is_active = status['is_active'] if status else True
    
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        disk_used_mb = disk.used // (1024**2)
        disk_total_mb = disk.total // (1024**2)
    except:
        cpu, mem, disk_used_mb, disk_total_mb = 0, type('obj', (object,), {'percent': 0})(), 0, 1
    
    text = (
        f"⚙️ **وضعیت ربات**\n━━━━━━━━━━━━━━━━\n\n"
        f"🤖 ربات: {'🟢 فعال' if is_active else '🔴 غیرفعال'}\n\n"
        f"📈 **سرور:**\n"
        f"   CPU: {cpu}%\n"
        f"   RAM: {mem.percent}%\n"
        f"   Disk: {disk.percent}% ({disk_used_mb}MB / {disk_total_mb}MB)\n"
    )
    
    await query.edit_message_text(text, reply_markup=admin_bot_status_keyboard(is_active), parse_mode='Markdown')

async def toggle_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغییر وضعیت"""
    query = update.callback_query
    await query.answer()
    
    new_status = toggle_bot_status()
    await query.edit_message_text(f"🤖 ربات {'🟢 روشن' if new_status else '🔴 خاموش'} شد!", reply_markup=back_to_admin_keyboard())

async def delete_all_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تایید حذف داده‌ها"""
    query = update.callback_query
    await query.answer()
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ تأیید حذف", callback_data="admin_confirm_delete")],
        [InlineKeyboardButton("🔙 انصراف", callback_data="admin_bot_status")]
    ])
    
    await query.edit_message_text("⚠️ **هشدار!**\n\nهمه داده‌های کاربران حذف می‌شود!\nاین عملیات قابل بازگشت نیست!\n\nمطمئن هستید؟", reply_markup=keyboard, parse_mode='Markdown')

async def confirm_delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف همه داده‌ها"""
    query = update.callback_query
    await query.answer()
    
    delete_all_user_data()
    await query.edit_message_text("✅ همه داده‌ها حذف شد!", reply_markup=back_to_admin_keyboard())

# ---------- مدیریت ادمین‌ها ----------

async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی ادمین‌ها"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("👥 **مدیریت ادمین‌ها**", reply_markup=admin_manage_admins_keyboard(), parse_mode='Markdown')

async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """افزودن ادمین"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    if user_id != admin_id:
        await query.edit_message_text("⛔ فقط ادمین اصلی!")
        return ConversationHandler.END
    
    context.user_data['awaiting_message'] = True
    await query.edit_message_text("➕ **افزودن ادمین**\n\nلطفاً **user_id** را ارسال کنید:", reply_markup=back_to_admin_keyboard(), parse_mode='Markdown')
    return ADD_ADMIN_ID

async def add_admin_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای افزودن"""
    if not context.user_data.get('awaiting_message'):
        return ConversationHandler.END
    
    try:
        user_id = int(update.message.text.strip())
        db_add_admin(user_id)
        await update.message.reply_text(f"✅ کاربر `{user_id}` ادمین شد!", parse_mode='Markdown', reply_markup=back_to_admin_keyboard())
    except ValueError:
        await update.message.reply_text("❌ شناسه نامعتبر!", reply_markup=back_to_admin_keyboard())
    
    context.user_data.clear()
    return ConversationHandler.END

async def remove_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف ادمین"""
    query = update.callback_query
    await query.answer()
    
    admins = get_all_admins()
    if not admins:
        await query.edit_message_text("📭 هیچ ادمین فرعی وجود ندارد!", reply_markup=back_to_admin_keyboard())
        return
    
    keyboard = []
    for admin in admins:
        name = admin['first_name'] or 'ناشناس'
        keyboard.append([InlineKeyboardButton(f"👤 {name} ({admin['user_id']})", callback_data=f"admin_remove_{admin['user_id']}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_manage_admins")])
    
    await query.edit_message_text("➖ **حذف ادمین**\n\nادمین مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def remove_admin_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای حذف"""
    query = update.callback_query
    await query.answer()
    
    user_id = int(query.data.split("_")[-1])
    db_remove_admin(user_id)
    await query.edit_message_text(f"✅ کاربر `{user_id}` از ادمین‌ها حذف شد!", parse_mode='Markdown', reply_markup=back_to_admin_keyboard())

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست ادمین‌ها"""
    query = update.callback_query
    await query.answer()
    
    admins = get_all_admins()
    admin_id = int(os.getenv('ADMIN_ID'))
    
    text = f"👑 **لیست ادمین‌ها:**\n\n🔸 ادمین اصلی: `{admin_id}`\n\n"
    if admins:
        text += "**ادمین‌های فرعی:**\n"
        for admin in admins:
            name = admin['first_name'] or 'ناشناس'
            text += f"   👤 {name} (`{admin['user_id']}`)\n"
    else:
        text += "📭 هیچ ادمین فرعی وجود ندارد"
    
    await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode='Markdown')

# ---------- مدیریت کاربران ----------

async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی کاربران"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🚫 **مدیریت کاربران**", reply_markup=admin_manage_users_keyboard(), parse_mode='Markdown')

async def ban_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع بن"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['awaiting_message'] = True
    await query.edit_message_text("🔨 **بن کردن کاربر**\n\nلطفاً **user_id** را ارسال کنید:", reply_markup=back_to_admin_keyboard(), parse_mode='Markdown')
    return BAN_USER_ID

async def ban_user_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای بن"""
    if not context.user_data.get('awaiting_message'):
        return ConversationHandler.END
    
    try:
        user_id = int(update.message.text.strip())
        db_ban_user(user_id)
        await update.message.reply_text(f"🚫 کاربر `{user_id}` بن شد!", parse_mode='Markdown', reply_markup=back_to_admin_keyboard())
    except ValueError:
        await update.message.reply_text("❌ شناسه نامعتبر!", reply_markup=back_to_admin_keyboard())
    
    context.user_data.clear()
    return ConversationHandler.END

async def unban_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع آزادسازی"""
    query = update.callback_query
    await query.answer()
    
    banned = get_banned_users()
    if not banned:
        await query.edit_message_text("📭 هیچ کاربر بن شده‌ای وجود ندارد!", reply_markup=back_to_admin_keyboard())
        return
    
    keyboard = []
    for user in banned:
        name = user['first_name'] or 'ناشناس'
        keyboard.append([InlineKeyboardButton(f"🔓 {name} ({user['user_id']})", callback_data=f"admin_unban_{user['user_id']}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_manage_users")])
    
    await query.edit_message_text("🔓 **آزادسازی کاربر**\n\nکاربر مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def unban_user_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای آزادسازی"""
    query = update.callback_query
    await query.answer()
    
    user_id = int(query.data.split("_")[-1])
    db_unban_user(user_id)
    await query.edit_message_text(f"✅ کاربر `{user_id}` آزاد شد!", parse_mode='Markdown', reply_markup=back_to_admin_keyboard())

async def banned_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست بن شده‌ها"""
    query = update.callback_query
    await query.answer()
    
    banned = get_banned_users()
    if not banned:
        await query.edit_message_text("📭 هیچ کاربر بن شده‌ای وجود ندارد!", reply_markup=back_to_admin_keyboard())
        return
    
    text = "🚫 **لیست کاربران بن شده:**\n\n"
    for user in banned:
        name = user['first_name'] or 'ناشناس'
        text += f"🔴 {name} (`{user['user_id']}`)\n"
    
    await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode='Markdown')

# ---------- جستجوی کاربر ----------

async def search_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع جستجو"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['awaiting_message'] = True
    await query.edit_message_text("🔍 **جستجوی کاربر**\n\nلطفاً **user_id** را ارسال کنید:", reply_markup=back_to_admin_keyboard(), parse_mode='Markdown')
    return SEARCH_USER_ID

async def search_user_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نتیجه جستجو"""
    if not context.user_data.get('awaiting_message'):
        return ConversationHandler.END
    
    try:
        user_id = int(update.message.text.strip())
        user = get_user_info(user_id)
        
        if not user:
            await update.message.reply_text("❌ کاربر یافت نشد!", reply_markup=back_to_admin_keyboard())
        else:
            reminders = get_all_user_reminders(user_id)
            active_reminders = len([r for r in reminders if r['is_active']])
            
            text = (
                f"🔍 **اطلاعات کاربر**\n\n"
                f"🆔 شناسه: `{user['user_id']}`\n"
                f"👤 نام: {user['first_name'] or 'ندارد'}\n"
                f"📝 یوزرنیم: @{user['username'] or 'ندارد'}\n"
                f"👑 ادمین: {'✅' if user['is_admin'] else '❌'}\n"
                f"🚫 بن شده: {'✅' if user['is_banned'] else '❌'}\n"
                f"📋 ریمایندرها: {len(reminders)} (فعال: {active_reminders})\n"
            )
            
            keyboard = []
            if user['is_banned']:
                keyboard.append([InlineKeyboardButton("🔓 آزادسازی", callback_data=f"admin_unban_{user_id}")])
            else:
                keyboard.append([InlineKeyboardButton("🔨 بن کاربر", callback_data=f"admin_ban_{user_id}")])
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")])
            
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    except ValueError:
        await update.message.reply_text("❌ شناسه نامعتبر!", reply_markup=back_to_admin_keyboard())
    
    context.user_data.clear()
    return ConversationHandler.END
