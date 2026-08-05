import logging
import asyncio
from telegram import Bot
from telegram.request import HTTPXRequest
import os
from dotenv import load_dotenv
from database import get_all_active_users
from admin.admin_database import (
    add_broadcast_log, update_broadcast_count,
    mark_broadcast_sent, get_broadcast_stats
)

load_dotenv()
TOKEN = os.getenv('TOKEN')

# افزایش connection pool
request = HTTPXRequest(
    connection_pool_size=20,
    pool_timeout=30
)
bot = Bot(token=TOKEN, request=request)

logger = logging.getLogger(__name__)

async def send_broadcast_now(broadcast_id, admin_id, title, message):
    """ارسال فوری پیام همگانی"""
    users = get_all_active_users()
    total = len(users)
    sent = 0
    failed = 0
    
    mark_broadcast_sent(broadcast_id, total)
    
    for i, user in enumerate(users):
        try:
            text = f"📢 **پیام همگانی**\n\n📌 **{title}**\n\n{message}"
            await bot.send_message(
                chat_id=user['user_id'],
                text=text,
                parse_mode='Markdown'
            )
            add_broadcast_log(broadcast_id, user['user_id'], 'success')
            sent += 1
            logger.info(f"📤 Sent to user {user['user_id']} ({sent}/{total})")
        except Exception as e:
            add_broadcast_log(broadcast_id, user['user_id'], 'failed', str(e))
            failed += 1
            logger.error(f"❌ Failed to send to {user['user_id']}: {e}")
        
        update_broadcast_count(broadcast_id, sent, failed)
        await asyncio.sleep(0.1)
    
    logger.info(f"✅ Broadcast {broadcast_id} completed: {sent}/{total} sent, {failed} failed")
    return sent, failed, total

def get_broadcast_progress_text(broadcast_id):
    """متن پیشرفت ارسال"""
    broadcast, logs = get_broadcast_stats(broadcast_id)
    
    if not broadcast:
        return "❌ پیام یافت نشد"
    
    total = broadcast['total_users'] if broadcast['total_users'] else 0
    sent = broadcast['sent_count'] if broadcast['sent_count'] else 0
    failed = broadcast['failed_count'] if broadcast['failed_count'] else 0
    
    if total == 0:
        return "⏳ در حال آماده‌سازی..."
    
    progress = round((sent + failed) / total * 100, 1) if total > 0 else 0
    
    bar_length = 20
    filled = int(bar_length * progress / 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    text = (
        f"📊 **پیشرفت ارسال**\n\n"
        f"📌 **{broadcast['title']}**\n\n"
        f"[{bar}] {progress}%\n\n"
        f"👥 کل کاربران: {total}\n"
        f"✅ ارسال موفق: {sent}\n"
        f"❌ ناموفق: {failed}\n"
        f"⏳ باقی‌مانده: {total - sent - failed}\n"
    )
    
    return text


async def send_broadcast_report(admin_chat_id, title, sent, failed, total):
    """ارسال گزارش نهایی به ادمین"""
    try:
        progress = round((sent + failed) / total * 100, 1) if total > 0 else 0
        bar_length = 20
        filled = int(bar_length * progress / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        text = (
            f"📊 **گزارش ارسال پیام همگانی**\n\n"
            f"📌 **{title}**\n\n"
            f"[{bar}] {progress}%\n\n"
            f"👥 کل کاربران: {total}\n"
            f"✅ ارسال موفق: {sent}\n"
            f"❌ ناموفق: {failed}\n\n"
            f"✅ **ارسال به پایان رسید!**"
        )
        
        await bot.send_message(
            chat_id=admin_chat_id,
            text=text,
            parse_mode='Markdown'
        )
        logger.info(f"📊 Report sent to admin {admin_chat_id}")
    except Exception as e:
        logger.error(f"❌ Failed to send report: {e}")
