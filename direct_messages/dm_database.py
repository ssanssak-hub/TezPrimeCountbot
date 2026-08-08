import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = 'tezprime.db'


def get_db_connection():
    """ایجاد اتصال به دیتابیس"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_dm_db():
    """ایجاد جداول پیام‌های مستقیم"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # جدول پیام‌های ادمین به کاربر
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            title TEXT,
            message TEXT,
            content_type TEXT DEFAULT 'text',
            file_id TEXT,
            file_caption TEXT,
            inline_buttons TEXT,
            from_chat_id TEXT,
            from_message_id INTEGER,
            is_read BOOLEAN DEFAULT 0,
            is_deleted BOOLEAN DEFAULT 0,
            read_at TIMESTAMP,
            admin_notif_msg_id INTEGER,
            user_notif_msg_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # جدول پیام‌های کاربر به ادمین
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            admin_id INTEGER NOT NULL,
            title TEXT,
            message TEXT,
            content_type TEXT DEFAULT 'text',
            file_id TEXT,
            file_caption TEXT,
            inline_buttons TEXT,
            from_chat_id TEXT,
            from_message_id INTEGER,
            status TEXT DEFAULT 'pending',
            admin_action TEXT,
            action_at TIMESTAMP,
            admin_notif_msg_id INTEGER,
            user_notif_msg_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ایندکس‌ها
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_admin_msg_user ON admin_messages(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_admin_msg_admin ON admin_messages(admin_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_msg_admin ON user_messages(admin_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_msg_user ON user_messages(user_id)')

    conn.commit()
    conn.close()
    logger.info("✅ DM database initialized")


# ============ admin_messages ============

def save_admin_message(admin_id, user_id, title, content_type='text',
                       message=None, file_id=None, file_caption=None,
                       inline_buttons=None, from_chat_id=None, from_message_id=None):
    """ذخیره پیام ادمین به کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()

    import json
    buttons_json = json.dumps(inline_buttons, ensure_ascii=False) if inline_buttons else None

    cursor.execute('''
        INSERT INTO admin_messages (
            admin_id, user_id, title, content_type, message,
            file_id, file_caption, inline_buttons,
            from_chat_id, from_message_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (admin_id, user_id, title, content_type, message,
          file_id, file_caption, buttons_json,
          from_chat_id, from_message_id))

    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"📨 Admin message {msg_id}: admin={admin_id} → user={user_id}")
    return msg_id


def get_admin_messages_for_user(user_id, include_deleted=False):
    """دریافت پیام‌های ارسال شده به یک کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = 'SELECT * FROM admin_messages WHERE user_id = ?'
    if not include_deleted:
        query += ' AND is_deleted = 0'
    query += ' ORDER BY created_at DESC'

    cursor.execute(query, (user_id,))
    messages = cursor.fetchall()
    conn.close()
    return [dict(m) for m in messages]


def get_admin_message_by_id(msg_id):
    """دریافت یک پیام ادمین با شناسه"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM admin_messages WHERE id = ?', (msg_id,))
    msg = cursor.fetchone()
    conn.close()
    return dict(msg) if msg else None


def mark_admin_message_read(msg_id):
    """علامت‌گذاری پیام به عنوان خوانده شده"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE admin_messages
        SET is_read = 1, read_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (msg_id,))
    conn.commit()
    conn.close()


def mark_admin_message_deleted(msg_id):
    """علامت‌گذاری پیام به عنوان حذف شده"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE admin_messages SET is_deleted = 1 WHERE id = ?', (msg_id,))
    conn.commit()
    conn.close()


def get_all_admin_messages(limit=50, offset=0):
    """دریافت همه پیام‌های ادمین (برای پنل)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM admin_messages
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    ''', (limit, offset))
    messages = cursor.fetchall()
    conn.close()
    return [dict(m) for m in messages]


# ============ user_messages ============

def save_user_message(user_id, admin_id, title, content_type='text',
                      message=None, file_id=None, file_caption=None,
                      inline_buttons=None, from_chat_id=None, from_message_id=None):
    """ذخیره پیام کاربر به ادمین"""
    conn = get_db_connection()
    cursor = conn.cursor()

    import json
    buttons_json = json.dumps(inline_buttons, ensure_ascii=False) if inline_buttons else None

    cursor.execute('''
        INSERT INTO user_messages (
            user_id, admin_id, title, content_type, message,
            file_id, file_caption, inline_buttons,
            from_chat_id, from_message_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, admin_id, title, content_type, message,
          file_id, file_caption, buttons_json,
          from_chat_id, from_message_id))

    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"📨 User message {msg_id}: user={user_id} → admin={admin_id}")
    return msg_id


def get_user_messages_for_admin(admin_id, status=None):
    """دریافت پیام‌های ارسال شده به یک ادمین"""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = 'SELECT * FROM user_messages WHERE admin_id = ?'
    params = [admin_id]

    if status:
        query += ' AND status = ?'
        params.append(status)

    query += ' ORDER BY created_at DESC'

    cursor.execute(query, params)
    messages = cursor.fetchall()
    conn.close()
    return [dict(m) for m in messages]


def get_user_message_by_id(msg_id):
    """دریافت یک پیام کاربر با شناسه"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM user_messages WHERE id = ?', (msg_id,))
    msg = cursor.fetchone()
    conn.close()
    return dict(msg) if msg else None


def update_user_message_status(msg_id, status, admin_action=None):
    """بروزرسانی وضعیت پیام کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE user_messages
        SET status = ?, admin_action = ?, action_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (status, admin_action, msg_id))
    conn.commit()
    conn.close()
    logger.info(f"📝 User message {msg_id} status: {status}, action: {admin_action}")


def get_user_messages_from_user(user_id):
    """دریافت پیام‌های ارسال شده توسط یک کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM user_messages
        WHERE user_id = ?
        ORDER BY created_at DESC
    ''', (user_id,))
    messages = cursor.fetchall()
    conn.close()
    return [dict(m) for m in messages]


def delete_user_message(msg_id):
    """حذف پیام کاربر"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM user_messages WHERE id = ?', (msg_id,))
    conn.commit()
    conn.close()


def get_unread_user_messages_count(admin_id):
    """تعداد پیام‌های خوانده نشده برای یک ادمین"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) as count FROM user_messages
        WHERE admin_id = ? AND status = 'pending'
    ''', (admin_id,))
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0


def save_notif_msg_id(table, msg_id, field, notif_msg_id):
    """ذخیره message_id پیام نوتیفیکیشن"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f'''
        UPDATE {table}
        SET {field} = ?
        WHERE id = ?
    ''', (notif_msg_id, msg_id))
    conn.commit()
    conn.close()
