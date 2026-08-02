from telegram import ReplyKeyboardMarkup, KeyboardButton
from exam_data import EXAMS

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
    
    # دکمه پنل مدیریت (فقط برای ادمین)
    if user_id == admin_id:
        buttons.append([KeyboardButton("🛠 پنل مدیریت")])
    
    # ایجاد صفحه‌کلید با ۱ ستون برای زیبایی
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

def get_exam_menu():
    """
    ساخت منوی انتخاب کنکور
    """
    buttons = []
    
    # اضافه کردن دکمه‌های کنکورها
    for exam_name in EXAMS.keys():
        buttons.append([KeyboardButton(f"📖 {exam_name}")])
    
    # دکمه بازگشت به منوی اصلی
    buttons.append([KeyboardButton("🔙 بازگشت به منوی اصلی")])
    
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

def get_exam_detail_menu(exam_name):
    """
    ساخت منوی جزئیات کنکور با دکمه‌های تازه کردن و بازگشت
    """
    buttons = [
        [KeyboardButton(f"🔄 تازه کردن {exam_name}")],
        [KeyboardButton("🔙 بازگشت به کنکورها")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

def get_admin_panel():
    """
    ساخت پنل مدیریت
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
