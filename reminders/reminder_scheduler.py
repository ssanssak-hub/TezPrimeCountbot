import logging
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
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

scheduler = BackgroundScheduler(timezone='UTC')

def start_scheduler():
    """راه‌اندازی زمان‌بند"""
    reminders = get_all_active_reminders()
    
    for reminder in reminders:
        schedule_reminder_sync(
            reminder['id'],
            reminder['user_id'],
            reminder['title'] if reminder['title'] else 'بدون عنوان',
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

async def schedule_reminder(reminder_id, user_id, title, message, days, hour, minute):
    """برنامه‌ریزی یک اعلان جدید"""
    days_str = ','.join(map(str, days))
    schedule_reminder_sync(reminder_id, user_id, title, message, days_str, hour, minute)

def schedule_reminder_sync(reminder_id, user_id, title, message, days_str, hour, minute):
    """برنامه‌ریزی هم‌زمان اعلان"""
    days = [int(d) for d in days_str.split(',')]
    
    def send_reminder():
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            current_day = get_current_weekday()
            logger.info(f"🔍 Reminder {reminder_id} triggered - Today: {current_day} ({get_weekday_name(current_day)}), Days: {days}")
            
            if current_day not in days:
                logger.info(f"⏭️ Reminder {reminder_id} skipped - today ({current_day}) not in selected days {days}")
                loop.close()
                return
            
            async def _send():
                try:
                    day_name = get_weekday_name(current_day)
                    text = (
                        f"🔔 **{title}**\n\n"
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
            
            loop.run_until_complete(_send())
            loop.close()
            
        except Exception as e:
            logger.error(f"❌ Error in send_reminder {reminder_id}: {e}", exc_info=True)
    
    server_hour, server_minute = convert_to_server_time(hour, minute)
    
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
        logger.info(f"   Title: {title[:20]}... | Days: {days} | User: {user_id}")
    except Exception as e:
        logger.error(f"❌ Error scheduling reminder {reminder_id}: {e}", exc_info=True)

def remove_scheduled_reminder(reminder_id):
    """حذف یک اعلان از زمان‌بند"""
    try:
        job_id = f"reminder_{reminder_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(f"✅ Reminder {reminder_id} removed from scheduler")
        else:
            logger.info(f"ℹ️ Reminder {reminder_id} job not found in scheduler (already removed)")
    except Exception as e:
        logger.warning(f"⚠️ Error removing reminder {reminder_id}: {e}")

