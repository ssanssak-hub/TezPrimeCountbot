from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔔 اعلان‌ها", callback_data="notifications")]
    ]
    return InlineKeyboardMarkup(keyboard)

def reminder_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("⚙️ تنظیم اعلان شخصی", callback_data="set_reminder")],
        [InlineKeyboardButton("📋 مشاهده اعلان‌ها", callback_data="view_reminders")],
        [InlineKeyboardButton("🗑️ حذف اعلان", callback_data="delete_reminder")],
        [InlineKeyboardButton("⛔ لغو اعلان", callback_data="cancel_reminder")],
        [InlineKeyboardButton("🔙 بازگشت به منو اصلی", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def days_keyboard(selected_days=None):
    if selected_days is None:
        selected_days = []
    
    days = [
        ("شنبه", 0), ("یکشنبه", 1), ("دوشنبه", 2),
        ("سه‌شنبه", 3), ("چهارشنبه", 4), ("پنجشنبه", 5),
        ("جمعه", 6)
    ]
    
    keyboard = []
    row = []
    for day_name, day_num in days:
        text = f"✅ {day_name}" if day_num in selected_days else day_name
        callback = f"days_{day_num}"
        row.append(InlineKeyboardButton(text, callback_data=callback))
        
        if len(row) == 3:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("✅ ادامه", callback_data="days_done")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(keyboard)

def time_keyboard(selected_hour=None, selected_minute=None, page=0):
    """
    کیبورد انتخاب زمان با تفکیک ساعت و دقیقه
    page: 0 = انتخاب ساعت, 1 = انتخاب دقیقه
    """
    keyboard = []
    
    if page == 0:
        # 📌 بخش انتخاب ساعت
        keyboard.append([InlineKeyboardButton("🕐 انتخاب ساعت (کلیک کنید) 🕐", callback_data="noop")])
        
        # ۲۴ ساعت در ۴ ردیف ۶ تایی
        hour_rows = []
        for h in range(24):
            text = f"✅ {h:02d}" if selected_hour == h else f"{h:02d}"
            callback = f"time_h_{h}"
            hour_rows.append(InlineKeyboardButton(text, callback_data=callback))
        
        # تقسیم به ردیف‌های ۶ تایی
        for i in range(0, 24, 6):
            keyboard.append(hour_rows[i:i+6])
        
        # دکمه رفتن به انتخاب دقیقه
        if selected_hour is not None:
            keyboard.append([InlineKeyboardButton("⏬ برو به انتخاب دقیقه ⏬", callback_data="time_page_1")])
        else:
            keyboard.append([InlineKeyboardButton("⚠️ اول یک ساعت انتخاب کن", callback_data="noop")])
    
    elif page == 1:
        # 📌 بخش انتخاب دقیقه
        keyboard.append([InlineKeyboardButton("🕐 انتخاب دقیقه (کلیک کنید) 🕐", callback_data="noop")])
        
        # ۶۰ دقیقه در ۶ ردیف ۱۰ تایی
        minute_rows = []
        for m in range(60):
            text = f"✅ {m:02d}" if selected_minute == m else f"{m:02d}"
            callback = f"time_m_{m}"
            minute_rows.append(InlineKeyboardButton(text, callback_data=callback))
        
        # تقسیم به ردیف‌های ۶ تایی (۱۰ ردیف)
        for i in range(0, 60, 6):
            keyboard.append(minute_rows[i:i+6])
        
        # دکمه بازگشت به انتخاب ساعت
        keyboard.append([InlineKeyboardButton("🔼 بازگشت به انتخاب ساعت", callback_data="time_page_0")])
    
    # نمایش وضعیت انتخاب شده
    status_text = ""
    if selected_hour is not None:
        status_text += f"ساعت: {selected_hour:02d}"
    else:
        status_text += "ساعت: انتخاب نشده"
    
    if selected_minute is not None:
        status_text += f" | دقیقه: {selected_minute:02d}"
    else:
        status_text += " | دقیقه: انتخاب نشده"
    
    keyboard.append([InlineKeyboardButton(f"📌 {status_text}", callback_data="noop")])
    
    # دکمه تایید نهایی (فقط وقتی هر دو انتخاب شدن)
    if selected_hour is not None and selected_minute is not None:
        keyboard.append([InlineKeyboardButton("✅ ثبت نهایی زمان", callback_data="time_done")])
    else:
        keyboard.append([InlineKeyboardButton("⚠️ باید ساعت و دقیقه را انتخاب کنید", callback_data="noop")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(keyboard)

def reminders_list_keyboard(reminders):
    keyboard = []
    
    for reminder in reminders:
        if isinstance(reminder, dict):
            reminder_id = reminder['id']
            message = reminder['message']
        else:
            reminder_id = reminder['id']
            message = reminder['message']
        
        text = f"📌 {message[:20]}..."
        callback = f"view_{reminder_id}"
        keyboard.append([InlineKeyboardButton(text, callback_data=callback)])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_notifications")])
    
    return InlineKeyboardMarkup(keyboard)

def reminder_action_keyboard(reminder_id):
    keyboard = [
        [InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_{reminder_id}")],
        [InlineKeyboardButton("⛔ لغو", callback_data=f"cancel_{reminder_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_notifications")]
    ]
    return InlineKeyboardMarkup(keyboard)
