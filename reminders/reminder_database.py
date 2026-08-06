import sqlite3
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# ایجاد پوشه reminders اگر وجود نداشت
if not os.path.exists('reminders'):
    os.makedirs('reminders')

REMINDER_DB_PATH = 'reminders/reminders.db'

def get_reminder_db_connection():
    conn = sqlite3.connect(REMINDER_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ✅ توابع کمکی برای تبدیل
def row_to_dict(row):
    """تبدیل sqlite3.Row به دیکشنری"""
    if row is None:
        return None
    return dict(row)

def rows_to_dicts(rows):
    """تبدیل لیست sqlite3.Row به لیست دیکشنری"""
    return [dict(row) for row in rows]

def init_reminder_db():
    """ایجاد جدول reminders اگر وجود نداشت"""
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT DEFAULT '',
            message TEXT,
            days_of_week TEXT,
            hour INTEGER,
            minute INTEGER,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # اضافه کردن ستون title به دیتابیس قدیمی (اگه وجود نداشته باشه)
    try:
        cursor.execute('ALTER TABLE reminders ADD COLUMN title TEXT DEFAULT ""')
        logger.info("✅ Added title column to reminders table")
    except sqlite3.OperationalError:
        pass  # ستون از قبل وجود داره
    
    conn.commit()
    conn.close()
    logger.info("✅ Reminder database initialized successfully")

def save_reminder(user_id, title, message, days, hour, minute):
    """ذخیره اعلان جدید با عنوان"""
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    days_str = ','.join(map(str, days))
    
    cursor.execute('''
        INSERT INTO reminders (user_id, title, message, days_of_week, hour, minute)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, title, message, days_str, hour, minute))
    
    conn.commit()
    reminder_id = cursor.lastrowid
    conn.close()
    
    logger.info(f"✅ Reminder {reminder_id} saved for user {user_id}")
    return reminder_id

def get_user_reminders(user_id):
    """دریافت اعلان‌های فعال کاربر"""
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM reminders 
        WHERE user_id = ? AND is_active = 1
        ORDER BY created_at DESC
    ''', (user_id,))
    
    reminders = cursor.fetchall()
    conn.close()
    
    return rows_to_dicts(reminders)  # ✅ تبدیل به دیکشنری

def get_all_user_reminders(user_id):
    """دریافت همه اعلان‌های کاربر (فعال و غیرفعال)"""
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM reminders 
        WHERE user_id = ?
        ORDER BY is_active DESC, created_at DESC
    ''', (user_id,))
    
    reminders = cursor.fetchall()
    conn.close()
    
    return rows_to_dicts(reminders)  # ✅ تبدیل به دیکشنری

def delete_reminder(reminder_id, user_id):
    """حذف کامل اعلان از دیتابیس"""
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM reminders 
        WHERE id = ? AND user_id = ?
    ''', (reminder_id, user_id))
    
    conn.commit()
    conn.close()
    logger.info(f"🗑️ Reminder {reminder_id} deleted for user {user_id}")

def cancel_reminder(reminder_id, user_id):
    """غیرفعال کردن اعلان (پاک نمیشه، فقط غیرفعال میشه)"""
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE reminders 
        SET is_active = 0 
        WHERE id = ? AND user_id = ?
    ''', (reminder_id, user_id))
    
    conn.commit()
    conn.close()
    logger.info(f"⛔ Reminder {reminder_id} cancelled for user {user_id}")

def activate_reminder(reminder_id, user_id):
    """فعال کردن مجدد اعلان"""
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE reminders 
        SET is_active = 1 
        WHERE id = ? AND user_id = ?
    ''', (reminder_id, user_id))
    
    conn.commit()
    conn.close()
    logger.info(f"✅ Reminder {reminder_id} activated for user {user_id}")

def get_all_active_reminders():
    """دریافت همه اعلان‌های فعال (برای scheduler)"""
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM reminders 
        WHERE is_active = 1
    ''')
    
    reminders = cursor.fetchall()
    conn.close()
    
    return rows_to_dicts(reminders)  # ✅ تبدیل به دیکشنری

def get_reminder_by_id(reminder_id):
    """دریافت یک اعلان با شناسه"""
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM reminders WHERE id = ?', (reminder_id,))
    reminder = cursor.fetchone()
    conn.close()
    
    return row_to_dict(reminder)  # ✅ تبدیل به دیکشنری
