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
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_admin BOOLEAN DEFAULT 0,
            is_banned BOOLEAN DEFAULT 0,
            admin_permissions TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
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
    
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN admin_permissions TEXT DEFAULT ""')
        logger.info("✅ Added admin_permissions column")
    except sqlite3.OperationalError:
        pass
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_status (
            id INTEGER PRIMARY KEY DEFAULT 1,
            is_active BOOLEAN DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('INSERT OR IGNORE INTO bot_status (id, is_active) VALUES (1, 1)')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def save_user(user_id, username, first_name, last_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT is_admin, is_banned FROM users WHERE user_id = ?', (user_id,))
    existing = cursor.fetchone()
    
    if existing:
        cursor.execute('''
            UPDATE users SET username = ?, first_name = ?, last_name = ?
            WHERE user_id = ?
        ''', (username, first_name, last_name, user_id))
    else:
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
    
    conn.commit()
    conn.close()

# ⚠️ تابع اصلی - ۳ خروجی
def _is_user_admin_full(user_id, admin_id):
    """اطلاعات کامل ادمین"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if user_id == admin_id:
        conn.close()
        return True, "main_admin", "all"
    
    cursor.execute('SELECT is_admin, admin_permissions FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result['is_admin']:
        return True, "sub_admin", result['admin_permissions'] or ''
    
    return False, None, ''

# ⚠️ تابع سازگار با کد قدیمی - ۲ خروجی
def is_user_admin(user_id, admin_id):
    """چک ادمین - ۲ خروجی (سازگار با کد قدیم)"""
    is_admin, admin_type, _ = _is_user_admin_full(user_id, admin_id)
    return is_admin, admin_type

# ⚠️ تابع جدید - ۳ خروجی برای جاهایی که permissions لازمه
def get_admin_info(user_id, admin_id):
    """اطلاعات کامل ادمین - ۳ خروجی"""
    return _is_user_admin_full(user_id, admin_id)

# ⚠️ تابع جدید: چک دسترسی ادمین فرعی
def check_admin_permission(user_id, admin_id, permission):
    """چک اینکه ادمین فرعی به یه بخش خاص دسترسی داره یا نه"""
    is_admin, admin_type, permissions = get_admin_info(user_id, admin_id)
    
    if not is_admin:
        return False
    
    if admin_type == "main_admin":
        return True
    
    if permission == "admin_panel":
        return True
    
    if permissions == "all":
        return True
    
    return permission in permissions.split(',') if permissions else False

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()
    conn.close()
    return users

def get_all_active_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE is_banned = 0')
    users = cursor.fetchall()
    conn.close()
    return users

def get_total_users_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM users')
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0

def ban_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    logger.info(f"🚫 User {user_id} banned")

def unban_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    logger.info(f"✅ User {user_id} unbanned")

def get_banned_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE is_banned = 1')
    users = cursor.fetchall()
    conn.close()
    return users

def is_user_banned(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result and result['is_banned'] == 1

def get_user_info(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_admin(user_id, permissions="all"):
    """اضافه کردن ادمین فرعی با دسترسی‌های مشخص"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users SET is_admin = 1, admin_permissions = ? WHERE user_id = ?
    ''', (permissions, user_id))
    conn.commit()
    conn.close()
    logger.info(f"👑 User {user_id} promoted to admin with permissions: {permissions}")

def remove_admin(user_id):
    """حذف ادمین فرعی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_admin = 0, admin_permissions = "" WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    logger.info(f"⬇️ User {user_id} demoted from admin")

def get_all_admins():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE is_admin = 1')
    admins = cursor.fetchall()
    conn.close()
    return admins

def get_bot_status():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bot_status WHERE id = 1')
    status = cursor.fetchone()
    conn.close()
    return status

def toggle_bot_status():
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users')
    conn.commit()
    conn.close()
    logger.info("🗑️ All user data deleted")

def is_bot_active():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_active FROM bot_status WHERE id = 1')
    result = cursor.fetchone()
    conn.close()
    return result['is_active'] == 1 if result else True
