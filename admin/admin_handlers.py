import logging
import os
import asyncio
import uuid
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
    check_admin_permission
)
from reminders.reminder_database import get_all_user_reminders
from admin.admin_keyboards import (
    admin_panel_keyboard, admin_manage_admins_keyboard,
    admin_manage_users_keyboard, admin_bot_status_keyboard,
    admin_broadcasts_list_keyboard, broadcast_action_keyboard,
    back_to_admin_keyboard, permissions_selection_keyboard,
    admin_confirm_add_keyboard,
    get_permission_name, date_selection_keyboard,
    # ✅ اضافه کردن import های جدید
    content_type_keyboard,
    inline_buttons_keyboard,
    broadcast_preview_keyboard,
    get_content_type_fa
)
from admin.admin_database import (
    init_admin_db, save_broadcast, get_all_broadcasts,
    mark_broadcast_cancelled, delete_broadcast, get_broadcast_stats,
    get_broadcast_progress, get_broadcast_by_id, save_broadcast_advanced
)
from admin.admin_broadcast import send_broadcast_now, get_broadcast_progress_text, send_broadcast_report, send_broadcast_advanced
from reminders.reminder_utils import get_weekday_name, get_persian_datetime

logger = logging.getLogger(__name__)

# حالت‌های Conversation
(BROADCAST_TITLE, BROADCAST_MESSAGE, BROADCAST_DATE, BROADCAST_TIME,
 BAN_USER_ID, UNBAN_USER_ID, ADD_ADMIN_ID, REMOVE_ADMIN_ID, SEARCH_USER_ID,
 BROADCAST_CONTENT_TYPE, BROADCAST_BUTTONS) = range(11)

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
    """شروع ارسال فوری - مرحله ۰: انتخاب نوع محتوا"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    if not check_admin_permission(user_id, admin_id, "perm_broadcast_now"):
        await query.edit_message_text("⛔ شما دسترسی ندارید!")
        return ConversationHandler.END
    
    context.user_data['broadcast'] = {}
    context.user_data['broadcast_type'] = 'now'
    context.user_data['broadcast_step'] = 'content_type'
    context.user_data['inline_buttons'] = []
    
    await query.edit_message_text(
        "📢 <b>ارسال پیام همگانی فوری</b>\n\n"
        "📌 <b>مرحله ۱/۴: انتخاب نوع پیام</b>\n\n"
        "لطفاً نوع محتوایی که می‌خواهید ارسال کنید را انتخاب نمایید:\n\n"
        "📝 متن | 🖼 عکس | 🎥 فیلم | 📄 فایل | 🎵 صدا",
        reply_markup=content_type_keyboard(),
        parse_mode='HTML'
    )
    return BROADCAST_CONTENT_TYPE

async def broadcast_now_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت عنوان و پیام - فقط برای نوع text"""
    if not context.user_data.get('awaiting_message'):
        return ConversationHandler.END
    
    broadcast_type = context.user_data.get('broadcast_type')
    content_type = context.user_data['broadcast'].get('content_type', 'text')
    
    if broadcast_type not in ['now', 'scheduled']:
        logger.error(f"❌ Unknown broadcast_type: {broadcast_type}")
        await update.message.reply_text("❌ خطا! نوع ارسال مشخص نیست.")
        return ConversationHandler.END
    
    # اگه محتوا فایل باشه، اینجا نباید بیاد
    if content_type != 'text':
        return ConversationHandler.END
    
    message = update.message.text
    step = context.user_data.get('broadcast_step', 'title')
    
    if step == 'title':
        context.user_data['broadcast']['title'] = message
        context.user_data['broadcast_step'] = 'message'
        
        await update.message.reply_text(
            f"📝 عنوان: <b>{message}</b>\n\n"
            f"حالا <b>متن پیام</b> را ارسال کنید:\n\n"
            f"⚠️ این پیام به <b>همه کاربران</b> ارسال خواهد شد!\n\n"
            f"🔙 برای بازگشت /cancel را بزنید",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_MESSAGE
    
    elif step == 'message':
        title = context.user_data['broadcast']['title']
        context.user_data['broadcast']['message'] = message
        context.user_data['broadcast_step'] = 'buttons'
        context.user_data['awaiting_message'] = False
        
        # رفتن به مرحله دکمه‌های شیشه‌ای
        await update.message.reply_text(
            f"📝 <b>متن پیام دریافت شد</b>\n\n"
            f"📌 عنوان: <b>{title}</b>\n"
            f"📝 متن: {message[:100]}...\n\n"
            f"حالا می‌توانید <b>دکمه‌های شیشه‌ای</b> به پیام اضافه کنید (اختیاری):\n\n"
            f"🔗 دکمه لینک: کاربر را به سایت/کانال هدایت می‌کند\n"
            f"🔘 دکمه داخلی: بعد از کلیک پیام نمایش می‌دهد",
            reply_markup=inline_buttons_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_BUTTONS

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
    """شروع پیام همگانی زمان‌بندی شده - مرحله ۰: انتخاب نوع محتوا"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    if not check_admin_permission(user_id, admin_id, "perm_broadcast_scheduled"):
        await query.edit_message_text("⛔ شما دسترسی به این بخش ندارید!")
        return ConversationHandler.END
    
    context.user_data['broadcast'] = {}
    context.user_data['broadcast_type'] = 'scheduled'
    context.user_data['broadcast_step'] = 'content_type'
    context.user_data['inline_buttons'] = []
    
    logger.info(f"📝 Scheduled broadcast started for user {user_id}")
    
    await query.edit_message_text(
        "📢 <b>ارسال پیام همگانی زمان‌بندی شده</b>\n\n"
        "📌 <b>مرحله ۱/۴: انتخاب نوع پیام</b>\n\n"
        "لطفاً نوع محتوایی که می‌خواهید ارسال کنید را انتخاب نمایید:\n\n"
        "📝 متن | 🖼 عکس | 🎥 فیلم | 📄 فایل | 🎵 صدا",
        reply_markup=content_type_keyboard(),
        parse_mode='HTML'
    )
    return BROADCAST_CONTENT_TYPE
    
async def broadcast_scheduled_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت عنوان و پیام برای زمان‌بندی"""
    if not context.user_data.get('awaiting_message'):
        return ConversationHandler.END

    if context.user_data.get('broadcast_type') != 'scheduled':
        return ConversationHandler.END    
    
    message = update.message.text
    step = context.user_data.get('broadcast_step', 'title')
    
    if step == 'title':
        # ✅ ذخیره عنوان
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
        # ✅ ذخیره متن پیام و رفتن به مرحله تاریخ
        context.user_data['broadcast']['message'] = message
        context.user_data['broadcast_step'] = 'date'

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
    
    else:
        await update.message.reply_text(
            "❌ خطا! لطفاً دوباره تلاش کنید.",
            reply_markup=back_to_admin_keyboard()
        )
        return ConversationHandler.END

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
    
    # ✅ دریافت broadcast و تبدیل به دیکشنری
    broadcast_row = get_broadcast_by_id(broadcast_id)
    
    if not broadcast_row:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())
        return
    
    # ✅ تبدیل به دیکشنری برای استفاده از .get()
    broadcast = dict(broadcast_row)
    
    # ✅ بررسی با .get() (چون الان دیکشنری هست)
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
    from telegram import Bot
    
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
        # ✅ دریافت broadcast و تبدیل به دیکشنری
        b_row = get_broadcast_by_id(broadcast_id)
        if not b_row:
            logger.warning(f"⚠️ Broadcast {broadcast_id} not found at execution time")
            return
        
        b = dict(b_row)  # ✅ تبدیل به دیکشنری
        
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
            
            # ✅ استفاده از send_broadcast_advanced به جای send_broadcast_now
            from admin.admin_broadcast import send_broadcast_advanced
            
            result = loop.run_until_complete(
                send_broadcast_advanced(
                    broadcast_id, 
                    b['admin_id'], 
                    b  # ✅ کل دیکشنری broadcast رو بفرست
                )
            )
            sent, failed, total = result
            
            # ✅ ارسال گزارش به ادمین
            from admin.admin_broadcast import send_broadcast_report
            loop.run_until_complete(
                send_broadcast_report(admin_chat_id, b['title'], sent, failed, total)
            )
            
            logger.info(f"✅ Scheduled broadcast {broadcast_id} completed: {sent}/{total} sent")
            
        except Exception as e:
            logger.error(f"❌ Scheduled broadcast error: {e}", exc_info=True)
            
            # ✅ تلاش برای ارسال گزارش خطا به ادمین
            try:
                bot = Bot(token=os.getenv('TOKEN'))
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
    
    # ✅ ذخیره job_id در دیتابیس
    try:
        from admin.admin_database import get_db_connection
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

# ============ هندلر انتخاب نوع محتوا ============

async def handle_content_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت انتخاب نوع محتوا - مشترک برای فوری و زمان‌بندی"""
    query = update.callback_query
    await query.answer()
    
    content_type = query.data.replace("content_type_", "")
    broadcast_type = context.user_data['broadcast_type']
    context.user_data['broadcast']['content_type'] = content_type
    
    if content_type == 'text':
        text = (
            "📝 <b>ارسال متن</b>\n\n"
            f"لطفاً <b>عنوان</b> پیام را وارد کنید:\n"
            "(مثلاً: اطلاعیه مهم، تخفیف ویژه)\n\n"
            "🔙 برای بازگشت /cancel را بزنید"
        )
        context.user_data['broadcast_step'] = 'title'
        context.user_data['awaiting_message'] = True
        
        await query.edit_message_text(
            text,
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_TITLE
        
    elif content_type in ['photo', 'video', 'document', 'audio']:
        content_fa = get_content_type_fa(content_type)
        text = (
            f"📎 <b>ارسال {content_fa}</b>\n\n"
            f"لطفاً فایل <b>{content_fa}</b> خود را ارسال کنید:\n\n"
            f"📌 می‌توانید برای فایل <b>کپشن</b> هم بنویسید.\n"
            f"📌 کپشن به عنوان عنوان پیام استفاده می‌شود.\n\n"
            f"🔙 برای بازگشت /cancel را بزنید"
        )
        context.user_data['broadcast_step'] = 'file'
        context.user_data['awaiting_message'] = True
        
        await query.edit_message_text(
            text,
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_TITLE


# ============ هندلر دریافت فایل ============

async def handle_file_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت فایل (عکس/فیلم/فایل/صدا) از ادمین"""
    if not context.user_data.get('awaiting_message'):
        return ConversationHandler.END
    
    broadcast_type = context.user_data.get('broadcast_type')
    if broadcast_type not in ['now', 'scheduled']:
        return ConversationHandler.END
    
    content_type = context.user_data['broadcast']['content_type']
    message = update.message
    
    file_id = None
    
    try:
        if content_type == 'photo':
            file_id = message.photo[-1].file_id  # بهترین کیفیت
        elif content_type == 'video':
            file_id = message.video.file_id
        elif content_type == 'document':
            file_id = message.document.file_id
        elif content_type == 'audio':
            if message.audio:
                file_id = message.audio.file_id
            elif message.voice:
                file_id = message.voice.file_id
                content_type = 'audio'  # ویس هم به عنوان audio ذخیره میشه
        
        if not file_id:
            await message.reply_text(
                f"❌ فایل نامعتبر! لطفاً یک <b>{get_content_type_fa(content_type)}</b> واقعی ارسال کنید:",
                reply_markup=back_to_admin_keyboard(),
                parse_mode='HTML'
            )
            return BROADCAST_TITLE
        
        # ذخیره اطلاعات فایل
        caption = message.caption or ''
        title = caption[:100] if caption else f"پیام {get_content_type_fa(content_type)}"
        
        context.user_data['broadcast']['file_id'] = file_id
        context.user_data['broadcast']['caption'] = caption
        context.user_data['broadcast']['title'] = title
        context.user_data['broadcast']['message'] = caption  # برای سازگاری
        
        # رفتن به مرحله دکمه‌های شیشه‌ای
        context.user_data['broadcast_step'] = 'buttons'
        context.user_data['awaiting_message'] = False
        context.user_data['awaiting_button'] = False
        
        await message.reply_text(
            f"✅ <b>فایل دریافت شد!</b>\n\n"
            f"📎 نوع: <b>{get_content_type_fa(content_type)}</b>\n"
            f"📝 کپشن: {caption[:100] if caption else 'ندارد'}\n\n"
            f"حالا می‌توانید <b>دکمه‌های شیشه‌ای</b> به پیام اضافه کنید (اختیاری):\n\n"
            f"🔗 دکمه لینک: کاربر را به سایت/کانال هدایت می‌کند\n"
            f"🔘 دکمه داخلی: بعد از کلیک پیام نمایش می‌دهد",
            reply_markup=inline_buttons_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_BUTTONS
        
    except Exception as e:
        logger.error(f"Error receiving file: {e}")
        await message.reply_text(
            "❌ خطا در دریافت فایل! دوباره تلاش کنید:",
            reply_markup=back_to_admin_keyboard()
        )
        return BROADCAST_TITLE

        
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
    
    # ✅ تبدیل sqlite3.Row به دیکشنری (این خط رو اضافه کنید)
    broadcasts = [dict(b) for b in broadcasts] if broadcasts else []
    
    if not broadcasts:
        await query.edit_message_text("📭 هیچ پیام همگانی وجود ندارد!", reply_markup=back_to_admin_keyboard())
        return
    
    await query.edit_message_text(
        "📋 <b>پیام‌های همگانی</b>", 
        reply_markup=admin_broadcasts_list_keyboard(broadcasts), 
        parse_mode='HTML'
    )
    
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
        new_text = progress_text + "\n\n⏳ <b>در حال ارسال...</b>"
        new_markup = broadcast_action_keyboard(broadcast_id, True, False)
    elif broadcast['status'] == 'pending':
        new_text = progress_text + "\n\n⏰ <b>در انتظار ارسال زمان‌بندی شده...</b>"
        new_markup = broadcast_action_keyboard(broadcast_id, False, False)
    elif broadcast['status'] == 'completed':
        new_text = progress_text + "\n\n✅ <b>ارسال به پایان رسید!</b>"
        new_markup = broadcast_action_keyboard(broadcast_id, True, False)
    elif broadcast['status'] == 'failed':
        error_msg = broadcast.get('error_message', 'خطای نامشخص')
        new_text = progress_text + f"\n\n❌ <b>ارسال ناموفق!</b>\n<code>{error_msg[:100]}</code>"
        new_markup = broadcast_action_keyboard(broadcast_id, False, False)
    elif broadcast['status'] == 'cancelled' or broadcast['is_cancelled']:
        new_text = progress_text + "\n\n⛔ <b>ارسال لغو شد!</b>"
        new_markup = broadcast_action_keyboard(broadcast_id, False, True)
    else:
        new_text = progress_text
        new_markup = broadcast_action_keyboard(broadcast_id, False, False)
    
    # ✅ با try/except خطا رو بگیر
    try:
        await query.edit_message_text(
            new_text,
            reply_markup=new_markup,
            parse_mode='HTML'
        )
    except Exception as e:
        if "Message is not modified" in str(e):
            await query.answer("ℹ️ اطلاعات قبلاً به‌روز است.")
        else:
            logger.error(f"❌ Error in broadcast_detail: {e}")
            raise
            
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

async def broadcast_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش آمار کامل broadcast"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    from database import check_admin_permission
    if not check_admin_permission(user_id, admin_id, "perm_broadcast_now"):
        await query.edit_message_text("⛔ شما دسترسی ندارید!")
        return
    
    broadcast_id = int(query.data.split("_")[-1])
    
    from admin.admin_database import get_broadcast_stats
    broadcast_row, logs = get_broadcast_stats(broadcast_id)
    
    if not broadcast_row:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())
        return
    
    broadcast = dict(broadcast_row)
    
    # محاسبه آمار از logs
    success_count = 0
    failed_count = 0
    for log in logs:
        if log['status'] == 'success':
            success_count += log['count']
        elif log['status'] == 'failed':
            failed_count += log['count']
    
    text = (
        f"📊 <b>آمار کامل</b>\n\n"
        f"📌 عنوان: {broadcast.get('title', 'بدون عنوان')}\n"
        f"📝 وضعیت: {broadcast.get('status', 'نامشخص')}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👥 کل کاربران: {broadcast.get('total_users', 0):,}\n"
        f"✅ ارسال موفق: {broadcast.get('sent_count', success_count):,}\n"
        f"❌ ناموفق: {broadcast.get('failed_count', failed_count):,}\n"
        f"🚫 بلاک شده: {broadcast.get('blocked_count', 0):,}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📅 تاریخ ایجاد: {broadcast.get('created_at', 'نامشخص')}\n"
    )
    
    if broadcast.get('started_at'):
        text += f"📤 زمان شروع: {broadcast.get('started_at')}\n"
    if broadcast.get('completed_at'):
        text += f"✅ زمان پایان: {broadcast.get('completed_at')}\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin_broadcasts_list")],
        [InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_panel")]
    ])
    
    # ✅ راه‌حل اصلی: با try/except خطا رو بگیر
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode='HTML')
    except Exception as e:
        if "Message is not modified" in str(e):
            # فقط به کاربر بگو تغییری نکرده
            await query.answer("ℹ️ اطلاعات قبلاً به‌روز است.")
        else:
            # خطای دیگه رو نشون بده
            logger.error(f"❌ Error in broadcast_stats: {e}")
            await query.edit_message_text(
                "❌ خطا در نمایش آمار!",
                reply_markup=back_to_admin_keyboard()
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

# برای چندرسانه هاست
# ============ هندلرهای دکمه‌های شیشه‌ای ============

async def handle_inline_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دکمه‌های شیشه‌ای (افزودن/حذف/تأیید)"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    buttons = context.user_data.get('inline_buttons', [])
    
    if data == "ib_skip":
        # رد کردن دکمه‌ها - رفتن به مرحله بعد
        broadcast_type = context.user_data['broadcast_type']
        if broadcast_type == 'now':
            return await show_final_preview(update, context)
        else:
            return await go_to_date_selection(update, context)
    
    elif data == "ib_confirm":
        # تأیید دکمه‌ها - رفتن به مرحله بعد
        broadcast_type = context.user_data['broadcast_type']
        if broadcast_type == 'now':
            return await show_final_preview(update, context)
        else:
            return await go_to_date_selection(update, context)
    
    elif data == "ib_add_url":
        # افزودن دکمه لینک
        context.user_data['awaiting_button'] = True
        context.user_data['adding_button_type'] = 'url'
        await query.edit_message_text(
            "🔗 <b>افزودن دکمه لینک</b>\n\n"
            "لطفاً متن دکمه و لینک را با فرمت زیر ارسال کنید:\n\n"
            "<code>متن دکمه | https://example.com</code>\n\n"
            "📌 مثال:\n"
            "<code>کانال ما | https://t.me/ourchannel</code>\n"
            "<code>سایت ما | https://example.com</code>\n\n"
            "🔙 برای بازگشت /cancel را بزنید",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_BUTTONS
    
    elif data == "ib_add_callback":
        # افزودن دکمه داخلی
        context.user_data['awaiting_button'] = True
        context.user_data['adding_button_type'] = 'callback'
        await query.edit_message_text(
            "🔘 <b>افزودن دکمه داخلی</b>\n\n"
            "لطفاً متن دکمه را ارسال کنید:\n"
            "(این دکمه بعد از کلیک، یک پیام نمایش می‌دهد)\n\n"
            "📌 مثال: <code>اطلاعات بیشتر</code>\n\n"
            "🔙 برای بازگشت /cancel را بزنید",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return BROADCAST_BUTTONS
    
    elif data.startswith("ib_remove_"):
        # حذف دکمه
        index = int(data.replace("ib_remove_", ""))
        if 0 <= index < len(buttons):
            removed = buttons.pop(index)
            context.user_data['inline_buttons'] = buttons
            
            # ✅ گرفتن متن دکمه از دیکشنری
            btn_text = removed.get('text', 'بدون متن')
            await query.answer(f"🗑️ دکمه '{btn_text[:20]}' حذف شد")
        
        await query.edit_message_text(
            "✏️ <b>مدیریت دکمه‌های شیشه‌ای</b>\n\n"
            f"تعداد دکمه‌ها: {len(buttons)}\n\n"
            "دکمه جدید اضافه کنید یا ادامه دهید:",
            reply_markup=inline_buttons_keyboard(buttons),
            parse_mode='HTML'
        )
        return BROADCAST_BUTTONS
    
    elif data == "ib_noop":
        # دکمه غیرفعال (برای نمایش فقط)
        await query.answer("ℹ️ این دکمه فقط برای نمایش است")
        return BROADCAST_BUTTONS

async def handle_button_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت متن/لینک دکمه شیشه‌ای"""
    if not context.user_data.get('awaiting_button'):
        return ConversationHandler.END
    
    text = update.message.text.strip()
    buttons = context.user_data.get('inline_buttons', [])
    btn_type = context.user_data.get('adding_button_type')
    
    # ✅ تعریف success_text با مقدار پیش‌فرض
    success_text = ""
    
    if btn_type == 'url':
        # فرمت: متن دکمه | لینک
        parts = text.split('|')
        if len(parts) != 2:
            await update.message.reply_text(
                "❌ فرمت اشتباه!\n\n"
                "📌 <b>فرمت صحیح:</b>\n"
                "<code>متن دکمه | https://example.com</code>\n\n"
                "مثال:\n"
                "<code>کانال ما | https://t.me/ourchannel</code>\n\n"
                "دوباره تلاش کنید:",
                reply_markup=back_to_admin_keyboard(),
                parse_mode='HTML'
            )
            return BROADCAST_BUTTONS
        
        btn_text = parts[0].strip()
        url = parts[1].strip()
        
        if not url.startswith('http'):
            await update.message.reply_text(
                "❌ لینک باید با http یا https شروع شود!\n"
                "دوباره تلاش کنید:",
                reply_markup=back_to_admin_keyboard()
            )
            return BROADCAST_BUTTONS
        
        buttons.append({
            'type': 'url',
            'text': btn_text,
            'url': url
        })
        
        success_text = (
            f"✅ <b>دکمه لینک افزوده شد!</b>\n\n"
            f"📌 متن: <b>{btn_text}</b>\n"
            f"🔗 لینک: {url}\n"
            f"🔢 تعداد کل: {len(buttons)}\n\n"
        )
    
    elif btn_type == 'callback':
        # ✅ فرمت اجباری: متن دکمه | پیام نمایشی
        
        if '|' not in text:
            # ❌ ادمین | نذاشته - راهنمایی کامل
            await update.message.reply_text(
                "❌ <b>فرمت اشتباه!</b>\n\n"
                "برای ساخت دکمه داخلی، باید متن دکمه و پیام را با <b>|</b> جدا کنید.\n\n"
                "📌 <b>فرمت صحیح:</b>\n"
                "<code>متن دکمه | پیام نمایشی</code>\n\n"
                "📋 <b>مثال‌ها:</b>\n"
                "<code>🎁 کد تخفیف | کد تخفیف: SALE50</code>\n"
                "<code>📞 پشتیبانی | پیام شما دریافت شد</code>\n"
                "<code>👍 لایک | ممنون از حمایت شما ❤️</code>\n\n"
                "⚠️ <b>نکات:</b>\n"
                "• متن دکمه: متنی که روی دکمه نمایش داده میشه (حداکثر ۳۰ کاراکتر)\n"
                "• پیام نمایشی: متنی که کاربر بعد از کلیک می‌بینه\n"
                "  - اگه ≤ ۲۰۰ کاراکتر باشه → به صورت Alert نشون داده میشه\n"
                "  - اگه بیشتر از ۲۰۰ کاراکتر باشه → به صورت پیام جداگانه ارسال میشه\n"
                "  - می‌تونی از <code>{name}</code> برای اسم کاربر استفاده کنی\n\n"
                "دوباره تلاش کنید:",
                reply_markup=back_to_admin_keyboard(),
                parse_mode='HTML'
            )
            return BROADCAST_BUTTONS
        
        # ✅ ادمین درست وارد کرده
        parts = text.split('|', 1)
        btn_text = parts[0].strip()
        alert_message = parts[1].strip()
        
        # ✅ چک کردن طول متن دکمه
        if len(btn_text) > 30:
            await update.message.reply_text(
                f"⚠️ <b>متن دکمه طولانیه!</b>\n\n"
                f"متن دکمه: <b>{btn_text}</b> ({len(btn_text)} کاراکتر)\n\n"
                f"حداکثر پیشنهادی: <b>۳۰ کاراکتر</b>\n"
                f"با این حال دکمه ساخته میشه، ولی ممکنه ظاهر خوبی نداشته باشه.\n\n"
                f"می‌خوای ادامه بدی یا متن کوتاه‌تری وارد کنی؟\n\n"
                f"برای ادامه، دوباره پیام رو بفرست.\n"
                f"برای لغو، /cancel رو بزن.",
                reply_markup=back_to_admin_keyboard(),  # ✅ اصلاح شد
                parse_mode='HTML'
            )
            return BROADCAST_BUTTONS
        
        # ✅ چک کردن طول پیام
        if len(alert_message) > 200:
            await update.message.reply_text(
                f"ℹ️ <b>پیام نمایشی طولانیه!</b> ({len(alert_message)} کاراکتر)\n\n"
                f"این پیام به صورت <b>Reply</b> ارسال میشه (نه Alert).\n"
                f"بعد از ۱۵ ثانیه به‌طور خودکار پاک میشه.\n\n"
                f"ادامه می‌دیم...",
                parse_mode='HTML'
            )
            import asyncio
            await asyncio.sleep(1)
        
        # ✅ ساختن دکمه
        import uuid
        button_id = uuid.uuid4().hex[:8]
        
        from admin.admin_database import save_button_message
        save_button_message(button_id, alert_message)
        
        callback_data = f"bc_{button_id}"
        
        buttons.append({
            'type': 'callback',
            'text': btn_text,
            'callback_data': callback_data,
            'button_id': button_id,
            'message': alert_message
        })
        
        success_text = (
            f"✅ <b>دکمه داخلی افزوده شد!</b>\n\n"
            f"📌 متن دکمه: <b>{btn_text}</b>\n"
            f"💬 پیام نمایشی:\n"
            f"<i>{alert_message[:150]}{'...' if len(alert_message) > 150 else ''}</i>\n"
            f"📏 طول پیام: {len(alert_message)} کاراکتر\n"
            f"🆔 شناسه: <code>{button_id}</code>\n"
            f"🔢 تعداد کل دکمه‌ها: {len(buttons)}\n\n"
        )
    
    else:
        logger.error(f"❌ Invalid btn_type: {btn_type}")
        await update.message.reply_text(
            "❌ خطا در تشخیص نوع دکمه! لطفاً دوباره تلاش کنید.",
            reply_markup=back_to_admin_keyboard()
        )
        return BROADCAST_BUTTONS
    
    context.user_data['inline_buttons'] = buttons
    context.user_data['awaiting_button'] = False
    context.user_data['adding_button_type'] = None
    
    success_text += "می‌توانید دکمه دیگری اضافه کنید یا ادامه دهید:"
    
    await update.message.reply_text(
        success_text,
        reply_markup=inline_buttons_keyboard(buttons),
        parse_mode='HTML'
    )
    return BROADCAST_BUTTONS

# ============ توابع کمکی برای مرحله بعد ============

async def go_to_date_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رفتن به مرحله انتخاب تاریخ (برای زمان‌بندی)"""
    query = update.callback_query
    
    title = context.user_data['broadcast'].get('title', 'بدون عنوان')
    content_type = context.user_data['broadcast'].get('content_type', 'text')
    buttons_count = len(context.user_data.get('inline_buttons', []))
    
    context.user_data['broadcast_step'] = 'date'
    
    await query.edit_message_text(
        f"📅 <b>مرحله ۳/۴ - انتخاب تاریخ</b>\n\n"
        f"📌 عنوان: <b>{title}</b>\n"
        f"📎 نوع: <b>{get_content_type_fa(content_type)}</b>\n"
        f"🔘 دکمه‌ها: {buttons_count} عدد\n\n"
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


async def show_final_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش پیش‌نمایش نهایی برای ارسال فوری"""
    query = update.callback_query
    
    broadcast_data = context.user_data['broadcast']
    content_type = broadcast_data.get('content_type', 'text')
    buttons = context.user_data.get('inline_buttons', [])
    title = broadcast_data.get('title', 'بدون عنوان')
    
    # ذخیره در دیتابیس
    import json
    from admin.admin_database import save_broadcast_advanced
    
    broadcast_id = save_broadcast_advanced(
        admin_id=update.effective_user.id,
        title=title,
        content_type=content_type,
        message=broadcast_data.get('message'),
        file_id=broadcast_data.get('file_id'),
        file_caption=broadcast_data.get('caption'),
        inline_buttons=buttons
    )
    
    users_count = get_total_users_count()
    
    # ارسال پیش‌نمایش به ادمین
    preview_text = (
        f"📢 <b>پیش‌نمایش نهایی پیام همگانی</b>\n\n"
        f"📌 عنوان: <b>{title}</b>\n"
        f"📎 نوع محتوا: <b>{get_content_type_fa(content_type)}</b>\n"
        f"👥 گیرندگان: <b>{users_count}</b> کاربر\n"
        f"🔘 دکمه‌های شیشه‌ای: <b>{len(buttons)} عدد</b>\n\n"
        f"آیا از ارسال اطمینان دارید؟"
    )
    
    await query.edit_message_text(
        preview_text,
        reply_markup=broadcast_preview_keyboard(broadcast_id, content_type),
        parse_mode='HTML'
    )
    
    context.user_data.clear()
    return ConversationHandler.END


# ============ هندلر تأیید نهایی ارسال پیشرفته ============

async def confirm_advanced_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأیید و ارسال پیشرفته"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    if not check_admin_permission(user_id, admin_id, "perm_broadcast_now"):
        await query.edit_message_text("⛔ شما دسترسی ندارید!")
        return
    
    # ✅ استخراج broadcast_id با regex
    import re
    match = re.search(r'confirm_adv_broadcast_(\d+)', query.data)
    if not match:
        await query.edit_message_text("❌ خطا در شناسایی پیام!", reply_markup=back_to_admin_keyboard())
        return
    
    broadcast_id = int(match.group(1))
    broadcast = get_broadcast_by_id(broadcast_id)
    
    if not broadcast:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())
        return
    
    broadcast_dict = dict(broadcast)
    
    if broadcast_dict.get('status') == 'sending':
        await query.answer("⏳ این پیام در حال ارسال است!", show_alert=True)
        return
    
    # پیام در حال ارسال
    progress_msg = await query.edit_message_text(
        "⏳ <b>در حال ارسال پیام همگانی...</b>\n\n"
        "🔄 لطفاً صبر کنید...",
        parse_mode='HTML'
    )
    
    try:
        # ✅ import تابع ارسال پیشرفته
        from admin.admin_broadcast import send_broadcast_advanced
        
        # استفاده از تابع ارسال پیشرفته
        task = asyncio.create_task(
            send_broadcast_advanced(
                broadcast_id,
                broadcast_dict['admin_id'],
                broadcast_dict
            )
        )
        
        # نمایش پیشرفت
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
        
        # ارسال گزارش
        admin_chat_id = update.effective_user.id
        await send_broadcast_report(admin_chat_id, broadcast_dict['title'], sent, failed, total)
        
        # نمایش نتیجه نهایی
        success_rate = round(sent / total * 100, 1) if total > 0 else 0
        
        final_text = (
            f"📊 <b>گزارش نهایی ارسال</b>\n\n"
            f"📌 <b>{broadcast_dict['title']}</b>\n\n"
            f"👥 کل کاربران: {total:,}\n"
            f"✅ ارسال موفق: {sent:,} ({success_rate}%)\n"
            f"❌ ناموفق: {failed:,}\n\n"
            f"✅ <b>ارسال به پایان رسید!</b>"
        )
        
        await progress_msg.edit_text(
            final_text,
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"❌ Advanced broadcast error: {e}", exc_info=True)
        await progress_msg.edit_text(
            f"❌ <b>خطا در ارسال پیام!</b>\n\n"
            f"<code>{str(e)[:200]}</code>",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )

# ============ هندلر ویرایش دکمه‌ها ============

async def edit_broadcast_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ویرایش دکمه‌های یک broadcast ذخیره شده"""
    query = update.callback_query
    await query.answer()
    
    # ✅ استخراج broadcast_id از callback_data جدید
    import re
    match = re.search(r'broadcast_edit_buttons_(\d+)', query.data)
    if not match:
        await query.edit_message_text("❌ خطا در شناسایی پیام!", reply_markup=back_to_admin_keyboard())
        return
    
    broadcast_id = int(match.group(1))
    broadcast = get_broadcast_by_id(broadcast_id)
    
    if not broadcast:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())
        return
    
    broadcast_dict = dict(broadcast)
    
    # بازیابی دکمه‌های قبلی
    import json
    old_buttons = []
    if broadcast_dict.get('inline_buttons'):
        try:
            old_buttons = json.loads(broadcast_dict['inline_buttons'])
        except:
            pass
    
    context.user_data['editing_broadcast_id'] = broadcast_id
    context.user_data['inline_buttons'] = old_buttons
    
    await query.edit_message_text(
        "✏️ <b>ویرایش دکمه‌های شیشه‌ای</b>\n\n"
        f"📌 عنوان: <b>{broadcast_dict['title']}</b>\n"
        f"🔢 تعداد دکمه‌های فعلی: {len(old_buttons)}\n\n"
        "دکمه‌ها را ویرایش کنید:",
        reply_markup=inline_buttons_keyboard(old_buttons, is_editing=True),
        parse_mode='HTML'
    )
    return BROADCAST_BUTTONS
