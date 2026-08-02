import logging
import os
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot
from reminder_data import load_reminders, jalali_to_gregorian, toggle_reminder
import pytz
from datetime import datetime

logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN is required for scheduler!")

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
        
        # غیرفعال کردن یادآوری بعد از ارسال
        from reminder_data import toggle_reminder
        toggle_reminder(chat_id, reminder["id"])
        
        logger.info(f"✅ Reminder sent to {chat_id}: {reminder['title']}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send reminder to {chat_id}: {e}")
        return False

async def check_and_send_reminders():
    """بررسی و ارسال یادآوری‌ها - نسخه async"""
    try:
        reminders = load_reminders()
        now_tehran = datetime.now(pytz.timezone('Asia/Tehran'))
        due_reminders = []
        
        logger.debug(f"🔍 Checking reminders at Tehran time: {now_tehran.strftime('%Y-%m-%d %H:%M:%S')}")
        
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
                    
                    # بررسی بدون محدودیت time_diff - هرچی زمانش رسیده باشه
                    if now_tehran >= reminder_datetime:
                        due_reminders.append({
                            "user_id": int(user_id),
                            "reminder": r,
                            "scheduled_time": reminder_datetime.strftime('%H:%M:%S')
                        })
                        
                        logger.info(f"⏰ Due: {r['title']} | Scheduled: {reminder_datetime.strftime('%H:%M:%S')} | Now: {now_tehran.strftime('%H:%M:%S')}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error processing reminder: {e}")
                    continue
        
        if due_reminders:
            logger.info(f"🔔 Sending {len(due_reminders)} reminders...")
            for item in due_reminders:
                await send_reminder_async(item["user_id"], item["reminder"])
                await asyncio.sleep(0.1)  # تاخیر کم بین ارسال‌ها
        
    except Exception as e:
        logger.error(f"❌ Error in check_and_send_reminders: {e}")

async def start_async_scheduler():
    """راه‌اندازی AsyncIOScheduler"""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_send_reminders,
        trigger=IntervalTrigger(seconds=10),  # هر ۱۰ ثانیه چک کن
        id='reminder_checker',
        replace_existing=True
    )
    scheduler.start()
    logger.info("✅ AsyncIOScheduler started - checking every 10 seconds (Tehran time)")
    return scheduler
