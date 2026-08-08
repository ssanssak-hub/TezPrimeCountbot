from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def dm_admin_menu_keyboard():
    """منوی پیام به کاربر - ادمین"""
    keyboard = [
        [InlineKeyboardButton("✉️ ارسال پیام به کاربر", callback_data="dm_admin_send")],
        [InlineKeyboardButton("📋 مشاهده پیام‌های ارسالی", callback_data="dm_admin_view_sent")],
        [InlineKeyboardButton("🗑️ حذف پیام", callback_data="dm_admin_delete")],
        [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin_panel")],
    ]
    return InlineKeyboardMarkup(keyboard)


def dm_admin_sent_list_keyboard(messages, page=0, per_page=5):
    """لیست پیام‌های ارسالی ادمین"""
    keyboard = []

    total = len(messages)
    start = page * per_page
    end = start + per_page
    page_messages = messages[start:end]

    for msg in page_messages:
        title = msg.get('title', 'بدون عنوان')[:30]
        user_id = msg.get('user_id')
        is_read = "✅" if msg.get('is_read') else "📩"
        text = f"{is_read} {title} → {user_id}"
        keyboard.append([InlineKeyboardButton(text, callback_data=f"dm_admin_detail_{msg['id']}")])

    if total > per_page:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"dm_admin_page_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{(total-1)//per_page+1}", callback_data="noop"))
        if end < total:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"dm_admin_page_{page+1}"))
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="dm_admin_menu")])
    return InlineKeyboardMarkup(keyboard)


def dm_admin_delete_list_keyboard(messages, page=0, per_page=5):
    """لیست پیام‌های قابل حذف"""
    keyboard = []

    total = len(messages)
    start = page * per_page
    end = start + per_page
    page_messages = messages[start:end]

    for msg in page_messages:
        title = msg.get('title', 'بدون عنوان')[:30]
        user_id = msg.get('user_id')
        text = f"🗑️ {title} → {user_id}"
        keyboard.append([InlineKeyboardButton(text, callback_data=f"dm_admin_delete_{msg['id']}")])

    if total > per_page:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"dm_del_page_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{(total-1)//per_page+1}", callback_data="noop"))
        if end < total:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"dm_del_page_{page+1}"))
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="dm_admin_menu")])
    return InlineKeyboardMarkup(keyboard)


def dm_admin_detail_keyboard(msg_id, user_id, is_read):
    """دکمه‌های جزئیات پیام ادمین"""
    keyboard = []
    if not is_read:
        keyboard.append([InlineKeyboardButton("👁 علامت‌گذاری به عنوان خوانده شده", callback_data=f"dm_admin_read_{msg_id}")])
    keyboard.append([InlineKeyboardButton("🗑️ حذف این پیام", callback_data=f"dm_admin_delete_{msg_id}")])
    keyboard.append([InlineKeyboardButton("✉️ ارسال پیام به این کاربر", callback_data=f"dm_admin_send_to_{user_id}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="dm_admin_view_sent")])
    return InlineKeyboardMarkup(keyboard)


def dm_user_menu_keyboard():
    """منوی پیام به مدیر - کاربر"""
    keyboard = [
        [InlineKeyboardButton("📨 ارسال پیام به مدیر", callback_data="dm_user_send")],
        [InlineKeyboardButton("📥 پیام‌های دریافتی از مدیر", callback_data="dm_user_view_received")],
        [InlineKeyboardButton("📤 پیام‌های ارسالی به مدیر", callback_data="dm_user_view_sent")],
        [InlineKeyboardButton("🗑️ حذف پیام ارسالی", callback_data="dm_user_delete")],
        [InlineKeyboardButton("🔙 بازگشت به منو اصلی", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def dm_user_received_list_keyboard(messages, page=0, per_page=5):
    """لیست پیام‌های دریافتی کاربر از مدیر"""
    keyboard = []

    total = len(messages)
    start = page * per_page
    end = start + per_page
    page_messages = messages[start:end]

    for msg in page_messages:
        title = msg.get('title', 'بدون عنوان')[:30]
        is_read = "✅" if msg.get('is_read') else "📩 جدید"
        text = f"{is_read} {title}"
        keyboard.append([InlineKeyboardButton(text, callback_data=f"dm_user_detail_{msg['id']}")])

    if total > per_page:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"dm_ur_page_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{(total-1)//per_page+1}", callback_data="noop"))
        if end < total:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"dm_ur_page_{page+1}"))
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="dm_user_menu")])
    return InlineKeyboardMarkup(keyboard)


def dm_user_sent_list_keyboard(messages, page=0, per_page=5):
    """لیست پیام‌های ارسالی کاربر به مدیر"""
    keyboard = []

    total = len(messages)
    start = page * per_page
    end = start + per_page
    page_messages = messages[start:end]

    status_emoji = {
        'pending': '⏳',
        'read': '👁',
        'ignored': '👀',
        'deleted': '🗑️',
        'replied': '💬',
    }

    for msg in page_messages:
        title = msg.get('title', 'بدون عنوان')[:25]
        st = msg.get('status', 'pending')
        emoji = status_emoji.get(st, '❓')
        text = f"{emoji} {title}"
        keyboard.append([InlineKeyboardButton(text, callback_data=f"dm_user_sent_detail_{msg['id']}")])

    if total > per_page:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"dm_us_page_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{(total-1)//per_page+1}", callback_data="noop"))
        if end < total:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"dm_us_page_{page+1}"))
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="dm_user_menu")])
    return InlineKeyboardMarkup(keyboard)


def dm_user_delete_list_keyboard(messages, page=0, per_page=5):
    """لیست پیام‌های قابل حذف توسط کاربر"""
    keyboard = []

    total = len(messages)
    start = page * per_page
    end = start + per_page
    page_messages = messages[start:end]

    for msg in page_messages:
        title = msg.get('title', 'بدون عنوان')[:30]
        text = f"🗑️ {title}"
        keyboard.append([InlineKeyboardButton(text, callback_data=f"dm_user_delete_{msg['id']}")])

    if total > per_page:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"dm_ud_page_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{(total-1)//per_page+1}", callback_data="noop"))
        if end < total:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"dm_ud_page_{page+1}"))
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="dm_user_menu")])
    return InlineKeyboardMarkup(keyboard)


def dm_user_detail_keyboard(msg_id):
    """دکمه‌های جزئیات پیام برای کاربر"""
    keyboard = [
        [InlineKeyboardButton("🔙 بازگشت", callback_data="dm_user_view_received")],
    ]
    return InlineKeyboardMarkup(keyboard)


def dm_user_sent_detail_keyboard(msg_id):
    """دکمه‌های جزئیات پیام ارسالی کاربر"""
    keyboard = [
        [InlineKeyboardButton("🗑️ حذف این پیام", callback_data=f"dm_user_delete_{msg_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="dm_user_view_sent")],
    ]
    return InlineKeyboardMarkup(keyboard)


def dm_admin_action_keyboard(msg_id, user_id):
    """دکمه‌های اقدام ادمین روی پیام کاربر"""
    keyboard = [
        [InlineKeyboardButton("✉️ ارسال پیام فوری به این کاربر", callback_data=f"dm_admin_reply_{user_id}")],
        [InlineKeyboardButton("🗑️ حذف پیام این کاربر", callback_data=f"dm_admin_delete_umsg_{msg_id}")],
        [InlineKeyboardButton("📋 مشاهده پیام‌های این کاربر", callback_data=f"dm_admin_user_msgs_{user_id}")],
        [InlineKeyboardButton("🚫 بن کردن این کاربر", callback_data=f"dm_admin_ban_{user_id}_{msg_id}")],
        [InlineKeyboardButton("👀 نادیده گرفتن", callback_data=f"dm_admin_ignore_{msg_id}")],
        [InlineKeyboardButton("🔙 ارسال پیام به کاربر", callback_data="dm_admin_send")],
        [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin_panel")],
    ]
    return InlineKeyboardMarkup(keyboard)


def dm_admin_select_keyboard(admins, selected=None):
    """کیبورد انتخاب ادمین‌ها (برای کاربر) - toggle"""
    if selected is None:
        selected = []

    keyboard = []

    for admin in admins:
        admin_id = admin['user_id']
        name = admin.get('first_name') or 'ناشناس'
        username = f" @{admin['username']}" if admin.get('username') else ""
        emoji = "✅" if admin_id in selected else "⬜"
        text = f"{emoji} {name}{username}"
        keyboard.append([InlineKeyboardButton(text, callback_data=f"dm_select_admin_{admin_id}")])

    keyboard.append([
        InlineKeyboardButton("✅ انتخاب همه", callback_data="dm_select_all"),
        InlineKeyboardButton("❌ حذف همه", callback_data="dm_select_none"),
    ])

    if selected:
        keyboard.append([InlineKeyboardButton(f"📨 ارسال به {len(selected)} ادمین", callback_data="dm_confirm_admins")])
    else:
        keyboard.append([InlineKeyboardButton("⚠️ حداقل یک ادمین انتخاب کنید", callback_data="noop")])

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="dm_user_menu")])
    return InlineKeyboardMarkup(keyboard)


def dm_user_notif_keyboard(msg_id):
    """دکمه مشاهده پیام در نوتیفیکیشن کاربر"""
    keyboard = [
        [InlineKeyboardButton("👁 مشاهده پیام ادمین", callback_data=f"dm_user_detail_{msg_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def dm_admin_notif_keyboard(msg_id):
    """دکمه مشاهده پیام در نوتیفیکیشن ادمین"""
    keyboard = [
        [InlineKeyboardButton("👁 مشاهده پیام کاربر", callback_data=f"dm_admin_view_umsg_{msg_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)
