import logging
from telegram import Update
from telegram.ext import ContextTypes
from keyboards import get_main_menu, get_exam_menu, get_exam_detail_menu, get_admin_panel
from exam_data import get_exam_info, EXAMS

logger = logging.getLogger(__name__)

ADMINS = [7703672187]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    user_id = update.effective_user.id
    text = update.message.text
    
    if text == "🔙 بازگشت به منوی اصلی":
        keyboard = get_main_menu(ADMINS[0], user_id)
        await update.message.reply_text("🔙 به منوی اصلی بازگشتید.", reply_markup=keyboard)
        return
    
    if text == "🔙 بازگشت به کنکورها":
        keyboard = get_exam_menu()
        await update.message.reply_text("📚 لطفاً یکی از کنکورها را انتخاب کنید:", reply_markup=keyboard)
        return
    
    if text == "📚 اطلاعات کنکور":
        keyboard = get_exam_menu()
        await update.message.reply_text(
            "📚 **اطلاعات کنکورها**\n\nلطفاً یکی از کنکورهای زیر را انتخاب کنید:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return
    
    for exam_name in EXAMS.keys():
        if text == f"📖 {exam_name}":
            await show_exam_details(update, exam_name)
            return
        if text == f"🔄 تازه کردن {exam_name}":
            await show_exam_details(update, exam_name, refresh=True)
            return
    
    if text == "🛠 پنل مدیریت" and user_id in ADMINS:
        keyboard = get_admin_panel()
        await update.message.reply_text("🛠 **پنل مدیریت**", reply_markup=keyboard, parse_mode="Markdown")
        return
    
    if user_id in ADMINS and text in ["📊 آمار کاربران", "📨 ارسال پیام همگانی", 
                                       "🚫 مسدود کردن کاربر", "✅ فعال کردن کاربر", 
                                       "📋 لیست کاربران"]:
        await handle_admin_commands(update, text)
        return
    
    await handle_menu_buttons(update, text)

async def show_exam_details(update: Update, exam_name: str, refresh: bool = False):
    exam_info = get_exam_info(exam_name)
    if not exam_info:
        await update.message.reply_text("❌ اطلاعات این کنکور یافت نشد!")
        return
    
    time_left = exam_info["time_left"]
    
    if time_left["passed"]:
        time_text = "⏰ **این کنکور برگزار شده است!**"
    else:
        time_text = (
            f"⏳ **زمان باقی‌مانده تا کنکور:**\n\n"
            f"📅 **{time_left['total_days']}** روز (مجموع)\n"
            f"📅 **{time_left['weeks']}** هفته و **{time_left['days']}** روز\n"
            f"🕐 **{time_left['hours']}** ساعت\n"
            f"⏱ **{time_left['minutes']}** دقیقه\n"
            f"⚡️ **{time_left['seconds']}** ثانیه"
        )
    
    message = (
        f"📖 **{exam_info['title']}**\n\n"
        f"📅 تاریخ برگزاری: **{exam_info['date']}**\n"
        f"🕐 ساعت برگزاری: **{exam_info['time']}**\n"
        f"📍 به وقت تهران\n\n"
        f"{time_text}\n\n"
        f"🔄 برای بروزرسانی زمان، دکمه تازه کردن را بزنید."
    )
    
    keyboard = get_exam_detail_menu(exam_name)
    await update.message.reply_text(message, reply_markup=keyboard, parse_mode="Markdown")

async def handle_admin_commands(update: Update, command: str):
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
    responses = {
        "⏰ یادآوری کن": "⏰ **یادآوری:**\n\nلطفاً موضوع و تاریخ یادآوری را مشخص کن.\nمثال: `یادآوری فردا ساعت ۱۰ جلسه مشاوره`",
        "⏳ شمارش معکوس": "⏳ **شمارش معکوس تا کنکور:**\n\n⏱ ۲۵۰ روز مانده به کنکور سراسری ۱۴۰۶",
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
