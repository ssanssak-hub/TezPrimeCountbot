import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = 'tezprime.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_admin_db():
    """ایجاد جداول پنل مدیریت"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # جدول پیام‌های همگانی
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            title TEXT,
            message TEXT,
            is_sent BOOLEAN DEFAULT 0,
            is_cancelled BOOLEAN DEFAULT 0,
            total_users INTEGER DEFAULT 0,
            sent_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            send_date TEXT,
            send_time TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # جدول لاگ ارسال‌ها
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broadcast_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broadcast_id INTEGER,
            user_id INTEGER,
            status TEXT,
            error TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ Admin database initialized")

def save_broadcast(admin_id, title, message, send_date=None, send_time=None):
    """ذخیره پیام همگانی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO broadcasts (admin_id, title, message, send_date, send_time)
        VALUES (?, ?, ?, ?, ?)
    ''', (admin_id, title, message, send_date, send_time))
    
    broadcast_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return broadcast_id

def get_pending_broadcasts():
    """دریافت پیام‌های همگانی در انتظار"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM broadcasts WHERE is_sent = 0 AND is_cancelled = 0 ORDER BY created_at')
    broadcasts = cursor.fetchall()
    conn.close()
    return broadcasts

def get_all_broadcasts():
    """دریافت همه پیام‌های همگانی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM broadcasts ORDER BY created_at DESC')
    broadcasts = cursor.fetchall()
    conn.close()
    return broadcasts

def mark_broadcast_sent(broadcast_id, total_users):
    """علامت‌گذاری پیام به عنوان ارسال شده"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE broadcasts SET is_sent = 1, total_users = ? WHERE id = ?
    ''', (total_users, broadcast_id))
    conn.commit()
    conn.close()

def mark_broadcast_cancelled(broadcast_id):
    """لغو پیام همگانی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE broadcasts SET is_cancelled = 1 WHERE id = ?', (broadcast_id,))
    conn.commit()
    conn.close()

def delete_broadcast(broadcast_id):
    """حذف پیام همگانی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM broadcasts WHERE id = ?', (broadcast_id,))
    conn.commit()
    conn.close()

def add_broadcast_log(broadcast_id, user_id, status, error=None):
    """ثبت لاگ ارسال"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO broadcast_logs (broadcast_id, user_id, status, error)
        VALUES (?, ?, ?, ?)
    ''', (broadcast_id, user_id, status, error))
    conn.commit()
    conn.close()

def update_broadcast_count(broadcast_id, sent_count, failed_count):
    """بروزرسانی تعداد ارسال‌ها"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE broadcasts SET sent_count = ?, failed_count = ? WHERE id = ?
    ''', (sent_count, failed_count, broadcast_id))
    conn.commit()
    conn.close()

def get_broadcast_stats(broadcast_id):
    """دریافت آمار یک پیام همگانی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM broadcasts WHERE id = ?', (broadcast_id,))
    broadcast = cursor.fetchone()
    
    cursor.execute('''
        SELECT status, COUNT(*) as count FROM broadcast_logs 
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
    cursor.execute('SELECT total_users, sent_count, failed_count FROM broadcasts WHERE id = ?', (broadcast_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or result['total_users'] == 0:
        return 0
    
    return round((result['sent_count'] + result['failed_count']) / result['total_users'] * 100, 1)
