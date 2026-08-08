import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = 'tezprime.db'

def get_db_connection():
    """ایجاد اتصال به دیتابیس با timeout"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # فعال کردن foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_admin_db():
    """ایجاد جداول پنل مدیریت"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # جدول پیام‌های همگانی (با فیلدهای جدید)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            is_cancelled BOOLEAN DEFAULT 0,
            total_users INTEGER DEFAULT 0,
            sent_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            blocked_count INTEGER DEFAULT 0,
            send_date TEXT,
            send_time TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # جدول لاگ ارسال‌ها (با ایندکس برای performance)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broadcast_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broadcast_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (broadcast_id) REFERENCES broadcasts(id) ON DELETE CASCADE
        )
    ''')
    
    # ایندکس‌ها برای بهبود performance
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_broadcast_logs_broadcast_id 
        ON broadcast_logs(broadcast_id)
    ''')    
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_broadcast_logs_user_id 
        ON broadcast_logs(user_id)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_broadcasts_status 
        ON broadcasts(status)
    ''')

    # ✅ جدول جدید برای پیام‌های دکمه‌های شیشه‌ای
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS button_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            button_id TEXT UNIQUE NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')    
    
    # ============ Migration های موجود ============
    
    try:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN status TEXT DEFAULT 'pending'")
        logger.info("✅ Added status column to broadcasts table")
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN blocked_count INTEGER DEFAULT 0")
        logger.info("✅ Added blocked_count column to broadcasts table")
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN started_at TIMESTAMP")
        logger.info("✅ Added started_at column to broadcasts table")
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN completed_at TIMESTAMP")
        logger.info("✅ Added completed_at column to broadcasts table")
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN error_message TEXT")
        logger.info("✅ Added error_message column to broadcasts table")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN job_id TEXT")
        logger.info("✅ Added job_id column to broadcasts table")
    except sqlite3.OperationalError:
        pass
    # توی init_admin_db() اضافه کن:
    try:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN from_chat_id TEXT")
    except: pass
    try:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN from_message_id INTEGER")
    except: pass
    # ============ Migration های جدید برای ارسال پیشرفته ============
    
    try:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN content_type TEXT DEFAULT 'text'")
        logger.info("✅ Added content_type column to broadcasts table")
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN file_id TEXT")
        logger.info("✅ Added file_id column to broadcasts table")
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN file_caption TEXT")
        logger.info("✅ Added file_caption column to broadcasts table")
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN inline_buttons TEXT")
        logger.info("✅ Added inline_buttons column to broadcasts table")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()
    logger.info("✅ Admin database initialized successfully")

# ============ عملیات Broadcast ============

def save_broadcast(admin_id, title, message, send_date=None, send_time=None):
    """ذخیره پیام همگانی جدید (روش قدیمی - فقط متن)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO broadcasts (admin_id, title, message, send_date, send_time, status)
        VALUES (?, ?, ?, ?, ?, 'pending')
    ''', (admin_id, title, message, send_date, send_time))
    
    broadcast_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"📝 Broadcast {broadcast_id} saved by admin {admin_id}")
    return broadcast_id


def save_broadcast_advanced(admin_id, title, content_type='text', 
                           message=None, file_id=None, file_caption=None, 
                           inline_buttons=None, send_date=None, send_time=None,
                           from_chat_id=None, from_message_id=None,
                           poll_mode=None, poll_question=None, poll_options=None):
    """
    ذخیره پیام همگانی با پشتیبانی از انواع محتوا و دکمه‌های شیشه‌ای
    
    Args:
        admin_id: شناسه ادمین
        title: عنوان پیام
        content_type: نوع محتوا (text, photo, video, document, audio)
        message: متن پیام (برای content_type='text')
        file_id: شناسه فایل تلگرام (برای مدیا)
        file_caption: کپشن فایل
        inline_buttons: لیست دکمه‌های شیشه‌ای [[text, url], [text, callback_data, type]]
        send_date: تاریخ ارسال (برای زمان‌بندی)
        send_time: ساعت ارسال (برای زمان‌بندی)
    
    Returns:
        int: broadcast_id
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    import json
    
    # تبدیل دکمه‌ها به JSON
    buttons_json = json.dumps(inline_buttons, ensure_ascii=False) if inline_buttons else None
    if inline_buttons:
        try:
            buttons_json = json.dumps(inline_buttons, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Error serializing inline_buttons: {e}")
    # قبل از INSERT:
    logger.info(f"💾 SAVING BROADCAST: from_chat_id={from_chat_id}, from_message_id={from_message_id}")
                               
    cursor.execute('''
        INSERT INTO broadcasts (
            admin_id, title, content_type, message, 
            file_id, file_caption, inline_buttons,
            send_date, send_time, from_chat_id, from_message_id, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    ''', (admin_id, title, content_type, message, 
          file_id, file_caption, buttons_json,
          send_date, send_time, from_chat_id, from_message_id))
    
    broadcast_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"📝 Advanced broadcast {broadcast_id} saved (type: {content_type}, buttons: {len(inline_buttons) if inline_buttons else 0})")
    return broadcast_id

def get_pending_broadcasts():
    """دریافت پیام‌های همگانی در انتظار ارسال"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM broadcasts 
        WHERE status = 'pending' AND is_cancelled = 0 
        ORDER BY created_at
    ''')
    broadcasts = cursor.fetchall()
    conn.close()
    return broadcasts

def get_all_broadcasts(limit=50, offset=0):
    """دریافت همه پیام‌های همگانی با pagination"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM broadcasts 
        ORDER BY created_at DESC 
        LIMIT ? OFFSET ?
    ''', (limit, offset))
    broadcasts = cursor.fetchall()
    conn.close()
    return broadcasts

def get_broadcast_by_id(broadcast_id):
    """دریافت یک پیام همگانی با شناسه"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM broadcasts WHERE id = ?', (broadcast_id,))
    broadcast = cursor.fetchone()
    conn.close()
    return broadcast

def mark_broadcast_sent(broadcast_id, total_users):
    """علامت‌گذاری پیام به عنوان در حال ارسال"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE broadcasts 
        SET status = 'sending', 
            total_users = ?, 
            started_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    ''', (total_users, broadcast_id))
    conn.commit()
    conn.close()
    logger.info(f"📤 Broadcast {broadcast_id} marked as sending to {total_users} users")

def mark_broadcast_completed(broadcast_id, sent_count, failed_count):
    """علامت‌گذاری پیام به عنوان تکمیل شده"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE broadcasts 
        SET status = 'completed',
            sent_count = ?,
            failed_count = ?,
            completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (sent_count, failed_count, broadcast_id))
    conn.commit()
    conn.close()
    logger.info(f"✅ Broadcast {broadcast_id} marked as completed")

def mark_broadcast_failed(broadcast_id, error_message):
    """علامت‌گذاری پیام به عنوان ناموفق"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE broadcasts 
        SET status = 'failed',
            error_message = ?,
            completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (error_message, broadcast_id))
    conn.commit()
    conn.close()
    logger.error(f"❌ Broadcast {broadcast_id} marked as failed: {error_message}")

def mark_broadcast_stopped(broadcast_id):
    """توقف ارسال پیام همگانی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE broadcasts 
        SET status = 'stopped',
            completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (broadcast_id,))
    conn.commit()
    conn.close()
    logger.info(f"🛑 Broadcast {broadcast_id} stopped")

def mark_broadcast_cancelled(broadcast_id):
    """لغو پیام همگانی قبل از ارسال"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE broadcasts 
        SET is_cancelled = 1, 
            status = 'cancelled' 
        WHERE id = ?
    ''', (broadcast_id,))
    conn.commit()
    conn.close()
    logger.info(f"❎ Broadcast {broadcast_id} cancelled")

def delete_broadcast(broadcast_id):
    """حذف پیام همگانی و لاگ‌های مرتبط"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # اول لاگ‌ها رو پاک کن
    cursor.execute('DELETE FROM broadcast_logs WHERE broadcast_id = ?', (broadcast_id,))
    # بعد خود broadcast رو پاک کن
    cursor.execute('DELETE FROM broadcasts WHERE id = ?', (broadcast_id,))
    conn.commit()
    conn.close()
    logger.info(f"🗑️ Broadcast {broadcast_id} and its logs deleted")

def update_broadcast_count(broadcast_id, sent_count, failed_count, blocked_count=0):
    """بروزرسانی تعداد ارسال‌ها"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE broadcasts 
        SET sent_count = ?, 
            failed_count = ?,
            blocked_count = ?
        WHERE id = ?
    ''', (sent_count, failed_count, blocked_count, broadcast_id))
    conn.commit()
    conn.close()

def add_broadcast_log(broadcast_id, user_id, status, error=None):
    """ثبت لاگ ارسال برای یک کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO broadcast_logs (broadcast_id, user_id, status, error)
        VALUES (?, ?, ?, ?)
    ''', (broadcast_id, user_id, status, error))
    conn.commit()
    conn.close()

def get_broadcast_stats(broadcast_id):
    """دریافت آمار کامل یک پیام همگانی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM broadcasts WHERE id = ?', (broadcast_id,))
    broadcast = cursor.fetchone()
    
    cursor.execute('''
        SELECT status, COUNT(*) as count 
        FROM broadcast_logs 
        WHERE broadcast_id = ? 
        GROUP BY status
    ''', (broadcast_id,))
    logs = cursor.fetchall()
    
    conn.close()
    return row_to_dict(broadcast), rows_to_dicts(logs)
    
def get_broadcast_progress(broadcast_id):
    """درصد پیشرفت ارسال"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT total_users, sent_count, failed_count, status 
        FROM broadcasts 
        WHERE id = ?
    ''', (broadcast_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or result['total_users'] == 0:
        return 0
    
    processed = result['sent_count'] + result['failed_count']
    return round(processed / result['total_users'] * 100, 1)

def get_broadcast_speed(broadcast_id):
    """محاسبه سرعت ارسال (پیام در ثانیه)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT sent_count, failed_count, started_at 
        FROM broadcasts 
        WHERE id = ? AND started_at IS NOT NULL
    ''', (broadcast_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or not result['started_at']:
        return 0
    
    processed = result['sent_count'] + result['failed_count']
    started_at = datetime.fromisoformat(result['started_at'])
    elapsed = (datetime.now() - started_at).total_seconds()
    
    if elapsed == 0:
        return 0
    
    return round(processed / elapsed, 1)

def get_broadcast_failed_users(broadcast_id, limit=100):
    """دریافت لیست کاربران ناموفق"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id, error, sent_at 
        FROM broadcast_logs 
        WHERE broadcast_id = ? AND status = 'failed'
        ORDER BY sent_at DESC
        LIMIT ?
    ''', (broadcast_id, limit))
    failed_users = cursor.fetchall()
    conn.close()
    return failed_users

def get_active_broadcasts():
    """دریافت پیام‌های در حال ارسال"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM broadcasts 
        WHERE status = 'sending'
        ORDER BY started_at DESC
    ''')
    broadcasts = cursor.fetchall()
    conn.close()
    return broadcasts

def stop_all_active_broadcasts():
    """توقف همه ارسال‌های فعال"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE broadcasts 
        SET status = 'stopped', 
            completed_at = CURRENT_TIMESTAMP 
        WHERE status = 'sending'
    ''')
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    logger.info(f"🛑 Stopped {affected} active broadcasts")
    return affected

def deactivate_user(user_id):
    """غیرفعال کردن کاربر (برای کاربران بلاک‌شده)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE users 
            SET is_active = 0, 
                deactivated_at = CURRENT_TIMESTAMP,
                deactivation_reason = 'blocked_bot'
            WHERE user_id = ?
        ''', (user_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        if affected > 0:
            logger.info(f"🚫 User {user_id} deactivated (blocked bot)")
        return affected > 0
    except sqlite3.OperationalError as e:
        logger.warning(f"⚠️ Could not deactivate user {user_id}: {e}")
        conn.close()
        return False

def get_broadcast_summary():
    """خلاصه آمار همه broadcast ها"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as total FROM broadcasts')
    total = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as active FROM broadcasts WHERE status = "sending"')
    active = cursor.fetchone()['active']
    
    cursor.execute('SELECT COUNT(*) as completed FROM broadcasts WHERE status = "completed"')
    completed = cursor.fetchone()['completed']
    
    cursor.execute('SELECT COUNT(*) as failed FROM broadcasts WHERE status = "failed"')
    failed = cursor.fetchone()['failed']
    
    conn.close()
    
    return {
        'total': total,
        'active': active,
        'completed': completed,
        'failed': failed
    }

# ============ توابع کمکی ============

def row_to_dict(row):
    """تبدیل sqlite3.Row به دیکشنری"""
    if row is None:
        return None
    return dict(row)

def rows_to_dicts(rows):
    """تبدیل لیست sqlite3.Row به لیست دیکشنری"""
    return [dict(row) for row in rows]

def get_broadcast_full_info(broadcast_id):
    """
    دریافت اطلاعات کامل یک broadcast شامل دکمه‌های پارس شده
    
    Returns:
        dict: اطلاعات کامل با inline_buttons پارس شده
    """
    broadcast = get_broadcast_by_id(broadcast_id)
    if not broadcast:
        return None
    
    broadcast_dict = dict(broadcast)
    
    # پارس کردن inline_buttons از JSON
    if broadcast_dict.get('inline_buttons'):
        try:
            import json
            broadcast_dict['inline_buttons'] = json.loads(broadcast_dict['inline_buttons'])
        except:
            broadcast_dict['inline_buttons'] = []
    else:
        broadcast_dict['inline_buttons'] = []
    
    return broadcast_dict

def update_broadcast_buttons(broadcast_id, inline_buttons):
    """
    بروزرسانی دکمه‌های شیشه‌ای یک broadcast
    
    Args:
        broadcast_id: شناسه broadcast
        inline_buttons: لیست جدید دکمه‌ها
    
    Returns:
        bool: موفقیت‌آمیز بودن عملیات
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    import json
    buttons_json = json.dumps(inline_buttons, ensure_ascii=False) if inline_buttons else None
    
    try:
        cursor.execute('''
            UPDATE broadcasts 
            SET inline_buttons = ?
            WHERE id = ?
        ''', (buttons_json, broadcast_id))
        conn.commit()
        conn.close()
        logger.info(f"✅ Broadcast {broadcast_id} buttons updated ({len(inline_buttons) if inline_buttons else 0} buttons)")
        return True
    except Exception as e:
        logger.error(f"❌ Error updating broadcast buttons: {e}")
        conn.close()
        return False

def get_broadcasts_by_type(content_type=None):
    """
    دریافت broadcast ها بر اساس نوع محتوا
    
    Args:
        content_type: نوع محتوا (text, photo, video, document, audio)
                      اگر None باشه، همه رو برمی‌گردونه
    
    Returns:
        list: لیست broadcast ها
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if content_type:
        cursor.execute('''
            SELECT * FROM broadcasts 
            WHERE content_type = ?
            ORDER BY created_at DESC
        ''', (content_type,))
    else:
        cursor.execute('''
            SELECT * FROM broadcasts 
            ORDER BY created_at DESC
        ''')
    
    broadcasts = cursor.fetchall()
    conn.close()
    return broadcasts

def get_broadcast_statistics():
    """
    آمار کلی broadcast ها بر اساس نوع محتوا
    
    Returns:
        dict: آمار تفکیک شده
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            content_type,
            COUNT(*) as total,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'sending' THEN 1 ELSE 0 END) as sending,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(sent_count) as total_sent,
            SUM(failed_count) as total_failed,
            SUM(total_users) as total_recipients
        FROM broadcasts
        GROUP BY content_type
    ''')
    
    stats = cursor.fetchall()
    conn.close()
    
    result = {}
    for row in stats:
        content_type = row['content_type'] or 'text'
        result[content_type] = {
            'total': row['total'],
            'completed': row['completed'],
            'pending': row['pending'],
            'sending': row['sending'],
            'failed': row['failed'],
            'total_sent': row['total_sent'] or 0,
            'total_failed': row['total_failed'] or 0,
            'total_recipients': row['total_recipients'] or 0,
            'success_rate': round(
                (row['total_sent'] or 0) / (row['total_recipients'] or 1) * 100, 1
            ) if row['total_recipients'] else 0
        }
    
    return result

def save_button_message(button_id, message):
    """ذخیره پیام دکمه در دیتابیس"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO button_messages (button_id, message)
        VALUES (?, ?)
    ''', (button_id, message))
    conn.commit()
    conn.close()
    return button_id

def get_button_message(button_id):
    """دریافت پیام دکمه از دیتابیس"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT message FROM button_messages WHERE button_id = ?', (button_id,))
    result = cursor.fetchone()
    conn.close()
    return result['message'] if result else None
