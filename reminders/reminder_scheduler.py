import logging
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
import os
from dotenv import load_dotenv
from .reminder_database import get_all_active_reminders, get_reminder_db_connection
from .reminder_utils import convert_to_tehran_time, get_weekday_name, get_current_weekday

load_dotenv()
TOKEN = os.getenv('TOKEN')
bot = Bot(token=TOKEN)

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone='Asia/Tehran')

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
    
    scheduler.start()
    logger.info("Scheduler started successfully")

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
            # بررسی اینکه آیا امروز روز اعلان است
            current_day = get_current_weekday()
            if current_day not in days:
                return
            
            # ارسال پیام
            day_name = get_weekday_name(current_day)
            await bot.send_message(
                chat_id=user_id,
                text=f"🔔 **یادآوری!**\n\n"
                     f"{message}\n\n"
                     f"📅 {day_name} | 🕐 {hour:02d}:{minute:02d}"
            )
            logger.info(f"Reminder {reminder_id} sent to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending reminder {reminder_id}: {e}")
    
    # اضافه کردن به برنامه زمان‌بندی با زمان سرور
    server_hour, server_minute = convert_to_server_time(hour, minute)
    
    # تنظیم کرون جاب برای هر روز
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
    
    logger.info(f"Reminder {reminder_id} scheduled for {server_hour:02d}:{server_minute:02d} UTC")

def remove_scheduled_reminder(reminder_id):
    """حذف یک اعلان از زمان‌بند"""
    try:
        scheduler.remove_job(f"reminder_{reminder_id}")
        logger.info(f"Reminder {reminder_id} removed from scheduler")
    except Exception as e:
        logger.error(f"Error removing reminder {reminder_id}: {e}")
