import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
import jdatetime
import re
from reminder_data import (
    add_reminder, get_user_reminders, get_active_reminders,
    delete_reminder, toggle_reminder, get_reminder_by_id
)
from exam_data import EXAMS
from keyboards import get_reminder_menu, get_exam_selection_menu

logger = logging.getLogger(__name__)

# ==================== وضعیت‌های مختلف برای مکالمه ====================
WAITING_FOR_EXAM_SELECTION = 1
WAITING_FOR_PERSONAL_TITLE = 2
WAITING_FOR_PERSONAL_DATE = 3
WAITING_FOR_PERSONAL_TIME = 4
WAITING_FOR_REMINDER_ACTION = 5

# ==================== دیکشنری وضعیت کاربران ====================
user_states = {}

# ==================== توابع ====================

async def handle_reminder_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی یادآوری"""
    keyboard = get_reminder_menu()
    await update.message.reply_text(
        "⏰ **منوی یادآوری**\n\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def handle_add_exam_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع فرآیند افزودن یادآوری کنکور"""
    keyboard = get_exam_selection_menu()
    await update.message.reply_text(
        "📚 **انتخاب کنکور برای یادآوری**\n\n"
        "لطفاً یکی از کنکورهای زیر را انتخاب کنید:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    user_id = update.effective_user.id
    user_states[user_id] = {"step": WAITING_FOR_EXAM_SELECTION}

async def handle_exam_selection_for_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش انتخاب کنکور برای یادآوری"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # بررسی اینکه کاربر آیا یک کنکور انتخاب کرده
    for exam_name in EXAMS.keys():
        if text == f"📖 {exam_name}":
            # پیدا کردن تاریخ و زمان کنکور
            exam_info = EXAMS[exam_name]
            reminder_id = add_reminder(
                user_id,
                "exam",
                f"یادآوری کنکور {exam_name}",
                exam_info["date"],
                exam_info["time"],
                exam_name
            )
            
            await update.message.reply_text(
                f"✅ **یادآوری کنکور {exam_name} با موفقیت ثبت شد!**\n\n"
                f"📅 تاریخ: {exam_info['date']}\n"
                f"🕐 ساعت: {exam_info['time']}\n"
                f"🆔 شناسه: `{reminder_id}`\n\n"
                f"ربات در زمان مقرر به شما یادآوری خواهد کرد.",
                parse_mode="Markdown"
            )
            
            # پاک کردن وضعیت کاربر
            if user_id in user_states:
                del user_states[user_id]
            
            # نمایش منوی اصلی یادآوری
            await handle_reminder_menu(update, context)
            return
    
    # اگر کاربر گزینه بازگشت را انتخاب کرد
    if text == "🔙 بازگشت به یادآوری":
        await handle_reminder_menu(update, context)
        return
    
    await update.message.reply_text("❌ لطفاً یکی از کنکورهای موجود را انتخاب کنید.")

async def handle_add_personal_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع فرآیند افزودن یادآوری شخصی"""
    user_id = update.effective_user.id
    user_states[user_id] = {"step": WAITING_FOR_PERSONAL_TITLE}
    
    await update.message.reply_text(
        "📝 **افزودن یادآوری شخصی**\n\n"
        "لطفاً عنوان یادآوری را وارد کنید:\n"
        "(مثلاً: جلسه مشاوره، مطالعه ریاضی، و غیره)",
        parse_mode="Markdown"
    )

async def handle_personal_reminder_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت عنوان یادآوری شخصی"""
    user_id = update.effective_user.id
    title = update.message.text
    
    if len(title) > 50:
        await update.message.reply_text("❌ عنوان یادآوری نباید بیشتر از ۵۰ کاراکتر باشد. لطفاً دوباره وارد کنید:")
        return
    
    user_states[user_id]["title"] = title
    user_states[user_id]["step"] = WAITING_FOR_PERSONAL_DATE
    
    await update.message.reply_text(
        f"📅 عنوان: **{title}**\n\n"
        "لطفاً تاریخ را به صورت **شمسی** وارد کنید:\n"
        "مثال: `1404/01/15`",
        parse_mode="Markdown"
    )

async def handle_personal_reminder_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت تاریخ یادآوری شخصی"""
    user_id = update.effective_user.id
    date_text = update.message.text.strip()
    
    # بررسی فرمت تاریخ
    if not re.match(r'^\d{4}/\d{2}/\d{2}$', date_text):
        await update.message.reply_text(
            "❌ فرمت تاریخ نامعتبر!\n"
            "لطفاً تاریخ را به صورت `1404/01/15` وارد کنید:",
            parse_mode="Markdown"
        )
        return
    
    # بررسی اعتبار تاریخ شمسی
    try:
        year, month, day = map(int, date_text.split('/'))
        jdatetime.date(year, month, day)
    except ValueError:
        await update.message.reply_text(
            "❌ تاریخ نامعتبر!\n"
            "لطفاً یک تاریخ معتبر شمسی وارد کنید:"
        )
        return
    
    user_states[user_id]["date"] = date_text
    user_states[user_id]["step"] = WAITING_FOR_PERSONAL_TIME
    
    await update.message.reply_text(
        f"📅 تاریخ: **{date_text}**\n\n"
        "لطفاً ساعت را به صورت **۲۴ ساعته** وارد کنید:\n"
        "مثال: `14:30`",
        parse_mode="Markdown"
    )

async def handle_personal_reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت زمان یادآوری شخصی"""
    user_id = update.effective_user.id
    time_text = update.message.text.strip()
    
    # بررسی فرمت زمان
    if not re.match(r'^\d{2}:\d{2}$', time_text):
        await update.message.reply_text(
            "❌ فرمت زمان نامعتبر!\n"
            "لطفاً زمان را به صورت `14:30` وارد کنید:",
            parse_mode="Markdown"
        )
        return
    
    hour, minute = map(int, time_text.split(':'))
    if hour > 23 or minute > 59:
        await update.message.reply_text(
            "❌ زمان نامعتبر!\n"
            "ساعت باید بین ۰ تا ۲۳ و دقیقه بین ۰ تا ۵۹ باشد."
        )
        return
    
    # ذخیره یادآوری
    title = user_states[user_id]["title"]
    date_text = user_states[user_id]["date"]
    
    reminder_id = add_reminder(
        user_id,
        "personal",
        title,
        date_text,
        time_text
    )
    
    await update.message.reply_text(
        f"✅ **یادآوری شخصی با موفقیت ثبت شد!**\n\n"
        f"📝 عنوان: {title}\n"
        f"📅 تاریخ: {date_text}\n"
        f"🕐 ساعت: {time_text}\n"
        f"🆔 شناسه: `{reminder_id}`\n\n"
        f"ربات در زمان مقرر به شما یادآوری خواهد کرد.",
        parse_mode="Markdown"
    )
    
    # پاک کردن وضعیت کاربر
    if user_id in user_states:
        del user_states[user_id]
    
    # نمایش منوی اصلی یادآوری
    await handle_reminder_menu(update, context)

async def handle_view_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست یادآوری‌های کاربر"""
    user_id = update.effective_user.id
    reminders = get_user_reminders(user_id)
    
    if not reminders:
        await update.message.reply_text(
            "📭 **لیست یادآوری‌ها خالی است!**\n\n"
            "برای افزودن یادآوری جدید، از گزینه‌های منو استفاده کنید.",
            parse_mode="Markdown"
        )
        return
    
    message = "📋 **لیست یادآوری‌های شما:**\n\n"
    active_count = 0
    inactive_count = 0
    
    for i, r in enumerate(reminders, 1):
        status = "✅ فعال" if r.get("is_active", True) else "❌ غیرفعال"
        if r.get("is_active", True):
            active_count += 1
        else:
            inactive_count += 1
        
        if r["type"] == "exam":
            message += f"{i}. 📖 {r['title']}\n"
        else:
            message += f"{i}. 📝 {r['title']}\n"
        
        message += f"   📅 {r['jalali_date']} 🕐 {r['time']}\n"
        message += f"   وضعیت: {status}\n"
        message += f"   🆔 شناسه: `{r['id']}`\n\n"
    
    message += f"📊 **جمع:** {len(reminders)} یادآوری ({active_count} فعال، {inactive_count} غیرفعال)"
    
    # ایجاد دکمه‌های عملیات
    keyboard = [
        [KeyboardButton("✏️ ویرایش/حذف یادآوری")],
        [KeyboardButton("🔙 بازگشت به یادآوری")]
    ]
    
    await update.message.reply_text(
        message,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )

async def handle_reminder_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت ویرایش/حذف یادآوری"""
    user_id = update.effective_user.id
    
    # اگر کاربر روی دکمه "✏️ ویرایش/حذف یادآوری" کلیک کرد
    if update.message.text == "✏️ ویرایش/حذف یادآوری":
        await update.message.reply_text(
            "✏️ **ویرایش/حذف یادآوری**\n\n"
            "لطفاً شناسه یادآوری مورد نظر را وارد کنید.\n"
            "می‌توانید شناسه را از لیست یادآوری‌ها پیدا کنید.",
            parse_mode="Markdown"
        )
        user_states[user_id] = {"step": WAITING_FOR_REMINDER_ACTION}
        return
    
    # اگر کاربر شناسه یادآوری را وارد کرده
    if user_id in user_states and user_states[user_id].get("step") == WAITING_FOR_REMINDER_ACTION:
        reminder_id = update.message.text.strip()
        reminder = get_reminder_by_id(user_id, reminder_id)
        
        if not reminder:
            await update.message.reply_text(
                "❌ شناسه یادآوری نامعتبر!\n"
                "لطفاً شناسه معتبر را وارد کنید:"
            )
            return
        
        # نمایش منوی عملیات برای آن یادآوری
        keyboard = [
            [KeyboardButton(f"✅ فعال کردن")],
            [KeyboardButton(f"❌ غیرفعال کردن")],
            [KeyboardButton(f"🗑 حذف")],
            [KeyboardButton("🔙 بازگشت به یادآوری")]
        ]
        
        # ذخیره شناسه یادآوری در وضعیت کاربر
        user_states[user_id]["target_reminder_id"] = reminder_id
        
        await update.message.reply_text(
            f"🆔 **یادآوری:** {reminder['title']}\n"
            f"وضعیت: {'✅ فعال' if reminder.get('is_active', True) else '❌ غیرفعال'}\n\n"
            "لطفاً عملیات مورد نظر را انتخاب کنید:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            parse_mode="Markdown"
        )
        return
    
    # اگر کاربر روی یکی از دکمه‌های عملیات کلیک کرد
    text = update.message.text
    target_id = user_states.get(user_id, {}).get("target_reminder_id")
    
    if text == "✅ فعال کردن" and target_id:
        if toggle_reminder(user_id, target_id):
            await update.message.reply_text(f"✅ یادآوری با شناسه `{target_id}` فعال شد!")
        else:
            await update.message.reply_text("❌ خطا در فعال‌سازی یادآوری!")
        # نمایش مجدد لیست
        await handle_view_reminders(update, context)
        return
    
    if text == "❌ غیرفعال کردن" and target_id:
        if toggle_reminder(user_id, target_id):
            await update.message.reply_text(f"❌ یادآوری با شناسه `{target_id}` غیرفعال شد!")
        else:
            await update.message.reply_text("❌ خطا در غیرفعال‌سازی یادآوری!")
        await handle_view_reminders(update, context)
        return
    
    if text == "🗑 حذف" and target_id:
        if delete_reminder(user_id, target_id):
            await update.message.reply_text(f"🗑 یادآوری با شناسه `{target_id}` حذف شد!")
            # پاک کردن وضعیت کاربر
            if user_id in user_states:
                del user_states[user_id]
        else:
            await update.message.reply_text("❌ خطا در حذف یادآوری!")
        await handle_view_reminders(update, context)
        return

def get_reminder_status(reminder):
    """دریافت وضعیت یادآوری"""
    return "✅ فعال" if reminder.get("is_active", True) else "❌ غیرفعال"
