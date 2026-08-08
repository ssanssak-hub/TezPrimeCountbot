import logging
import asyncio
from datetime import datetime
import pytz
import jdatetime
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, ConversationHandler
from telegram.request import HTTPXRequest

from database import (
    get_user_info, get_all_admins, is_user_admin,
    check_admin_permission, ban_user as db_ban_user,
    get_admin_info
)
from admin.admin_keyboards import (
    content_type_keyboard, inline_buttons_keyboard,
    get_content_type_fa, back_to_admin_keyboard
)
from admin.admin_database import save_button_message
from admin.admin_broadcast import get_admin_info_from_db

from direct_messages.dm_database import (
    save_admin_message, get_admin_messages_for_user,
    get_admin_message_by_id, mark_admin_message_read,
    mark_admin_message_deleted, get_all_admin_messages,
    save_user_message, get_user_messages_for_admin,
    get_user_message_by_id, update_user_message_status,
    get_user_messages_from_user, delete_user_message,
    save_notif_msg_id
)
from direct_messages.dm_keyboards import (
    dm_admin_menu_keyboard, dm_admin_sent_list_keyboard,
    dm_admin_delete_list_keyboard, dm_admin_detail_keyboard,
    dm_user_menu_keyboard, dm_user_received_list_keyboard,
    dm_user_sent_list_keyboard, dm_user_delete_list_keyboard,
    dm_user_detail_keyboard, dm_user_sent_detail_keyboard,
    dm_admin_action_keyboard, dm_admin_select_keyboard,
    dm_user_notif_keyboard, dm_admin_notif_keyboard
)

logger = logging.getLogger(__name__)

# Stateهای جدید
(DM_TITLE, DM_CONTENT, DM_BUTTONS, DM_USER_IDS, DM_SELECT_ADMINS) = range(100, 105)

# ============================================================
#                   بخش ادمین
# ============================================================

async def dm_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی پیام به کاربر - ادمین"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))

    if not check_admin_permission(user_id, admin_id, "perm_broadcast_now"):
        await query.edit_message_text("⛔ دسترسی ندارید!")
        return

    await query.edit_message_text(
        "📨 <b>ارسال پیام به کاربر</b>\n\n"
        "از منوی زیر انتخاب کنید:",
        reply_markup=dm_admin_menu_keyboard(),
        parse_mode='HTML'
    )


async def dm_admin_send_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ارسال پیام به کاربر - مرحله انتخاب نوع محتوا"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))

    if not check_admin_permission(user_id, admin_id, "perm_broadcast_now"):
        await query.edit_message_text("⛔ دسترسی ندارید!")
        return ConversationHandler.END

    context.user_data['dm_message'] = {}
    context.user_data['dm_type'] = 'admin_to_user'
    context.user_data['dm_step'] = 'content_type'
    context.user_data['inline_buttons'] = []

    await query.edit_message_text(
        "✉️ <b>ارسال پیام به کاربر</b>\n\n"
        "📌 <b>مرحله ۱/۴: انتخاب نوع پیام</b>\n\n"
        "لطفاً نوع محتوای پیام را انتخاب کنید:",
        reply_markup=content_type_keyboard(),
        parse_mode='HTML'
    )
    return DM_TITLE


async def dm_admin_handle_content_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت انتخاب نوع محتوا (استفاده از منطق admin_handlers)"""
    query = update.callback_query
    await query.answer()

    content_type = query.data.replace("content_type_", "")
    context.user_data['dm_message']['content_type'] = content_type

    if content_type == 'text':
        text = (
            "📝 <b>ارسال متن</b>\n\n"
            "لطفاً <b>عنوان</b> پیام را وارد کنید:\n"
            "🔙 برای بازگشت /cancel را بزنید"
        )
        context.user_data['dm_step'] = 'title'
        context.user_data['awaiting_message'] = True
        context.user_data['awaiting_dm'] = True

        await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode='HTML')
        return DM_TITLE

    elif content_type in ['photo', 'video', 'video_note', 'document', 'audio', 'voice']:
        content_fa = get_content_type_fa(content_type)
        text = (
            f"📎 <b>ارسال {content_fa}</b>\n\n"
            f"لطفاً فایل <b>{content_fa}</b> خود را ارسال کنید.\n"
            f"📌 می‌توانید کپشن هم بنویسید.\n"
            f"🔙 برای بازگشت /cancel را بزنید"
        )
        context.user_data['dm_step'] = 'file'
        context.user_data['awaiting_message'] = True
        context.user_data['awaiting_dm'] = True

        await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode='HTML')
        return DM_TITLE

    await query.edit_message_text("❌ نوع محتوا نامعتبر!", reply_markup=back_to_admin_keyboard())
    return ConversationHandler.END


async def dm_admin_receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت عنوان/متن یا فایل (استفاده از منطق handle_file_receive)"""
    if not context.user_data.get('awaiting_dm'):
        return ConversationHandler.END

    msg = update.message
    step = context.user_data.get('dm_step', 'title')
    content_type = context.user_data['dm_message'].get('content_type', 'text')

    # تشخیص فوروارد
    from_chat_id = None
    from_message_id = None
    is_forward = False

    if msg.forward_origin:
        is_forward = True
        from_chat_id = str(msg.chat.id)
        from_message_id = msg.message_id

    # ========== مرحله title (برای متن) ==========
    if step == 'title' and content_type == 'text':
        context.user_data['dm_message']['title'] = msg.text
        context.user_data['dm_message']['from_chat_id'] = from_chat_id
        context.user_data['dm_message']['from_message_id'] = from_message_id
        context.user_data['dm_step'] = 'message'

        await update.message.reply_text(
            f"📝 عنوان: <b>{msg.text}</b>\n\n"
            f"حالا <b>متن پیام</b> را ارسال کنید:",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return DM_CONTENT

    # ========== مرحله message (برای متن) ==========
    elif step == 'message' and content_type == 'text':
        context.user_data['dm_message']['message'] = msg.text
        if msg.forward_origin:
            context.user_data['dm_message']['from_chat_id'] = str(msg.chat.id)
            context.user_data['dm_message']['from_message_id'] = msg.message_id

        context.user_data['dm_step'] = 'buttons'
        context.user_data['awaiting_message'] = False
        context.user_data['awaiting_dm'] = False

        await update.message.reply_text(
            f"📝 <b>متن پیام دریافت شد</b>\n\n"
            f"حالا می‌توانید <b>دکمه‌های شیشه‌ای</b> اضافه کنید:",
            reply_markup=inline_buttons_keyboard(),
            parse_mode='HTML'
        )
        return DM_BUTTONS

    # ========== فایل ==========
    elif step == 'file' and content_type != 'text':
        file_id = None
        caption = msg.caption or ''

        if content_type == 'photo' and msg.photo:
            file_id = msg.photo[-1].file_id
        elif content_type == 'video' and msg.video:
            file_id = msg.video.file_id
        elif content_type == 'video_note' and msg.video_note:
            file_id = msg.video_note.file_id
        elif content_type == 'document' and msg.document:
            file_id = msg.document.file_id
        elif content_type == 'audio':
            if msg.audio:
                file_id = msg.audio.file_id
            elif msg.voice:
                file_id = msg.voice.file_id
                context.user_data['dm_message']['content_type'] = 'voice'

        if not file_id:
            await msg.reply_text("❌ فایل نامعتبر!", reply_markup=back_to_admin_keyboard())
            return DM_TITLE

        title = caption[:100] if caption else f"پیام {get_content_type_fa(content_type)}"
        if is_forward:
            title = f"↪️ {title}"

        context.user_data['dm_message']['file_id'] = file_id
        context.user_data['dm_message']['caption'] = caption
        context.user_data['dm_message']['title'] = title
        context.user_data['dm_message']['message'] = caption
        context.user_data['dm_message']['from_chat_id'] = from_chat_id
        context.user_data['dm_message']['from_message_id'] = from_message_id

        context.user_data['dm_step'] = 'buttons'
        context.user_data['awaiting_message'] = False
        context.user_data['awaiting_dm'] = False

        fwd_text = "📤 فوروارد شده - " if is_forward else ""
        await msg.reply_text(
            f"✅ {fwd_text}فایل دریافت شد!\n\n"
            f"📎 نوع: {get_content_type_fa(content_type)}\n"
            f"📝 کپشن: {caption[:100] if caption else 'ندارد'}\n\n"
            f"حالا می‌توانید دکمه‌های شیشه‌ای اضافه کنید:",
            reply_markup=inline_buttons_keyboard(),
            parse_mode='HTML'
        )
        return DM_BUTTONS

    return ConversationHandler.END


async def dm_admin_handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دکمه‌های شیشه‌ای (استفاده از منطق handle_inline_buttons)"""
    query = update.callback_query
    await query.answer()

    data = query.data
    buttons = context.user_data.get('inline_buttons', [])

    if data == "ib_skip" or data == "ib_confirm":
        # رفتن به مرحله دریافت آیدی کاربر
        return await dm_admin_ask_user_ids(update, context)

    elif data == "ib_add_url":
        context.user_data['awaiting_button'] = True
        context.user_data['adding_button_type'] = 'url'
        await query.edit_message_text(
            "🔗 <b>افزودن دکمه لینک</b>\n\n"
            "فرمت: <code>متن دکمه | https://...</code>",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return DM_BUTTONS

    elif data == "ib_add_callback":
        context.user_data['awaiting_button'] = True
        context.user_data['adding_button_type'] = 'callback'
        await query.edit_message_text(
            "🔘 <b>افزودن دکمه داخلی</b>\n\n"
            "فرمت: <code>متن دکمه | پیام نمایشی</code>",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return DM_BUTTONS

    elif data.startswith("ib_remove_"):
        index = int(data.replace("ib_remove_", ""))
        if 0 <= index < len(buttons):
            removed = buttons.pop(index)
            context.user_data['inline_buttons'] = buttons
            await query.answer(f"🗑️ حذف شد")

        await query.edit_message_text(
            f"✏️ تعداد دکمه‌ها: {len(buttons)}",
            reply_markup=inline_buttons_keyboard(buttons),
            parse_mode='HTML'
        )
        return DM_BUTTONS

    return DM_BUTTONS

async def dm_admin_button_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت متن/لینک دکمه"""
    if not context.user_data.get('awaiting_button'):
        return ConversationHandler.END
    
    text = update.message.text.strip()
    buttons = context.user_data.get('inline_buttons', [])
    btn_type = context.user_data.get('adding_button_type')

    if btn_type == 'url':
        parts = text.split('|')
        if len(parts) != 2:
            await update.message.reply_text("❌ فرمت اشتباه! دوباره:", reply_markup=back_to_admin_keyboard())
            return DM_BUTTONS

        btn_text, url = parts[0].strip(), parts[1].strip()
        buttons.append({'type': 'url', 'text': btn_text, 'url': url})

    elif btn_type == 'callback':
        if '|' not in text:
            await update.message.reply_text(
                "❌ فرمت اشتباه!\nفرمت: <code>متن دکمه | پیام نمایشی</code>",
                reply_markup=back_to_admin_keyboard(), parse_mode='HTML'
            )
            return DM_BUTTONS

        parts = text.split('|', 1)
        btn_text = parts[0].strip()
        alert_message = parts[1].strip()

        import uuid
        button_id = uuid.uuid4().hex[:8]
        save_button_message(button_id, alert_message)

        buttons.append({
            'type': 'callback',
            'text': btn_text,
            'callback_data': f"bc_{button_id}",
            'button_id': button_id,
            'message': alert_message
        })

    context.user_data['inline_buttons'] = buttons
    context.user_data['awaiting_button'] = False
    context.user_data['adding_button_type'] = None

    await update.message.reply_text(
        f"✅ دکمه افزوده شد! ({len(buttons)} عدد)\n"
        f"می‌توانید دکمه دیگری اضافه کنید:",
        reply_markup=inline_buttons_keyboard(buttons),
        parse_mode='HTML'
    )
    return DM_BUTTONS

async def dm_admin_ask_user_ids(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """درخواست آیدی کاربر(ها)"""
    query = update.callback_query
    if query:
        await query.answer()

    context.user_data['dm_step'] = 'user_ids'
    context.user_data['awaiting_message'] = True
    context.user_data['awaiting_dm'] = True

    text = (
        "👤 <b>مرحله آخر: مشخص کردن گیرنده</b>\n\n"
        "لطفاً <b>آیدی عددی کاربر</b> را وارد کنید.\n"
        "برای چند کاربر، آیدی‌ها را با <b>کاما</b> جدا کنید:\n\n"
        "📌 مثال: <code>123456789</code>\n"
        "📌 مثال چندتایی: <code>123, 456, 789</code>\n\n"
        "🔙 برای بازگشت /cancel را بزنید"
    )

    if query:
        await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=back_to_admin_keyboard(), parse_mode='HTML')

    return DM_USER_IDS


async def dm_admin_send_to_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال پیام به کاربر(ان) مشخص شده"""
    if not context.user_data.get('awaiting_dm'):
        return ConversationHandler.END

    text = update.message.text.strip()
    admin_id = update.effective_user.id

    # پارس کردن آیدی‌ها
    try:
        user_ids = [int(uid.strip()) for uid in text.split(',') if uid.strip().isdigit()]
    except:
        await update.message.reply_text("❌ آیدی نامعتبر! دوباره:", reply_markup=back_to_admin_keyboard())
        return DM_USER_IDS

    if not user_ids:
        await update.message.reply_text("❌ حداقل یک آیدی معتبر وارد کنید:", reply_markup=back_to_admin_keyboard())
        return DM_USER_IDS

    dm_data = context.user_data['dm_message']
    buttons = context.user_data.get('inline_buttons', [])
    admin_info = get_admin_info_from_db(admin_id)
    admin_name = admin_info.get('first_name', 'ادمین') if admin_info else 'ادمین'

    # زمان
    tehran_tz = pytz.timezone('Asia/Tehran')
    now = datetime.now(tehran_tz)
    time_str = now.strftime('%H:%M:%S')
    try:
        jalali_date = jdatetime.date.fromgregorian(date=now.date())
        persian_date = jalali_date.strftime('%Y/%m/%d')
    except:
        persian_date = now.strftime('%Y/%m/%d')

    bot = context.bot
    sent_count = 0
    failed_ids = []

    for user_id in user_ids:
        try:
            # ذخیره در دیتابیس
            msg_id = save_admin_message(
                admin_id=admin_id,
                user_id=user_id,
                title=dm_data.get('title', 'بدون عنوان'),
                content_type=dm_data.get('content_type', 'text'),
                message=dm_data.get('message'),
                file_id=dm_data.get('file_id'),
                file_caption=dm_data.get('caption'),
                inline_buttons=buttons,
                from_chat_id=dm_data.get('from_chat_id'),
                from_message_id=dm_data.get('from_message_id')
            )

            # ارسال نوتیفیکیشن به کاربر
            notif_text = (
                f"📨 <b>پیام جدید از مدیر</b>\n\n"
                f"👤 <b>{admin_name}</b> در تاریخ <b>{persian_date}</b> "
                f"ساعت <b>{time_str}</b> برای شما پیامی ارسال کرده است.\n\n"
                f"👇 برای مشاهده روی دکمه زیر کلیک کنید:"
            )

            notif_msg = await bot.send_message(
                chat_id=user_id,
                text=notif_text,
                reply_markup=dm_user_notif_keyboard(msg_id),
                parse_mode='HTML'
            )

            # ذخیره message_id نوتیفیکیشن
            save_notif_msg_id('admin_messages', msg_id, 'user_notif_msg_id', notif_msg.message_id)

            sent_count += 1

        except Exception as e:
            logger.error(f"❌ Failed to send to {user_id}: {e}")
            failed_ids.append(str(user_id))

    # گزارش به ادمین
    report = f"✅ پیام به <b>{sent_count}</b> کاربر ارسال شد!"
    if failed_ids:
        report += f"\n❌ ناموفق: {', '.join(failed_ids)}"

    context.user_data.clear()
    await update.message.reply_text(report, reply_markup=dm_admin_menu_keyboard(), parse_mode='HTML')
    return ConversationHandler.END


async def dm_admin_view_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده پیام‌های ارسالی"""
    query = update.callback_query
    await query.answer()

    messages = get_all_admin_messages()
    if not messages:
        await query.edit_message_text("📭 هیچ پیامی ارسال نشده!", reply_markup=dm_admin_menu_keyboard())
        return

    context.user_data['dm_admin_msgs'] = messages
    await query.edit_message_text(
        "📋 <b>پیام‌های ارسالی به کاربران</b>",
        reply_markup=dm_admin_sent_list_keyboard(messages),
        parse_mode='HTML'
    )


async def dm_admin_view_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده جزئیات پیام ارسالی"""
    query = update.callback_query
    await query.answer()

    msg_id = int(query.data.split("_")[-1])
    msg = get_admin_message_by_id(msg_id)

    if not msg:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=dm_admin_menu_keyboard())
        return

    mark_admin_message_read(msg_id)

    user_info = get_user_info(msg['user_id'])
    user_name = user_info['first_name'] if user_info else 'ناشناس'

    text = (
        f"📋 <b>جزئیات پیام ارسالی</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 عنوان: <b>{msg['title']}</b>\n"
        f"📎 نوع: <b>{get_content_type_fa(msg['content_type'])}</b>\n"
        f"👤 گیرنده: {user_name} (<code>{msg['user_id']}</code>)\n"
        f"👁 وضعیت: {'✅ خوانده شده' if msg['is_read'] else '📩 خوانده نشده'}\n"
        f"📅 تاریخ: {msg['created_at']}\n"
        f"━━━━━━━━━━━━━━━━\n"
    )

    if msg['content_type'] == 'text' and msg['message']:
        text += f"📝 متن:\n{msg['message'][:500]}\n"

    await query.edit_message_text(
        text,
        reply_markup=dm_admin_detail_keyboard(msg_id, msg['user_id'], msg['is_read']),
        parse_mode='HTML'
    )


async def dm_admin_delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف پیام ارسالی"""
    query = update.callback_query
    await query.answer()

    data = query.data

    # لیست پیام‌ها برای حذف
    if data == "dm_admin_delete":
        messages = get_all_admin_messages()
        if not messages:
            await query.edit_message_text("📭 پیامی برای حذف نیست!", reply_markup=dm_admin_menu_keyboard())
            return

        context.user_data['dm_admin_msgs'] = messages
        await query.edit_message_text(
            "🗑️ <b>انتخاب پیام برای حذف</b>",
            reply_markup=dm_admin_delete_list_keyboard(messages),
            parse_mode='HTML'
        )
        return

    # حذف پیام مشخص
    if data.startswith("dm_admin_delete_"):
        msg_id = int(data.split("_")[-1])
        msg = get_admin_message_by_id(msg_id)

        if msg:
            # تلاش برای حذف نوتیفیکیشن کاربر
            if msg.get('user_notif_msg_id'):
                try:
                    await context.bot.delete_message(msg['user_id'], msg['user_notif_msg_id'])
                except:
                    pass

            mark_admin_message_deleted(msg_id)
            await query.answer("✅ پیام حذف شد!")

        messages = get_all_admin_messages()
        await query.edit_message_text(
            "🗑️ <b>انتخاب پیام برای حذف</b>",
            reply_markup=dm_admin_delete_list_keyboard(messages),
            parse_mode='HTML'
        )


async def dm_admin_read_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """علامت‌گذاری به عنوان خوانده شده"""
    query = update.callback_query
    await query.answer()

    msg_id = int(query.data.split("_")[-1])
    mark_admin_message_read(msg_id)

    msg = get_admin_message_by_id(msg_id)
    if msg:
        await query.edit_message_text(
            f"✅ پیام #{msg_id} خوانده شد!",
            reply_markup=dm_admin_detail_keyboard(msg_id, msg['user_id'], True),
            parse_mode='HTML'
        )


async def dm_admin_delete_user_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف پیام کاربر (توسط ادمین)"""
    query = update.callback_query
    await query.answer()

    msg_id = int(query.data.split("_")[-1])
    msg = get_user_message_by_id(msg_id)

    if msg:
        # تلاش برای حذف نوتیفیکیشن
        if msg.get('admin_notif_msg_id'):
            try:
                await context.bot.delete_message(msg['admin_id'], msg['admin_notif_msg_id'])
            except:
                pass

        update_user_message_status(msg_id, 'deleted', 'deleted_by_admin')

        # اطلاع به کاربر
        try:
            await context.bot.send_message(
                chat_id=msg['user_id'],
                text=f"📢 مدیر پیام شما با عنوان <b>«{msg['title']}»</b> را حذف کرد.",
                parse_mode='HTML'
            )
        except:
            pass

        await query.edit_message_text("✅ پیام کاربر حذف شد!", reply_markup=back_to_admin_keyboard())
    else:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())


async def dm_admin_ignore_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نادیده گرفتن پیام کاربر"""
    query = update.callback_query
    await query.answer()

    msg_id = int(query.data.split("_")[-1])
    msg = get_user_message_by_id(msg_id)

    if msg:
        update_user_message_status(msg_id, 'ignored', 'ignored')

        try:
            await context.bot.send_message(
                chat_id=msg['user_id'],
                text=f"👀 مدیر پیام شما با عنوان <b>«{msg['title']}»</b> را مشاهده کرد.",
                parse_mode='HTML'
            )
        except:
            pass

        await query.edit_message_text("👀 پیام نادیده گرفته شد.", reply_markup=back_to_admin_keyboard())
    else:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())


async def dm_admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بن کردن کاربر از طریق پیام"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    user_id = int(parts[-2])
    msg_id = int(parts[-1])

    db_ban_user(user_id)
    update_user_message_status(msg_id, 'read', 'banned')

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="🚫 شما توسط مدیر از ربات مسدود شدید.",
            parse_mode='HTML'
        )
    except:
        pass

    await query.edit_message_text(
        f"🚫 کاربر <code>{user_id}</code> بن شد!",
        reply_markup=back_to_admin_keyboard(),
        parse_mode='HTML'
    )


async def dm_admin_view_user_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده پیام‌های یک کاربر خاص"""
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.split("_")[-1])
    messages = get_user_messages_from_user(user_id)

    if not messages:
        await query.edit_message_text("📭 پیامی از این کاربر نیست!", reply_markup=back_to_admin_keyboard())
        return

    text = f"📋 <b>پیام‌های کاربر {user_id}</b>\n\n"
    for i, msg in enumerate(messages[:10], 1):
        status = {'pending': '⏳', 'read': '👁', 'ignored': '👀', 'deleted': '🗑️'}.get(msg.get('status', ''), '❓')
        text += f"{i}. {status} {msg['title'][:30]}\n"

    keyboard = [
        [InlineKeyboardButton("✉️ ارسال پیام به این کاربر", callback_data=f"dm_admin_reply_{user_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def dm_admin_view_umsg_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده جزئیات پیام کاربر (توسط ادمین)"""
    query = update.callback_query
    await query.answer()

    msg_id = int(query.data.split("_")[-1])
    msg = get_user_message_by_id(msg_id)

    if not msg:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=back_to_admin_keyboard())
        return

    # علامت‌گذاری به عنوان خوانده شده
    if msg['status'] == 'pending':
        update_user_message_status(msg_id, 'read', 'viewed')

        # اطلاع به کاربر
        try:
            await context.bot.send_message(
                chat_id=msg['user_id'],
                text=f"👁 مدیر پیام شما با عنوان <b>«{msg['title']}»</b> را مشاهده کرد.",
                parse_mode='HTML'
            )
        except:
            pass

    user_info = get_user_info(msg['user_id'])
    user_name = user_info['first_name'] if user_info else 'ناشناس'
    username = f" @{user_info['username']}" if user_info and user_info.get('username') else ""

    text = (
        f"📋 <b>پیام از کاربر</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 فرستنده: {user_name} (<code>{msg['user_id']}</code>){username}\n"
        f"📌 عنوان: <b>{msg['title']}</b>\n"
        f"📎 نوع: <b>{get_content_type_fa(msg['content_type'])}</b>\n"
        f"📊 وضعیت: {msg['status']}\n"
        f"📅 تاریخ: {msg['created_at']}\n"
        f"━━━━━━━━━━━━━━━━\n"
    )

    if msg['content_type'] == 'text' and msg['message']:
        text += f"📝 متن:\n{msg['message'][:500]}\n"

    # نمایش محتوای فوروارد شده
    if msg.get('from_chat_id') and msg.get('from_message_id'):
        try:
            await context.bot.copy_message(
                chat_id=update.effective_user.id,
                from_chat_id=msg['from_chat_id'],
                message_id=msg['from_message_id']
            )
        except:
            pass

    await query.edit_message_text(
        text,
        reply_markup=dm_admin_action_keyboard(msg_id, msg['user_id']),
        parse_mode='HTML'
    )


# ============================================================
#                   بخش کاربر
# ============================================================

async def dm_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی پیام به مدیر - کاربر"""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "📨 <b>پیام به مدیر</b>\n\nاز منوی زیر انتخاب کنید:",
        reply_markup=dm_user_menu_keyboard(),
        parse_mode='HTML'
    )


async def dm_user_send_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ارسال پیام به مدیر - انتخاب نوع محتوا"""
    query = update.callback_query
    await query.answer()

    context.user_data['dm_message'] = {}
    context.user_data['dm_type'] = 'user_to_admin'
    context.user_data['dm_step'] = 'content_type'
    context.user_data['inline_buttons'] = []

    await query.edit_message_text(
        "📨 <b>ارسال پیام به مدیر</b>\n\n"
        "📌 <b>مرحله ۱/۴: انتخاب نوع پیام</b>\n\n"
        "لطفاً نوع محتوای پیام را انتخاب کنید:",
        reply_markup=content_type_keyboard(),
        parse_mode='HTML'
    )
    return DM_TITLE


async def dm_user_handle_content_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت انتخاب نوع محتوا (کاربر)"""
    query = update.callback_query
    await query.answer()

    content_type = query.data.replace("content_type_", "")
    context.user_data['dm_message']['content_type'] = content_type

    if content_type == 'text':
        context.user_data['dm_step'] = 'title'
        context.user_data['awaiting_message'] = True
        context.user_data['awaiting_dm'] = True

        await query.edit_message_text(
            "📝 <b>ارسال متن</b>\n\nلطفاً <b>عنوان</b> پیام را وارد کنید:",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return DM_TITLE

    elif content_type in ['photo', 'video', 'video_note', 'document', 'audio', 'voice']:
        content_fa = get_content_type_fa(content_type)
        context.user_data['dm_step'] = 'file'
        context.user_data['awaiting_message'] = True
        context.user_data['awaiting_dm'] = True

        await query.edit_message_text(
            f"📎 <b>ارسال {content_fa}</b>\n\nلطفاً فایل خود را ارسال کنید.",
            reply_markup=back_to_admin_keyboard(),
            parse_mode='HTML'
        )
        return DM_TITLE

    return ConversationHandler.END


async def dm_user_receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت محتوای پیام کاربر (استفاده از منطق مشترک)"""
    # از تابع مشترک استفاده می‌کنیم
    result = await dm_admin_receive_content(update, context)

    # اگر به مرحله دکمه‌ها رفت، برمی‌گردیم
    if context.user_data.get('dm_step') == 'buttons':
        return DM_BUTTONS

    return result


async def dm_user_handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دکمه‌های شیشه‌ای (کاربر)"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "ib_skip" or data == "ib_confirm":
        # رفتن به مرحله انتخاب ادمین
        return await dm_user_select_admins(update, context)

    # برای بقیه موارد از تابع ادمین استفاده کن
    return await dm_admin_handle_buttons(update, context)


async def dm_user_button_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت متن دکمه (کاربر)"""
    return await dm_admin_button_text_input(update, context)


async def dm_user_select_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب ادمین(های) گیرنده"""
    query = update.callback_query
    if query:
        await query.answer()

    admins = get_all_admins()
    admin_id = int(os.getenv('ADMIN_ID'))

    # اضافه کردن ادمین اصلی به لیست
    admin_main_info = get_user_info(admin_id)
    if admin_main_info:
        admins_list = [dict(admin_main_info)] + [dict(a) for a in admins if a['user_id'] != admin_id]
    else:
        admins_list = [dict(a) for a in admins]

    context.user_data['dm_admins'] = admins_list

    if 'selected_admins' not in context.user_data:
        context.user_data['selected_admins'] = []

    await query.edit_message_text(
        "👥 <b>انتخاب مدیر گیرنده</b>\n\n"
        f"مدیر(ان) مورد نظر را انتخاب کنید:",
        reply_markup=dm_admin_select_keyboard(admins_list, context.user_data['selected_admins']),
        parse_mode='HTML'
    )
    return DM_SELECT_ADMINS


async def dm_user_toggle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تاگل انتخاب ادمین"""
    query = update.callback_query
    await query.answer()

    data = query.data
    selected = context.user_data.get('selected_admins', [])

    if data == "dm_select_all":
        selected = [a['user_id'] for a in context.user_data['dm_admins']]
    elif data == "dm_select_none":
        selected = []
    elif data.startswith("dm_select_admin_"):
        admin_id = int(data.split("_")[-1])
        if admin_id in selected:
            selected.remove(admin_id)
        else:
            selected.append(admin_id)
    elif data == "dm_confirm_admins":
        # ارسال پیام به ادمین‌های انتخاب شده
        return await dm_user_send_to_admins(update, context)

    context.user_data['selected_admins'] = selected

    await query.edit_message_text(
        f"👥 <b>انتخاب مدیر گیرنده</b>\n\n"
        f"انتخاب شده: <b>{len(selected)}</b> مدیر\n"
        f"مدیر(ان) مورد نظر را انتخاب کنید:",
        reply_markup=dm_admin_select_keyboard(context.user_data['dm_admins'], selected),
        parse_mode='HTML'
    )
    return DM_SELECT_ADMINS


async def dm_user_send_to_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال پیام به ادمین‌های انتخاب شده"""
    query = update.callback_query
    await query.answer()

    selected = context.user_data.get('selected_admins', [])
    if not selected:
        await query.answer("⚠️ حداقل یک مدیر انتخاب کنید!", show_alert=True)
        return DM_SELECT_ADMINS

    user = update.effective_user
    user_id = user.id
    user_name = user.first_name or 'کاربر'
    username = f" @{user.username}" if user.username else ""

    dm_data = context.user_data['dm_message']
    buttons = context.user_data.get('inline_buttons', [])

    # زمان
    tehran_tz = pytz.timezone('Asia/Tehran')
    now = datetime.now(tehran_tz)
    time_str = now.strftime('%H:%M:%S')
    try:
        jalali_date = jdatetime.date.fromgregorian(date=now.date())
        persian_date = jalali_date.strftime('%Y/%m/%d')
    except:
        persian_date = now.strftime('%Y/%m/%d')

    bot = context.bot
    sent_count = 0

    for admin_id in selected:
        try:
            msg_id = save_user_message(
                user_id=user_id,
                admin_id=admin_id,
                title=dm_data.get('title', 'بدون عنوان'),
                content_type=dm_data.get('content_type', 'text'),
                message=dm_data.get('message'),
                file_id=dm_data.get('file_id'),
                file_caption=dm_data.get('caption'),
                inline_buttons=buttons,
                from_chat_id=dm_data.get('from_chat_id'),
                from_message_id=dm_data.get('from_message_id')
            )

            notif_text = (
                f"📨 <b>پیام جدید از کاربر</b>\n\n"
                f"👤 <b>{user_name}</b> با آیدی <code>{user_id}</code>{username}\n"
                f"📅 تاریخ: <b>{persian_date}</b> ساعت <b>{time_str}</b>\n\n"
                f"برای شما پیامی ارسال کرده است.\n"
                f"👇 برای مشاهده روی دکمه زیر کلیک کنید:"
            )

            notif_msg = await bot.send_message(
                chat_id=admin_id,
                text=notif_text,
                reply_markup=dm_admin_notif_keyboard(msg_id),
                parse_mode='HTML'
            )

            save_notif_msg_id('user_messages', msg_id, 'admin_notif_msg_id', notif_msg.message_id)
            sent_count += 1

        except Exception as e:
            logger.error(f"❌ Failed to send to admin {admin_id}: {e}")

    context.user_data.clear()

    await query.edit_message_text(
        f"✅ پیام شما به <b>{sent_count}</b> مدیر ارسال شد!",
        reply_markup=dm_user_menu_keyboard(),
        parse_mode='HTML'
    )
    return ConversationHandler.END


async def dm_user_view_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده پیام‌های دریافتی از مدیر"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    messages = get_admin_messages_for_user(user_id)

    if not messages:
        await query.edit_message_text("📭 پیامی از مدیر ندارید!", reply_markup=dm_user_menu_keyboard())
        return

    context.user_data['dm_user_msgs'] = messages
    await query.edit_message_text(
        "📥 <b>پیام‌های دریافتی از مدیر</b>",
        reply_markup=dm_user_received_list_keyboard(messages),
        parse_mode='HTML'
    )


async def dm_user_view_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده پیام‌های ارسالی به مدیر"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    messages = get_user_messages_from_user(user_id)

    if not messages:
        await query.edit_message_text("📭 پیامی ارسال نکرده‌اید!", reply_markup=dm_user_menu_keyboard())
        return

    context.user_data['dm_user_sent_msgs'] = messages
    await query.edit_message_text(
        "📤 <b>پیام‌های ارسالی به مدیر</b>",
        reply_markup=dm_user_sent_list_keyboard(messages),
        parse_mode='HTML'
    )


async def dm_user_view_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده جزئیات پیام دریافتی از مدیر"""
    query = update.callback_query
    await query.answer()

    msg_id = int(query.data.split("_")[-1])
    msg = get_admin_message_by_id(msg_id)

    if not msg:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=dm_user_menu_keyboard())
        return

    mark_admin_message_read(msg_id)

    admin_info = get_user_info(msg['admin_id'])
    admin_name = admin_info['first_name'] if admin_info else 'ادمین'

    text = (
        f"📋 <b>پیام از مدیر</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 فرستنده: <b>{admin_name}</b>\n"
        f"📌 عنوان: <b>{msg['title']}</b>\n"
        f"📎 نوع: <b>{get_content_type_fa(msg['content_type'])}</b>\n"
        f"📅 تاریخ: {msg['created_at']}\n"
        f"━━━━━━━━━━━━━━━━\n"
    )

    if msg['content_type'] == 'text' and msg['message']:
        text += f"📝 متن:\n{msg['message'][:500]}\n"

    # نمایش محتوای فوروارد شده
    if msg.get('from_chat_id') and msg.get('from_message_id'):
        try:
            await context.bot.copy_message(
                chat_id=update.effective_user.id,
                from_chat_id=msg['from_chat_id'],
                message_id=msg['from_message_id']
            )
        except:
            pass

    await query.edit_message_text(
        text,
        reply_markup=dm_user_detail_keyboard(msg_id),
        parse_mode='HTML'
    )


async def dm_user_view_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده جزئیات پیام دریافتی از مدیر"""
    query = update.callback_query
    await query.answer()

    msg_id = int(query.data.split("_")[-1])
    msg = get_admin_message_by_id(msg_id)

    if not msg:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=dm_user_menu_keyboard())
        return

    mark_admin_message_read(msg_id)

    admin_info = get_user_info(msg['admin_id'])
    admin_name = admin_info['first_name'] if admin_info else 'ادمین'

    text = (
        f"📋 <b>پیام از مدیر</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 فرستنده: <b>{admin_name}</b>\n"
        f"📌 عنوان: <b>{msg['title']}</b>\n"
        f"📎 نوع: <b>{get_content_type_fa(msg['content_type'])}</b>\n"
        f"📅 تاریخ: {msg['created_at']}\n"
        f"━━━━━━━━━━━━━━━━\n"
    )

    if msg['content_type'] == 'text' and msg['message']:
        text += f"📝 متن:\n{msg['message'][:500]}\n"

    # 🆕 ساخت reply_markup از دکمه‌های شیشه‌ای
    reply_markup = None
    if msg.get('inline_buttons'):
        try:
            import json
            buttons_data = json.loads(msg['inline_buttons']) if isinstance(msg['inline_buttons'], str) else msg['inline_buttons']
            keyboard = []
            for btn in buttons_data:
                if isinstance(btn, dict):
                    if btn.get('type') == 'url':
                        keyboard.append([InlineKeyboardButton(btn['text'][:64], url=btn['url'])])
                    elif btn.get('type') == 'callback':
                        keyboard.append([InlineKeyboardButton(btn['text'][:64], callback_data=btn['callback_data'])])
            if keyboard:
                # دکمه بازگشت رو اضافه کن
                keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="dm_user_view_received")])
                reply_markup = InlineKeyboardMarkup(keyboard)
        except Exception as e:
            logger.error(f"Error parsing inline buttons: {e}")

    # اگه دکمه‌ای نبود، فقط دکمه بازگشت
    if not reply_markup:
        reply_markup = dm_user_detail_keyboard(msg_id)

    # نمایش محتوای فوروارد شده
    if msg.get('from_chat_id') and msg.get('from_message_id'):
        try:
            await context.bot.copy_message(
                chat_id=update.effective_user.id,
                from_chat_id=msg['from_chat_id'],
                message_id=msg['from_message_id']
            )
        except:
            pass

    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def dm_user_delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف پیام ارسالی توسط کاربر"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "dm_user_delete":
        user_id = update.effective_user.id
        messages = get_user_messages_from_user(user_id)
        if not messages:
            await query.edit_message_text("📭 پیامی برای حذف نیست!", reply_markup=dm_user_menu_keyboard())
            return

        context.user_data['dm_user_sent_msgs'] = messages
        await query.edit_message_text(
            "🗑️ <b>انتخاب پیام برای حذف</b>",
            reply_markup=dm_user_delete_list_keyboard(messages),
            parse_mode='HTML'
        )
        return

    if data.startswith("dm_user_delete_"):
        msg_id = int(data.split("_")[-1])
        delete_user_message(msg_id)

        user_id = update.effective_user.id
        messages = get_user_messages_from_user(user_id)

        await query.edit_message_text(
            "🗑️ <b>پیام حذف شد!</b>\n\nانتخاب پیام برای حذف:",
            reply_markup=dm_user_delete_list_keyboard(messages),
            parse_mode='HTML'
        )


# ============================================================
#                   هندلرهای pagination
# ============================================================

async def dm_handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت pagination لیست‌ها"""
    query = update.callback_query
    await query.answer()

    data = query.data

    # pagination لیست ارسالی ادمین
    if data.startswith("dm_admin_page_"):
        page = int(data.split("_")[-1])
        messages = get_all_admin_messages()
        await query.edit_message_text(
            "📋 <b>پیام‌های ارسالی به کاربران</b>",
            reply_markup=dm_admin_sent_list_keyboard(messages, page),
            parse_mode='HTML'
        )

    # pagination لیست حذف ادمین
    elif data.startswith("dm_del_page_"):
        page = int(data.split("_")[-1])
        messages = get_all_admin_messages()
        await query.edit_message_text(
            "🗑️ <b>انتخاب پیام برای حذف</b>",
            reply_markup=dm_admin_delete_list_keyboard(messages, page),
            parse_mode='HTML'
        )

    # pagination لیست دریافتی کاربر
    elif data.startswith("dm_ur_page_"):
        page = int(data.split("_")[-1])
        user_id = update.effective_user.id
        messages = get_admin_messages_for_user(user_id)
        await query.edit_message_text(
            "📥 <b>پیام‌های دریافتی از مدیر</b>",
            reply_markup=dm_user_received_list_keyboard(messages, page),
            parse_mode='HTML'
        )

    # pagination لیست ارسالی کاربر
    elif data.startswith("dm_us_page_"):
        page = int(data.split("_")[-1])
        user_id = update.effective_user.id
        messages = get_user_messages_from_user(user_id)
        await query.edit_message_text(
            "📤 <b>پیام‌های ارسالی به مدیر</b>",
            reply_markup=dm_user_sent_list_keyboard(messages, page),
            parse_mode='HTML'
        )

    # pagination لیست حذف کاربر
    elif data.startswith("dm_ud_page_"):
        page = int(data.split("_")[-1])
        user_id = update.effective_user.id
        messages = get_user_messages_from_user(user_id)
        await query.edit_message_text(
            "🗑️ <b>انتخاب پیام برای حذف</b>",
            reply_markup=dm_user_delete_list_keyboard(messages, page),
            parse_mode='HTML'
        )

# ============================================================
#                   برگشت به منوها
# ============================================================

async def dm_back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """برگشت به منوی ادمین"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID'))
    
    await query.edit_message_text(
        "📨 <b>ارسال پیام به کاربر</b>\n\nاز منوی زیر انتخاب کنید:",
        reply_markup=dm_admin_menu_keyboard(),
        parse_mode='HTML'
    )


async def dm_back_to_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """برگشت به منوی کاربر"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📨 <b>پیام به مدیر</b>\n\nاز منوی زیر انتخاب کنید:",
        reply_markup=dm_user_menu_keyboard(),
        parse_mode='HTML'
    )


async def dm_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو عملیات"""
    context.user_data.clear()
    
    if update.message:
        await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=back_to_admin_keyboard())
    elif update.callback_query:
        await update.callback_query.edit_message_text("❌ عملیات لغو شد.", reply_markup=back_to_admin_keyboard())
    
    return ConversationHandler.END

async def dm_user_view_sent_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده جزئیات پیام ارسالی به مدیر"""
    query = update.callback_query
    await query.answer()

    msg_id = int(query.data.split("_")[-1])
    msg = get_user_message_by_id(msg_id)

    if not msg:
        await query.edit_message_text("❌ پیام یافت نشد!", reply_markup=dm_user_menu_keyboard())
        return

    status_text = {
        'pending': '⏳ در انتظار مشاهده',
        'read': '👁 مشاهده شده',
        'ignored': '👀 دیده شده',
        'deleted': '🗑️ حذف شده توسط مدیر',
        'replied': '💬 پاسخ داده شده',
    }.get(msg['status'], msg['status'])

    text = (
        f"📋 <b>پیام ارسالی به مدیر</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 عنوان: <b>{msg['title']}</b>\n"
        f"📎 نوع: <b>{get_content_type_fa(msg['content_type'])}</b>\n"
        f"📊 وضعیت: {status_text}\n"
        f"📅 تاریخ: {msg['created_at']}\n"
        f"━━━━━━━━━━━━━━━━\n"
    )

    if msg['content_type'] == 'text' and msg['message']:
        text += f"📝 متن:\n{msg['message'][:300]}\n"

    await query.edit_message_text(
        text,
        reply_markup=dm_user_sent_detail_keyboard(msg_id),
        parse_mode='HTML'
    )
