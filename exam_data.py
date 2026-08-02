from datetime import datetime, timedelta
import pytz
import jdatetime

# اطلاعات کنکورها
EXAMS = {
    "کنکور تجربی": {
        "date": "1406/04/11",  # ۱۱ تیر ۱۴۰۶
        "time": "08:00",
        "title": "کنکور تجربی"
    },
    "کنکور هنر و زبان": {
        "date": "1406/04/11",  # ۱۱ تیر ۱۴۰۶
        "time": "14:30",
        "title": "کنکور هنر و زبان"
    },
    "کنکور ریاضی و فنی": {
        "date": "1406/04/10",  # ۱۰ تیر ۱۴۰۶
        "time": "08:00",
        "title": "کنکور ریاضی و فنی"
    },
    "کنکور علوم انسانی": {
        "date": "1406/04/10",  # ۱۰ تیر ۱۴۰۶
        "time": "08:00",
        "title": "کنکور علوم انسانی"
    },
    "کنکور فرهنگیان": {
        "date": "1406/04/12",  # ۱۲ تیر ۱۴۰۶ (فرضی)
        "time": "08:00",
        "title": "کنکور فرهنگیان"
    }
}

def jalali_to_gregorian(jalali_date):
    """تبدیل تاریخ شمسی به میلادی"""
    year, month, day = map(int, jalali_date.split('/'))
    gregorian_date = jdatetime.date(year, month, day).togregorian()
    return gregorian_date

def get_exam_datetime(exam_key):
    """دریافت تاریخ و زمان میلادی کنکور"""
    exam = EXAMS.get(exam_key)
    if not exam:
        return None
    
    # تبدیل تاریخ شمسی به میلادی
    gregorian_date = jalali_to_gregorian(exam["date"])
    
    # تنظیم زمان
    hour, minute = map(int, exam["time"].split(':'))
    exam_datetime = datetime(
        gregorian_date.year,
        gregorian_date.month,
        gregorian_date.day,
        hour,
        minute,
        0,
        tzinfo=pytz.timezone('Asia/Tehran')
    )
    
    return exam_datetime

def calculate_time_remaining(exam_key):
    """محاسبه زمان باقی‌مانده تا کنکور"""
    exam_datetime = get_exam_datetime(exam_key)
    if not exam_datetime:
        return None
    
    now = datetime.now(pytz.timezone('Asia/Tehran'))
    time_left = exam_datetime - now
    
    if time_left.total_seconds() < 0:
        return {
            "weeks": 0,
            "days": 0,
            "hours": 0,
            "minutes": 0,
            "seconds": 0,
            "passed": True
        }
    
    # محاسبه هفته‌ها، روزها، ساعت‌ها، دقیقه‌ها و ثانیه‌ها
    total_seconds = int(time_left.total_seconds())
    
    weeks = total_seconds // (7 * 24 * 3600)
    remaining = total_seconds % (7 * 24 * 3600)
    
    days = remaining // (24 * 3600)
    remaining %= (24 * 3600)
    
    hours = remaining // 3600
    remaining %= 3600
    
    minutes = remaining // 60
    seconds = remaining % 60
    
    return {
        "weeks": weeks,
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
        "passed": False,
        "total_seconds": total_seconds
    }

def get_exam_info(exam_key):
    """دریافت اطلاعات کامل کنکور"""
    exam = EXAMS.get(exam_key)
    if not exam:
        return None
    
    time_left = calculate_time_remaining(exam_key)
    
    return {
        "title": exam["title"],
        "date": exam["date"],
        "time": exam["time"],
        "time_left": time_left
    }
