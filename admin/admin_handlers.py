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
from ..reminders.reminder_database import get_all_user_reminders
from .admin_keyboards import (
    admin_panel_keyboard, admin_manage_admins_keyboard,
    admin_manage_users_keyboard, admin_bot_status_keyboard,
    admin_broadcasts_list_keyboard, broadcast_action_keyboard,
    back_to_admin_keyboard
)
from .admin_database import (
    init_admin_db, save_broadcast, get_all_broadcasts,
    mark_broadcast_cancelled, delete_broadcast, get_broadcast_stats,
    get_broadcast_progress
)
from admin.admin_broadcast import send_broadcast_now, get_broadcast_progress_text

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
    
    # چک ادمین
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    is_admin, admin_type = is_user_admin(user_id, admin_id)
    
    if not is_admin:
        if query:
            await query.edit_message_text("⛔ شما دسترسی به پنل مدیریت ندارید!")
        return
    
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
    """شروع فرآیند ارسال فوری - مرحله عنوان"""
    query = update.callback_query
    await query.answer()
    
    # چک ادمین اصلی بودن
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    if user_id != admin_id:
        await query.edit_message_text("⛔ فقط ادمین اصلی می‌تواند پیام همگانی ارسال کند!")
        return
    
    context.user_data['broadcast'] = {}
    
    await query.edit_message_text(
        "📝 **ارسال پیام همگانی فوری**\n\n"
        "لطفاً **عنوان** پیام را ارسال کنید:",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='Markdown'
    )
    context.user_data['awaiting_message'] = True
    return BROADCAST_TITLE

async def broadcast_now_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت عنوان و درخواست پیام"""
    message = update.message.text
    step = context.user_data.get('broadcast_step', 'title')
    
    if step == 'title':
        context.user_data['broadcast']['title'] = message
        context.user_data['broadcast_step'] = 'message'
        
        await update.message.reply_text(
            "📝 **ارسال پیام همگانی فوری**\n\n"
            f"عنوان: **{message}**\n\n"
            "حالا لطفاً **متن پیام** را ارسال کنید:\n\n"
            "⚠️ این پیام به **همه کاربران** ارسال خواهد شد!",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='Markdown'
        )
        return BROADCAST_MESSAGE
    
    elif step == 'message':
        context.user_data['broadcast']['message'] = message
        title = context.user_data['broadcast']['title']
        
        # ذخیره در دیتابیس
        broadcast_id = save_broadcast(update.effective_user.id, title, message)
        
        # ارسال تایید
        users_count = get_total_users_count()
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تایید ارسال", callback_data=f"admin_confirm_broadcast_{broadcast_id}")],
            [InlineKeyboardButton("❌ لغو", callback_data="admin_panel")]
        ])
        
        await update.message.reply_text(
            f"📢 **تایید نهایی**\n\n"
            f"📌 عنوان: **{title}**\n"
            f"📝 پیام: {message[:100]}...\n"
            f"👥 تعداد گیرندگان: **{users_count}** کاربر\n\n"
            f"آیا از ارسال اطمینان دارید؟",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
        context.user_data.clear()
        return ConversationHandler.END

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تایید و ارسال پیام همگانی"""
    query = update.callback_query
    await query.answer()
    
    broadcast_id = int(query.data.split("_")[-1])
    
    from .admin_database import get_all_broadcasts
    broadcasts = get_all_broadcasts()
    broadcast = None
    for b in broadcasts:
        if b['id'] == broadcast_id:
            broadcast = b
            break
    
    if not broadcast:
        await query.edit_message_text("❌ پیام یافت نشد!")
        return
    
    # شروع ارسال (در background)
    await query.edit_message_text("⏳ **در حال ارسال پیام همگانی...**\n\nلطفاً شکیبا باشید...", parse_mode='Markdown')
    
    import asyncio
    asyncio.create_task(
        send_broadcast_now(broadcast_id, broadcast['admin_id'], broadcast['title'], broadcast['message'])
    )
    
    await asyncio.sleep(2)
    
    progress_text = get_broadcast_progress_text(broadcast_id)
    await query.edit_message_text(progress_text, reply_markup=back_to_admin_keyboard(), parse_mode='Markdown')

# ---------- آمار و گزارشات ----------

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش آمار و گزارشات"""
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
    admins = len(get_all_admins())
    
    broadcasts = get_all_broadcasts()
    total_broadcasts = len(broadcasts)
    pending = len([b for b in broadcasts if not b['is_sent'] and not b['is_cancelled']])
    
    text = (
        f"📊 **آمار و گزارشات**\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"👥 **کاربران:**\n"
        f"   کل: {total_users}\n"
        f"   فعال: {active_users}\n"
        f"   بن شده: {banned_users}\n\n"
        f"👑 **ادمین‌ها:** {admins}\n\n"
        f"📢 **پیام‌های همگانی:**\n"
        f"   کل: {total_broadcasts}\n"
        f"   در انتظار: {pending}\n"
    )
    
    await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode='Markdown')

# ---------- وضعیت ربات ----------

async def admin_bot_status_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی وضعیت ربات"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    if user_id != admin_id:
        await query.edit_message_text("⛔ فقط ادمین اصلی!")
        return
    
    status = get_bot_status()
    is_active = status['is_active'] if status else True
    
    # وضعیت سرور
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
    except:
        cpu, mem, disk = 0, type('obj', (object,), {'percent': 0})(), type('obj', (object,), {'percent': 0, 'used': 0, 'total': 1})()
    
    text = (
        f"⚙️ **وضعیت ربات**\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"🤖 ربات: {'🟢 فعال' if is_active else '🔴 غیرفعال'}\n\n"
        f"📈 **وضعیت سرور:**\n"
        f"   CPU: {cpu}%\n"
        f"   RAM: {mem.percent}%\n"
        f"   Disk: {disk.percent}% ({disk.used // (1024**2)}MB / {disk.total // (1024**2)}MB)\n"
    )
    
    await query.edit_message_text(
        text,
        reply_markup=admin_bot_status_keyboard(is_active),
        parse_mode='Markdown'
    )

async def toggle_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغییر وضعیت ربات"""
    query = update.callback_query
    await query.answer()
    
    new_status = toggle_bot_status()
    await query.edit_message_text(
        f"🤖 ربات {'🟢 روشن' if new_status else '🔴 خاموش'} شد!",
        reply_markup=back_to_admin_keyboard()
    )

async def delete_all_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف همه داده‌ها"""
    query = update.callback_query
    await query.answer()
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ تأیید حذف همه داده‌ها", callback_data="admin_confirm_delete")],
        [InlineKeyboardButton("🔙 انصراف", callback_data="admin_bot_status")]
    ])
    
    await query.edit_message_text(
        "⚠️ **هشدار!**\n\n"
        "با این کار همه داده‌های کاربران حذف می‌شود!\n"
        "این عملیات قابل بازگشت نیست!\n\n"
        "آیا مطمئن هستید؟",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def confirm_delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأیید حذف همه داده‌ها"""
    query = update.callback_query
    await query.answer()
    
    delete_all_user_data()
    await query.edit_message_text(
        "✅ همه داده‌های کاربران با موفقیت حذف شد!",
        reply_markup=back_to_admin_keyboard()
    )

# ---------- مدیریت ادمین‌ها ----------

async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی مدیریت ادمین‌ها"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "👥 **مدیریت ادمین‌ها**",
        reply_markup=admin_manage_admins_keyboard(),
        parse_mode='Markdown'
    )

async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع افزودن ادمین"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "➕ **افزودن ادمین**\n\n"
        "لطفاً **user_id** کاربر مورد نظر را ارسال کنید:\n"
        "(مثال: 123456789)",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='Markdown'
    )
    context.user_data['awaiting_message'] = True
    return ADD_ADMIN_ID

async def add_admin_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای افزودن ادمین"""
    try:
        user_id = int(update.message.text.strip())
        db_add_admin(user_id)
        await update.message.reply_text(f"✅ کاربر `{user_id}` به ادمین‌ها اضافه شد!", parse_mode='Markdown', reply_markup=back_to_admin_keyboard())
    except ValueError:
        await update.message.reply_text("❌ شناسه کاربر نامعتبر!", reply_markup=back_to_admin_keyboard())
    
    context.user_data.clear()
    return ConversationHandler.END

async def remove_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع حذف ادمین"""
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
    
    await query.edit_message_text(
        "➖ **حذف ادمین**\n\nادمین مورد نظر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def remove_admin_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای حذف ادمین"""
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
    
    text = "👑 **لیست ادمین‌ها:**\n\n"
    text += f"🔸 **ادمین اصلی:** `{admin_id}`\n\n"
    
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
    """منوی مدیریت کاربران"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🚫 **مدیریت کاربران**",
        reply_markup=admin_manage_users_keyboard(),
        parse_mode='Markdown'
    )

async def ban_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع بن کردن کاربر"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔨 **بن کردن کاربر**\n\n"
        "لطفاً **user_id** کاربر را ارسال کنید:",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='Markdown'
    )
    context.user_data['awaiting_message'] = True
    return BAN_USER_ID

async def ban_user_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای بن"""
    try:
        user_id = int(update.message.text.strip())
        db_ban_user(user_id)
        await update.message.reply_text(f"🚫 کاربر `{user_id}` بن شد!", parse_mode='Markdown', reply_markup=back_to_admin_keyboard())
    except ValueError:
        await update.message.reply_text("❌ شناسه کاربر نامعتبر!", reply_markup=back_to_admin_keyboard())
    
    context.user_data.clear()
    return ConversationHandler.END

async def unban_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع آزادسازی کاربر"""
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
    
    await query.edit_message_text(
        "🔓 **آزادسازی کاربر**\n\nکاربر مورد نظر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def unban_user_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای آزادسازی"""
    query = update.callback_query
    await query.answer()
    
    user_id = int(query.data.split("_")[-1])
    db_unban_user(user_id)
    await query.edit_message_text(f"✅ کاربر `{user_id}` آزاد شد!", parse_mode='Markdown', reply_markup=back_to_admin_keyboard())

async def banned_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست کاربران بن شده"""
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
    """شروع جستجوی کاربر"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔍 **جستجوی کاربر**\n\n"
        "لطفاً **user_id** کاربر را ارسال کنید:",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='Markdown'
    )
    context.user_data['awaiting_message'] = True
    return SEARCH_USER_ID

async def search_user_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش نتیجه جستجو"""
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
                keyboard.append([InlineKeyboardButton("🔓 آزادسازی کاربر", callback_data=f"admin_unban_{user_id}")])
            else:
                keyboard.append([InlineKeyboardButton("🔨 بن کاربر", callback_data=f"admin_ban_{user_id}")])
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")])
            
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    except ValueError:
        await update.message.reply_text("❌ شناسه کاربر نامعتبر!", reply_markup=back_to_admin_keyboard())
    
    context.user_data.clear()
    return ConversationHandler.END

# ---------- مشاهده پیام‌های همگانی ----------

async def broadcasts_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست پیام‌های همگانی"""
    query = update.callback_query
    await query.answer()
    
    broadcasts = get_all_broadcasts()
    if not broadcasts:
        await query.edit_message_text("📭 هیچ پیام همگانی وجود ندارد!", reply_markup=back_to_admin_keyboard())
        return
    
    await query.edit_message_text(
        "📋 **پیام‌های همگانی**",
        reply_markup=admin_broadcasts_list_keyboard(broadcasts),
        parse_mode='Markdown'
    )

async def broadcast_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """جزئیات پیام همگانی"""
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
        await query.edit_message_text(
            progress_text,
            reply_markup=broadcast_action_keyboard(broadcast_id, broadcast['is_sent'], broadcast['is_cancelled']),
            parse_mode='Markdown'
        )

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو پیام همگانی"""
    query = update.callback_query
    await query.answer()
    
    broadcast_id = int(query.data.split("_")[-1])
    mark_broadcast_cancelled(broadcast_id)
    
    await query.edit_message_text("⛔ پیام همگانی لغو شد!", reply_markup=back_to_admin_keyboard())

async def delete_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف پیام همگانی"""
    query = update.callback_query
    await query.answer()
    
    broadcast_id = int(query.data.split("_")[-1])
    delete_broadcast(broadcast_id)
    
    await query.edit_message_text("🗑️ پیام همگانی حذف شد!", reply_markup=back_to_admin_keyboard())

