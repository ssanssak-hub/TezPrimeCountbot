from telegram import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu(admin_id, user_id):
    """
    ساخت منوی اصلی با دکمه‌های شیشه‌ای
    """
    # دکمه‌های عمومی (برای همه)
    buttons = [
        [KeyboardButton("📚 اطلاعات کنکور")],
        [KeyboardButton("⏰ یادآوری کن")],
        [KeyboardButton("⏳ شمارش معکوس")],
        [KeyboardButton("📝 ثبت اطلاعات درسی")],
        [KeyboardButton("📋 برنامه ریزی")],
        [KeyboardButton("📊 مشاهده وضعیت درسی")],
        [KeyboardButton("🏆 رقابت با دیگران")],
        [KeyboardButton("👥 رقبا و دوستان من")],
        [KeyboardButton("✉️ ارسال پیام به دیگران")],
        [KeyboardButton("🤖 گپ با هوش مصنوعی")],
        [KeyboardButton("🎓 دریافت مشاوره")],
        [KeyboardButton("🗑 حذف حساب و اطلاعات من")]
    ]
    
    # دکمه پنل مدیریت (فقط برای ادمین‌ها)
    if user_id == admin_id:
        buttons.append([KeyboardButton("🛠 پنل مدیریت")])
    
    # ایجاد صفحه‌کلید با ۳ ستون برای زیبایی
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

def get_admin_panel():
    """
    دکمه‌های پنل مدیریت
    """
    buttons = [
        ["📊 آمار کاربران"],
        ["📨 ارسال پیام همگانی"],
        ["🚫 مسدود کردن کاربر"],
        ["✅ فعال کردن کاربر"],
        ["📋 لیست کاربران"],
        ["🔙 بازگشت به منوی اصلی"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)
