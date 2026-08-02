import logging
from telegram import Update
from keyboards import get_admin_panel

logger = logging.getLogger(__name__)

ADMINS = [7703672187]

async def handle_admin_panel(update: Update):
    """
    نمایش پنل مدیریت
    """
    keyboard = get_admin_panel()
    await update.message.reply_text(
        "🛠 پنل مدیریت\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کن:",
        reply_markup=keyboard
    )

async def handle_admin_commands(update: Update, command: str):
    """
    مدیریت دستورات پنل مدیریت
    """
    messages = {
        "📊 آمار کاربران": "📊 **آمار کاربران:**\n\n• تعداد کل کاربران: ۰\n• کاربران فعال: ۰\n• کاربران مسدود: ۰",
        "📨 ارسال پیام همگانی": "📨 لطفاً پیام خود را برای ارسال همگانی وارد کن:",
        "🚫 مسدود کردن کاربر": "🚫 شناسه کاربر مورد نظر برای مسدودسازی را وارد کن:",
        "✅ فعال کردن کاربر": "✅ شناسه کاربر مورد نظر برای فعال‌سازی را وارد کن:",
        "📋 لیست کاربران": "📋 **لیست کاربران:**\n\n• هنوز کاربری ثبت نشده است."
    }
    
    message = messages.get(command, "⚠️ گزینه نامعتبر!")
    await update.message.reply_text(message, parse_mode="Markdown")

def is_admin(user_id):
    """
    بررسی ادمین بودن کاربر
    """
    return user_id in ADMINS
