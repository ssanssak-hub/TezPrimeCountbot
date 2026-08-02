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

def time_keyboard():
    keyboard = []
    
    # ساعت‌ها ۰ تا ۲۳
    hour_row = []
    for h in range(0, 24):
        hour_row.append(InlineKeyboardButton(str(h), callback_data=f"time_h_{h}"))
        if len(hour_row) == 6:
            keyboard.append(hour_row)
            hour_row = []
    if hour_row:
        keyboard.append(hour_row)
    
    # دقیقه‌ها ۰ تا ۵۹ (با گام ۵)
    minute_row = []
    for m in range(0, 60, 5):
        minute_row.append(InlineKeyboardButton(str(m), callback_data=f"time_m_{m}"))
        if len(minute_row) == 6:
            keyboard.append(minute_row)
            minute_row = []
    if minute_row:
        keyboard.append(minute_row)
    
    keyboard.append([InlineKeyboardButton("✅ تایید زمان", callback_data="time_done")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(keyboard)

def reminders_list_keyboard(reminders):
    keyboard = []
    
    for reminder in reminders:
        text = f"📌 {reminder['message'][:20]}..."
        callback = f"view_{reminder['id']}"
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
