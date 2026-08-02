import jdatetime
from datetime import datetime
import pytz

TEHRAN_TZ = pytz.timezone('Asia/Tehran')

def get_persian_datetime():
    """گرفتن تاریخ و زمان فعلی به شمسی"""
    now = datetime.now(TEHRAN_TZ)
    persian_date = jdatetime.datetime.fromgregorian(datetime=now)
    return persian_date.strftime("%A %d %B %Y - %H:%M")

def get_persian_date():
    """فقط تاریخ شمسی"""
    now = datetime.now(TEHRAN_TZ)
    persian_date = jdatetime.datetime.fromgregorian(datetime=now)
    return persian_date.strftime("%Y/%m/%d")

def get_persian_time():
    """فقط ساعت شمسی"""
    now = datetime.now(TEHRAN_TZ)
    persian_date = jdatetime.datetime.fromgregorian(datetime=now)
    return persian_date.strftime("%H:%M")

def convert_to_server_time(hour, minute):
    """تبدیل ساعت تهران به ساعت سرور (برای زمان‌بندی)"""
    # تهران ۹ صبح = سرور ۵:۱۰ صبح (تفاوت ۳:۵۰ ساعت)
    total_minutes = (hour * 60 + minute) - (3 * 60 + 50)
    if total_minutes < 0:
        total_minutes += 24 * 60
    server_hour = total_minutes // 60
    server_minute = total_minutes % 60
    return server_hour, server_minute

def convert_to_tehran_time(hour, minute):
    """تبدیل ساعت سرور به ساعت تهران (برای نمایش به کاربر)"""
    total_minutes = (hour * 60 + minute) + (3 * 60 + 50)
    if total_minutes >= 24 * 60:
        total_minutes -= 24 * 60
    tehran_hour = total_minutes // 60
    tehran_minute = total_minutes % 60
    return tehran_hour, tehran_minute

def get_current_weekday():
    """گرفتن روز هفته فعلی (۰=شنبه)"""
    now = datetime.now(TEHRAN_TZ)
    # تبدیل دوشنبه (۰) به شنبه (۰)
    weekday = now.weekday()  # 0=دوشنبه
    return (weekday + 2) % 7  # 0=شنبه

def get_weekday_name(day_num):
    """گرفتن نام روز هفته به فارسی"""
    days = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه']
    return days[day_num]

def is_today_weekday(day_num):
    """بررسی اینکه آیا امروز روز مشخصی از هفته است یا خیر"""
    return get_current_weekday() == day_num

def format_datetime_for_display(year, month, day, hour, minute):
    """فرمت کردن تاریخ و زمان برای نمایش"""
    return f"{year}/{month:02d}/{day:02d} {hour:02d}:{minute:02d}"
