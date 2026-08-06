import logging
import os
import asyncio
import psutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import TelegramError
from database import (
    get_all_users, get_all_active_users, get_admin_info, get_total_users_count,
    ban_user as db_ban_user, unban_user as db_unban_user,
    get_banned_users, is_user_banned, get_user_info,
    add_admin as db_add_admin, remove_admin as db_remove_admin,
    get_all_admins, get_bot_status, toggle_bot_status,
    delete_all_user_data, is_user_admin,
    check_admin_permission  # ✅ فقط یکبار import کن
)
from reminders.reminder_database import get_all_user_reminders
from admin.admin_keyboards import (
    admin_panel_keyboard, admin_manage_admins_keyboard,
    admin_manage_users_keyboard, admin_bot_status_keyboard,
    admin_broadcasts_list_keyboard, broadcast_action_keyboard,
    back_to_admin_keyboard, permissions_selection_keyboard,
    admin_confirm_add_keyboard,
    get_permission_name, date_selection_keyboard
)
from admin.admin_database import (
    init_admin_db, save_broadcast, get_all_broadcasts,
    mark_broadcast_cancelled, delete_broadcast, get_broadcast_stats,
    get_broadcast_progress, get_broadcast_by_id  # ✅ اضافه کردن get_broadcast_by_id
)
from admin.admin_broadcast import send_broadcast_now, get_broadcast_progress_text, send_broadcast_report
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
    is_admin, admin_type, permissions = get_admin_info(user_id, admin_id)
    
    if not is_admin:
        if query:
            await query.edit_message_text("⛔ شما دسترسی به پنل مدیریت ندارید!")
        return
    
    context.user_data.clear()
    
    text = (
        f"👑 <b>پنل مدیریت</b>\n\n"
        f"🎭 سطح دسترسی: {'ادمین اصلی' if admin_type == 'main_admin' else 'ادمین فرعی'}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"از منوی زیر استفاده کنید:"
    )
    
    keyboard = admin_panel_keyboard(user_id=user_id, admin_id=admin_id)
    
    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')
# ---------- ارسال پیام همگانی فوری ----------

async def broadcast_now_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ارسال فوری"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    from database import check_admin_permission
    if not check_admin_permission(user_id, admin_id, "perm_broadcast_now"):
        await query.edit_message_text("⛔ شما دسترسی ندارید!")
        return ConversationHandler.END
    
    context.user_data['broadcast'] = {}
    context.user_data['broadcast_type'] = 'now'
    context.user_data['broadcast_step'] = 'title'
    context.user_data['awaiting_message'] = True
    
    # ✅ اول پیام رو نشون بده، بعد return کن
    await query.edit_message_text(
        "📝 <b>ارسال پیام همگانی فوری</b>\n\nلطفاً <b>عنوان</b> پیام را ارسال کنید:",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='HTML'
    )
    return BROADCAST_TITLE  # ✅ فقط یه return، اونم آخر کار

async def broadcast_now_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت عنوان و پیام برای ارسال فوری"""
    if not context.user_data.get('awaiting_message'):
        return ConversationHandler.END
    
    if context.user_data.get('broadcast_type') != 'now':
        return ConversationHandler.END
    
    message = update.message.text
    step = context.user_data.get('broadcast_step', 'title')
    
    if step == 'title':
        context.user_data['broadcast']['title'] = message
        context.user_data['broadcast_step'] = 'message'
        
        await update.message.reply_text(
            f"📝 عنوان: <b>{message}</b>\n\n"
            f"حالا <b>متن پیام</b> را ارسال کنید:\n\n"
            f"⚠️ این پیام به <b>همه کاربران</b> ارسال خواهد شد!",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_MESSAGE
    
    elif step == 'message':
        title = context.user_data['broadcast']['title']
        broadcast_id = save_broadcast(update.effective_user.id, title, message)
        users_count = get_total_users_count()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تایید و ارسال", callback_data=f"admin_confirm_broadcast_{broadcast_id}")],
            [InlineKeyboardButton("❌ لغو", callback_data="admin_panel")]
        ])
        
        await update.message.reply_text(
            f"📢 <b>تایید نهایی</b>\n\n"
            f"📌 عنوان: <b>{title}</b>\n"
            f"📝 پیام: {message[:100]}...\n"
            f"👥 گیرندگان: <b>{users_count}</b> کاربر\n\n"
            f"آیا از ارسال اطمینان دارید؟",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        
        context.user_data.clear()
        return ConversationHandler.END

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تایید و ارسال فوری با مدیریت بهتر"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # چک دسترسی
    if not check_admin_permission(user_id, admin_id, "perm_broadcast_now"):
        await query.edit_message_text("⛔ شما دسترسی ندارید!")
        return
    
    broadcast_id = int(query.data.split("_")[-1])
    
    # استفاده از فانکشن جدید به‌جای حلقه
    broadcast = get_broadcast_by_id(broadcast_id)
    
    if not broadcast:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())
        return
    
    # بررسی وضعیت فعلی
    if broadcast['status'] == 'sending':
        await query.answer("⏳ این پیام در حال ارسال است!", show_alert=True)
        progress_text = get_broadcast_progress_text(broadcast_id)
        await query.edit_message_text(progress_text, reply_markup=back_to_admin_keyboard(), parse_mode='HTML')
        return
    
    # پیام در حال ارسال
    progress_msg = await query.edit_message_text(
        "⏳ <b>در حال ارسال پیام همگانی...</b>\n\n"
        "🔄 لطفاً صبر کنید...",
        parse_mode='HTML'
    )
    
    try:
        # اجرای ارسال در background
        task = asyncio.create_task(
            send_broadcast_now(
                broadcast_id, 
                broadcast['admin_id'], 
                broadcast['title'], 
                broadcast['message']
            )
        )
        
        # نمایش پیشرفت هر ۲ ثانیه
        last_text = ""
        while not task.done():
            await asyncio.sleep(2)
            progress_text = get_broadcast_progress_text(broadcast_id)
            
            if progress_text != last_text:
                last_text = progress_text
                try:
                    await progress_msg.edit_text(
                        progress_text,
                        reply_markup=back_to_admin_keyboard(),
                        parse_mode='HTML'
                    )
                except Exception:
                    pass
        
        # دریافت نتیجه
        sent, failed, total = task.result()
        
        # ارسال گزارش به ادمین
        admin_chat_id = update.effective_user.id
        await send_broadcast_report(admin_chat_id, broadcast['title'], sent, failed, total)
        
        # نمایش نتیجه نهایی
        progress = round((sent + failed) / total * 100, 1) if total > 0 else 0
        success_rate = round(sent / total * 100, 1) if total > 0 else 0
        
        final_text = (
            f"📊 **گزارش نهایی ارسال**\n\n"
            f"📌 **{broadcast['title']}**\n\n"
            f"👥 کل کاربران: {total:,}\n"
            f"✅ ارسال موفق: {sent:,} ({success_rate}%)\n"
            f"❌ ناموفق: {failed:,}\n\n"
            f"📈 پیشرفت: {progress}%\n"
            f"✅ **ارسال به پایان رسید!**"
        )
        
        await progress_msg.edit_text(
            final_text,
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"❌ Broadcast error: {e}", exc_info=True)
        await progress_msg.edit_text(
            f"❌ <b>خطا در ارسال پیام!</b>\n\n"
            f"<code>{str(e)[:200]}</code>",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )

# ---------- پیام همگانی زمان‌بندی شده ----------

async def broadcast_scheduled_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع پیام همگانی زمان‌بندی شده"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    from database import check_admin_permission
    
    if user_id != admin_id:
        if not check_admin_permission(user_id, admin_id, "perm_broadcast_scheduled"):
            await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
            return ConversationHandler.END
    
    context.user_data['broadcast'] = {}
    context.user_data['broadcast_type'] = 'scheduled'
    context.user_data['broadcast_step'] = 'title'
    context.user_data['awaiting_message'] = True
    
    # ✅ اول پیام رو نشون بده
    await query.edit_message_text(
        "📝 <b>پیام همگانی زمان‌بندی شده - مرحله ۱/۴</b>\n\n"
        "لطفاً <b>عنوان</b> پیام را ارسال کنید:\n"
        "(مثلاً: اطلاعیه مهم، تخفیف ویژه)\n\n"
        "🔙 برای بازگشت /cancel را بزنید",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='HTML'
    )
    return BROADCAST_TITLE  # ✅ بعد از نمایش پیام

async def broadcast_scheduled_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت عنوان و پیام برای زمان‌بندی"""
    if not context.user_data.get('awaiting_message'):
        return ConversationHandler.END

    if context.user_data.get('broadcast_type') != 'scheduled':
        return ConversationHandler.END    
    
    message = update.message.text
    step = context.user_data.get('broadcast_step', 'title')
    
    if step == 'title':
        context.user_data['broadcast']['title'] = message
        context.user_data['broadcast_step'] = 'message'
        
        await update.message.reply_text(
            f"📝 <b>مرحله ۲/۴</b>\n\n"
            f"عنوان: <b>{message}</b>\n\n"
            f"حالا لطفاً <b>متن پیام</b> را ارسال کنید:\n\n"
            f"🔙 برای بازگشت /cancel را بزنید",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_MESSAGE
    
    elif step == 'message':
        context.user_data['broadcast']['message'] = message
        context.user_data['broadcast_step'] = 'date'

        # کیبورد انتخاب تاریخ با توضیحات کامل
        await update.message.reply_text(
            f"📅 <b>مرحله ۳/۴ - انتخاب تاریخ</b>\n\n"
            f"عنوان: <b>{context.user_data['broadcast']['title']}</b>\n"
            f"پیام: {message[:50]}...\n\n"
            f"می‌توانید تاریخ <b>امروز</b> را انتخاب کنید\n"
            f"یا یک <b>تاریخ دلخواه</b> وارد نمایید.\n\n"
            f"⚠️ <b>نکات مهم:</b>\n"
            f"• تاریخ نمی‌تواند مربوط به گذشته باشد\n"
            f"• فرمت تاریخ شمسی: <b>YYYY/MM/DD</b>\n"
            f"• مثال: <b>1405/05/15</b>\n\n"
            f"لطفاً تاریخ ارسال را انتخاب کنید:",
            reply_markup=date_selection_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_DATE


async def broadcast_scheduled_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت تاریخ شمسی و اعتبارسنجی"""
    date_input = update.message.text.strip()
    
    try:
        import jdatetime
        parts = date_input.split('/')
        if len(parts) != 3:
            raise ValueError("فرمت اشتباه")
        
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        persian_date = jdatetime.date(year, month, day)
        gregorian_date = persian_date.togregorian()
        
        today = jdatetime.date.today()
        if persian_date < today:
            await update.message.reply_text(
                f"❌ <b>خطا!</b>\n\n"
                f"تاریخ وارد شده ({date_input}) مربوط به گذشته است!\n"
                f"📌 امروز: <b>{today.strftime('%Y/%m/%d')}</b>\n\n"
                f"لطفاً یک تاریخ <b>امروز یا بعد از امروز</b> وارد کنید:",
                reply_markup=back_to_admin_keyboard(),
                parse_mode='HTML'
            )
            return BROADCAST_DATE
        
        context.user_data['broadcast']['date'] = gregorian_date.strftime("%Y-%m-%d")
        context.user_data['broadcast']['persian_date'] = date_input
        context.user_data['broadcast_step'] = 'time'
        
        await update.message.reply_text(
            f"🕐 <b>مرحله ۴/۴ - انتخاب ساعت</b>\n\n"
            f"📅 تاریخ: <b>{date_input}</b>\n\n"
            f"لطفاً <b>ساعت</b> را به صورت تهران وارد کنید:\n"
            f"📌 فرمت: <b>HH:MM</b> (۲۴ ساعته)\n"
            f"📌 مثال: <b>14:30</b> یا <b>09:00</b>\n\n"
            f"⚠️ اگر تاریخ امروز است، ساعت باید بعد از الان باشد.\n\n"
            f"🔙 برای بازگشت /cancel را بزنید",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_TIME
        
    except Exception as e:
        logger.error(f"Date validation error: {e}")
        await update.message.reply_text(
            f"❌ <b>فرمت تاریخ اشتباه است!</b>\n\n"
            f"لطفاً تاریخ را به صورت <b>YYYY/MM/DD</b> وارد کنید.\n"
            f"مثال: <b>1405/05/15</b>\n\n"
            f"دوباره تلاش کنید:",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_DATE


async def broadcast_scheduled_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت ساعت تهران و ثبت نهایی"""
    time_input = update.message.text.strip()
    
    try:
        parts = time_input.split(':')
        if len(parts) != 2:
            raise ValueError("فرمت اشتباه")
        
        hour, minute = int(parts[0]), int(parts[1])
        
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("ساعت یا دقیقه نامعتبر")
        
        import jdatetime
        from datetime import datetime
        import pytz
        
        persian_date_str = context.user_data['broadcast']['persian_date']
        today = jdatetime.date.today()
        
        if persian_date_str == today.strftime('%Y/%m/%d'):
            now_tehran = datetime.now(pytz.timezone('Asia/Tehran'))
            scheduled_time = now_tehran.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if scheduled_time <= now_tehran:
                await update.message.reply_text(
                    f"❌ <b>خطا!</b>\n\n"
                    f"ساعت وارد شده ({time_input}) مربوط به گذشته است!\n"
                    f"📌 الان ساعت: <b>{now_tehran.strftime('%H:%M')}</b>\n\n"
                    f"لطفاً یک ساعت <b>بعد از الان</b> وارد کنید:",
                    reply_markup=back_to_admin_keyboard(),
                    parse_mode='HTML'
                )
                return BROADCAST_TIME
        
        context.user_data['broadcast']['time'] = f"{hour:02d}:{minute:02d}"
        
        title = context.user_data['broadcast']['title']
        message = context.user_data['broadcast']['message']
        date_miladi = context.user_data['broadcast']['date']
        
        broadcast_id = save_broadcast(
            update.effective_user.id, title, message,
            date_miladi, f"{hour:02d}:{minute:02d}"
        )
        
        total_users = get_total_users_count()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تایید و برنامه‌ریزی", callback_data=f"admin_confirm_scheduled_{broadcast_id}")],
            [InlineKeyboardButton("❌ لغو", callback_data="admin_panel")]
        ])
        
        await update.message.reply_text(
            f"📢 <b>تایید نهایی</b>\n\n"
            f"📌 عنوان: <b>{title}</b>\n"
            f"📝 پیام: {message[:100]}...\n"
            f"📅 تاریخ: <b>{persian_date_str}</b> (شمسی)\n"
            f"🕐 ساعت: <b>{hour:02d}:{minute:02d}</b> (تهران)\n"
            f"👥 گیرندگان: <b>{total_users}</b> کاربر\n\n"
            f"آیا تأیید می‌کنید؟",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Time validation error: {e}")
        await update.message.reply_text(
            f"❌ <b>فرمت ساعت اشتباه است!</b>\n\n"
            f"لطفاً ساعت را به صورت <b>HH:MM</b> (۲۴ ساعته) وارد کنید.\n"
            f"مثال: <b>14:30</b> یا <b>09:00</b>\n\n"
            f"دوباره تلاش کنید:",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_TIME

async def broadcast_date_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت انتخاب تاریخ (امروز یا دستی)"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "broadcast_date_custom":
        # کاربر می‌خواد دستی وارد کنه
        await query.edit_message_text(
            "📅 <b>وارد کردن تاریخ دلخواه</b>\n\n"
            "لطفاً تاریخ را به صورت شمسی وارد کنید:\n\n"
            "📌 فرمت: <b>YYYY/MM/DD</b>\n"
            "📌 مثال: <b>1405/05/15</b>\n\n"
            "⚠️ <b>شرایط:</b>\n"
            "• تاریخ نمی‌تواند مربوط به گذشته باشد\n"
            "• تاریخ امروز یا بعد از آن مجاز است\n\n"
            "🔙 برای بازگشت /cancel را بزنید",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_DATE
    
    elif data.startswith("broadcast_date_"):
        # کاربر امروز رو انتخاب کرده
        persian_date_str = data.replace("broadcast_date_", "")
        
        try:
            import jdatetime
            parts = persian_date_str.split('/')
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            persian_date = jdatetime.date(year, month, day)
            gregorian_date = persian_date.togregorian()
            
            # اعتبارسنجی - تاریخ امروز طبیعتاً معتبره
            today = jdatetime.date.today()
            if persian_date < today:
                await query.edit_message_text(
                    "❌ خطای سیستمی! تاریخ امروز نامعتبر است.",
                    reply_markup=back_to_admin_keyboard()
                )
                return BROADCAST_DATE
            
            context.user_data['broadcast']['date'] = gregorian_date.strftime("%Y-%m-%d")
            context.user_data['broadcast']['persian_date'] = persian_date_str
            context.user_data['broadcast_step'] = 'time'
            
            await query.edit_message_text(
                f"🕐 <b>مرحله ۴/۴ - انتخاب ساعت</b>\n\n"
                f"📅 تاریخ: <b>{persian_date_str}</b>\n\n"
                f"لطفاً <b>ساعت</b> را به صورت تهران وارد کنید:\n"
                f"📌 فرمت: <b>HH:MM</b> (۲۴ ساعته)\n"
                f"📌 مثال: <b>14:30</b> یا <b>09:00</b>\n\n"
                f"⚠️ اگر تاریخ امروز است،\n"
                f"ساعت باید بعد از زمان فعلی باشد.\n\n"
                f"🔙 برای بازگشت /cancel را بزنید",
                reply_markup=back_to_admin_keyboard(),
                parse_mode='HTML'
            )
            return BROADCAST_TIME
            
        except Exception as e:
            logger.error(f"Date processing error: {e}")
            await query.edit_message_text(
                "❌ خطا در پردازش تاریخ!",
                reply_markup=back_to_admin_keyboard()
            )
            return BROADCAST_DATE

async def confirm_scheduled_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تایید نهایی و برنامه‌ریزی"""
    query = update.callback_query
    await query.answer()
    
    broadcast_id = int(query.data.split("_")[-1])
    
    # ✅ استفاده از get_broadcast_by_id به جای لوپ
    broadcast = get_broadcast_by_id(broadcast_id)
    
    if not broadcast:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())
        return
    
    # ✅ چک کن که قبلاً لغو نشده باشه
    if broadcast.get('is_cancelled') or broadcast.get('status') == 'cancelled':
        await query.edit_message_text(
            "⛔ این پیام قبلاً لغو شده است!",
            reply_markup=back_to_admin_keyboard()
        )
        return
    
    from reminders.reminder_scheduler import scheduler
    from apscheduler.triggers.date import DateTrigger
    from datetime import datetime
    import pytz
    import asyncio
    
    tehran_tz = pytz.timezone('Asia/Tehran')
    
    # ✅ اعتبارسنجی تاریخ و زمان
    try:
        run_date_tehran = datetime.strptime(
            f"{broadcast['send_date']} {broadcast['send_time']}:00",
            "%Y-%m-%d %H:%M:%S"
        )
        run_date_tehran = tehran_tz.localize(run_date_tehran)
        
        # ✅ چک کن که زمان وارد شده از الان بزرگتر باشه
        now_tehran = datetime.now(tehran_tz)
        if run_date_tehran <= now_tehran:
            await query.edit_message_text(
                f"❌ <b>خطا!</b>\n\n"
                f"زمان وارد شده ({broadcast['send_time']}) مربوط به گذشته است!\n"
                f"📌 الان ساعت: <b>{now_tehran.strftime('%H:%M')}</b>\n\n"
                f"لطفاً دوباره تلاش کنید.",
                reply_markup=back_to_admin_keyboard(),
                parse_mode='HTML'
            )
            return
            
    except Exception as e:
        logger.error(f"❌ Date/time validation error: {e}")
        await query.edit_message_text(
            "❌ تاریخ یا زمان نامعتبر است!",
            reply_markup=back_to_admin_keyboard()
        )
        return
    
    run_date_utc = run_date_tehran.astimezone(pytz.UTC)
    admin_chat_id = update.effective_user.id
    
    # ✅ تابع ارسال با چک‌های اضافی
    def send_scheduled_broadcast_sync():
        # ✅ چک کن که broadcast هنوز وجود داره
        b = get_broadcast_by_id(broadcast_id)
        if not b:
            logger.warning(f"⚠️ Broadcast {broadcast_id} not found at execution time")
            return
        
        # ✅ چک کن که لغو نشده باشه
        if b.get('is_cancelled') or b.get('status') == 'cancelled':
            logger.info(f"⛔ Broadcast {broadcast_id} was cancelled, skipping...")
            return
        
        # ✅ چک کن که قبلاً ارسال نشده باشه
        if b.get('status') in ['completed', 'sending']:
            logger.info(f"⏭️ Broadcast {broadcast_id} already sent or sending, skipping...")
            return
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            logger.info(f"🚀 Starting scheduled broadcast {broadcast_id}")
            
            result = loop.run_until_complete(
                send_broadcast_now(
                    broadcast_id, 
                    b['admin_id'], 
                    b['title'], 
                    b['message']
                )
            )
            sent, failed, total = result
            
            # ✅ ارسال گزارش به ادمین
            loop.run_until_complete(
                send_broadcast_report(admin_chat_id, b['title'], sent, failed, total)
            )
            
            logger.info(f"✅ Scheduled broadcast {broadcast_id} completed: {sent}/{total} sent")
            
        except Exception as e:
            logger.error(f"❌ Scheduled broadcast error: {e}", exc_info=True)
            
            # ✅ تلاش برای ارسال گزارش خطا به ادمین
            try:
                loop.run_until_complete(
                    bot.send_message(
                        chat_id=admin_chat_id,
                        text=f"❌ <b>خطا در ارسال زمان‌بندی شده!</b>\n\n"
                             f"📌 {b['title']}\n"
                             f"<code>{str(e)[:200]}</code>",
                        parse_mode='HTML'
                    )
                )
            except:
                pass
        finally:
            loop.close()
    
    # ✅ لاگ زمان‌بندی
    logger.info(f"⏰ Scheduled broadcast {broadcast_id} for {run_date_tehran} (UTC: {run_date_utc})")
    
    # ✅ اضافه کردن job به scheduler
    job_id = f"broadcast_{broadcast_id}"
    scheduler.add_job(
        send_scheduled_broadcast_sync,
        trigger=DateTrigger(run_date=run_date_utc),
        id=job_id,
        replace_existing=True
    )
    
    # ✅ ذخیره job_id در دیتابیس (اختیاری)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE broadcasts 
            SET job_id = ? 
            WHERE id = ?
        ''', (job_id, broadcast_id))
        conn.commit()
        conn.close()
        logger.info(f"💾 Job ID {job_id} saved for broadcast {broadcast_id}")
    except Exception as e:
        logger.warning(f"⚠️ Could not save job_id: {e}")
    
    total_users = get_total_users_count()
    
    # ✅ نمایش پیام تایید نهایی
    await query.edit_message_text(
        f"✅ <b>پیام همگانی برنامه‌ریزی شد!</b>\n\n"
        f"📌 عنوان: <b>{broadcast['title']}</b>\n"
        f"📅 تاریخ: <b>{broadcast['send_date']}</b>\n"
        f"🕐 ساعت تهران: <b>{broadcast['send_time']}</b>\n"
        f"👥 گیرندگان: <b>{total_users}</b> کاربر\n\n"
        f"⏳ پیام در تاریخ مشخص شده ارسال خواهد شد.\n"
        f"📊 گزارش ارسال برای شما فرستاده می‌شود.",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='HTML'
    )

async def show_broadcast_progress(update: Update, context: ContextTypes.DEFAULT_TYPE, broadcast_id: int):
    """نمایش و آپدیت خودکار پیشرفت ارسال - با محدودیت زمانی"""
    max_attempts = 120  # حداکثر ۳ دقیقه (۱۲۰ × ۱.۵ ثانیه)
    last_text = ""
    
    for attempt in range(max_attempts):
        progress_text = get_broadcast_progress_text(broadcast_id)
        
        # فقط اگر متن تغییر کرده آپدیت کن
        if progress_text != last_text:
            last_text = progress_text
            
            # بررسی وضعیت broadcast
            broadcast = get_broadcast_by_id(broadcast_id)
            if not broadcast:
                break
            
            # اگر تموم شده یا متوقف شده
            if broadcast['status'] in ['completed', 'failed', 'stopped', 'cancelled']:
                final_text = get_broadcast_progress_text(broadcast_id)
                
                if broadcast['status'] == 'completed':
                    final_text += "\n\n✅ <b>ارسال به پایان رسید!</b>"
                elif broadcast['status'] == 'stopped':
                    final_text += "\n\n🛑 <b>ارسال متوقف شد!</b>"
                elif broadcast['status'] == 'failed':
                    final_text += "\n\n❌ <b>ارسال با خطا مواجه شد!</b>"
                
                try:
                    await update.effective_message.edit_text(
                        final_text,
                        reply_markup=broadcast_action_keyboard(
                            broadcast_id, 
                            broadcast['status'] == 'completed', 
                            broadcast['status'] == 'cancelled'
                        ),
                        parse_mode='HTML'
                    )
                except Exception:
                    pass
                return
            
            # آپدیت پیام
            try:
                await update.effective_message.edit_text(
                    progress_text,
                    reply_markup=broadcast_action_keyboard(
                        broadcast_id,
                        broadcast['status'] == 'sending',
                        False
                    ),
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.debug(f"Could not update progress message: {e}")
        
        await asyncio.sleep(1.5)
    
    # اگر به حداکثر تلاش رسید
    logger.warning(f"⚠️ Progress monitoring timed out for broadcast {broadcast_id}")
    try:
        final_text = get_broadcast_progress_text(broadcast_id)
        await update.effective_message.edit_text(
            final_text + "\n\n⚠️ <b>مانیتورینگ متوقف شد. لطفاً دوباره بررسی کنید.</b>",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
    except Exception:
        pass
        
async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عملیات جاری را کنسل کن و به مدیریت پنل برگرد"""
    context.user_data.clear()
    
    if update.message:
        await update.message.reply_text(
            "❌ عملیات لغو شد.\n\nبازگشت به پنل مدیریت:",
            reply_markup=back_to_admin_keyboard()
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            "❌ عملیات لغو شد.",
            reply_markup=back_to_admin_keyboard()
        )
    
    return ConversationHandler.END

async def edit_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ویرایش ادمین - نمایش لیست برای انتخاب"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # ✅ اصلاح: هم ادمین اصلی و هم دسترسی رو چک کن
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_edit_permissions"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return  # ✅ اینجا نیازی به ConversationHandler.END نیست چون از کالبک اومده
    
    admins = get_all_admins()
    if not admins:
        await query.edit_message_text("📭 هیچ ادمین فرعی وجود ندارد!", reply_markup=back_to_admin_keyboard())
        return
    
    keyboard = []
    for admin in admins:
        name = admin['first_name'] or 'ناشناس'
        keyboard.append([InlineKeyboardButton(
            f"✏️ {name} ({admin['user_id']})",
            callback_data=f"admin_edit_{admin['user_id']}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_manage_admins")])
    
    await query.edit_message_text(
        "✏️ <b>ویرایش دسترسی ادمین</b>\n\nادمین مورد نظر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def edit_admin_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش دسترسی‌های فعلی برای ویرایش"""
    query = update.callback_query
    await query.answer()
    
    edit_user_id = int(query.data.split("_")[-1])
    
    # گرفتن دسترسی‌های فعلی
    user = get_user_info(edit_user_id)
    current_perms = user['admin_permissions'] if user and user['admin_permissions'] else ''
    selected = current_perms.split(',') if current_perms else []
    
    context.user_data['edit_admin_id'] = edit_user_id
    context.user_data['new_admin_permissions'] = selected
    
    await query.edit_message_text(
        f"✏️ <b>ویرایش دسترسی - کاربر: <code>{edit_user_id}</code></b>\n\n"
        f"دسترسی‌های فعلی: {len(selected)} مورد\n"
        f"دسترسی‌های مورد نظر را انتخاب کنید:",
        reply_markup=permissions_selection_keyboard(selected, is_edit=True),
        parse_mode='HTML'
    )
    return ADD_ADMIN_ID


async def save_admin_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ذخیره دسترسی‌های ویرایش شده"""
    query = update.callback_query
    await query.answer()
    
    edit_user_id = context.user_data.get('edit_admin_id')
    permissions = context.user_data.get('new_admin_permissions', [])
    perms_str = ','.join(permissions) if permissions else ''
    
    db_add_admin(edit_user_id, perms_str)  # آپدیت می‌کنه
    
    from admin.admin_keyboards import get_permission_name
    perm_names = [get_permission_name(p) for p in permissions]
    perm_text = "\n".join([f"✅ {n}" for n in perm_names]) if perm_names else "❌ هیچ دسترسی"
    
    await query.edit_message_text(
        f"✅ <b>دسترسی‌ها با موفقیت ویرایش شد!</b>\n\n"
        f"🆔 کاربر: <code>{edit_user_id}</code>\n\n"
        f"<b>دسترسی‌های جدید:</b>\n{perm_text}",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='HTML'
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# ---------- لیست پیام‌های همگانی ----------

async def broadcasts_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست پیام‌ها"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # ✅ اضافه کردن چک دسترسی
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_broadcast_now"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    broadcasts = get_all_broadcasts()
    if not broadcasts:
        await query.edit_message_text("📭 هیچ پیام همگانی وجود ندارد!", reply_markup=back_to_admin_keyboard())
        return
    
    await query.edit_message_text("📋 <b>پیام‌های همگانی</b>", reply_markup=admin_broadcasts_list_keyboard(broadcasts), parse_mode='HTML')
    
async def broadcast_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """جزئیات پیام همگانی با مدیریت بهتر وضعیت‌ها"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    if not check_admin_permission(user_id, admin_id, "perm_broadcast_now"):
        await query.edit_message_text("⛔ شما دسترسی ندارید!")
        return
    
    broadcast_id = int(query.data.split("_")[-1])
    broadcast = get_broadcast_by_id(broadcast_id)
    
    if not broadcast:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())
        return
    
    progress_text = get_broadcast_progress_text(broadcast_id)
    
    # وضعیت‌های مختلف
    if broadcast['status'] == 'sending':
        # در حال ارسال - شروع مانیتورینگ
        await query.edit_message_text(
            progress_text + "\n\n⏳ <b>در حال ارسال...</b>",
            reply_markup=broadcast_action_keyboard(broadcast_id, True, False),
            parse_mode='HTML'
        )
        asyncio.create_task(show_broadcast_progress(update, context, broadcast_id))
        
    elif broadcast['status'] == 'pending':
        # در انتظار ارسال
        await query.edit_message_text(
            progress_text + "\n\n⏰ <b>در انتظار ارسال زمان‌بندی شده...</b>",
            reply_markup=broadcast_action_keyboard(broadcast_id, False, False),
            parse_mode='HTML'
        )
        
    elif broadcast['status'] == 'completed':
        await query.edit_message_text(
            progress_text + "\n\n✅ <b>ارسال به پایان رسید!</b>",
            reply_markup=broadcast_action_keyboard(broadcast_id, True, False),
            parse_mode='HTML'
        )
        
    elif broadcast['status'] == 'failed':
        error_msg = broadcast.get('error_message', 'خطای نامشخص')
        await query.edit_message_text(
            progress_text + f"\n\n❌ <b>ارسال ناموفق!</b>\n<code>{error_msg[:100]}</code>",
            reply_markup=broadcast_action_keyboard(broadcast_id, False, False),
            parse_mode='HTML'
        )
        
    elif broadcast['status'] == 'cancelled' or broadcast['is_cancelled']:
        await query.edit_message_text(
            progress_text + "\n\n⛔ <b>ارسال لغو شد!</b>",
            reply_markup=broadcast_action_keyboard(broadcast_id, False, True),
            parse_mode='HTML'
        )
    
    else:
        await query.edit_message_text(
            progress_text,
            reply_markup=broadcast_action_keyboard(broadcast_id, False, False),
            parse_mode='HTML'
        )
            
async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو پیام با توقف ارسال فعال"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    if not check_admin_permission(user_id, admin_id, "perm_broadcast_now"):
        await query.edit_message_text("⛔ شما دسترسی ندارید!")
        return
    
    broadcast_id = int(query.data.split("_")[-1])
    broadcast = get_broadcast_by_id(broadcast_id)
    
    if not broadcast:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())
        return
    
    # اگر در حال ارسال بود، متوقفش کن
    if broadcast['status'] == 'sending':
        from admin.admin_database import mark_broadcast_stopped
        mark_broadcast_stopped(broadcast_id)
        await query.edit_message_text(
            f"🛑 <b>ارسال متوقف شد!</b>\n\n"
            f"📌 عنوان: {broadcast['title']}\n"
            f"✅ ارسال شده: {broadcast['sent_count']}\n"
            f"❌ ناموفق: {broadcast['failed_count']}",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
    else:
        # لغو معمولی برای پیام‌های در انتظار
        mark_broadcast_cancelled(broadcast_id)
        await query.edit_message_text(
            f"⛔ <b>پیام همگانی لغو شد!</b>\n\n📌 {broadcast['title']}",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )

async def delete_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف پیام با تایید"""
    query = update.callback_query
    
    broadcast_id = int(query.data.split("_")[-1])
    
    # اگر callback_data شامل confirm هست، یعنی تایید نهایی
    if "confirm_delete_broadcast" in query.data:
        await query.answer()
        delete_broadcast(broadcast_id)
        await query.edit_message_text(
            "🗑️ <b>پیام همگانی حذف شد!</b>",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return
    
    # در غیر این صورت، نمایش تاییدیه
    await query.answer()
    broadcast = get_broadcast_by_id(broadcast_id)
    
    if not broadcast:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())
        return
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ تأیید حذف", callback_data=f"admin_confirm_delete_broadcast_{broadcast_id}"),
            InlineKeyboardButton("🔙 انصراف", callback_data=f"admin_broadcast_detail_{broadcast_id}")
        ]
    ])
    
    await query.edit_message_text(
        f"⚠️ <b>حذف پیام همگانی</b>\n\n"
        f"📌 {broadcast['title']}\n\n"
        f"آیا از حذف این پیام اطمینان دارید؟\n"
        f"این عملیات قابل بازگشت نیست!",
        reply_markup=keyboard,
        parse_mode='HTML'
    )


# ---------- آمار ----------

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آمار و گزارشات با جزئیات بیشتر"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    if not check_admin_permission(user_id, admin_id, "perm_stats"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    # آمار کاربران
    total_users = get_total_users_count()
    active_users = len(get_all_active_users())
    banned_users = len(get_banned_users())
    inactive_users = total_users - active_users - banned_users
    
    # آمار ادمین‌ها
    sub_admins = get_all_admins()
    
    # آمار broadcast ها
    broadcasts = get_all_broadcasts()
    total_broadcasts = len(broadcasts)
    pending = len([b for b in broadcasts if b['status'] == 'pending'])
    sending = len([b for b in broadcasts if b['status'] == 'sending'])
    completed = len([b for b in broadcasts if b['status'] == 'completed'])
    failed = len([b for b in broadcasts if b['status'] == 'failed'])
    
    # محاسبه نرخ موفقیت broadcast
    success_rate = round(completed / total_broadcasts * 100, 1) if total_broadcasts > 0 else 0
    
    text = (
        f"📊 <b>آمار و گزارشات</b>\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"👑 <b>ادمین‌ها:</b>\n"
        f"   🔸 ادمین اصلی: ۱\n"
        f"   🔹 ادمین فرعی: {len(sub_admins)}\n\n"
        f"👥 <b>کاربران:</b>\n"
        f"   📊 کل: {total_users:,}\n"
        f"   🟢 فعال: {active_users:,}\n"
        f"   🔴 بن شده: {banned_users:,}\n"
        f"   ⚪ غیرفعال: {inactive_users:,}\n\n"
        f"📢 <b>پیام‌های همگانی:</b>\n"
        f"   📊 کل: {total_broadcasts}\n"
        f"   ⏰ در انتظار: {pending}\n"
        f"   📤 در حال ارسال: {sending}\n"
        f"   ✅ تکمیل شده: {completed}\n"
        f"   ❌ ناموفق: {failed}\n"
        f"   📈 نرخ موفقیت: {success_rate}%\n"
    )
    
    # هشدارها
    warnings = []
    if banned_users > total_users * 0.1:  # بیشتر از ۱۰٪
        warnings.append("⚠️ تعداد کاربران بن شده بالاست!")
    if inactive_users > total_users * 0.5:  # بیشتر از ۵۰٪
        warnings.append("⚠️ بیش از نیمی از کاربران غیرفعالند!")
    
    if warnings:
        text += f"\n<b>⚠️ هشدارها:</b>\n"
        for w in warnings:
            text += f"   {w}\n"
    
    await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode='HTML')
    
# ---------- وضعیت ربات ----------

async def admin_server_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش وضعیت سرور"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # ✅ چک دسترسی
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_bot_status"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    try:
        import psutil
        import platform
        import time
        
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()
        
        memory = psutil.virtual_memory()
        memory_used_gb = memory.used / (1024**3)
        memory_total_gb = memory.total / (1024**3)
        memory_percent = memory.percent
        
        disk = psutil.disk_usage('/')
        disk_used_gb = disk.used / (1024**3)
        disk_total_gb = disk.total / (1024**3)
        disk_percent = disk.percent
        
        system = platform.system()
        release = platform.release()
        uptime_seconds = time.time() - psutil.boot_time()
        uptime_days = int(uptime_seconds // 86400)
        uptime_hours = int((uptime_seconds % 86400) // 3600)
        uptime_minutes = int((uptime_seconds % 3600) // 60)
        
        text = (
            f"🖥️ <b>وضعیت سرور</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>💻 سیستم:</b>\n"
            f"   سیستم‌عامل: {system} {release}\n"
            f"   هسته‌های CPU: {cpu_count}\n"
            f"   فرکانس CPU: {cpu_freq.current:.0f} MHz\n"
            f"   زمان روشنایی: {uptime_days} روز {uptime_hours} ساعت {uptime_minutes} دقیقه\n\n"
            f"<b>📊 منابع:</b>\n"
            f"   🔹 CPU: {cpu_percent}%\n"
            f"   🔸 RAM: {memory_percent}% ({memory_used_gb:.1f}GB / {memory_total_gb:.1f}GB)\n"
            f"   🔹 Disk: {disk_percent}% ({disk_used_gb:.1f}GB / {disk_total_gb:.1f}GB)\n"
        )
        
        # نوار وضعیت گرافیکی
        def progress_bar(percent, length=10):
            filled = int(length * percent / 100)
            bar = "█" * filled + "░" * (length - filled)
            return bar
        
        text += f"\n<b>📈 نمودار وضعیت:</b>\n"
        text += f"   CPU  [{progress_bar(cpu_percent)}] {cpu_percent}%\n"
        text += f"   RAM  [{progress_bar(memory_percent)}] {memory_percent}%\n"
        text += f"   Disk [{progress_bar(disk_percent)}] {disk_percent}%\n"
        
        warnings = []
        if cpu_percent > 80:
            warnings.append("⚠️ CPU بالاست!")
        if memory_percent > 80:
            warnings.append("⚠️ RAM بالاست!")
        if disk_percent > 80:
            warnings.append("⚠️ Disk پر شده!")
        
        if warnings:
            text += f"\n<b>⚠️ هشدارها:</b>\n"
            for warning in warnings:
                text += f"   {warning}\n"
        
        await query.edit_message_text(
            text,
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Error getting server status: {e}")
        await query.edit_message_text(
            "❌ خطا در دریافت وضعیت سرور!",
            reply_markup=back_to_admin_keyboard()
        )

async def admin_bot_status_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # ✅ اصلاح
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_bot_status"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    status = get_bot_status()
    # ... ادامه کد
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
        f"⚙️ <b>وضعیت ربات</b>\n━━━━━━━━━━━━━━━━\n\n"
        f"🤖 ربات: {'🟢 فعال' if is_active else '🔴 غیرفعال'}\n\n"
        f"📈 <b>سرور:</b>\n"
        f"   CPU: {cpu}%\n"
        f"   RAM: {mem.percent}%\n"
        f"   Disk: {disk.percent}% ({disk_used_mb}MB / {disk_total_mb}MB)\n"
    )
    
    await query.edit_message_text(text, reply_markup=admin_bot_status_keyboard(is_active), parse_mode='HTML')

async def toggle_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغییر وضعیت ربات"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # ✅ اضافه کردن چک دسترسی
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_bot_status"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    new_status = toggle_bot_status()
    await query.edit_message_text(f"🤖 ربات {'🟢 روشن' if new_status else '🔴 خاموش'} شد!", reply_markup=back_to_admin_keyboard())
    
async def delete_all_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # ✅ اصلاح
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_delete_all"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ تأیید حذف", callback_data="admin_confirm_delete")],
        [InlineKeyboardButton("🔙 انصراف", callback_data="admin_bot_status")]
    ])
    # ... ادامه کد
    
    await query.edit_message_text("⚠️ <b>هشدار!</b>\n\nهمه داده‌های کاربران حذف می‌شود!\nاین عملیات قابل بازگشت نیست!\n\nمطمئن هستید؟", reply_markup=keyboard, parse_mode='HTML')

async def confirm_delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف همه داده‌ها"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # ✅ اضافه کردن چک دسترسی
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_delete_all"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    delete_all_user_data()
    await query.edit_message_text("✅ همه داده‌ها حذف شد!", reply_markup=back_to_admin_keyboard())
    
# ---------- مدیریت ادمین‌ها ----------

async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # ✅ اصلاح: هم ادمین اصلی و هم دسترسی رو چک کن
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_manage_admins"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    await query.edit_message_text("👥 <b>مدیریت ادمین‌ها</b>", reply_markup=admin_manage_admins_keyboard(), parse_mode='HTML')
    
async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """افزودن ادمین - مرحله ۱: دریافت user_id"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # ✅ اصلاح: هم ادمین اصلی و هم دسترسی رو چک کن
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_manage_admins"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return ConversationHandler.END
    
    context.user_data['awaiting_message'] = True
    context.user_data['awaiting_admin'] = True
    context.user_data['new_admin_permissions'] = []
    context.user_data['new_admin_step'] = 'user_id'
    
    await query.edit_message_text(
        "➕ <b>افزودن ادمین - مرحله ۱/۳</b>\n\nلطفاً <b>user_id</b> را ارسال کنید:",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='HTML'
    )
    return ADD_ADMIN_ID

async def add_admin_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مرحله ۲: دریافت user_id و نمایش انتخاب دسترسی"""
    if not context.user_data.get('awaiting_message'):
        return ConversationHandler.END
    
    # ✅ اضافه کردن چک دسترسی
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_manage_admins"):
        await update.message.reply_text("⛔ شما دسترسی به این بخش ندارید!")
        return ConversationHandler.END
    
    try:
        new_admin_id = int(update.message.text.strip())
        context.user_data['new_admin_id'] = new_admin_id
        context.user_data['new_admin_step'] = 'permissions'
        
        await update.message.reply_text(
            f"➕ <b>افزودن ادمین - مرحله ۲/۳</b>\n\n"
            f"🆔 کاربر: <code>{new_admin_id}</code>\n\n"
            f"دسترسی‌های مورد نظر را انتخاب کنید:",
            reply_markup=permissions_selection_keyboard([]),
            parse_mode='HTML'
        )
        return ADD_ADMIN_ID
    except ValueError:
        await update.message.reply_text(
            "❌ شناسه نامعتبر! دوباره تلاش کنید:",
            reply_markup=back_to_admin_keyboard()
        )
        return ADD_ADMIN_ID

async def handle_permission_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تاگل دسترسی‌ها (شیشه‌ای)"""
    query = update.callback_query
    await query.answer()
    
    # ✅ اضافه کردن چک دسترسی
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_manage_admins"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    data = query.data
    selected = context.user_data.get('new_admin_permissions', [])
    
    if data == "perm_all":
        from admin.admin_keyboards import PERMISSION_BUTTONS
        selected = [code for _, code in PERMISSION_BUTTONS]
        context.user_data['new_admin_permissions'] = selected
    elif data == "perm_none":
        selected = []
        context.user_data['new_admin_permissions'] = []
    elif data == "perm_done":
        new_admin_id = context.user_data.get('new_admin_id')
        perms = context.user_data.get('new_admin_permissions', [])
        
        from admin.admin_keyboards import PERMISSION_BUTTONS, get_permission_name
        perm_names = [get_permission_name(p) for p in perms]
        perm_text = "\n".join([f"✅ {n}" for n in perm_names]) if perm_names else "❌ هیچ دسترسی"
        
        await query.edit_message_text(
            f"📢 <b>تایید نهایی - مرحله ۳/۳</b>\n\n"
            f"🆔 کاربر: <code>{new_admin_id}</code>\n\n"
            f"<b>دسترسی‌ها:</b>\n{perm_text}\n\n"
            f"آیا تأیید می‌کنید؟",
            reply_markup=admin_confirm_add_keyboard(),
            parse_mode='HTML'
        )
        return
    elif data.startswith("perm_toggle_"):
        perm = data.replace("perm_toggle_", "")
        if perm in selected:
            selected.remove(perm)
        else:
            selected.append(perm)
        context.user_data['new_admin_permissions'] = selected
    
    # آپدیت کیبورد - فقط اگه تغییر کرده
    if data not in ["perm_done"]:
        new_text = (
            f"➕ <b>افزودن ادمین - مرحله ۲/۳</b>\n\n"
            f"🆔 کاربر: <code>{context.user_data.get('new_admin_id')}</code>\n\n"
            f"دسترسی‌های انتخاب شده: {len(selected)} مورد\n"
            f"دسترسی‌های مورد نظر را انتخاب کنید:"
        )
        new_markup = permissions_selection_keyboard(selected)
        
        try:
            await query.edit_message_text(
                new_text,
                reply_markup=new_markup,
                parse_mode='HTML'
            )
        except:
            pass  # متن تغییر نکرده - بی‌خیال

async def confirm_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأیید نهایی و ذخیره ادمین"""
    query = update.callback_query
    await query.answer()
    
    # ✅ اضافه کردن چک دسترسی
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_manage_admins"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    new_admin_id = context.user_data.get('new_admin_id')
    permissions = context.user_data.get('new_admin_permissions', [])
    perms_str = ','.join(permissions) if permissions else ''
    
    db_add_admin(new_admin_id, perms_str)
    
    perm_names = [get_permission_name(p) for p in permissions]
    perm_text = "\n".join([f"✅ {n}" for n in perm_names]) if perm_names else "❌ هیچ دسترسی"
    
    # ✅ اول پیام تایید به خودت بفرست
    await query.edit_message_text(
        f"✅ <b>ادمین با موفقیت افزوده شد!</b>\n\n"
        f"🆔 کاربر: <code>{new_admin_id}</code>\n\n"
        f"<b>دسترسی‌ها:</b>\n{perm_text}",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='HTML'
    )
    
    # ✅ بعدش سعی کن به ادمین جدید پیام بدی (با try/except)
    try:
        from telegram import Bot
        import os
        bot = Bot(token=os.getenv('TOKEN'))
        
        perm_names_text = "\n".join([f"🔹 {n}" for n in perm_names]) if perm_names else "🔹 دسترسی محدود"
        
        if new_admin_id:
            await bot.send_message(
                chat_id=new_admin_id,
                text=(
                    f"🎉 <b>تبریک! شما به عنوان ادمین منصوب شدید!</b>\n\n"
                    f"👑 <b>پنل مدیریت</b> به منوی اصلی شما اضافه شد.\n\n"
                    f"<b>دسترسی‌های شما:</b>\n{perm_names_text}\n\n"
                    f"برای مشاهده پنل، /start را بزنید."
                ),
                parse_mode='HTML'
            )
            logger.info(f"📩 Notification sent to new admin {new_admin_id}")
        else:
            logger.warning("⚠️ new_admin_id is empty! Cannot send notification.")
    except Exception as e:
        logger.error(f"❌ Failed to notify new admin {new_admin_id}: {e}")
        await update.effective_message.reply_text(
            f"⚠️ کاربر <code>{new_admin_id}</code> ربات رو استارت نکرده یا بلاک کرده.\n"
            f"دسترسی‌ها ذخیره شد ولی پیام تایید براش ارسال نشد.",
            parse_mode='HTML'
        )
    
    context.user_data.clear()
    
async def cancel_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو افزودن ادمین"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    await query.edit_message_text(
        "❌ افزودن ادمین لغو شد.",
        reply_markup=back_to_admin_keyboard()
    )
    return ConversationHandler.END

async def remove_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف ادمین"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # ✅ اضافه کردن چک دسترسی
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_manage_admins"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    admins = get_all_admins()
    if not admins:
        await query.edit_message_text("📭 هیچ ادمین فرعی وجود ندارد!", reply_markup=back_to_admin_keyboard())
        return
    
    keyboard = []
    for admin in admins:
        name = admin['first_name'] or 'ناشناس'
        keyboard.append([InlineKeyboardButton(
            f"👤 {name} ({admin['user_id']})", 
            callback_data=f"admin_remove_{admin['user_id']}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_manage_admins")])
    
    await query.edit_message_text(
        "➖ <b>حذف ادمین</b>\n\nادمین مورد نظر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def remove_admin_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای حذف ادمین"""
    query = update.callback_query
    await query.answer()
    
    # ✅ اضافه کردن چک دسترسی
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_manage_admins"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    user_id_to_remove = int(query.data.split("_")[-1])
    db_remove_admin(user_id_to_remove)
    
    # ✅ اول پیام تایید به خودت بفرست
    await query.edit_message_text(
        f"✅ کاربر <code>{user_id_to_remove}</code> از ادمین‌ها حذف شد!",
        parse_mode='HTML',
        reply_markup=back_to_admin_keyboard()
    )
    
    # ✅ بعدش سعی کن به کاربر حذف شده پیام بدی
    try:
        from telegram import Bot
        import os
        bot = Bot(token=os.getenv('TOKEN'))
        
        if user_id_to_remove:
            await bot.send_message(
                chat_id=user_id_to_remove,
                text="📢 <b>دسترسی ادمین شما لغو شد.</b>\n\nدیگر به پنل مدیریت دسترسی ندارید.",
                parse_mode='HTML'
            )
            logger.info(f"📩 Notification sent to removed admin {user_id_to_remove}")
        else:
            logger.warning("⚠️ user_id is empty! Cannot send notification.")
    except Exception as e:
        logger.error(f"❌ Failed to notify removed admin {user_id_to_remove}: {e}")
        await update.effective_message.reply_text(
            f"⚠️ کاربر <code>{user_id_to_remove}</code> ربات رو استارت نکرده یا بلاک کرده.\n"
            f"دسترسی‌ها حذف شد ولی پیام اطلاع‌رسانی براش ارسال نشد.",
            parse_mode='HTML'
        )
    
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # ✅ اضافه کردن چک دسترسی
    from database import check_admin_permission
    if not check_admin_permission(user_id, admin_id, "perm_list_admins"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    admins = get_all_admins()
    # ... ادامه کد
    
    text = f"👑 <b>لیست ادمین‌ها:</b>\n\n🔸 ادمین اصلی: <code>{admin_id}</code>\n🔹 دسترسی: همه موارد\n\n"
    
    if admins:
        text += "<b>ادمین‌های فرعی:</b>\n"
        for admin in admins:
            name = admin['first_name'] or 'ناشناس'
            permissions = admin['admin_permissions'] or ''
            
            if permissions == 'all' or permissions == '':
                perm_text = "همه موارد"
            else:
                from admin.admin_keyboards import get_permission_name
                perms = permissions.split(',')
                perm_text = ', '.join([get_permission_name(p) for p in perms])
            
            text += f"   👤 {name} (<code>{admin['user_id']}</code>)\n"
            text += f"      🔹 {perm_text}\n"
    else:
        text += "📭 هیچ ادمین فرعی وجود ندارد"
    
    await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode='HTML')
    
# ---------- مدیریت کاربران ----------

async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی کاربران"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # ✅ اضافه کردن چک دسترسی
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_manage_users"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    await query.edit_message_text("🚫 <b>مدیریت کاربران</b>", reply_markup=admin_manage_users_keyboard(), parse_mode='HTML')
    
async def ban_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع بن"""
    query = update.callback_query
    await query.answer()
    
    # ✅ اضافه کردن چک دسترسی
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_manage_users"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    context.user_data['awaiting_message'] = True
    context.user_data['awaiting_ban'] = True
    
    await query.edit_message_text(
        "🔨 <b>بن کردن کاربر</b>\n\nلطفاً <b>user_id</b> را ارسال کنید:",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='HTML'
    )
    return BAN_USER_ID

async def ban_user_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای بن"""
    if not context.user_data.get('awaiting_message'):
        return ConversationHandler.END
    
    # ✅ اضافه کردن چک دسترسی
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_manage_users"):
        await update.message.reply_text("⛔ شما دسترسی به این بخش ندارید!")
        return ConversationHandler.END
    
    try:
        user_id_to_ban = int(update.message.text.strip())
        db_ban_user(user_id_to_ban)
        
        await update.message.reply_text(
            f"🚫 کاربر <code>{user_id_to_ban}</code> بن شد!",
            parse_mode='HTML',
            reply_markup=back_to_admin_keyboard()
        )
    except ValueError:
        await update.message.reply_text(
            "❌ شناسه نامعتبر!",
            reply_markup=back_to_admin_keyboard()
        )
    
    context.user_data.clear()
    return ConversationHandler.END
    
async def unban_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع آزادسازی"""
    query = update.callback_query
    await query.answer()
    
    # ✅ اضافه کردن چک دسترسی
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_manage_users"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    banned = get_banned_users()
    if not banned:
        await query.edit_message_text("📭 هیچ کاربر بن شده‌ای وجود ندارد!", reply_markup=back_to_admin_keyboard())
        return
    
    keyboard = []
    for user in banned:
        name = user['first_name'] or 'ناشناس'
        keyboard.append([InlineKeyboardButton(f"🔓 {name} ({user['user_id']})", callback_data=f"admin_unban_{user['user_id']}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_manage_users")])
    
    await query.edit_message_text("🔓 <b>آزادسازی کاربر</b>\n\nکاربر مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def unban_user_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای آزادسازی"""
    query = update.callback_query
    await query.answer()
    
    # ✅ اضافه کردن چک دسترسی
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_manage_users"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    user_id_to_unban = int(query.data.split("_")[-1])
    db_unban_user(user_id_to_unban)
    
    await query.edit_message_text(
        f"✅ کاربر <code>{user_id_to_unban}</code> آزاد شد!",
        parse_mode='HTML',
        reply_markup=back_to_admin_keyboard()
    )
    
async def banned_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست بن شده‌ها"""
    query = update.callback_query
    await query.answer()
    
    # ✅ اضافه کردن چک دسترسی
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_manage_users"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    banned = get_banned_users()
    if not banned:
        await query.edit_message_text("📭 هیچ کاربر بن شده‌ای وجود ندارد!", reply_markup=back_to_admin_keyboard())
        return
    
    text = "🚫 <b>لیست کاربران بن شده:</b>\n\n"
    for user in banned:
        name = user['first_name'] or 'ناشناس'
        text += f"🔴 {name} (<code>{user['user_id']}</code>)\n"
    
    await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode='HTML')
    
# ---------- جستجوی کاربر ----------

async def search_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع جستجو"""
    query = update.callback_query
    await query.answer()
    
    # ✅ اضافه کردن چک دسترسی
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_search_user"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return
    
    context.user_data['awaiting_message'] = True
    context.user_data['awaiting_search'] = True
    
    await query.edit_message_text(
        "🔍 <b>جستجوی کاربر</b>\n\nلطفاً <b>user_id</b> را ارسال کنید:",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='HTML'
    )
    return SEARCH_USER_ID
    
async def search_user_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نتیجه جستجو"""
    if not context.user_data.get('awaiting_message'):
        return ConversationHandler.END
    
    # ✅ اضافه کردن چک دسترسی
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    from database import check_admin_permission
    if user_id != admin_id and not check_admin_permission(user_id, admin_id, "perm_search_user"):
        await update.message.reply_text("⛔ شما دسترسی به این بخش ندارید!")
        return ConversationHandler.END
    
    try:
        search_user_id = int(update.message.text.strip())
        user = get_user_info(search_user_id)
        
        if not user:
            await update.message.reply_text("❌ کاربر یافت نشد!", reply_markup=back_to_admin_keyboard())
        else:
            reminders = get_all_user_reminders(search_user_id)
            active_reminders = len([r for r in reminders if r['is_active']])
            
            text = (
                f"🔍 <b>اطلاعات کاربر</b>\n\n"
                f"🆔 شناسه: <code>{user['user_id']}</code>\n"
                f"👤 نام: {user['first_name'] or 'ندارد'}\n"
                f"📝 یوزرنیم: @{user['username'] or 'ندارد'}\n"
                f"👑 ادمین: {'✅' if user['is_admin'] else '❌'}\n"
                f"🚫 بن شده: {'✅' if user['is_banned'] else '❌'}\n"
                f"📋 ریمایندرها: {len(reminders)} (فعال: {active_reminders})\n"
            )
            
            keyboard = []
            if user['is_banned']:
                keyboard.append([InlineKeyboardButton("🔓 آزادسازی", callback_data=f"admin_unban_{search_user_id}")])
            else:
                keyboard.append([InlineKeyboardButton("🔨 بن کاربر", callback_data=f"admin_ban_{search_user_id}")])
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")])
            
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    
    except ValueError:
        await update.message.reply_text("❌ شناسه نامعتبر!", reply_markup=back_to_admin_keyboard())
    
    context.user_data.clear()
    return ConversationHandler.END

# ---------- برگشت به پنل (اصلاح‌شده) ----------

async def back_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """برگشت به پنل مدیریت با پاکسازی"""
    query = update.callback_query
    await query.answer()
    
    # پاکسازی context
    context.user_data.clear()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    is_admin, admin_type, permissions = get_admin_info(user_id, admin_id)
    
    if not is_admin:
        await query.edit_message_text("⛔ شما دسترسی به پنل مدیریت ندارید!")
        return
    
    text = (
        f"👑 <b>پنل مدیریت</b>\n\n"
        f"🎭 سطح دسترسی: {'ادمین اصلی' if admin_type == 'main_admin' else 'ادمین فرعی'}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"از منوی زیر استفاده کنید:"
    )
    
    keyboard = admin_panel_keyboard(user_id=user_id, admin_id=admin_id)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode='HTML')

# ---------- مدیریت خطای کلی ----------

async def admin_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت خطاهای پنل ادمین"""
    logger.error(f"Admin panel error: {context.error}", exc_info=True)
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ <b>خطایی رخ داد!</b>\n\n"
                "لطفاً دوباره تلاش کنید یا به پنل مدیریت برگردید.",
                reply_markup=back_to_admin_keyboard(),
                parse_mode='HTML'
            )
        elif update.message:
            await update.message.reply_text(
                "❌ <b>خطایی رخ داد!</b>\n\n"
                "لطفاً دوباره تلاش کنید.",
                reply_markup=back_to_admin_keyboard(),
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")
    
    # پاکسازی context
    context.user_data.clear()

