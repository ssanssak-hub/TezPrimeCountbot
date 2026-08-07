import logging
import asyncio
from telegram import Bot
from telegram.error import Forbidden, TelegramError, RetryAfter, BadRequest
from telegram.request import HTTPXRequest
import os
from dotenv import load_dotenv
from database import get_all_active_users, deactivate_user
from admin.admin_database import (
    add_broadcast_log, update_broadcast_count,
    mark_broadcast_sent, get_broadcast_stats,
    mark_broadcast_failed, mark_broadcast_completed
)

load_dotenv()
TOKEN = os.getenv('TOKEN')

# تنظیمات پیشرفته connection pool
request = HTTPXRequest(
    connection_pool_size=20,
    pool_timeout=30,
    connect_timeout=10.0,
    read_timeout=30.0,
    write_timeout=30.0
)
bot = Bot(token=TOKEN, request=request)

logger = logging.getLogger(__name__)

# محدودیت‌های تلگرام
MESSAGES_PER_SECOND = 30  # حداکثر مجاز
BATCH_SIZE = 25  # تعداد پیام در هر batch
BATCH_DELAY = 1.0  # تأخیر بین batch‌ها (ثانیه)
MESSAGE_DELAY = 0.05  # تأخیر بین پیام‌های معمولی
DB_UPDATE_FREQUENCY = 10  # آپدیت دیتابیس هر ۱۰ کاربر


async def send_broadcast_now(broadcast_id, admin_id, title, message):
    """
    ارسال فوری پیام همگانی با مدیریت کامل خطاها
    
    Args:
        broadcast_id: شناسه پیام همگانی
        admin_id: شناسه ادمین ارسال‌کننده
        title: عنوان پیام
        message: متن پیام
    
    Returns:
        tuple: (sent, failed, total)
    """
    # گرفتن کاربران فعال
    users = get_all_active_users()
    total = len(users)
    sent = 0
    failed = 0
    blocked_users = []
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 10  # توقف اگر ۱۰ خطای متوالی داشتیم
    
    # بررسی وجود کاربر
    if total == 0:
        logger.warning(f"⚠️ Broadcast {broadcast_id}: No active users")
        mark_broadcast_completed(broadcast_id, 0, 0)
        return 0, 0, 0
    
    # شروع ارسال
    mark_broadcast_sent(broadcast_id, total)
    logger.info(f"🚀 [Admin:{admin_id}] Starting broadcast {broadcast_id} to {total} users")
    
    # آماده‌سازی متن پیام
    broadcast_text = f"📢 **پیام همگانی**\n\n📌 **{title}**\n\n{message}"
    
    try:
        for i, user in enumerate(users):
            # اگر خطاهای متوالی زیاد شد، متوقف کن
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                error_msg = f"Stopped after {MAX_CONSECUTIVE_ERRORS} consecutive errors"
                logger.error(f"🛑 {error_msg}")
                mark_broadcast_failed(broadcast_id, error_msg)
                break
            
            user_id = user['user_id']
            
            try:
                # ارسال پیام
                await bot.send_message(
                    chat_id=user_id,
                    text=broadcast_text,
                    parse_mode='Markdown',
                    disable_web_page_preview=True,
                    disable_notification=False  # می‌تونی True کنی برای سایلنت
                )
                
                # ثبت موفقیت
                add_broadcast_log(broadcast_id, user_id, 'success')
                sent += 1
                consecutive_errors = 0  # ریست شمارنده خطا
                logger.debug(f"📤 [{sent}/{total}] Sent to {user_id}")
                
            except Forbidden as e:
                # کاربر ربات رو بلاک کرده یا اکانتش پاک شده
                deactivate_user(user_id)
                add_broadcast_log(broadcast_id, user_id, 'failed', f'Forbidden: {str(e)}')
                failed += 1
                blocked_users.append(user_id)
                consecutive_errors += 1
                logger.warning(f"🚫 User {user_id} blocked - deactivated")
                
            except BadRequest as e:
                # خطای بد ریکوئست (مثلاً پیام خالی یا فرمت اشتباه)
                add_broadcast_log(broadcast_id, user_id, 'failed', f'BadRequest: {str(e)}')
                failed += 1
                consecutive_errors += 1
                logger.error(f"⚠️ Bad request for {user_id}: {e}")
                
            except RetryAfter as e:
                # محدودیت نرخ - صبر کن و تلاش مجدد
                retry_after = e.retry_after
                logger.warning(f"⏳ Rate limited for {retry_after}s")
                await asyncio.sleep(retry_after)
                
                # تلاش مجدد
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=broadcast_text,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                    add_broadcast_log(broadcast_id, user_id, 'success')
                    sent += 1
                    consecutive_errors = 0
                    logger.info(f"✅ Retry successful for {user_id}")
                    
                except Exception as retry_e:
                    add_broadcast_log(broadcast_id, user_id, 'failed', str(retry_e))
                    failed += 1
                    consecutive_errors += 1
                    logger.error(f"❌ Retry failed for {user_id}: {retry_e}")
                    
            except TelegramError as e:
                # سایر خطاهای تلگرام
                add_broadcast_log(broadcast_id, user_id, 'failed', f'TelegramError: {str(e)}')
                failed += 1
                consecutive_errors += 1
                logger.error(f"❌ Telegram error for {user_id}: {e}")
                
            except Exception as e:
                # خطاهای غیرمنتظره
                add_broadcast_log(broadcast_id, user_id, 'failed', f'Unexpected: {str(e)}')
                failed += 1
                consecutive_errors += 1
                logger.error(f"💥 Unexpected error for {user_id}: {e}", exc_info=True)
            
            # آپدیت دیتابیس (نه برای هر کاربر، بلکه هر DB_UPDATE_FREQUENCY کاربر)
            if (i + 1) % DB_UPDATE_FREQUENCY == 0:
                update_broadcast_count(broadcast_id, sent, failed)
            
            # مدیریت Delay
            if (i + 1) % BATCH_SIZE == 0:
                # استراحت بعد از هر batch
                logger.debug(f"😴 Batch pause: {sent}/{total} sent")
                await asyncio.sleep(BATCH_DELAY)
            else:
                await asyncio.sleep(MESSAGE_DELAY)
        
        # آپدیت نهایی دیتابیس
        update_broadcast_count(broadcast_id, sent, failed)
        mark_broadcast_completed(broadcast_id, sent, failed)
        
    except Exception as critical_error:
        logger.critical(f"💀 Critical broadcast failure: {critical_error}", exc_info=True)
        mark_broadcast_failed(broadcast_id, str(critical_error))
        raise
    finally:
        # لاگ نهایی
        logger.info(
            f"✅ Broadcast {broadcast_id} finished: "
            f"{sent}/{total} sent, {failed} failed, "
            f"{len(blocked_users)} blocked"
        )
    
    return sent, failed, total


def get_broadcast_progress_text(broadcast_id):
    """
    دریافت متن پیشرفت ارسال برای نمایش به ادمین
    
    Args:
        broadcast_id: شناسه پیام همگانی
    
    Returns:
        str: متن فرمت شده پیشرفت
    """
    broadcast, logs = get_broadcast_stats(broadcast_id)
    
    if not broadcast:
        return "❌ پیام یافت نشد"
    
    total = broadcast.get('total_users', 0) or 0
    sent = broadcast.get('sent_count', 0) or 0
    failed = broadcast.get('failed_count', 0) or 0
    status = broadcast.get('status', 'unknown')
    
    if total == 0 and status == 'pending':
        return "⏳ در حال آماده‌سازی..."
    
    if total == 0 and status != 'pending':
        return "⚠️ کاربر فعالی یافت نشد"
    
    processed = sent + failed
    progress = round(processed / total * 100, 1) if total > 0 else 0
    
    # ساخت progress bar
    bar_length = 20
    filled = int(bar_length * progress / 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    # وضعیت
    status_emoji = {
        'pending': '⏳',
        'sending': '📤',
        'completed': '✅',
        'failed': '❌',
        'stopped': '🛑'
    }
    status_text = status_emoji.get(status, '❓')
    
    text = (
        f"📊 **پیشرفت ارسال** {status_text}\n\n"
        f"📌 **{broadcast.get('title', 'بدون عنوان')}**\n\n"
        f"[{bar}] {progress}%\n\n"
        f"👥 کل کاربران: {total:,}\n"
        f"✅ ارسال موفق: {sent:,}\n"
        f"❌ ناموفق: {failed:,}\n"
        f"⏳ باقی‌مانده: {total - processed:,}\n"
    )
    
    # محاسبه سرعت (اگر در حال ارسال باشه)
    if status == 'sending' and broadcast.get('started_at'):
        from datetime import datetime
        import math
        
        started_at = broadcast['started_at']
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        
        elapsed = (datetime.now() - started_at).total_seconds()
        if elapsed > 0:
            speed = processed / elapsed
            if speed > 0:
                eta_seconds = (total - processed) / speed
                eta_minutes = math.ceil(eta_seconds / 60)
                text += f"\n⚡ سرعت: {speed:.1f} پیام/ثانیه"
                text += f"\n⏰ زمان باقی‌مانده: ~{eta_minutes} دقیقه"
    
    return text


async def send_broadcast_report(admin_chat_id, title, sent, failed, total, blocked_count=0):
    """
    ارسال گزارش نهایی به ادمین
    
    Args:
        admin_chat_id: شناسه چت ادمین
        title: عنوان پیام
        sent: تعداد ارسال موفق
        failed: تعداد ناموفق
        total: کل کاربران
        blocked_count: تعداد کاربران بلاک‌شده (اختیاری)
    """
    try:
        success_rate = round(sent / total * 100, 1) if total > 0 else 0
        failed_rate = round(failed / total * 100, 1) if total > 0 else 0
        
        # Progress bar
        processed = sent + failed
        progress = round(processed / total * 100, 1) if total > 0 else 0
        bar_length = 20
        filled = int(bar_length * progress / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        text = (
            f"📊 **گزارش نهایی ارسال همگانی**\n\n"
            f"📌 **{title}**\n\n"
            f"[{bar}] {progress}%\n\n"
            f"👥 کل کاربران: {total:,}\n"
            f"✅ ارسال موفق: {sent:,} ({success_rate}%)\n"
            f"❌ ناموفق: {failed:,} ({failed_rate}%)\n"
        )
        
        if blocked_count > 0:
            text += f"🚫 کاربران بلاک‌شده: {blocked_count:,} (غیرفعال شدند)\n"
        
        text += f"\n✅ **ارسال به پایان رسید!**"
        
        await bot.send_message(
            chat_id=admin_chat_id,
            text=text,
            parse_mode='Markdown'
        )
        logger.info(f"📊 Report sent to admin {admin_chat_id}")
        
    except Exception as e:
        logger.error(f"❌ Failed to send report to admin {admin_chat_id}: {e}")


# تابع کمکی برای تبدیل broadcast_text به متن ساده (در صورت خطای Markdown)
def escape_markdown(text):
    """اسکیپ کردن کاراکترهای خاص Markdown"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


async def send_broadcast_safe(broadcast_id, admin_id, title, message):
    """
    ارسال امن - با تلاش برای Markdown و fallback به متن ساده
    """
    users = get_all_active_users()
    total = len(users)
    sent = 0
    failed = 0
    
    mark_broadcast_sent(broadcast_id, total)
    
    for user in users:
        user_id = user['user_id']
        
        try:
            # ابتدا با Markdown
            text = f"📢 **پیام همگانی**\n\n📌 **{title}**\n\n{message}"
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode='Markdown'
                )
            except BadRequest:
                # اگر Markdown مشکل داشت، با متن ساده
                plain_text = (
                    f"📢 پیام همگانی\n\n"
                    f"📌 {title}\n\n"
                    f"{message}"
                )
                await bot.send_message(
                    chat_id=user_id,
                    text=plain_text
                )
            
            add_broadcast_log(broadcast_id, user_id, 'success')
            sent += 1
            
        except Exception as e:
            add_broadcast_log(broadcast_id, user_id, 'failed', str(e))
            failed += 1
        
        await asyncio.sleep(0.05)
    
    return sent, failed, total

# اضافه کردن به انتهای admin_broadcast.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import json

async def send_broadcast_advanced(broadcast_id, admin_id, broadcast_data):
    """
    ارسال پیشرفته با پشتیبانی از انواع محتوا و دکمه‌های شیشه‌ای
    
    Args:
        broadcast_id: شناسه broadcast
        admin_id: شناسه ادمین
        broadcast_data: دیکشنری حاوی اطلاعات broadcast
    
    Returns:
        tuple: (sent, failed, total)
    """
    users = get_all_active_users()
    total = len(users)
    sent = 0
    failed = 0
    blocked_users = []
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 10
    
    if total == 0:
        logger.warning(f"⚠️ Broadcast {broadcast_id}: No active users")
        mark_broadcast_completed(broadcast_id, 0, 0)
        return 0, 0, 0
    
    content_type = broadcast_data.get('content_type', 'text')
    message_text = broadcast_data.get('message')
    file_id = broadcast_data.get('file_id')
    caption = broadcast_data.get('file_caption', '')
    title = broadcast_data.get('title', 'بدون عنوان')
    
    # ✅ دریافت اطلاعات ادمین
    admin_info = get_admin_info_from_db(admin_id)
    admin_name = admin_info.get('first_name', 'ادمین') if admin_info else 'ادمین'
    
    # ✅ دریافت زمان فعلی به وقت تهران
    from datetime import datetime
    import pytz
    tehran_tz = pytz.timezone('Asia/Tehran')
    now_tehran = datetime.now(tehran_tz)
    date_str = now_tehran.strftime('%Y/%m/%d')
    time_str = now_tehran.strftime('%H:%M:%S')
    
    # ✅ تبدیل تاریخ میلادی به شمسی
    try:
        import jdatetime
        jalali_date = jdatetime.date.fromgregorian(date=now_tehran.date())
        persian_date = jalali_date.strftime('%Y/%m/%d')
        persian_weekday = jalali_date.strftime('%A')
        weekdays_fa = {
            'Saturday': 'شنبه',
            'Sunday': 'یکشنبه',
            'Monday': 'دوشنبه',
            'Tuesday': 'سه‌شنبه',
            'Wednesday': 'چهارشنبه',
            'Thursday': 'پنجشنبه',
            'Friday': 'جمعه'
        }
        persian_weekday_fa = weekdays_fa.get(persian_weekday, persian_weekday)
    except:
        persian_date = date_str
        persian_weekday_fa = ''
    
    # ✅ ساخت هدر و فوتر پیام
    header = (
        f"📢 <b>پیام همگانی فوری</b>\n"
        f"━━ ━━━ ━━━ ━━━ ━━━ ━━ \n"
    )
    
    if content_type == 'text':
        # برای متن: هدر + عنوان + متن + فوتر
        full_message = (
            f"{header}"
            f"📌 عنوان پیام: <b>{title}</b>\n"
            f"━━ ━━━ ━━━━ ━━━ ━━━━ \n"
            f"📄 متن پیام: <b>{message_text}</b>\n"
            f"━━ ━━━ ━━━ ━━━ ━━━ ━━ \n"
            f"👤 مدیر ارسال کننده: <b>{admin_name}</b>\n"
            f"📅 تاریخ ارسال: <b>{persian_date}</b> ({persian_weekday_fa})\n"
            f"⏰ ساعت ارسال: <b>{time_str}</b>\n"
            f"━━ ━━━ ━━━ ━━━ ━━━ ━━ \n"
            f"🤖 Id Bot:@TezPrimeCountbot"
            f"🤖 Id Channel:@video_amouzeshi"
        )
    else:
        # برای مدیا: کپشن شامل اطلاعات کامل
        full_message = (
            f"{header}"
            f"📌 <b>{title}</b>\n"
            f"👤 ارسال‌کننده: <b>{admin_name}</b>\n"
            f"📅 تاریخ: <b>{persian_date}</b> ({persian_weekday_fa})\n"
            f"⏰ ساعت: <b>{time_str}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🤖 @TezPrimeCountbot"
        )
        if caption:
            full_message = f"{caption}\n\n{full_message}"
    
    # ساخت reply_markup از دکمه‌های شیشه‌ای
    reply_markup = None
    inline_buttons = broadcast_data.get('inline_buttons')
    if inline_buttons:
        try:
            import json
            buttons = json.loads(inline_buttons) if isinstance(inline_buttons, str) else inline_buttons
            if buttons:
                keyboard = []
                for btn in buttons:
                    if len(btn) == 2:  # URL button
                        keyboard.append([InlineKeyboardButton(btn[0], url=btn[1])])
                    elif len(btn) == 3:  # Callback button
                        keyboard.append([InlineKeyboardButton(btn[0], callback_data=btn[1])])
                reply_markup = InlineKeyboardMarkup(keyboard)
        except Exception as e:
            logger.error(f"❌ Error parsing inline buttons: {e}")
    
    # شروع ارسال
    mark_broadcast_sent(broadcast_id, total)
    logger.info(f"🚀 [Admin:{admin_id}] Starting advanced broadcast {broadcast_id} to {total} users (type: {content_type})")
    
    try:
        for i, user in enumerate(users):
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                error_msg = f"Stopped after {MAX_CONSECUTIVE_ERRORS} consecutive errors"
                logger.error(f"🛑 {error_msg}")
                mark_broadcast_failed(broadcast_id, error_msg)
                break
            
            user_id = user['user_id']
            
            try:
                # ارسال بر اساس نوع محتوا
                if content_type == 'text':
                    await bot.send_message(
                        chat_id=user_id,
                        text=full_message,
                        parse_mode='HTML',
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                elif content_type == 'photo':
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=file_id,
                        caption=full_message,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                elif content_type == 'video':
                    await bot.send_video(
                        chat_id=user_id,
                        video=file_id,
                        caption=full_message,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                elif content_type == 'document':
                    await bot.send_document(
                        chat_id=user_id,
                        document=file_id,
                        caption=full_message,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                elif content_type == 'audio':
                    await bot.send_audio(
                        chat_id=user_id,
                        audio=file_id,
                        caption=full_message,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                
                # ثبت موفقیت
                add_broadcast_log(broadcast_id, user_id, 'success')
                sent += 1
                consecutive_errors = 0
                logger.debug(f"📤 [{sent}/{total}] Sent to {user_id}")
                
            except Forbidden as e:
                deactivate_user(user_id)
                add_broadcast_log(broadcast_id, user_id, 'failed', f'Forbidden: {str(e)}')
                failed += 1
                blocked_users.append(user_id)
                consecutive_errors += 1
                logger.warning(f"🚫 User {user_id} blocked - deactivated")
                
            except BadRequest as e:
                add_broadcast_log(broadcast_id, user_id, 'failed', f'BadRequest: {str(e)}')
                failed += 1
                consecutive_errors += 1
                logger.error(f"⚠️ Bad request for {user_id}: {e}")
                
            except RetryAfter as e:
                retry_after = e.retry_after
                logger.warning(f"⏳ Rate limited for {retry_after}s")
                await asyncio.sleep(retry_after)
                
                try:
                    # تلاش مجدد با متن ساده
                    if content_type == 'text':
                        await bot.send_message(
                            chat_id=user_id,
                            text=full_message,
                            reply_markup=reply_markup
                        )
                    add_broadcast_log(broadcast_id, user_id, 'success')
                    sent += 1
                    consecutive_errors = 0
                    logger.info(f"✅ Retry successful for {user_id}")
                except Exception as retry_e:
                    add_broadcast_log(broadcast_id, user_id, 'failed', str(retry_e))
                    failed += 1
                    consecutive_errors += 1
                    logger.error(f"❌ Retry failed for {user_id}: {retry_e}")
                    
            except TelegramError as e:
                add_broadcast_log(broadcast_id, user_id, 'failed', f'TelegramError: {str(e)}')
                failed += 1
                consecutive_errors += 1
                logger.error(f"❌ Telegram error for {user_id}: {e}")
                
            except Exception as e:
                add_broadcast_log(broadcast_id, user_id, 'failed', f'Unexpected: {str(e)}')
                failed += 1
                consecutive_errors += 1
                logger.error(f"💥 Unexpected error for {user_id}: {e}", exc_info=True)
            
            # آپدیت دیتابیس
            if (i + 1) % DB_UPDATE_FREQUENCY == 0:
                update_broadcast_count(broadcast_id, sent, failed)
            
            # مدیریت Delay
            if (i + 1) % BATCH_SIZE == 0:
                logger.debug(f"😴 Batch pause: {sent}/{total} sent")
                await asyncio.sleep(BATCH_DELAY)
            else:
                await asyncio.sleep(MESSAGE_DELAY)
        
        # آپدیت نهایی
        update_broadcast_count(broadcast_id, sent, failed)
        mark_broadcast_completed(broadcast_id, sent, failed)
        
    except Exception as critical_error:
        logger.critical(f"💀 Critical broadcast failure: {critical_error}", exc_info=True)
        mark_broadcast_failed(broadcast_id, str(critical_error))
        raise
    finally:
        logger.info(
            f"✅ Broadcast {broadcast_id} finished: "
            f"{sent}/{total} sent, {failed} failed, "
            f"{len(blocked_users)} blocked"
        )
    
    return sent, failed, total


def get_admin_info_from_db(admin_id):
    """
    دریافت اطلاعات ادمین از دیتابیس
    
    Args:
        admin_id: شناسه ادمین
    
    Returns:
        dict: اطلاعات ادمین یا None
    """
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, first_name, username, last_name 
            FROM users 
            WHERE user_id = ?
        ''', (admin_id,))
        user = cursor.fetchone()
        conn.close()
        return dict(user) if user else None
    except Exception as e:
        logger.warning(f"⚠️ Could not get admin info: {e}")
        return None
