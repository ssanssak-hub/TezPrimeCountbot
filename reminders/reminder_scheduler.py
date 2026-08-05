import logging
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
import os
from dotenv import load_dotenv
from .reminder_database import get_all_active_reminders, get_reminder_db_connection
from .reminder_utils import convert_to_server_time, convert_to_tehran_time, get_weekday_name, get_current_weekday

load_dotenv()
TOKEN = os.getenv('TOKEN')
bot = Bot(token=TOKEN)

logger = logging.getLogger(__name__)

# ⚠️ event loop موجود رو استفاده کن
import asyncio
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

scheduler = AsyncIOScheduler(event_loop=loop, timezone='Asia/Tehran')

def start_scheduler():
    """راه‌اندازی زمان‌بند"""
    # بارگذاری همه اعلان‌های فعال
    reminders = get_all_active_reminders()
    
    for reminder in reminders:
        schedule_reminder_sync(
            reminder['id'],
            reminder['user_id'],
            reminder['message'],
            reminder['days_of_week'],
            reminder['hour'],
            reminder['minute']
        )
    
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Scheduler started successfully")
    else:
        logger.info("Scheduler already running")

async def schedule_reminder(reminder_id, user_id, message, days, hour, minute):
    """برنامه‌ریزی یک اعلان جدید"""
    days_str = ','.join(map(str, days))
    schedule_reminder_sync(reminder_id, user_id, message, days_str, hour, minute)

def schedule_reminder_sync(reminder_id, user_id, message, days_str, hour, minute):
    """برنامه‌ریزی هم‌زمان اعلان"""
    days = [int(d) for d in days_str.split(',')]
    
    # تابع ارسال پیام
    async def send_reminder():
        try:
            # لاگ برای دیباگ
            current_day = get_current_weekday()
            logger.info(f"🔍 Reminder {reminder_id} triggered - Today: {current_day} ({get_weekday_name(current_day)}), Days: {days}")
            
            # بررسی اینکه آیا امروز روز اعلان است
            if current_day not in days:
                logger.info(f"⏭️ Reminder {reminder_id} skipped - today ({current_day}) not in selected days {days}")
                return
            
            # ارسال پیام
            day_name = get_weekday_name(current_day)
            text = (
                f"🔔 **یادآوری!**\n\n"
                f"{message}\n\n"
                f"📅 {day_name} | 🕐 {hour:02d}:{minute:02d}"
            )
            
            logger.info(f"📤 Sending reminder {reminder_id} to user {user_id}")
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode='Markdown'
            )
            logger.info(f"✅ Reminder {reminder_id} sent to user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Error sending reminder {reminder_id}: {e}", exc_info=True)
    
    # تبدیل ساعت تهران به UTC
    server_hour, server_minute = convert_to_server_time(hour, minute)
    
    # اضافه کردن job
    try:
        scheduler.add_job(
            send_reminder,
            trigger=CronTrigger(
                hour=server_hour,
                minute=server_minute,
                timezone='UTC'
            ),
            id=f"reminder_{reminder_id}",
            replace_existing=True
        )
        logger.info(f"✅ Reminder {reminder_id} scheduled for {server_hour:02d}:{server_minute:02d} UTC (Tehran: {hour:02d}:{minute:02d})")
        logger.info(f"   Message: {message[:30]}... | Days: {days} | User: {user_id}")
    except Exception as e:
        logger.error(f"❌ Error scheduling reminder {reminder_id}: {e}", exc_info=True)

def remove_scheduled_reminder(reminder_id):
    """حذف یک اعلان از زمان‌بند"""
    try:
        scheduler.remove_job(f"reminder_{reminder_id}")
        logger.info(f"✅ Reminder {reminder_id} removed from scheduler")
    except Exception as e:
        logger.error(f"❌ Error removing reminder {reminder_id}: {e}")
