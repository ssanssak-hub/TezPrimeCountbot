import logging
import asyncio
from telegram import Bot
import os
from dotenv import load_dotenv
from ..database import get_all_active_users
from .admin_database import (
    add_broadcast_log, update_broadcast_count,
    mark_broadcast_sent, get_broadcast_stats
)

load_dotenv()
TOKEN = os.getenv('TOKEN')
bot = Bot(token=TOKEN)

logger = logging.getLogger(__name__)

async def send_broadcast_now(broadcast_id, admin_id, title, message):
    """ارسال فوری پیام همگانی"""
    users = get_all_active_users()
    total = len(users)
    sent = 0
    failed = 0
    
    # بروزرسانی اولیه
    mark_broadcast_sent(broadcast_id, total)
    
    for user in users:
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
        
        # بروزرسانی تدریجی
        update_broadcast_count(broadcast_id, sent, failed)
        
        # وقفه کوتاه برای جلوگیری از rate limit
        await asyncio.sleep(0.05)
    
    logger.info(f"✅ Broadcast {broadcast_id} completed: {sent}/{total} sent, {failed} failed")
    return sent, failed, total

def get_broadcast_progress_text(broadcast_id):
    """متن پیشرفت ارسال"""
    broadcast, logs = get_broadcast_stats(broadcast_id)
    
    if not broadcast:
        return "❌ پیام یافت نشد"
    
    total = broadcast['total_users']
    sent = broadcast['sent_count']
    failed = broadcast['failed_count']
    
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
