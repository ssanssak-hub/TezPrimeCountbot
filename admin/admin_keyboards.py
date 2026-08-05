from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def admin_panel_keyboard():
    """منوی اصلی پنل مدیریت"""
    keyboard = [
        [InlineKeyboardButton("📢 ارسال پیام همگانی فوری", callback_data="admin_broadcast_now")],
        [InlineKeyboardButton("⏰ پیام همگانی زمان‌بندی شده", callback_data="admin_broadcast_scheduled")],
        [InlineKeyboardButton("📋 پیام‌های همگانی", callback_data="admin_broadcasts_list")],
        [InlineKeyboardButton("👥 مدیریت ادمین‌ها", callback_data="admin_manage_admins")],
        [InlineKeyboardButton("🚫 مدیریت کاربران", callback_data="admin_manage_users")],
        [InlineKeyboardButton("🔍 جستجوی کاربر", callback_data="admin_search_user")],
        [InlineKeyboardButton("📊 آمار و گزارشات", callback_data="admin_stats")],
        [InlineKeyboardButton("⚙️ وضعیت ربات", callback_data="admin_bot_status")],
        [InlineKeyboardButton("🔙 بازگشت به منو اصلی", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_manage_admins_keyboard():
    """کیبورد مدیریت ادمین‌ها"""
    keyboard = [
        [InlineKeyboardButton("➕ افزودن ادمین", callback_data="admin_add_admin")],
        [InlineKeyboardButton("➖ حذف ادمین", callback_data="admin_remove_admin")],
        [InlineKeyboardButton("📋 لیست ادمین‌ها", callback_data="admin_list_admins")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_manage_users_keyboard():
    """کیبورد مدیریت کاربران"""
    keyboard = [
        [InlineKeyboardButton("🔨 بن کاربر", callback_data="admin_ban_user")],
        [InlineKeyboardButton("🔓 آزادسازی کاربر", callback_data="admin_unban_user")],
        [InlineKeyboardButton("📋 لیست بن شده‌ها", callback_data="admin_banned_list")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_bot_status_keyboard(is_active):
    """کیبورد وضعیت ربات"""
    status_text = "🔴 خاموش کردن ربات" if is_active else "🟢 روشن کردن ربات"
    status_callback = "admin_toggle_bot" if is_active else "admin_toggle_bot"
    
    keyboard = [
        [InlineKeyboardButton(status_text, callback_data=status_callback)],
        [InlineKeyboardButton("🗑️ حذف همه داده‌های کاربران", callback_data="admin_delete_all_data")],
        [InlineKeyboardButton("📈 وضعیت سرور", callback_data="admin_server_status")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_broadcasts_list_keyboard(broadcasts):
    """کیبورد لیست پیام‌های همگانی"""
    keyboard = []
    
    for b in broadcasts:
        status = "✅" if b['is_sent'] else "⛔" if b['is_cancelled'] else "⏳"
        text = f"{status} {b['title'][:30]}..."
        keyboard.append([InlineKeyboardButton(text, callback_data=f"admin_broadcast_{b['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def broadcast_action_keyboard(broadcast_id, is_sent, is_cancelled):
    """کیبورد عملیات پیام همگانی"""
    keyboard = []
    
    if not is_sent and not is_cancelled:
        keyboard.append([InlineKeyboardButton("⛔ لغو ارسال", callback_data=f"admin_cancel_broadcast_{broadcast_id}")])
    keyboard.append([InlineKeyboardButton("🗑️ حذف", callback_data=f"admin_delete_broadcast_{broadcast_id}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_broadcasts_list")])
    
    return InlineKeyboardMarkup(keyboard)

def back_to_admin_keyboard():
    """دکمه بازگشت به پنل"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_panel")
    ]])
