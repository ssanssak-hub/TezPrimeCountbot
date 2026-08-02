import logging
from telegram import Update
from keyboards import get_exam_menu, get_exam_detail_menu
from exam_data import get_exam_info

logger = logging.getLogger(__name__)

async def show_exam_details(update: Update, exam_name: str, refresh: bool = False):
    """نمایش جزئیات کنکور با دکمه‌های شیشه‌ای"""
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
    await update.message.reply_text(
        message,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def handle_exam_menu(update: Update):
    """نمایش منوی انتخاب کنکور با دکمه‌های شیشه‌ای"""
    keyboard = get_exam_menu()
    # حذف parse_mode برای جلوگیری از تداخل
    await update.message.reply_text(
        "📚 اطلاعات کنکورها\n\nلطفاً یکی از کنکورهای زیر را انتخاب کنید:",
        reply_markup=keyboard
    )

async def handle_exam_selection(update: Update, text: str):
    """مدیریت انتخاب کنکور"""
    from exam_data import EXAMS
    for exam_name in EXAMS.keys():
        if text == f"📖 {exam_name}":
            await show_exam_details(update, exam_name)
            return True
        if text == f"🔄 تازه کردن {exam_name}":
            await show_exam_details(update, exam_name, refresh=True)
            return True
    return False
