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
    
    # Migration: اگر فیلد status وجود نداره، اضافه کن
    try:
        cursor.execute("ALTER TABLE broadcasts ADD COLUMN status TEXT DEFAULT 'pending'")
        logger.info("✅ Added status column to broadcasts table")
    except sqlite3.OperationalError:
        pass  # فیلد از قبل وجود داره
    
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
    
    conn.commit()
    conn.close()
    logger.info("✅ Admin database initialized successfully")

# ============ عملیات Broadcast ============

def save_broadcast(admin_id, title, message, send_date=None, send_time=None):
    """ذخیره پیام همگانی جدید"""
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
    
    # اطلاعات اصلی broadcast
    cursor.execute('SELECT * FROM broadcasts WHERE id = ?', (broadcast_id,))
    broadcast = cursor.fetchone()
    
    # آمار لاگ‌ها
    cursor.execute('''
        SELECT status, COUNT(*) as count 
        FROM broadcast_logs 
        WHERE broadcast_id = ? 
        GROUP BY status
    ''', (broadcast_id,))
    logs = cursor.fetchall()
    
    conn.close()
    return broadcast, logs

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
    # فرض می‌کنیم جدول users وجود داره با فیلد is_active
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
        # اگر جدول users وجود نداشت یا فیلدها متفاوت بودن
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
