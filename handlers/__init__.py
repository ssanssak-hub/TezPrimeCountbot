from .exam_handler import show_exam_details, handle_exam_menu, handle_exam_selection
from .admin_handler import handle_admin_panel, handle_admin_commands, is_admin
from .menu_handler import handle_menu_buttons
from .reminder_handler import (
    handle_reminder_menu,
    handle_add_exam_reminder,
    handle_exam_selection_for_reminder,
    handle_add_personal_reminder,
    handle_personal_reminder_title,
    handle_personal_reminder_date,
    handle_personal_reminder_time,
    handle_view_reminders,
    handle_reminder_action,
    user_states
)
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
    
    # ========== بازگشت به منوی اصلی ==========
    if text == "🔙 بازگشت به منوی اصلی":
        keyboard = get_main_menu(ADMINS[0], user_id)
        await update.message.reply_text("🔙 به منوی اصلی بازگشتید.", reply_markup=keyboard)
        return
    
    # ========== بازگشت به منوی کنکورها ==========
    if text == "🔙 بازگشت به کنکورها":
        from .exam_handler import handle_exam_menu
        await handle_exam_menu(update)
        return
    
    # ========== بازگشت به منوی یادآوری ==========
    if text == "🔙 بازگشت به یادآوری":
        await handle_reminder_menu(update, context)
        return
    
    # ========== دکمه اطلاعات کنکور ==========
    if text == "📚 اطلاعات کنکور":
        from .exam_handler import handle_exam_menu
        await handle_exam_menu(update)
        return
    
    # ========== بررسی انتخاب کنکور (از exam_handler) ==========
    from .exam_handler import handle_exam_selection
    if await handle_exam_selection(update, text):
        return
    
    # ========== دکمه یادآوری کن ==========
    if text == "⏰ یادآوری کن":
        await handle_reminder_menu(update, context)
        return
    
    # ========== منوی یادآوری ==========
    if text == "➕ افزودن یادآوری کنکور":
        await handle_add_exam_reminder(update, context)
        return
    
    if text == "➕ افزودن یادآوری شخصی":
        await handle_add_personal_reminder(update, context)
        return
    
    if text == "📋 مشاهده یادآوری‌ها":
        await handle_view_reminders(update, context)
        return
    
    # ========== مراحل افزودن یادآوری شخصی ==========
    if user_id in user_states:
        step = user_states[user_id].get("step")
        
        if step == 2:  # WAITING_FOR_PERSONAL_TITLE
            await handle_personal_reminder_title(update, context)
            return
        elif step == 3:  # WAITING_FOR_PERSONAL_DATE
            await handle_personal_reminder_date(update, context)
            return
        elif step == 4:  # WAITING_FOR_PERSONAL_TIME
            await handle_personal_reminder_time(update, context)
            return
        elif step == 5 or step == 6:  # WAITING_FOR_REMINDER_ACTION یا WAITING_FOR_REMINDER_ID
            await handle_reminder_action(update, context)
            return
    
    # ========== انتخاب کنکور برای یادآوری ==========
    if text.startswith("📖 "):
        from exam_data import EXAMS
        for exam_name in EXAMS.keys():
            if text == f"📖 {exam_name}":
                await handle_exam_selection_for_reminder(update, context)
                return
    
    # ========== پنل مدیریت ==========
    if text == "🛠 پنل مدیریت" and is_admin(user_id):
        await handle_admin_panel(update)
        return
    
    # ========== دکمه‌های پنل مدیریت ==========
    if is_admin(user_id) and text in ["📊 آمار کاربران", "📨 ارسال پیام همگانی", 
                                       "🚫 مسدود کردن کاربر", "✅ فعال کردن کاربر", 
                                       "📋 لیست کاربران"]:
        await handle_admin_commands(update, text)
        return
    
    # ========== سایر دکمه‌های منوی اصلی ==========
    await handle_menu_buttons(update, text)
