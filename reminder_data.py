import json
import os
from datetime import datetime, timedelta
import pytz
import jdatetime
from exam_data import EXAMS, jalali_to_gregorian

# فایل ذخیره‌سازی یادآوری‌ها
REMINDERS_FILE = "reminders.json"

def load_reminders():
    """بارگذاری یادآوری‌ها از فایل"""
    if os.path.exists(REMINDERS_FILE):
        with open(REMINDERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_reminders(reminders):
    """ذخیره یادآوری‌ها در فایل"""
    with open(REMINDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(reminders, f, ensure_ascii=False, indent=2)

def add_reminder(user_id, reminder_type, title, jalali_date, time, exam_name=None):
    """
    افزودن یادآوری جدید
    user_id: شناسه کاربر
    reminder_type: 'exam' یا 'personal'
    title: عنوان یادآوری
    jalali_date: تاریخ شمسی به صورت '1404/01/15'
    time: زمان به صورت '14:30'
    exam_name: نام کنکور (فقط برای نوع exam)
    """
    reminders = load_reminders()
    user_id = str(user_id)
    
    if user_id not in reminders:
        reminders[user_id] = []
    
    # تبدیل تاریخ شمسی به میلادی برای ذخیره
    gregorian_date = jalali_to_gregorian(jalali_date)
    
    # ایجاد شناسه یکتا برای یادآوری
    reminder_id = f"{user_id}_{len(reminders[user_id])}_{int(datetime.now().timestamp())}"
    
    reminder = {
        "id": reminder_id,
        "type": reminder_type,
        "title": title,
        "jalali_date": jalali_date,
        "time": time,
        "exam_name": exam_name,
        "is_active": True,
        "created_at": datetime.now().isoformat()
    }
    
    reminders[user_id].append(reminder)
    save_reminders(reminders)
    return reminder_id

def get_user_reminders(user_id):
    """دریافت لیست یادآوری‌های یک کاربر"""
    reminders = load_reminders()
    user_id = str(user_id)
    return reminders.get(user_id, [])

def get_active_reminders(user_id):
    """دریافت یادآوری‌های فعال یک کاربر"""
    all_reminders = get_user_reminders(user_id)
    return [r for r in all_reminders if r.get("is_active", True)]

def delete_reminder(user_id, reminder_id):
    """حذف یک یادآوری"""
    reminders = load_reminders()
    user_id = str(user_id)
    
    if user_id in reminders:
        reminders[user_id] = [r for r in reminders[user_id] if r["id"] != reminder_id]
        save_reminders(reminders)
        return True
    return False

def toggle_reminder(user_id, reminder_id):
    """فعال/غیرفعال کردن یک یادآوری"""
    reminders = load_reminders()
    user_id = str(user_id)
    
    if user_id in reminders:
        for r in reminders[user_id]:
            if r["id"] == reminder_id:
                r["is_active"] = not r.get("is_active", True)
                save_reminders(reminders)
                return True
    return False

def get_reminder_by_id(user_id, reminder_id):
    """دریافت یک یادآوری با شناسه"""
    reminders = load_reminders()
    user_id = str(user_id)
    
    if user_id in reminders:
        for r in reminders[user_id]:
            if r["id"] == reminder_id:
                return r
    return None

def get_due_reminders():
    """دریافت یادآوری‌هایی که زمانشان رسیده"""
    reminders = load_reminders()
    due_reminders = []
    now = datetime.now(pytz.timezone('Asia/Tehran'))
    
    for user_id, user_reminders in reminders.items():
        for r in user_reminders:
            try:
                if not r.get("is_active", True):
                    continue
                
                # بررسی تاریخ
                gregorian_date = jalali_to_gregorian(r["jalali_date"])
                hour, minute = map(int, r["time"].split(':'))
                
                reminder_datetime = datetime(
                    gregorian_date.year,
                    gregorian_date.month,
                    gregorian_date.day,
                    hour,
                    minute,
                    0,
                    tzinfo=pytz.timezone('Asia/Tehran')
                )
                
                # اگر زمان یادآوری رسیده باشد
                if now >= reminder_datetime:
                    due_reminders.append({
                        "user_id": int(user_id),
                        "reminder": r,
                        "datetime": reminder_datetime
                    })
            except Exception as e:
                logger.warning(f"⚠️ Error processing reminder {r.get('id', 'unknown')}: {e}")
                continue
    
    return due_reminders
