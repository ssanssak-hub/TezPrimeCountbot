#scheduler.py
import logging
import os
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot
from reminder_data import load_reminders, jalali_to_gregorian, toggle_reminder
import pytz
from datetime import datetime

logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN is required for scheduler!")

# یک event loop واحد برای کل scheduler
loop = asyncio.new_event_loop()
bot = Bot(token=TOKEN)

async def send_reminder_async(chat_id, reminder):
    """ارسال پیام به صورت async"""
    try:
        if reminder["type"] == "exam":
            message = f"⏰ **یادآوری کنکور!**\n\n📖 {reminder['title']}\n📅 تاریخ: {reminder['jalali_date']}\n🕐 ساعت: {reminder['time']}"
        else:
            message = f"⏰ **یادآوری شخصی!**\n\n📝 {reminder['title']}\n📅 تاریخ: {reminder['jalali_date']}\n🕐 ساعت: {reminder['time']}"
        
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown",
            read_timeout=10,
            write_timeout=10,
            connect_timeout=10
        )
        
        toggle_reminder(chat_id, reminder["id"])
        logger.info(f"✅ Reminder sent to {chat_id}: {reminder['title']}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send reminder to {chat_id}: {e}")
        return False

def check_and_send_reminders():
    """بررسی و ارسال یادآوری‌ها"""
    try:
        reminders = load_reminders()
        now_tehran = datetime.now(pytz.timezone('Asia/Tehran'))
        due_reminders = []
        
        for user_id, user_reminders in reminders.items():
            for r in user_reminders:
                try:
                    if not r.get("is_active", True):
                        continue
                    
                    gregorian_date = jalali_to_gregorian(r["jalali_date"])
                    hour, minute = map(int, r["time"].split(':'))
                    
                    reminder_datetime = datetime(
                        gregorian_date.year,
                        gregorian_date.month,
                        gregorian_date.day,
                        hour,
                        minute,
                        0,
                        tzinfo=pytz.timezone('Asia/Tehran')
                    )
                    
                    time_diff = (now_tehran - reminder_datetime).total_seconds()
                    if 0 <= time_diff <= 60:  # فقط یادآورهای یک دقیقه اخیر
                        due_reminders.append({
                            "user_id": int(user_id),
                            "reminder": r
                        })
                except Exception as e:
                    logger.warning(f"⚠️ Error processing reminder: {e}")
                    continue
        
        if due_reminders:
            logger.info(f"🔔 Found {len(due_reminders)} due reminders")
            
            async def send_all():
                for item in due_reminders:
                    await send_reminder_async(item["user_id"], item["reminder"])
                    await asyncio.sleep(0.1)
            
            asyncio.set_event_loop(loop)
            loop.run_until_complete(send_all())
        
    except Exception as e:
        logger.error(f"❌ Error in check_and_send_reminders: {e}")

def start_scheduler():
    """راه‌اندازی scheduler"""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=check_and_send_reminders,
        trigger=IntervalTrigger(seconds=30),
        id='reminder_checker',
        replace_existing=True,
        misfire_grace_time=30
    )
    scheduler.start()
    logger.info("✅ Scheduler started - checking every 30 seconds (Tehran time)")
    return scheduler
