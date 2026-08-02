import logging
import os
from datetime import datetime
import pytz

TEHRAN_TZ = pytz.timezone('Asia/Tehran')

def setup_logger(name, log_file=None, level=logging.INFO):
    """تنظیم لاگر با فرمت فارسی"""
    
    # ایجاد پوشه لاگ اگر وجود نداشت
    if log_file and not os.path.exists('logs'):
        os.makedirs('logs')
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # فرمت با زمان تهران
    class TehranTimeFormatter(logging.Formatter):
        def formatTime(self, record, datefmt=None):
            dt = datetime.fromtimestamp(record.created, TEHRAN_TZ)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
    
    formatter = TehranTimeFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # هندلر کنسول
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # هندلر فایل (اختیاری)
    if log_file:
        file_handler = logging.FileHandler(f'logs/{log_file}')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

# لاگر پیش‌فرض
default_logger = setup_logger('TezPrimeBot')
