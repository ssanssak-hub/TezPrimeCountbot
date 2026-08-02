import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot
import os
from reminder_data import get_due_reminders
import asyncio

logger = logging.getLogger(__name__)

# دریافت توکن از متغیرهای محیطی
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN is required for scheduler!")

# ایجاد یک نمونه Bot با تنظیمات timeout بیشتر
bot = Bot(token=TOKEN)

# یک حلقه رویداد جدید برای Scheduler
scheduler_loop = asyncio.new_event_loop()
asyncio.set_event_loop(scheduler_loop)

async def send_reminder(chat_id, reminder):
    """ارسال پیام یادآوری به کاربر با مدیریت خطا"""
    try:
        # تنظیم timeout برای درخواست
        if reminder["type"] == "exam":
            message = f"⏰ **یادآوری کنکور!**\n\n📖 {reminder['title']}\n📅 تاریخ: {reminder['jalali_date']}\n🕐 ساعت: {reminder['time']}"
        else:
            message = f"⏰ **یادآوری شخصی!**\n\n📝 {reminder['title']}\n📅 تاریخ: {reminder['jalali_date']}\n🕐 ساعت: {reminder['time']}"
        
        # ارسال با timeout 30 ثانیه
        await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown", read_timeout=30, write_timeout=30)
        logger.info(f"✅ Reminder sent to {chat_id}: {reminder['title']}")
        
        # غیرفعال کردن یادآوری بعد از ارسال
        from reminder_data import toggle_reminder
        toggle_reminder(chat_id, reminder["id"])
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send reminder to {chat_id}: {e}")
        return False

def send_reminder_sync(chat_id, reminder):
    """ارسال همزمان (سینک) یادآوری با مدیریت خطا"""
    try:
        # هر بار یک حلقه جدید بسازیم
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(send_reminder(chat_id, reminder))
            return result
        finally:
            # بستن کامل حلقه
            loop.close()
    except Exception as e:
        logger.error(f"❌ Error in send_reminder_sync: {e}")
        return False

def check_and_send_reminders():
    """بررسی و ارسال یادآوری‌های سررسید شده"""
    try:
        due_reminders = get_due_reminders()
        if due_reminders:
            logger.info(f"🔔 Found {len(due_reminders)} due reminders")
            for item in due_reminders:
                # ارسال پیام به صورت همزمان (با مدیریت بهتر)
                success = send_reminder_sync(item["user_id"], item["reminder"])
                if not success:
                    logger.warning(f"⚠️ Failed to send reminder to {item['user_id']}")
    except Exception as e:
        logger.error(f"❌ Error in check_and_send_reminders: {e}")

def start_scheduler():
    """راه‌اندازی برنامه‌ریز با تنظیمات بهینه"""
    scheduler = BackgroundScheduler()
    # هر ۱۰ ثانیه یک بار بررسی کن
    scheduler.add_job(
        func=check_and_send_reminders,
        trigger=IntervalTrigger(seconds=10),
        id='reminder_checker',
        replace_existing=True
    )
    scheduler.start()
    logger.info("✅ Scheduler started - checking reminders every 10 seconds")
    return scheduler
