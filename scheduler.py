import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot
import os
from reminder_data import get_due_reminders
import asyncio
import time

logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN is required for scheduler!")

# تنظیم timeout بیشتر برای اتصالات
bot = Bot(token=TOKEN)

def send_reminder_sync(chat_id, reminder):
    """ارسال پیام با مدیریت بهتر خطا و timeout"""
    try:
        # هر بار یک حلقه جدید بسازیم
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # ساخت پیام
            if reminder["type"] == "exam":
                message = f"⏰ **یادآوری کنکور!**\n\n📖 {reminder['title']}\n📅 تاریخ: {reminder['jalali_date']}\n🕐 ساعت: {reminder['time']}"
            else:
                message = f"⏰ **یادآوری شخصی!**\n\n📝 {reminder['title']}\n📅 تاریخ: {reminder['jalali_date']}\n🕐 ساعت: {reminder['time']}"
            
            # ارسال با timeout 60 ثانیه
            loop.run_until_complete(
                bot.send_message(
                    chat_id=chat_id, 
                    text=message, 
                    parse_mode="Markdown",
                    read_timeout=60,
                    write_timeout=60,
                    connect_timeout=60,
                    pool_timeout=60
                )
            )
            logger.info(f"✅ Reminder sent to {chat_id}: {reminder['title']}")
            
            # غیرفعال کردن یادآوری بعد از ارسال
            from reminder_data import toggle_reminder
            toggle_reminder(chat_id, reminder["id"])
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send reminder to {chat_id}: {e}")
            return False
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
                # ارسال پیام
                success = send_reminder_sync(item["user_id"], item["reminder"])
                if success:
                    # بعد از ارسال موفق، کمی صبر کنیم
                    time.sleep(1)
                else:
                    logger.warning(f"⚠️ Failed to send reminder to {item['user_id']}")
        else:
            # برای کاهش لاگ، فقط هر ۱۰ بار یک بار
            if int(time.time()) % 100 < 10:
                logger.info("📭 No due reminders found")
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
