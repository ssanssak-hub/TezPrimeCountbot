from telegram import ReplyKeyboardMarkup, KeyboardButton
from exam_data import EXAMS

def get_main_menu(admin_id, user_id):
    """منوی اصلی - دکمه‌های معمولی"""
    buttons = [
        ["📚 اطلاعات کنکور"],
        ["⏰ یادآوری کن"],
        ["⏳ شمارش معکوس"],
        ["📝 ثبت اطلاعات درسی"],
        ["📋 برنامه ریزی"],
        ["📊 مشاهده وضعیت درسی"],
        ["🏆 رقابت با دیگران"],
        ["👥 رقبا و دوستان من"],
        ["✉️ ارسال پیام به دیگران"],
        ["🤖 گپ با هوش مصنوعی"],
        ["🎓 دریافت مشاوره"],
        ["🗑 حذف حساب و اطلاعات من"]
    ]
    
    if user_id == admin_id:
        buttons.append(["🛠 پنل مدیریت"])
    
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

def get_exam_menu():
    """منوی انتخاب کنکور - دکمه‌های شیشه‌ای"""
    buttons = []
    for exam_name in EXAMS.keys():
        buttons.append([KeyboardButton(f"📖 {exam_name}")])
    buttons.append([KeyboardButton("🔙 بازگشت به منوی اصلی")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

def get_exam_detail_menu(exam_name):
    """منوی جزئیات کنکور - دکمه‌های شیشه‌ای"""
    buttons = [
        [KeyboardButton(f"🔄 تازه کردن {exam_name}")],
        [KeyboardButton("🔙 بازگشت به کنکورها")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

def get_admin_panel():
    """پنل مدیریت - دکمه‌های شیشه‌ای"""
    buttons = [
        [KeyboardButton("📊 آمار کاربران")],
        [KeyboardButton("📨 ارسال پیام همگانی")],
        [KeyboardButton("🚫 مسدود کردن کاربر")],
        [KeyboardButton("✅ فعال کردن کاربر")],
        [KeyboardButton("📋 لیست کاربران")],
        [KeyboardButton("🔙 بازگشت به منوی اصلی")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

# ==================== دکمه‌های جدید برای یادآوری ====================

def get_reminder_menu():
    """منوی یادآوری - دکمه‌های شیشه‌ای"""
    buttons = [
        [KeyboardButton("➕ افزودن یادآوری کنکور")],
        [KeyboardButton("➕ افزودن یادآوری شخصی")],
        [KeyboardButton("📋 مشاهده یادآوری‌ها")],
        [KeyboardButton("🔙 بازگشت به منوی اصلی")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

def get_exam_selection_menu():
    """منوی انتخاب کنکور برای یادآوری - دکمه‌های شیشه‌ای"""
    buttons = []
    for exam_name in EXAMS.keys():
        buttons.append([KeyboardButton(f"📖 {exam_name}")])
    buttons.append([KeyboardButton("🔙 بازگشت به یادآوری")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)
