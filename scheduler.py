import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot
import os
from reminder_data import get_due_reminders
from exam_data import jalali_to_gregorian

logger = logging.getLogger(__name__)

# دریافت توکن از متغیرهای محیطی
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN is required for scheduler!")

bot = Bot(token=TOKEN)

async def send_reminder(chat_id, reminder):
    """ارسال پیام یادآوری به کاربر"""
    try:
        if reminder["type"] == "exam":
            message = f"⏰ **یادآوری کنکور!**\n\n📖 {reminder['title']}\n📅 تاریخ: {reminder['jalali_date']}\n🕐 ساعت: {reminder['time']}"
        else:
            message = f"⏰ **یادآوری شخصی!**\n\n📝 {reminder['title']}\n📅 تاریخ: {reminder['jalali_date']}\n🕐 ساعت: {reminder['time']}"
        
        await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
        logger.info(f"✅ Reminder sent to {chat_id}: {reminder['title']}")
        
        # غیرفعال کردن یادآوری بعد از ارسال (تا دوباره ارسال نشود)
        from reminder_data import toggle_reminder
        toggle_reminder(chat_id, reminder["id"])
        
    except Exception as e:
        logger.error(f"❌ Failed to send reminder to {chat_id}: {e}")

def check_and_send_reminders():
    """بررسی و ارسال یادآوری‌های سررسید شده"""
    try:
        due_reminders = get_due_reminders()
        if due_reminders:
            logger.info(f"🔔 Found {len(due_reminders)} due reminders")
            for item in due_reminders:
                # ارسال پیام در حلقه رویداد اصلی
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(send_reminder(item["user_id"], item["reminder"]))
                loop.close()
    except Exception as e:
        logger.error(f"❌ Error in check_and_send_reminders: {e}")

def start_scheduler():
    """راه‌اندازی برنامه‌ریز"""
    scheduler = BackgroundScheduler()
    # هر ۱۰ ثانیه یک بار بررسی کن
    scheduler.add_job(
        func=check_and_send_reminders,
        trigger=IntervalTrigger(seconds=10),
        id='reminder_checker',
        replace_existing=True
    )
    scheduler.start()
    logger.info("✅ Scheduler started - checking reminders every 30 seconds")
    return scheduler
