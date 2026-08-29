"""
پنل مدیریت گروه با دکمه‌ها
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler

import database as db
from utils.permissions import is_admin
from utils.helpers import escape_markdown


def get_main_admin_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users"),
            InlineKeyboardButton("⚙️ تنظیمات", callback_data="admin_settings"),
        ],
        [
            InlineKeyboardButton("🚫 مدیریت اخطارها", callback_data="admin_warns"),
            InlineKeyboardButton("🔇 مدیریت بی‌صداها", callback_data="admin_mutes"),
        ],
        [
            InlineKeyboardButton("📌 مدیریت پین‌ها", callback_data="admin_pins"),
            InlineKeyboardButton("🔒 قفل/باز کردن", callback_data="admin_lock"),
        ],
        [
            InlineKeyboardButton("📋 لیست ادمین‌ها", callback_data="admin_list"),
            InlineKeyboardButton("📊 آمار گروه", callback_data="admin_stats"),
        ],
        [
            InlineKeyboardButton("❌ بستن پنل", callback_data="admin_close"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🔙 بازگشت به پنل اصلی", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(update, context, user_id):
        await update.effective_message.reply_text("⛔️ شما دسترسی به این بخش ندارید.")
        return
    
    await update.effective_message.reply_text(
        "🛡️ *پنل مدیریت گروه*\n\n"
        "از دکمه‌های زیر برای مدیریت گروه استفاده کنید:",
        reply_markup=get_main_admin_keyboard(),
        parse_mode="Markdown"
    )


async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    data = query.data
    
    if not await is_admin(update, context, user_id):
        await query.edit_message_text("⛔️ شما دسترسی به این بخش ندارید.")
        return
    
    if data == "admin_users":
        await query.edit_message_text(
            "👥 *مدیریت کاربران*\n\n"
            "🔹 برای افزودن ادمین: /addadmin @username\n"
            "🔹 برای حذف ادمین: /removeadmin @username\n"
            "🔹 برای مشاهده اطلاعات کاربر: /userinfo @username",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "admin_warns":
        warns_list = db.get_users_with_warns(chat_id)
        if not warns_list:
            text = "✅ هیچ کاربری اخطار ندارد."
        else:
            text = "⚠️ *لیست کاربران دارای اخطار:*\n\n"
            for user in warns_list[:10]:
                name = user.get('first_name') or user.get('username') or str(user.get('user_id', 'نامشخص'))
                text += f"• {escape_markdown(name)}: {user.get('warns', 0)} اخطار\n"
            if len(warns_list) > 10:
                text += f"\n... و {len(warns_list) - 10} کاربر دیگر"
        
        await query.edit_message_text(
            text,
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "admin_settings":
        settings = db.get_settings(chat_id)
        locked = "🔒 قفل" if settings.get("locked", 0) else "🔓 باز"
        welcome = escape_markdown(settings.get("welcome_text", "تنظیم نشده")[:30])
        rules = escape_markdown(settings.get("rules_text", "تنظیم نشده")[:30])
        
        await query.edit_message_text(
            f"⚙️ *تنظیمات گروه*\n\n"
            f"🔒 وضعیت گروه: {locked}\n"
            f"📝 خوش‌آمدگویی: {welcome}...\n"
            f"📜 قوانین: {rules}...\n\n"
            "برای تغییر:\n"
            "/setwelcome متن جدید\n"
            "/setrules متن جدید\n"
            "/lock یا /unlock",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "admin_back":
        await query.edit_message_text(
            "🛡️ *پنل مدیریت گروه*\n\n"
            "از دکمه‌های زیر برای مدیریت گروه استفاده کنید:",
            reply_markup=get_main_admin_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "admin_stats":
        stats = db.chat_stats(chat_id)
        await query.edit_message_text(
            f"📊 *آمار گروه*\n\n"
            f"👥 تعداد اعضا: {stats.get('member_count', 0)}\n"
            f"⭐️ مجموع امتیازات: {stats.get('total_points', 0)}\n"
            f"⚠️ مجموع اخطارها: {stats.get('total_warns', 0)}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "admin_lock":
        settings = db.get_settings(chat_id)
        current = settings.get("locked", 0)
        new_state = 0 if current else 1
        db.set_setting(chat_id, "locked", new_state)
        status = "قفل" if new_state else "باز"
        emoji = "🔒" if new_state else "🔓"
        
        await query.edit_message_text(
            f"{emoji} گروه {status} شد.\n\n"
            f"وضعیت فعلی: {status}",
            reply_markup=get_back_keyboard()
        )
    
    elif data == "admin_close":
        await query.edit_message_text("❌ پنل مدیریت بسته شد.")
    
    elif data == "admin_mutes":
        await query.edit_message_text(
            "🔇 *مدیریت بی‌صداها*\n\n"
            "برای بی‌صدا کردن کاربر:\n"
            "روی پیام کاربر ریپلای کنید و /mute دقیقه\n"
            "مثال: /mute 5\n\n"
            "برای باز کردن صدا:\n"
            "روی پیام کاربر ریپلای کنید و /unmute",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "admin_pins":
        await query.edit_message_text(
            "📌 *مدیریت پین‌ها*\n\n"
            "برای پین کردن پیام:\n"
            "روی پیام مورد نظر ریپلای کنید و /pin\n\n"
            "برای برداشتن پین:\n"
            "/unpin",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "admin_list":
        admins = db.get_admins(chat_id)
        if not admins:
            text = "📋 لیست ادمین‌های دیتابیس خالی است.\n"
            text += "ادمین‌های تلگرام به صورت خودکار شناسایی می‌شوند."
        else:
            text = "📋 *لیست ادمین‌های دیتابیس:*\n\n"
            for admin in admins[:10]:
                user_id = admin.get('user_id', 'نامشخص')
                level = escape_markdown(admin.get('level', 'admin'))
                text += f"• کاربر {user_id} - سطح: {level}\n"
        
        await query.edit_message_text(
            text,
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )


def register_panel_handlers(app):
    app.add_handler(CommandHandler("panel", panel))
    app.add_handler(CallbackQueryHandler(panel_callback, pattern="^admin_"))