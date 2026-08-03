import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from .reminder_keyboards import (
    reminder_menu_keyboard, days_keyboard, time_keyboard,
    reminders_list_keyboard, reminder_action_keyboard,
    main_menu_keyboard
)
from .reminder_database import (
    save_reminder, get_user_reminders, delete_reminder, cancel_reminder
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
    """شروع فرآیند تنظیم اعلان"""
    query = update.callback_query
    await query.answer()
    
    # پاک کردن داده‌های قبلی
    context.user_data['reminder'] = {}
    context.user_data['selected_days'] = []
    context.user_data['hour'] = None
    context.user_data['minute'] = None
    
    await query.edit_message_text(
        "📝 **تنظیم اعلان جدید**\n\n"
        "لطفاً پیام یادآوری را ارسال کنید:\n"
        "(مثلاً: جلسه ساعت ۱۰ صبح)",
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_message'] = True
    return REMINDER_MESSAGE

async def set_reminder_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت پیام اعلان"""
    message = update.message.text
    context.user_data['reminder']['message'] = message
    context.user_data['awaiting_message'] = False
    
    # نمایش انتخاب روزهای هفته
    await update.message.reply_text(
        "📅 **انتخاب روزهای هفته**\n\n"
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
        # بررسی اینکه حداقل یک روز انتخاب شده
        if not context.user_data.get('selected_days'):
            await query.edit_message_text(
                "❌ لطفاً حداقل یک روز را انتخاب کنید!",
                reply_markup=days_keyboard(context.user_data.get('selected_days', []))
            )
            return REMINDER_DAYS
        
        # رفتن به مرحله انتخاب زمان
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
        # بررسی اینکه ساعت و دقیقه انتخاب شده
        if context.user_data.get('hour') is None or context.user_data.get('minute') is None:
            await query.edit_message_text(
                "❌ لطفاً ساعت و دقیقه را انتخاب کنید!",
                reply_markup=time_keyboard()
            )
            return REMINDER_TIME
        
        # ذخیره اعلان در دیتابیس
        user_id = update.effective_user.id
        message = context.user_data['reminder']['message']
        days = context.user_data['selected_days']
        hour = context.user_data['hour']
        minute = context.user_data['minute']
        
        reminder_id = save_reminder(user_id, message, days, hour, minute)
        
        # برنامه‌ریزی تسک
        await schedule_reminder(reminder_id, user_id, message, days, hour, minute)
        
        # نمایش پیام موفقیت
        days_text = ", ".join([get_weekday_name(d) for d in days])
        await query.edit_message_text(
            f"✅ **اعلان با موفقیت تنظیم شد!**\n\n"
            f"📝 **پیام:** {message}\n"
            f"📅 **روزها:** {days_text}\n"
            f"🕐 **زمان:** {hour:02d}:{minute:02d}\n\n"
            f"ربات در روزهای مشخص شده ساعت {hour:02d}:{minute:02d} به شما یادآوری خواهد کرد.",
            reply_markup=reminder_menu_keyboard(),
            parse_mode='Markdown'
        )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    elif data.startswith("time_h_"):
        hour = int(data.split("_")[2])
        context.user_data['hour'] = hour
        await query.answer(f"ساعت {hour} انتخاب شد")
        return REMINDER_TIME
    
    elif data.startswith("time_m_"):
        minute = int(data.split("_")[2])
        context.user_data['minute'] = minute
        await query.answer(f"دقیقه {minute} انتخاب شد")
        return REMINDER_TIME

async def view_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست اعلان‌ها"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    reminders = get_user_reminders(user_id)
    
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
        text += f"🆔 {r['id']}: {r['message']}\n"
        text += f"   📅 {days} | 🕐 {r['hour']:02d}:{r['minute']:02d}\n"
        text += f"   {'✅ فعال' if r['is_active'] else '❌ غیرفعال'}\n\n"
    
    await query.edit_message_text(
        text,
        reply_markup=reminders_list_keyboard(reminders),
        parse_mode='Markdown'
    )


async def delete_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف اعلان"""
    query = update.callback_query
    await query.answer()
    
    try:
        # استخراج ID از callback_data
        data = query.data
        if not data.startswith("delete_"):
            await query.edit_message_text("❌ خطا در پردازش درخواست!")
            return
        
        reminder_id = int(data.split("_")[1])
        user_id = update.effective_user.id
        
        from .reminder_database import delete_reminder as delete_reminder_db
        delete_reminder_db(reminder_id, user_id)
        
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
    """لغو اعلان (غیرفعال کردن)"""
    query = update.callback_query
    await query.answer()
    
    try:
        # استخراج ID از callback_data
        data = query.data
        if not data.startswith("cancel_"):
            await query.edit_message_text("❌ خطا در پردازش درخواست!")
            return
        
        reminder_id = int(data.split("_")[1])
        user_id = update.effective_user.id
        
        from .reminder_database import cancel_reminder as cancel_reminder_db
        cancel_reminder_db(reminder_id, user_id)
        
        await query.edit_message_text(
            "⛔ **اعلان با موفقیت لغو شد!**\n\n"
            "برای فعال کردن مجدد، اعلان جدید تنظیم کنید.",
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

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازگشت به منوی اصلی"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "🏠 **منوی اصلی**\n\n"
            "از دکمه‌های زیر استفاده کنید:",
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "🏠 **منوی اصلی**",
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )
    
    # پاک کردن داده‌های کاربر
    context.user_data.clear()

async def back_to_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازگشت به منوی اعلان‌ها"""
    query = update.callback_query
    await query.answer()
    await reminder_menu(update, context)
