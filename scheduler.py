#scheduler.py
import logging
import os
import time
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot
from reminder_data import get_due_reminders
import pytz
from datetime import datetime

logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN is required for scheduler!")

bot = Bot(token=TOKEN)

def send_reminder_sync(chat_id, reminder):
    """ارسال پیام با مدیریت بهتر خطا و timeout"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if reminder["type"] == "exam":
                message = f"⏰ **یادآوری کنکور!**\n\n📖 {reminder['title']}\n📅 تاریخ: {reminder['jalali_date']}\n🕐 ساعت: {reminder['time']}"
            else:
                message = f"⏰ **یادآوری شخصی!**\n\n📝 {reminder['title']}\n📅 تاریخ: {reminder['jalali_date']}\n🕐 ساعت: {reminder['time']}"
            
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
            from reminder_data import toggle_reminder
            toggle_reminder(chat_id, reminder["id"])
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send reminder to {chat_id}: {e}")
            return False
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"❌ Error in send_reminder_sync: {e}")
        return False

def check_and_send_reminders():
    """بررسی و ارسال یادآوری‌های سررسید شده با زمان تهران"""
    try:
        from reminder_data import load_reminders, jalali_to_gregorian
        
        reminders = load_reminders()
        now_tehran = datetime.now(pytz.timezone('Asia/Tehran'))
        due_reminders = []
        
        for user_id, user_reminders in reminders.items():
            for r in user_reminders:
                try:
                    if not r.get("is_active", True):
                        continue
                    
                    # تبدیل تاریخ شمسی به میلادی
                    gregorian_date = jalali_to_gregorian(r["jalali_date"])
                    hour, minute = map(int, r["time"].split(':'))
                    
                    # ساخت زمان یادآوری با منطقه زمانی تهران
                    reminder_datetime = datetime(
                        gregorian_date.year,
                        gregorian_date.month,
                        gregorian_date.day,
                        hour,
                        minute,
                        0,
                        tzinfo=pytz.timezone('Asia/Tehran')
                    )
                    
                    # مقایسه با زمان فعلی تهران
                    if now_tehran >= reminder_datetime:
                        due_reminders.append({
                            "user_id": int(user_id),
                            "reminder": r,
                            "datetime": reminder_datetime
                        })
                except Exception as e:
                    logger.warning(f"⚠️ Error processing reminder {r.get('id', 'unknown')}: {e}")
                    continue
        
        if due_reminders:
            logger.info(f"🔔 Found {len(due_reminders)} due reminders (Tehran time)")
            for item in due_reminders:
                success = send_reminder_sync(item["user_id"], item["reminder"])
                if success:
                    time.sleep(1)
                else:
                    logger.warning(f"⚠️ Failed to send reminder to {item['user_id']}")
        else:
            # هر ۵ بار یک بار لاگ بده
            if int(time.time()) % 50 < 10:
                logger.info(f"📭 No due reminders (Tehran time: {now_tehran.strftime('%Y-%m-%d %H:%M:%S')})")
                
    except Exception as e:
        logger.error(f"❌ Error in check_and_send_reminders: {e}")

def start_scheduler():
    """راه‌اندازی برنامه‌ریز با تنظیمات بهینه"""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=check_and_send_reminders,
        trigger=IntervalTrigger(seconds=10),
        id='reminder_checker',
        replace_existing=True
    )
    scheduler.start()
    logger.info("✅ Scheduler started - checking reminders every 10 seconds (Tehran timezone)")
    return scheduler
