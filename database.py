-- دیتابیس اصلی (root/database.py)
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- دیتابیس اعلان‌ها (reminders/reminder_database.py)
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    message TEXT,
    days_of_week TEXT,  -- مثلاً "1,3,5" برای شنبه، دوشنبه، چهارشنبه
    hour INTEGER,
    minute INTEGER,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
