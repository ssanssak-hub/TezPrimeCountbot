from .exam_handler import show_exam_details, handle_exam_menu, handle_exam_selection
from .admin_handler import handle_admin_panel, handle_admin_commands, is_admin
from .menu_handler import handle_menu_buttons
from keyboards import get_main_menu

ADMINS = [7703672187]

async def start(update, context):
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

async def handle_message(update, context):
    """مدیریت پیام‌های دریافتی"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # بازگشت به منوی اصلی
    if text == "🔙 بازگشت به منوی اصلی":
        keyboard = get_main_menu(ADMINS[0], user_id)
        await update.message.reply_text(
            "🔙 به منوی اصلی بازگشتید.",
            reply_markup=keyboard
        )
        return
    
    # بازگشت به منوی کنکورها
    if text == "🔙 بازگشت به کنکورها":
        await handle_exam_menu(update)
        return
    
    # دکمه اطلاعات کنکور
    if text == "📚 اطلاعات کنکور":
        await handle_exam_menu(update)
        return
    
    # بررسی انتخاب کنکور
    if await handle_exam_selection(update, text):
        return
    
    # پنل مدیریت (فقط برای ادمین)
    if text == "🛠 پنل مدیریت" and is_admin(user_id):
        await handle_admin_panel(update)
        return
    
    # دکمه‌های پنل مدیریت
    if is_admin(user_id) and text in ["📊 آمار کاربران", "📨 ارسال پیام همگانی", 
                                       "🚫 مسدود کردن کاربر", "✅ فعال کردن کاربر", 
                                       "📋 لیست کاربران"]:
        await handle_admin_commands(update, text)
        return
    
    # سایر دکمه‌های منوی اصلی
    await handle_menu_buttons(update, text)
