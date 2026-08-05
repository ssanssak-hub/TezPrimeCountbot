from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# دکمه‌های قابل تنظیم برای ادمین فرعی
PERMISSION_BUTTONS = [
    ("📋 پیام‌های همگانی", "perm_broadcasts_list"),
    ("🚫 مدیریت کاربران", "perm_manage_users"),
    ("🔍 جستجوی کاربر", "perm_search_user"),
    ("📊 آمار و گزارشات", "perm_stats"),
    ("⚙️ وضعیت ربات", "perm_bot_status"),
    ("👥 مدیریت ادمین‌ها", "perm_manage_admins"),
    ("📢 ارسال پیام همگانی فوری", "perm_broadcast_now"),
    ("⏰ پیام همگانی زمان‌بندی", "perm_broadcast_scheduled"),
]

def get_permission_name(perm_code):
    """دریافت نام فارسی دسترسی"""
    for name, code in PERMISSION_BUTTONS:
        if code == perm_code:
            return name
    return perm_code

def admin_panel_keyboard(user_id=None, admin_id=None):
    """منوی پنل مدیریت - بر اساس دسترسی ادمین"""
    from database import check_admin_permission
    
    keyboard = []
    
    if user_id and admin_id:
        if check_admin_permission(user_id, admin_id, "admin_broadcast_now"):
            keyboard.append([InlineKeyboardButton("📢 ارسال پیام همگانی فوری", callback_data="admin_broadcast_now")])
        if check_admin_permission(user_id, admin_id, "admin_broadcast_scheduled"):
            keyboard.append([InlineKeyboardButton("⏰ پیام همگانی زمان‌بندی شده", callback_data="admin_broadcast_scheduled")])
        if check_admin_permission(user_id, admin_id, "broadcasts_list"):
            keyboard.append([InlineKeyboardButton("📋 پیام‌های همگانی", callback_data="admin_broadcasts_list")])
        if check_admin_permission(user_id, admin_id, "manage_admins"):
            keyboard.append([InlineKeyboardButton("👥 مدیریت ادمین‌ها", callback_data="admin_manage_admins")])
        if check_admin_permission(user_id, admin_id, "manage_users"):
            keyboard.append([InlineKeyboardButton("🚫 مدیریت کاربران", callback_data="admin_manage_users")])
        if check_admin_permission(user_id, admin_id, "search_user"):
            keyboard.append([InlineKeyboardButton("🔍 جستجوی کاربر", callback_data="admin_search_user")])
        if check_admin_permission(user_id, admin_id, "stats"):
            keyboard.append([InlineKeyboardButton("📊 آمار و گزارشات", callback_data="admin_stats")])
        if check_admin_permission(user_id, admin_id, "bot_status"):
            keyboard.append([InlineKeyboardButton("⚙️ وضعیت ربات", callback_data="admin_bot_status")])
    else:
        # حالت پیش‌فرض - همه دکمه‌ها
        keyboard = [
            [InlineKeyboardButton("📢 ارسال پیام همگانی فوری", callback_data="admin_broadcast_now")],
            [InlineKeyboardButton("⏰ پیام همگانی زمان‌بندی شده", callback_data="admin_broadcast_scheduled")],
            [InlineKeyboardButton("📋 پیام‌های همگانی", callback_data="admin_broadcasts_list")],
            [InlineKeyboardButton("👥 مدیریت ادمین‌ها", callback_data="admin_manage_admins")],
            [InlineKeyboardButton("🚫 مدیریت کاربران", callback_data="admin_manage_users")],
            [InlineKeyboardButton("🔍 جستجوی کاربر", callback_data="admin_search_user")],
            [InlineKeyboardButton("📊 آمار و گزارشات", callback_data="admin_stats")],
            [InlineKeyboardButton("⚙️ وضعیت ربات", callback_data="admin_bot_status")],
        ]
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به منو اصلی", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)


def permissions_selection_keyboard(selected_permissions):
    """کیبورد انتخاب دسترسی‌ها (شیشه‌ای/toggle)"""
    keyboard = []
    
    for name, code in PERMISSION_BUTTONS:
        emoji = "✅" if code in selected_permissions else "❌"
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {name}",
            callback_data=f"perm_toggle_{code}"
        )])
    
    # ردیف دکمه‌های کنترلی
    keyboard.append([
        InlineKeyboardButton("✅ دسترسی به همه", callback_data="perm_all"),
        InlineKeyboardButton("❌ حذف همه", callback_data="perm_none")
    ])
    keyboard.append([InlineKeyboardButton("✅ ادامه", callback_data="perm_done")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_manage_admins")])
    
    return InlineKeyboardMarkup(keyboard)


def admin_confirm_add_keyboard():
    """کیبورد تأیید نهایی افزودن ادمین"""
    keyboard = [
        [InlineKeyboardButton("✅ تأیید و افزودن", callback_data="admin_confirm_add")],
        [InlineKeyboardButton("❌ لغو", callback_data="admin_cancel_add")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="perm_back")],
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
    
    keyboard = [
        [InlineKeyboardButton(status_text, callback_data="admin_toggle_bot")],
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
