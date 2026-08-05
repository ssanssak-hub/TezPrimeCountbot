import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = 'tezprime.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # جدول کاربران با ستون‌های جدید
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_admin BOOLEAN DEFAULT 0,
            is_banned BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # اضافه کردن ستون‌های جدید به دیتابیس قدیمی
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0')
        logger.info("✅ Added is_admin column")
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT 0')
        logger.info("✅ Added is_banned column")
    except sqlite3.OperationalError:
        pass
    
    # جدول وضعیت ربات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_status (
            id INTEGER PRIMARY KEY DEFAULT 1,
            is_active BOOLEAN DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # اطمینان از وجود رکورد وضعیت
    cursor.execute('''
        INSERT OR IGNORE INTO bot_status (id, is_active) VALUES (1, 1)
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def save_user(user_id, username, first_name, last_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # اول چک کن کاربر وجود داره یا نه
    cursor.execute('SELECT is_admin, is_banned FROM users WHERE user_id = ?', (user_id,))
    existing = cursor.fetchone()
    
    if existing:
        # کاربر هست - فقط نام و یوزرنیم رو آپدیت کن
        cursor.execute('''
            UPDATE users SET username = ?, first_name = ?, last_name = ?
            WHERE user_id = ?
        ''', (username, first_name, last_name, user_id))
    else:
        # کاربر جدید - insert کن
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
    
    conn.commit()
    conn.close()

def is_user_admin(user_id, admin_id):
    """چک کردن ادمین بودن کاربر (ادمین اصلی یا فرعی)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # ادمین اصلی (از .env)
    if user_id == admin_id:
        conn.close()
        return True, "main_admin"
    
    # ادمین فرعی (از دیتابیس)
    cursor.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result['is_admin']:
        return True, "sub_admin"
    
    return False, None

def get_all_users():
    """دریافت همه کاربران"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()
    conn.close()
    return users

def get_all_active_users():
    """دریافت کاربران فعال (بن نشده)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE is_banned = 0')
    users = cursor.fetchall()
    conn.close()
    return users

def get_total_users_count():
    """تعداد کل کاربران"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM users')
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0

def ban_user(user_id):
    """بن کردن کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    logger.info(f"🚫 User {user_id} banned")

def unban_user(user_id):
    """آزاد کردن کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    logger.info(f"✅ User {user_id} unbanned")

def get_banned_users():
    """لیست کاربران بن شده"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE is_banned = 1')
    users = cursor.fetchall()
    conn.close()
    return users

def is_user_banned(user_id):
    """چک کردن بن بودن کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result and result['is_banned'] == 1

def get_user_info(user_id):
    """دریافت اطلاعات کامل یک کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_admin(user_id):
    """اضافه کردن ادمین فرعی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    logger.info(f"👑 User {user_id} promoted to admin")

def remove_admin(user_id):
    """حذف ادمین فرعی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_admin = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    logger.info(f"⬇️ User {user_id} demoted from admin")

def get_all_admins():
    """لیست همه ادمین‌ها"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE is_admin = 1')
    admins = cursor.fetchall()
    conn.close()
    return admins

def get_bot_status():
    """دریافت وضعیت ربات"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bot_status WHERE id = 1')
    status = cursor.fetchone()
    conn.close()
    return status

def toggle_bot_status():
    """تغییر وضعیت ربات (روشن/خاموش)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    current = cursor.execute('SELECT is_active FROM bot_status WHERE id = 1').fetchone()
    new_status = 0 if current['is_active'] else 1
    cursor.execute('UPDATE bot_status SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1', (new_status,))
    conn.commit()
    conn.close()
    logger.info(f"🤖 Bot status changed to: {'ON' if new_status else 'OFF'}")
    return new_status

def delete_all_user_data():
    """حذف همه داده‌های کاربران"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users')
    conn.commit()
    conn.close()
    logger.info("🗑️ All user data deleted")

def is_bot_active():
    """چک کردن فعال بودن ربات"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_active FROM bot_status WHERE id = 1')
    result = cursor.fetchone()
    conn.close()
    return result['is_active'] == 1 if result else True
