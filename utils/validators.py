import re
from datetime import datetime
import pytz

TEHRAN_TZ = pytz.timezone('Asia/Tehran')

def is_valid_time(hour, minute):
    """بررسی اعتبار ساعت و دقیقه"""
    try:
        hour = int(hour)
        minute = int(minute)
        return 0 <= hour <= 23 and 0 <= minute <= 59
    except (ValueError, TypeError):
        return False

def is_valid_phone(phone):
    """بررسی اعتبار شماره تلفن ایرانی"""
    # الگوی شماره موبایل: ۰۹۱۲۳۴۵۶۷۸۹
    pattern = r'^09\d{9}$'
    return bool(re.match(pattern, phone))

def is_valid_email(email):
    """بررسی اعتبار ایمیل"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def is_valid_weekday(day_num):
    """بررسی اعتبار شماره روز هفته (۰ تا ۶)"""
    try:
        day = int(day_num)
        return 0 <= day <= 6
    except (ValueError, TypeError):
        return False

def is_future_time(hour, minute):
    """بررسی اینکه زمان انتخابی در آینده است یا نه"""
    now = datetime.now(TEHRAN_TZ)
    current_hour = now.hour
    current_minute = now.minute
    
    if hour > current_hour:
        return True
    elif hour == current_hour and minute > current_minute:
        return True
    return False

def sanitize_text(text):
    """پاکسازی متن ورودی (حذف کاراکترهای خطرناک)"""
    # حذف کاراکترهای خاص
    text = re.sub(r'[<>{}()\[\]]', '', text)
    # محدود کردن طول
    if len(text) > 1000:
        text = text[:1000]
    return text.strip()

def validate_reminder_message(message):
    """اعتبارسنجی پیام یادآوری"""
    if not message or len(message.strip()) == 0:
        return False, "پیام نمی‌تواند خالی باشد"
    
    message = message.strip()
    
    if len(message) > 1000:
        return False, "پیام طولانی‌تر از ۱۰۰۰ کاراکتر است"
    
    # بررسی کاراکترهای ممنوعه
    if any(char in message for char in ['<', '>', '{', '}']):
        return False, "پیام حاوی کاراکترهای ممنوعه است"
    
    return True, message

def is_admin(user_id, admin_id):
    """بررسی اینکه کاربر ادمین است یا خیر"""
    return str(user_id) == str(admin_id)
