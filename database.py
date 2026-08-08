import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = 'tezprime.db'

def get_db_connection():
    """ایجاد اتصال به دیتابیس با timeout"""
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    # فعال کردن foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """ایجاد و بروزرسانی جداول اصلی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # جدول کاربران با تمام فیلدهای لازم
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_admin BOOLEAN DEFAULT 0,
            is_banned BOOLEAN DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            admin_permissions TEXT DEFAULT '',
            deactivated_at TIMESTAMP,
            deactivation_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Migration ها - اضافه کردن فیلدهای جدید به جدول موجود
    migrations = [
        ("is_admin", "BOOLEAN DEFAULT 0"),
        ("is_banned", "BOOLEAN DEFAULT 0"),
        ("is_active", "BOOLEAN DEFAULT 1"),
        ("admin_permissions", 'TEXT DEFAULT ""'),
        ("deactivated_at", "TIMESTAMP"),
        ("deactivation_reason", "TEXT"),
        ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ]
    
    for column_name, column_type in migrations:
        try:
            cursor.execute(f'ALTER TABLE users ADD COLUMN {column_name} {column_type}')
            logger.info(f"✅ Added {column_name} column to users table")
        except sqlite3.OperationalError:
            pass  # فیلد از قبل وجود داره
    
    # جدول وضعیت ربات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_status (
            id INTEGER PRIMARY KEY DEFAULT 1,
            is_active BOOLEAN DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # مقدار پیش‌فرض برای bot_status
    cursor.execute('INSERT OR IGNORE INTO bot_status (id, is_active) VALUES (1, 1)')
    
    # ایندکس‌ها برای بهبود performance
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_users_is_admin 
        ON users(is_admin)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_users_is_banned 
        ON users(is_banned)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_users_is_active 
        ON users(is_active)
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized successfully")


# ============ عملیات کاربران ============

def save_user(user_id, username, first_name, last_name):
    """ذخیره یا بروزرسانی اطلاعات کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT user_id, is_admin, is_banned FROM users WHERE user_id = ?', (user_id,))
    existing = cursor.fetchone()
    
    if existing:
        cursor.execute('''
            UPDATE users 
            SET username = ?, 
                first_name = ?, 
                last_name = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (username, first_name, last_name, user_id))
    else:
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
        logger.info(f"👤 New user registered: {user_id}")
    
    conn.commit()
    conn.close()

def get_user_info(user_id):
    """دریافت اطلاعات کامل یک کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_all_users():
    """دریافت همه کاربران"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
    users = cursor.fetchall()
    conn.close()
    return users

def get_all_active_users():
    """دریافت کاربران فعال (بن نشده و غیرفعال نشده)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM users 
        WHERE is_banned = 0 AND is_active = 1
        ORDER BY user_id
    ''')
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

def get_user_stats():
    """آمار کامل کاربران"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    stats = {}
    
    # کل کاربران
    cursor.execute('SELECT COUNT(*) as count FROM users')
    stats['total'] = cursor.fetchone()['count']
    
    # کاربران فعال
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_banned = 0 AND is_active = 1')
    stats['active'] = cursor.fetchone()['count']
    
    # کاربران بن شده
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_banned = 1')
    stats['banned'] = cursor.fetchone()['count']
    
    # کاربران غیرفعال (بلاک کرده‌اند یا inactive)
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_active = 0')
    stats['inactive'] = cursor.fetchone()['count']
    
    # ادمین‌ها
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_admin = 1')
    stats['admins'] = cursor.fetchone()['count']
    
    # کاربران جدید امروز
    cursor.execute('''
        SELECT COUNT(*) as count FROM users 
        WHERE date(created_at) = date('now')
    ''')
    stats['new_today'] = cursor.fetchone()['count']
    
    conn.close()
    return stats


# ============ مدیریت ادمین‌ها ============

def _is_user_admin_full(user_id, admin_id):
    """اطلاعات کامل ادمین - استفاده داخلی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # ادمین اصلی (از .env)
    if user_id == admin_id:
        conn.close()
        return True, "main_admin", "all"
    
    # ادمین فرعی
    cursor.execute('SELECT is_admin, admin_permissions FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result['is_admin']:
        return True, "sub_admin", result['admin_permissions'] or ''
    
    return False, None, ''

def is_user_admin(user_id, admin_id):
    """چک ادمین بودن - ۲ خروجی (سازگار با کد قدیم)"""
    is_admin, admin_type, _ = _is_user_admin_full(user_id, admin_id)
    return is_admin, admin_type

def get_admin_info(user_id, admin_id):
    """اطلاعات کامل ادمین - ۳ خروجی"""
    return _is_user_admin_full(user_id, admin_id)

def check_admin_permission(user_id, admin_id, permission):
    """
    چک دسترسی ادمین فرعی
    
    Args:
        user_id: شناسه کاربر جاری
        admin_id: شناسه ادمین اصلی
        permission: کد دسترسی (مثلاً "perm_broadcast_now")
    
    Returns:
        bool: آیا دسترسی دارد؟
    """
    # اگر کاربر لاگین نکرده یا معتبر نیست
    if not user_id:
        return False
    
    is_admin, admin_type, permissions = get_admin_info(user_id, admin_id)
    
    if not is_admin:
        return False
    
    # ادمین اصلی به همه چیز دسترسی دارد
    if admin_type == "main_admin":
        return True
    
    # دسترسی به پنل مدیریت برای همه ادمین‌ها
    if permission == "admin_panel":
        return True
    
    # دسترسی کامل
    if permissions == "all":
        return True
    
    # چک دسترسی خاص
    if permissions:
        return permission in permissions.split(',')
    
    return False

def add_admin(user_id, permissions="all"):
    """اضافه کردن ادمین فرعی با دسترسی‌های مشخص"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET is_admin = 1, 
            admin_permissions = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (permissions, user_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    if affected > 0:
        logger.info(f"👑 User {user_id} promoted to admin with permissions: {permissions}")
    else:
        logger.warning(f"⚠️ User {user_id} not found for admin promotion")
    
    return affected > 0

def remove_admin(user_id):
    """حذف ادمین فرعی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET is_admin = 0, 
            admin_permissions = "",
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (user_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    if affected > 0:
        logger.info(f"⬇️ User {user_id} demoted from admin")
    return affected > 0

def get_all_admins():
    """دریافت لیست همه ادمین‌های فرعی"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE is_admin = 1 ORDER BY user_id')
    admins = cursor.fetchall()
    conn.close()
    return admins


# ============ مدیریت بن ============

def ban_user(user_id):
    """بن کردن کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET is_banned = 1, 
            updated_at = CURRENT_TIMESTAMP 
        WHERE user_id = ?
    ''', (user_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    if affected > 0:
        logger.info(f"🚫 User {user_id} banned")
    return affected > 0

def unban_user(user_id):
    """آزادسازی کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET is_banned = 0, 
            updated_at = CURRENT_TIMESTAMP 
        WHERE user_id = ?
    ''', (user_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    if affected > 0:
        logger.info(f"✅ User {user_id} unbanned")
    return affected > 0

def get_banned_users():
    """دریافت لیست کاربران بن شده"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE is_banned = 1 ORDER BY user_id')
    users = cursor.fetchall()
    conn.close()
    return users

def is_user_banned(user_id):
    """بررسی بن بودن کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None and result['is_banned'] == 1


# ============ مدیریت غیرفعال‌سازی ============

def deactivate_user(user_id, reason="blocked_bot"):
    """
    غیرفعال کردن کاربر (مثلاً وقتی ربات رو بلاک کرده)
    
    Args:
        user_id: شناسه کاربر
        reason: دلیل غیرفعال‌سازی
    
    Returns:
        bool: موفقیت‌آمیز بودن
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET is_active = 0,
            deactivated_at = CURRENT_TIMESTAMP,
            deactivation_reason = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (reason, user_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    if affected > 0:
        logger.info(f"🚫 User {user_id} deactivated (reason: {reason})")
    return affected > 0

def reactivate_user(user_id):
    """فعال‌سازی مجدد کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET is_active = 1,
            deactivated_at = NULL,
            deactivation_reason = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (user_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    if affected > 0:
        logger.info(f"✅ User {user_id} reactivated")
    return affected > 0

def get_inactive_users():
    """دریافت کاربران غیرفعال"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE is_active = 0 ORDER BY deactivated_at DESC')
    users = cursor.fetchall()
    conn.close()
    return users


# ============ وضعیت ربات ============

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
    cursor.execute('''
        UPDATE bot_status 
        SET is_active = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE id = 1
    ''', (new_status,))
    conn.commit()
    conn.close()
    logger.info(f"🤖 Bot status changed to: {'ON' if new_status else 'OFF'}")
    return new_status

def is_bot_active():
    """بررسی فعال بودن ربات"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_active FROM bot_status WHERE id = 1')
    result = cursor.fetchone()
    conn.close()
    return result['is_active'] == 1 if result else True

def set_bot_status(is_active):
    """تنظیم وضعیت ربات"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE bot_status 
        SET is_active = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE id = 1
    ''', (1 if is_active else 0,))
    conn.commit()
    conn.close()


# ============ عملیات حذف ============

def delete_all_user_data():
    """حذف همه داده‌های کاربران (بجز ادمین اصلی)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # ادمین اصلی (user_id=1 یا مقدار از .env) رو نگه می‌داریم
    # cursor.execute("DELETE FROM users WHERE is_admin = 0 OR (is_admin = 1 AND admin_permissions != '')")
    cursor.execute('DELETE FROM users')
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    logger.info(f"🗑️ All user data deleted ({affected} users)")
    return affected

def delete_user(user_id):
    """حذف کامل یک کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    if affected > 0:
        logger.info(f"🗑️ User {user_id} deleted completely")
    return affected > 0


# ============ توابع کمکی ============

def search_users(query, limit=10):
    """
    جستجوی کاربران با نام، یوزرنیم یا شناسه
    
    Args:
        query: عبارت جستجو
        limit: حداکثر نتایج
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    search = f"%{query}%"
    
    cursor.execute('''
        SELECT * FROM users 
        WHERE user_id LIKE ? 
           OR username LIKE ? 
           OR first_name LIKE ? 
           OR last_name LIKE ?
        LIMIT ?
    ''', (search, search, search, search, limit))
    
    users = cursor.fetchall()
    conn.close()
    return users

def get_users_count_by_date(days=7):
    """تعداد کاربران ثبت‌نام شده در n روز اخیر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT date(created_at) as date, COUNT(*) as count 
        FROM users 
        WHERE created_at >= date('now', '-' || ? || ' days')
        GROUP BY date(created_at)
        ORDER BY date(created_at)
    ''', (days,))
    result = cursor.fetchall()
    conn.close()
    return result

def get_user_growth_stats():
    """آمار رشد کاربران"""
    stats = {
        'today': 0,
        'this_week': 0,
        'this_month': 0,
        'total': 0
    }
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE date(created_at) = date('now')")
    stats['today'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE created_at >= date('now', '-7 days')")
    stats['this_week'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE created_at >= date('now', '-30 days')")
    stats['this_month'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM users")
    stats['total'] = cursor.fetchone()['count']
    
    conn.close()
    return stats
