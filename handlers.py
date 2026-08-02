import logging
from telegram import Update
from telegram.ext import ContextTypes
from keyboards import get_main_menu, get_admin_panel

logger = logging.getLogger(__name__)

# لیست ادمین‌ها (می‌توانید چند ادمین اضافه کنید)
ADMINS = [7703672187]  # ادمین اصلی

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /start"""
    user = update.effective_user
    user_id = user.id
    
    welcome_message = (
        f"👋 سلام {user.first_name}!\n\n"
        "به ربات جامع کنکور خوش آمدی!\n"
        "از طریق منوی زیر می‌توانی از تمام امکانات استفاده کنی:\n\n"
        "📌 لطفاً یکی از گزینه‌ها را انتخاب کن."
    )
    
    keyboard = get_main_menu(ADMINS[0], user_id)
    await update.message.reply_text(welcome_message, reply_markup=keyboard)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت پیام‌های دریافتی"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # دکمه بازگشت به منوی اصلی
    if text == "🔙 بازگشت به منوی اصلی":
        keyboard = get_main_menu(ADMINS[0], user_id)
        await update.message.reply_text(
            "🔙 به منوی اصلی بازگشتید.",
            reply_markup=keyboard
        )
        return
    
    # پنل مدیریت (فقط برای ادمین‌ها)
    if text == "🛠 پنل مدیریت" and user_id in ADMINS:
        keyboard = get_admin_panel()
        await update.message.reply_text(
            "🛠 **پنل مدیریت**\n\n"
            "لطفاً یکی از گزینه‌های زیر را انتخاب کن:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return
    
    # دکمه‌های پنل مدیریت
    if user_id in ADMINS and text in ["📊 آمار کاربران", "📨 ارسال پیام همگانی", 
                                       "🚫 مسدود کردن کاربر", "✅ فعال کردن کاربر", 
                                       "📋 لیست کاربران"]:
        await handle_admin_commands(update, text)
        return
    
    # پردازش سایر دکمه‌ها (نمونه)
    await handle_menu_buttons(update, text)

async def handle_admin_commands(update: Update, command: str):
    """مدیریت دستورات پنل مدیریت"""
    messages = {
        "📊 آمار کاربران": "📊 **آمار کاربران:**\n\n• تعداد کل کاربران: ۰\n• کاربران فعال: ۰\n• کاربران مسدود: ۰",
        "📨 ارسال پیام همگانی": "📨 لطفاً پیام خود را برای ارسال همگانی وارد کن:",
        "🚫 مسدود کردن کاربر": "🚫 شناسه کاربر مورد نظر برای مسدودسازی را وارد کن:",
        "✅ فعال کردن کاربر": "✅ شناسه کاربر مورد نظر برای فعال‌سازی را وارد کن:",
        "📋 لیست کاربران": "📋 **لیست کاربران:**\n\n• هنوز کاربری ثبت نشده است."
    }
    
    message = messages.get(command, "⚠️ گزینه نامعتبر!")
    await update.message.reply_text(message, parse_mode="Markdown")

async def handle_menu_buttons(update: Update, text: str):
    """مدیریت دکمه‌های منوی اصلی"""
    responses = {
        "📚 اطلاعات کنکور": "📚 **اطلاعات کنکور:**\n\n• تاریخ کنکور: ۱۴۰۵/۰۲/۱۵\n• زمان باقی‌مانده: ۲۵۰ روز\n• مواد امتحانی: ریاضی، فیزیک، شیمی، زیست",
        "⏰ یادآوری کن": "⏰ **یادآوری:**\n\nلطفاً موضوع و تاریخ یادآوری را مشخص کن.\nمثال: `یادآوری فردا ساعت ۱۰ جلسه مشاوره`",
        "⏳ شمارش معکوس": "⏳ **شمارش معکوس تا کنکور:**\n\n⏱ ۲۵۰ روز مانده به کنکور سراسری ۱۴۰۵",
        "📝 ثبت اطلاعات درسی": "📝 **ثبت اطلاعات درسی:**\n\nلطفاً اطلاعات درسی خود را وارد کن:\n• درس: \n• مبحث: \n• درصد: \n• زمان مطالعه:",
        "📋 برنامه ریزی": "📋 **برنامه ریزی درسی:**\n\nبرنامه هفتگی خود را تنظیم کن:\n• شنبه: \n• یکشنبه: \n• دوشنبه: \n• سه‌شنبه: \n• چهارشنبه: \n• پنجشنبه: \n• جمعه:",
        "📊 مشاهده وضعیت درسی": "📊 **وضعیت درسی:**\n\n• میانگین مطالعه روزانه: ۴.۵ ساعت\n• درصد پیشرفت: ۶۰٪\n• دروس ضعیف: شیمی، فیزیک",
        "🏆 رقابت با دیگران": "🏆 **رقابت با دیگران:**\n\n• رتبه شما: ۱۵ از ۲۰۰\n• امتیاز: ۷۸۰\n• پیشرفت هفتگی: +۱۲٪",
        "👥 رقبا و دوستان من": "👥 **رقبا و دوستان:**\n\n• دوستان: ۳ نفر\n• رقبا: ۷ نفر\n• برای افزودن، شناسه کاربر را وارد کن:",
        "✉️ ارسال پیام به دیگران": "✉️ **ارسال پیام:**\n\nلطفاً شناسه کاربر و متن پیام را وارد کن:\nمثال: `پیام ۱۲۳۴۵ سلام چطوری؟`",
        "🤖 گپ با هوش مصنوعی": "🤖 **گپ با هوش مصنوعی:**\n\nسلام! من دستیار هوشمند تو هستم. سوالات درسی یا مشاوره‌ای خود را بپرس.",
        "🎓 دریافت مشاوره": "🎓 **دریافت مشاوره:**\n\nلطفاً موضوع مشاوره خود را انتخاب کن:\n• انتخاب رشته\n• روش مطالعه\n• کاهش استرس\n• مدیریت زمان",
        "🗑 حذف حساب و اطلاعات من": "🗑 **حذف حساب:**\n\n⚠️ آیا مطمئنی که می‌خواهی حساب و تمام اطلاعات خود را حذف کنی؟\n\nبرای تأیید، کلمه `تأیید` را وارد کن."
    }
    
    response = responses.get(text, "⚠️ این گزینه در حال توسعه است. به زودی اضافه می‌شود!")
    await update.message.reply_text(response, parse_mode="Markdown")
