import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from .reminder_keyboards import (
    reminder_menu_keyboard, days_keyboard, time_keyboard,
    reminders_list_keyboard, reminder_action_keyboard,
    main_menu_keyboard
)
from .reminder_database import (
    save_reminder as db_save_reminder,
    get_user_reminders as db_get_user_reminders,
    get_all_user_reminders as db_get_all_user_reminders,
    delete_reminder as db_delete_reminder,
    cancel_reminder as db_cancel_reminder,
    activate_reminder as db_activate_reminder
)
from .reminder_utils import get_weekday_name, get_persian_datetime
from .reminder_scheduler import schedule_reminder

logger = logging.getLogger(__name__)

# حالت‌های Conversation
REMINDER_MESSAGE, REMINDER_DAYS, REMINDER_TIME = range(3)

async def reminder_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی اعلان‌ها"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "🔔 **منوی اعلان‌ها**\n\n"
            "از دکمه‌های زیر استفاده کنید:",
            reply_markup=reminder_menu_keyboard(),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "🔔 **منوی اعلان‌ها**\n\n"
            "از دکمه‌های زیر استفاده کنید:",
            reply_markup=reminder_menu_keyboard(),
            parse_mode='Markdown'
        )

async def handle_reminder_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دکمه‌های منوی اعلان‌ها"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "set_reminder":
        await set_reminder_start(update, context)
    elif data == "view_reminders":
        await view_reminders(update, context)
    elif data == "delete_reminder":
        await show_delete_reminders(update, context)
    elif data == "cancel_reminder":
        await show_cancel_reminders(update, context)

async def set_reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع فرآیند تنظیم اعلان - مرحله ۱: عنوان"""
    query = update.callback_query
    await query.answer()
    
    # پاک کردن داده‌های قبلی
    context.user_data['reminder'] = {}
    context.user_data['selected_days'] = []
    context.user_data['hour'] = None
    context.user_data['minute'] = None
    context.user_data['step'] = 'title'
    
    await query.edit_message_text(
        "📝 **تنظیم اعلان جدید - مرحله ۱/۳**\n\n"
        "لطفاً **عنوان** اعلان را ارسال کنید:\n"
        "(مثلاً: جلسه هفتگی، کنکور، یادآوری دارو)\n\n"
        "🔙 برای بازگشت /cancel را بزنید",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_main")
        ]]),
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_message'] = True
    return REMINDER_MESSAGE

async def set_reminder_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت عنوان و پیام اعلان"""
    message = update.message.text
    step = context.user_data.get('step', 'title')
    
    if step == 'title':
        # ذخیره عنوان و درخواست پیام
        context.user_data['reminder']['title'] = message
        context.user_data['step'] = 'message'
        
        await update.message.reply_text(
            "📝 **تنظیم اعلان جدید - مرحله ۲/۳**\n\n"
            f"عنوان: **{message}**\n\n"
            "حالا لطفاً **متن پیام** یادآوری را ارسال کنید:\n"
            "(مثلاً: جلسه امروز ساعت ۱۰ صبح در اتاق کنفرانس)\n\n"
            "🔙 برای بازگشت /cancel را بزنید",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_main")
            ]]),
            parse_mode='Markdown'
        )
        return REMINDER_MESSAGE
    
    elif step == 'message':
        # ذخیره پیام و رفتن به انتخاب روزها
        context.user_data['reminder']['message'] = message
        context.user_data['awaiting_message'] = False
        context.user_data['step'] = 'days'
        
        await update.message.reply_text(
            "📅 **مرحله ۳/۳ - انتخاب روزهای هفته**\n\n"
            "روزهای مورد نظر را انتخاب کنید:\n"
            f"📌 **راهنما:** {get_persian_datetime()}",
            reply_markup=days_keyboard(),
            parse_mode='Markdown'
        )
        return REMINDER_DAYS

async def set_reminder_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت انتخاب روزهای هفته"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "days_done":
        if not context.user_data.get('selected_days'):
            await query.edit_message_text(
                "❌ لطفاً حداقل یک روز را انتخاب کنید!",
                reply_markup=days_keyboard(context.user_data.get('selected_days', []))
            )
            return REMINDER_DAYS
        
        await query.edit_message_text(
            "🕐 **انتخاب زمان**\n\n"
            "ساعت و دقیقه مورد نظر را انتخاب کنید:\n"
            f"📌 **زمان کنونی تهران:** {get_persian_datetime()}",
            reply_markup=time_keyboard(),
            parse_mode='Markdown'
        )
        return REMINDER_TIME
    
    elif data.startswith("days_"):
        day_num = int(data.split("_")[1])
        selected = context.user_data.get('selected_days', [])
        
        if day_num in selected:
            selected.remove(day_num)
        else:
            selected.append(day_num)
        
        context.user_data['selected_days'] = sorted(selected)
        
        await query.edit_message_text(
            "📅 **انتخاب روزهای هفته**\n\n"
            "روزهای مورد نظر را انتخاب کنید:\n"
            f"✅ انتخاب شده: {len(selected)} روز",
            reply_markup=days_keyboard(selected),
            parse_mode='Markdown'
        )
        return REMINDER_DAYS

async def set_reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت انتخاب زمان"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "time_done":
        hour = context.user_data.get('hour')
        minute = context.user_data.get('minute')
        
        if hour is None or minute is None:
            await query.answer("❌ لطفاً هم ساعت و هم دقیقه را انتخاب کنید!", show_alert=True)
            return REMINDER_TIME
        
        user_id = update.effective_user.id
        title = context.user_data['reminder'].get('title', 'بدون عنوان')
        message = context.user_data['reminder']['message']
        days = context.user_data['selected_days']
        
        # ذخیره در دیتابیس
        reminder_id = db_save_reminder(user_id, title, message, days, hour, minute)
        
        # برنامه‌ریزی تسک
        await schedule_reminder(reminder_id, user_id, title, message, days, hour, minute)
        
        # نمایش پیام موفقیت
        days_text = ", ".join([get_weekday_name(d) for d in days])
        await query.edit_message_text(
            f"✅ **اعلان با موفقیت تنظیم شد!**\n\n"
            f"📌 **عنوان:** {title}\n"
            f"📝 **پیام:** {message}\n"
            f"📅 **روزها:** {days_text}\n"
            f"🕐 **زمان:** {hour:02d}:{minute:02d}\n\n"
            f"ربات در روزهای مشخص شده ساعت {hour:02d}:{minute:02d} به شما یادآوری خواهد کرد.",
            reply_markup=reminder_menu_keyboard(),
            parse_mode='Markdown'
        )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    elif data == "time_page_0":
        await query.edit_message_text(
            "🕐 **انتخاب ساعت**\n\n"
            "لطفاً ساعت مورد نظر را انتخاب کنید:",
            reply_markup=time_keyboard(
                selected_hour=context.user_data.get('hour'),
                selected_minute=context.user_data.get('minute'),
                page=0
            ),
            parse_mode='Markdown'
        )
        return REMINDER_TIME
    
    elif data == "time_page_1":
        hour = context.user_data.get('hour')
        if hour is None:
            await query.answer("❌ لطفاً اول ساعت را انتخاب کنید!", show_alert=True)
            return REMINDER_TIME
        
        await query.edit_message_text(
            "🕐 **انتخاب دقیقه**\n\n"
            f"ساعت انتخاب شده: {hour:02d}\n"
            "لطفاً دقیقه مورد نظر را انتخاب کنید:",
            reply_markup=time_keyboard(
                selected_hour=hour,
                selected_minute=context.user_data.get('minute'),
                page=1
            ),
            parse_mode='Markdown'
        )
        return REMINDER_TIME
    
    elif data.startswith("time_h_"):
        hour = int(data.split("_")[2])
        context.user_data['hour'] = hour
        await query.answer(f"✅ ساعت {hour:02d} انتخاب شد")
        
        await query.edit_message_text(
            f"🕐 **انتخاب ساعت**\n\n"
            f"ساعت انتخاب شده: {hour:02d}\n\n"
            f"حالا می‌توانید به انتخاب دقیقه بروید:",
            reply_markup=time_keyboard(
                selected_hour=hour,
                selected_minute=context.user_data.get('minute'),
                page=0
            ),
            parse_mode='Markdown'
        )
        return REMINDER_TIME
    
    elif data.startswith("time_m_"):
        minute = int(data.split("_")[2])
        context.user_data['minute'] = minute
        await query.answer(f"✅ دقیقه {minute:02d} انتخاب شد")
        
        await query.edit_message_text(
            f"🕐 **انتخاب دقیقه**\n\n"
            f"دقیقه انتخاب شده: {minute:02d}\n"
            f"ساعت: {context.user_data.get('hour', '?')}:{minute:02d}\n\n"
            f"می‌توانید ثبت نهایی کنید یا ساعت را تغییر دهید:",
            reply_markup=time_keyboard(
                selected_hour=context.user_data.get('hour'),
                selected_minute=minute,
                page=1
            ),
            parse_mode='Markdown'
        )
        return REMINDER_TIME
    
    elif data == "noop":
        return REMINDER_TIME

async def view_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست همه اعلان‌ها (فعال و غیرفعال)"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    reminders = db_get_all_user_reminders(user_id)
    
    if not reminders:
        await query.edit_message_text(
            "📭 **هیچ اعلانی ندارید!**\n\n"
            "برای تنظیم اعلان جدید به منوی اعلان‌ها برگردید.",
            reply_markup=reminder_menu_keyboard(),
            parse_mode='Markdown'
        )
        return
    
    text = "📋 **لیست اعلان‌های شما:**\n\n"
    for r in reminders:
        days = ", ".join([get_weekday_name(int(d)) for d in r['days_of_week'].split(',')])
        status = "✅ فعال" if r['is_active'] else "⛔ غیرفعال"
        title = r['title'] if r['title'] else 'بدون عنوان'
        
        text += f"🆔 {r['id']}: **{title}**\n"
        text += f"   📝 {r['message'][:30]}...\n"
        text += f"   📅 {days} | 🕐 {r['hour']:02d}:{r['minute']:02d}\n"
        text += f"   📊 {status}\n\n"
    
    await query.edit_message_text(
        text,
        reply_markup=reminders_list_keyboard(reminders),
        parse_mode='Markdown'
    )

async def show_delete_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست اعلان‌ها برای حذف"""
    query = update.callback_query
    user_id = update.effective_user.id
    reminders = db_get_all_user_reminders(user_id)
    
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

async def show_cancel_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست اعلان‌ها برای لغو (غیرفعال کردن)"""
    query = update.callback_query
    user_id = update.effective_user.id
    reminders = db_get_user_reminders(user_id)  # فقط فعال‌ها
    
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

async def view_reminder_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش جزئیات یک اعلان خاص"""
    query = update.callback_query
    await query.answer()
    
    try:
        reminder_id = int(query.data.split("_")[1])
        user_id = update.effective_user.id
        
        reminders = db_get_all_user_reminders(user_id)
        reminder = None
        
        for r in reminders:
            if r['id'] == reminder_id:
                reminder = r
                break
        
        if not reminder:
            await query.edit_message_text(
                "❌ اعلان مورد نظر یافت نشد!",
                reply_markup=reminder_menu_keyboard()
            )
            return
        
        days = ", ".join([get_weekday_name(int(d)) for d in reminder['days_of_week'].split(',')])
        status = "✅ فعال" if reminder['is_active'] else "⛔ غیرفعال"
        title = reminder['title'] if reminder['title'] else 'بدون عنوان'
        
        text = (
            f"📋 **جزئیات اعلان**\n\n"
            f"🆔 شناسه: {reminder['id']}\n"
            f"📌 عنوان: **{title}**\n"
            f"📝 پیام: {reminder['message']}\n"
            f"📅 روزها: {days}\n"
            f"🕐 زمان: {reminder['hour']:02d}:{reminder['minute']:02d}\n"
            f"📊 وضعیت: {status}\n"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=reminder_action_keyboard(reminder_id, reminder['is_active']),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error viewing reminder detail: {e}")
        await query.edit_message_text(
            "❌ خطا در نمایش جزئیات اعلان!",
            reply_markup=reminder_menu_keyboard()
        )

async def delete_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف کامل اعلان"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        if not data.startswith("delete_"):
            await query.edit_message_text("❌ خطا در پردازش درخواست!")
            return
        
        reminder_id = int(data.split("_")[1])
        user_id = update.effective_user.id
        
        db_delete_reminder(reminder_id, user_id)
        
        # حذف از scheduler (اگه خطا داد بی‌خیال شو)
        from .reminder_scheduler import remove_scheduled_reminder
        try:
            remove_scheduled_reminder(reminder_id)
        except Exception as e:
            logger.warning(f"Scheduler removal warning (job may not exist): {e}")
        
        await query.edit_message_text(
            "✅ **اعلان با موفقیت حذف شد!**",
            reply_markup=reminder_menu_keyboard(),
            parse_mode='Markdown'
        )
    except (IndexError, ValueError) as e:
        logger.error(f"Error in delete_reminder: {e}")
        await query.edit_message_text(
            "❌ خطا در حذف اعلان!",
            reply_markup=reminder_menu_keyboard(),
            parse_mode='Markdown'
        )

async def cancel_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """غیرفعال کردن اعلان"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        if not data.startswith("cancel_"):
            await query.edit_message_text("❌ خطا در پردازش درخواست!")
            return
        
        reminder_id = int(data.split("_")[1])
        user_id = update.effective_user.id
        
        # غیرفعال کردن در دیتابیس
        db_cancel_reminder(reminder_id, user_id)
        
        # حذف از scheduler (اگه خطا داد بی‌خیال شو - ممکنه job وجود نداشته باشه)
        from .reminder_scheduler import remove_scheduled_reminder
        try:
            remove_scheduled_reminder(reminder_id)
        except Exception as e:
            logger.warning(f"Scheduler removal warning (job may not exist): {e}")
        
        await query.edit_message_text(
            "⛔ **اعلان غیرفعال شد!**\n\n"
            "اعلان پاک نشده و می‌توانید بعداً از طریق مشاهده اعلان‌ها دوباره فعالش کنید.",
            reply_markup=reminder_menu_keyboard(),
            parse_mode='Markdown'
        )
    except (IndexError, ValueError) as e:
        logger.error(f"Error in cancel_reminder: {e}")
        await query.edit_message_text(
            "❌ خطا در لغو اعلان!",
            reply_markup=reminder_menu_keyboard(),
            parse_mode='Markdown'
        )

async def activate_reminder_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فعال‌سازی مجدد اعلان"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        reminder_id = int(data.split("_")[1])
        user_id = update.effective_user.id
        
        # فعال کردن در دیتابیس
        db_activate_reminder(reminder_id, user_id)
        
        # دوباره به scheduler اضافه کن
        reminders = db_get_all_user_reminders(user_id)
        for r in reminders:
            if r['id'] == reminder_id:
                await schedule_reminder(
                    r['id'], r['user_id'], r['title'], r['message'],
                    [int(d) for d in r['days_of_week'].split(',')],
                    r['hour'], r['minute']
                )
                break
        
        await query.edit_message_text(
            "✅ **اعلان با موفقیت فعال شد!**",
            reply_markup=reminder_menu_keyboard(),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error activating reminder: {e}")
        await query.edit_message_text(
            "❌ خطا در فعال‌سازی اعلان!",
            reply_markup=reminder_menu_keyboard()
        )

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازگشت به منوی اصلی"""
    import os
    
    query = update.callback_query
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    # ⚠️ حالا user_id و admin_id رو پاس بده
    keyboard = main_menu_keyboard(user_id=user_id, admin_id=admin_id)
    
    if query:
        await query.answer()
        await query.edit_message_text(
            "🏠 **منوی اصلی**\n\n"
            "از دکمه‌های زیر استفاده کنید:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "🏠 **منوی اصلی**",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    context.user_data.clear()

async def back_to_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازگشت به منوی اعلان‌ها"""
    query = update.callback_query
    await query.answer()
    await reminder_menu(update, context)
