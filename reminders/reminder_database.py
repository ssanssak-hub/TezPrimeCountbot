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

def init_reminder_db():
    """ایجاد جدول reminders اگر وجود نداشت"""
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            days_of_week TEXT,
            hour INTEGER,
            minute INTEGER,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ Reminder database initialized successfully")

def save_reminder(user_id, message, days, hour, minute):
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    days_str = ','.join(map(str, days))
    
    cursor.execute('''
        INSERT INTO reminders (user_id, message, days_of_week, hour, minute)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, message, days_str, hour, minute))
    
    conn.commit()
    reminder_id = cursor.lastrowid
    conn.close()
    
    logger.info(f"✅ Reminder {reminder_id} saved for user {user_id}")
    return reminder_id

def get_user_reminders(user_id):
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM reminders 
        WHERE user_id = ? AND is_active = 1
        ORDER BY created_at DESC
    ''', (user_id,))
    
    reminders = cursor.fetchall()
    conn.close()
    
    return reminders

def get_all_user_reminders(user_id):
    """دریافت همه اعلان‌های کاربر (فعال و غیرفعال)"""
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM reminders 
        WHERE user_id = ?
        ORDER BY created_at DESC
    ''', (user_id,))
    
    reminders = cursor.fetchall()
    conn.close()
    
    return reminders

def delete_reminder(reminder_id, user_id):
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

def get_all_active_reminders():
    conn = get_reminder_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM reminders 
        WHERE is_active = 1
    ''')
    
    reminders = cursor.fetchall()
    conn.close()
    
    return reminders
