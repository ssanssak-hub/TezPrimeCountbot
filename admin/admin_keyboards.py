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
    ("✏️ ویرایش دسترسی ادمین", "perm_edit_permissions"),
    ("📋 لیست ادمین‌ها", "perm_list_admins"),
    ("🗑️ حذف همه داده‌ها", "perm_delete_all"),
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
        # ادمین اصلی همه دسترسی‌ها رو داره
        is_main_admin = (user_id == admin_id)
        
        if is_main_admin or check_admin_permission(user_id, admin_id, "perm_broadcast_now"):
            keyboard.append([InlineKeyboardButton("📢 ارسال پیام همگانی فوری", callback_data="admin_broadcast_now")])
        
        if is_main_admin or check_admin_permission(user_id, admin_id, "perm_broadcast_scheduled"):
            keyboard.append([InlineKeyboardButton("⏰ پیام همگانی زمان‌بندی شده", callback_data="admin_broadcast_scheduled")])
        
        if is_main_admin or check_admin_permission(user_id, admin_id, "perm_broadcasts_list"):
            keyboard.append([InlineKeyboardButton("📋 پیام‌های همگانی", callback_data="admin_broadcasts_list")])
        
        # جداکننده
        if keyboard:
            keyboard.append([InlineKeyboardButton("➖➖➖➖➖➖➖➖", callback_data="admin_noop")])
        
        if is_main_admin or check_admin_permission(user_id, admin_id, "perm_manage_admins"):
            keyboard.append([InlineKeyboardButton("👥 مدیریت ادمین‌ها", callback_data="admin_manage_admins")])
        
        if is_main_admin or check_admin_permission(user_id, admin_id, "perm_manage_users"):
            keyboard.append([InlineKeyboardButton("🚫 مدیریت کاربران", callback_data="admin_manage_users")])
        
        if is_main_admin or check_admin_permission(user_id, admin_id, "perm_search_user"):
            keyboard.append([InlineKeyboardButton("🔍 جستجوی کاربر", callback_data="admin_search_user")])
        
        if is_main_admin or check_admin_permission(user_id, admin_id, "perm_stats"):
            keyboard.append([InlineKeyboardButton("📊 آمار و گزارشات", callback_data="admin_stats")])
        
        if is_main_admin or check_admin_permission(user_id, admin_id, "perm_bot_status"):
            keyboard.append([InlineKeyboardButton("⚙️ وضعیت ربات", callback_data="admin_bot_status")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به منو اصلی", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def permissions_selection_keyboard(selected_permissions, is_edit=False):
    """کیبورد انتخاب دسترسی‌ها (شیشه‌ای/toggle)"""
    keyboard = []
    
    # فقط دسترسی‌های قابل واگذاری رو نشون بده
    delegatable_permissions = [
        ("📋 پیام‌های همگانی", "perm_broadcasts_list"),
        ("🚫 مدیریت کاربران", "perm_manage_users"),
        ("🔍 جستجوی کاربر", "perm_search_user"),
        ("📊 آمار و گزارشات", "perm_stats"),
        ("⚙️ وضعیت ربات", "perm_bot_status"),
        ("📢 ارسال پیام همگانی فوری", "perm_broadcast_now"),
        ("⏰ پیام همگانی زمان‌بندی", "perm_broadcast_scheduled"),
    ]
    
    for name, code in delegatable_permissions:
        emoji = "✅" if code in selected_permissions else "❌"
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {name}",
            callback_data=f"perm_toggle_{code}"
        )])
    
    # ردیف انتخاب همه/هیچ
    keyboard.append([
        InlineKeyboardButton("✅ انتخاب همه", callback_data="perm_all"),
        InlineKeyboardButton("❌ حذف همه", callback_data="perm_none")
    ])
    
    # دکمه تایید
    if is_edit:
        keyboard.append([InlineKeyboardButton("💾 ذخیره تغییرات", callback_data="admin_save_permissions")])
    else:
        keyboard.append([InlineKeyboardButton("✅ ادامه", callback_data="perm_done")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_manage_admins")])
    
    return InlineKeyboardMarkup(keyboard)

def admin_confirm_add_keyboard():
    """کیبورد تأیید نهایی افزودن ادمین"""
    keyboard = [
        [InlineKeyboardButton("✅ تأیید و افزودن", callback_data="admin_confirm_add")],
        [InlineKeyboardButton("✏️ ویرایش دسترسی‌ها", callback_data="perm_done")],
        [InlineKeyboardButton("❌ لغو", callback_data="admin_cancel_add")],
        [InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_panel")],
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_manage_admins_keyboard():
    """کیبورد مدیریت ادمین‌ها"""
    keyboard = [
        [InlineKeyboardButton("➕ افزودن ادمین", callback_data="admin_add_admin")],
        [InlineKeyboardButton("➖ حذف ادمین", callback_data="admin_remove_admin")],
        [InlineKeyboardButton("✏️ ویرایش دسترسی ادمین", callback_data="admin_edit_admin")],
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
        [InlineKeyboardButton("📈 وضعیت سرور", callback_data="admin_server_status")],
        [InlineKeyboardButton("🗑️ حذف همه داده‌های کاربران", callback_data="admin_delete_all_data")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_broadcasts_list_keyboard(broadcasts, page=0, per_page=10):
    """
    کیبورد لیست پیام‌های همگانی با pagination
    
    Args:
        broadcasts: لیست broadcast ها
        page: شماره صفحه (۰-based)
        per_page: تعداد در هر صفحه
    """
    keyboard = []
    
    def get_status_emoji(b):
        status = b['status'] if 'status' in b.keys() else ''
        
        if status == 'completed' or (b.get('is_sent') if hasattr(b, 'get') else False):
            return '✅'
        elif status == 'sending':
            return '📤'
        elif status == 'pending':
            return '⏰'
        elif status == 'failed':
            return '❌'
        elif status == 'stopped':
            return '🛑'
        elif status == 'cancelled' or (b.get('is_cancelled') if hasattr(b, 'get') else False):
            return '⛔'
        else:
            return '📝'
    
    # Pagination
    total = len(broadcasts)
    total_pages = (total + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    page_broadcasts = broadcasts[start:end]
    
    for b in page_broadcasts:
        emoji = get_status_emoji(b)
        title = b['title'] if 'title' in b.keys() else 'بدون عنوان'
        if len(title) > 35:
            title = title[:32] + "..."
        
        sent = b['sent_count'] if 'sent_count' in b.keys() else 0
        total_users = b['total_users'] if 'total_users' in b.keys() else 0
        count_text = f" ({sent}/{total_users})" if total_users > 0 else ""
        
        text = f"{emoji} {title}{count_text}"
        keyboard.append([InlineKeyboardButton(text, callback_data=f"admin_broadcast_{b['id']}")])
    
    # دکمه‌های pagination
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_broadcasts_page_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="admin_noop"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"admin_broadcasts_page_{page+1}"))
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def broadcast_action_keyboard(broadcast_id, status_or_is_sent, is_cancelled=None):
    """
    کیبورد عملیات پیام همگانی
    
    Args:
        broadcast_id: شناسه broadcast
        status_or_is_sent: می‌تونه status جدید (string) یا is_sent قدیمی (boolean) باشه
        is_cancelled: وضعیت لغو (برای سازگاری با کد قدیمی)
    """
    keyboard = []
    
    # تشخیص وضعیت
    if isinstance(status_or_is_sent, str):
        status = status_or_is_sent
        is_sent = status in ['completed', 'sending']
        is_cancelled = status == 'cancelled'
    else:
        is_sent = status_or_is_sent
        status = 'completed' if is_sent else ('cancelled' if is_cancelled else 'pending')
    
    # دکمه‌ها بر اساس وضعیت
    if status == 'sending':
        keyboard.append([InlineKeyboardButton("🛑 توقف ارسال", callback_data=f"admin_cancel_broadcast_{broadcast_id}")])
        keyboard.append([InlineKeyboardButton("🔄 بروزرسانی وضعیت", callback_data=f"admin_broadcast_{broadcast_id}")])
    
    elif status == 'pending':
        keyboard.append([InlineKeyboardButton("⛔ لغو ارسال", callback_data=f"admin_cancel_broadcast_{broadcast_id}")])
        keyboard.append([InlineKeyboardButton("📤 ارسال فوری", callback_data=f"admin_send_now_{broadcast_id}")])
    
    elif status == 'failed':
        keyboard.append([InlineKeyboardButton("🔄 ارسال مجدد", callback_data=f"admin_retry_broadcast_{broadcast_id}")])
    
    elif status == 'stopped':
        keyboard.append([InlineKeyboardButton("▶️ ادامه ارسال", callback_data=f"admin_resume_broadcast_{broadcast_id}")])
    
    elif status == 'completed':
        keyboard.append([InlineKeyboardButton("📊 آمار کامل", callback_data=f"admin_broadcast_stats_{broadcast_id}")])
    
    # دکمه‌های مشترک
    keyboard.append([InlineKeyboardButton("🗑️ حذف", callback_data=f"admin_delete_broadcast_{broadcast_id}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin_broadcasts_list")])
    
    return InlineKeyboardMarkup(keyboard)

def back_to_admin_keyboard():
    """دکمه بازگشت به پنل"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin_panel")]
    ])

def confirm_delete_keyboard(item_type, item_id, back_callback):
    """
    کیبورد تایید حذف (عمومی)
    
    Args:
        item_type: نوع آیتم (مثلاً "broadcast", "user")
        item_id: شناسه آیتم
        back_callback: callback_data برای بازگشت
    """
    keyboard = [
        [
            InlineKeyboardButton("⚠️ تأیید حذف", callback_data=f"admin_confirm_delete_{item_type}_{item_id}"),
            InlineKeyboardButton("🔙 انصراف", callback_data=back_callback)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def broadcast_stats_keyboard(broadcast_id):
    """کیبورد آمار پیشرفته broadcast"""
    keyboard = [
        [InlineKeyboardButton("📊 آمار کلی", callback_data=f"admin_broadcast_stats_{broadcast_id}")],
        [InlineKeyboardButton("❌ کاربران ناموفق", callback_data=f"admin_broadcast_failed_{broadcast_id}")],
        [InlineKeyboardButton("📥 خروجی CSV", callback_data=f"admin_broadcast_export_{broadcast_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin_broadcast_{broadcast_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)

def search_results_keyboard(user_id, is_banned):
    """کیبورد نتایج جستجوی کاربر"""
    keyboard = []
    
    if is_banned:
        keyboard.append([InlineKeyboardButton("🔓 آزادسازی کاربر", callback_data=f"admin_unban_{user_id}")])
    else:
        keyboard.append([InlineKeyboardButton("🔨 بن کاربر", callback_data=f"admin_ban_{user_id}")])
    
    keyboard.append([InlineKeyboardButton("📋 ریمایندرهای کاربر", callback_data=f"admin_user_reminders_{user_id}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(keyboard)

def date_selection_keyboard():
    """کیبورد انتخاب تاریخ - امروز یا دستی"""
    import jdatetime
    
    today = jdatetime.date.today()
    today_str = today.strftime("%Y/%m/%d")
    weekday = today.weekday()
    
    weekdays_fa = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
    
    keyboard = [
        [InlineKeyboardButton(
            f"📅 امروز: {today_str} ({weekdays_fa[weekday]})", 
            callback_data=f"broadcast_date_{today_str}"
        )],
        [InlineKeyboardButton("✏️ وارد کردن تاریخ دلخواه", callback_data="broadcast_date_custom")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ============ کیبوردهای جدید برای ارسال پیشرفته ============

def content_type_keyboard():
    """کیبورد انتخاب نوع محتوا برای پیام همگانی"""
    keyboard = [
        [InlineKeyboardButton("📝 متن", callback_data="content_type_text")],
        [InlineKeyboardButton("🖼 عکس", callback_data="content_type_photo")],
        [InlineKeyboardButton("🎥 فیلم", callback_data="content_type_video")],
        [InlineKeyboardButton("📄 فایل", callback_data="content_type_document")],
        [InlineKeyboardButton("🎵 صدا/ویس", callback_data="content_type_audio")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)


def inline_buttons_keyboard(current_buttons=None, is_editing=False):
    """کیبورد مدیریت دکمه‌های شیشه‌ای"""
    if current_buttons is None:
        current_buttons = []
    
    keyboard = []
    
    # نمایش دکمه‌های فعلی
    for i, btn in enumerate(current_buttons):
        if len(btn) == 2:  # دکمه URL
            text, url = btn
            keyboard.append([
                InlineKeyboardButton(f"🔗 {text[:20]}", url=url),
                InlineKeyboardButton("❌", callback_data=f"ib_remove_{i}")
            ])
        elif len(btn) == 3:  # دکمه Callback
            text, data, _ = btn
            keyboard.append([
                InlineKeyboardButton(f"🔘 {text[:20]}", callback_data=f"ib_noop"),
                InlineKeyboardButton("❌", callback_data=f"ib_remove_{i}")
            ])
    
    # دکمه‌های مدیریت
    if len(current_buttons) < 10:  # حداکثر ۱۰ دکمه
        keyboard.append([
            InlineKeyboardButton("➕ لینک", callback_data="ib_add_url"),
            InlineKeyboardButton("➕ دکمه", callback_data="ib_add_callback")
        ])
    
    # دکمه‌های تأیید/رد
    action_row = []
    if current_buttons:
        action_row.append(InlineKeyboardButton("✅ تأیید دکمه‌ها", callback_data="ib_confirm"))
    action_row.append(InlineKeyboardButton("⏭ رد کردن", callback_data="ib_skip"))
    keyboard.append(action_row)
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(keyboard)


def broadcast_preview_keyboard(broadcast_id, content_type):
    """کیبورد پیش‌نمایش و تأیید نهایی"""
    keyboard = [
        [InlineKeyboardButton("✅ تأیید و ارسال", callback_data=f"admin_confirm_advanced_{broadcast_id}")],
        [InlineKeyboardButton("✏️ ویرایش دکمه‌ها", callback_data=f"broadcast_edit_buttons_{broadcast_id}")],
        [InlineKeyboardButton("❌ لغو", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_content_type_fa(content_type):
    """ترجمه فارسی نوع محتوا"""
    types = {
        'text': 'متن',
        'photo': 'عکس',
        'video': 'فیلم',
        'document': 'فایل',
        'audio': 'صدا/ویس',
        'poll': 'نظرسنجی'
    }
    return types.get(content_type, 'محتوا')
