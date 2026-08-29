"""
داشبورد مدیریت پیشرفته
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler

import database as db
from utils.permissions import is_admin

logger = logging.getLogger(__name__)


# ===== کیبوردهای داخل پنل =====

def get_main_dashboard() -> InlineKeyboardMarkup:
    """داشبورد اصلی مدیریت"""
    keyboard = [
        [
            InlineKeyboardButton("👥 مدیریت کاربران", callback_data="dash_users"),
            InlineKeyboardButton("⚙️ تنظیمات گروه", callback_data="dash_settings"),
        ],
        [
            InlineKeyboardButton("🚫 مدیریت کلمات ممنوعه", callback_data="dash_badwords"),
            InlineKeyboardButton("📊 آمار و گزارشات", callback_data="dash_stats"),
        ],
        [
            InlineKeyboardButton("👑 مدیریت ادمین‌ها", callback_data="dash_admins"),
            InlineKeyboardButton("🔔 اعلانات گروه", callback_data="dash_announce"),
        ],
        [
            InlineKeyboardButton("🎫 مدیریت تیکت‌ها", callback_data="dash_tickets"),
            InlineKeyboardButton("📣 تگ همه‌ی اعضا", callback_data="dash_tagall"),
        ],
        [
            InlineKeyboardButton("🤖 هوش مصنوعی", callback_data="dash_ai"),
            InlineKeyboardButton("🔄 بک‌آپ و بازیابی", callback_data="dash_backup"),
        ],
        [
            InlineKeyboardButton("❌ بستن پنل", callback_data="dash_close"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_keyboard() -> InlineKeyboardMarkup:
    """کیبورد بازگشت"""
    keyboard = [
        [InlineKeyboardButton("🔙 بازگشت به پنل اصلی", callback_data="dash_back")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش داشبورد مدیریت"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(update, context, user_id):
        await update.effective_message.reply_text("⛔️ شما دسترسی به این بخش ندارید.")
        return
    
    if update.effective_chat.type != "private" and not db.is_feature_enabled(chat_id, "admin_panel"):
        await update.effective_message.reply_text("⛔️ پنل مدیریت برای این گروه غیرفعال شده.")
        return
    
    await update.effective_message.reply_text(
        "🛡️ *داشبورد مدیریت گروه*\n\n"
        "از دکمه‌های زیر برای مدیریت گروه استفاده کنید:",
        reply_markup=get_main_dashboard(),
        parse_mode="Markdown"
    )


async def dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش دکمه‌های داشبورد"""
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    data = query.data
    
    if not await is_admin(update, context, user_id):
        await query.edit_message_text("⛔️ شما دسترسی به این بخش ندارید.")
        return
    
    # ===== مدیریت کاربران =====
    
    if data == "dash_users":
        await query.edit_message_text(
            "👥 *مدیریت کاربران*\n\n"
            "این دستورات رو با *ریپلای* روی پیام کاربر مورد نظر بفرست (فارسی هم پشتیبانی می‌شه):\n\n"
            "🔹 /warn یا «اخطار» - اخطار به کاربر\n"
            "🔹 /unwarn یا «حذف اخطار» - حذف یک اخطار\n"
            "🔹 /mute یا «بی‌صدا» - بی‌صدا کردن کاربر\n"
            "🔹 /unmute یا «باز کردن صدا» - باز کردن صدا\n"
            "🔹 /kick یا «اخراج» - اخراج از گروه\n"
            "🔹 /ban یا «بن» - بن کردن کاربر\n"
            "🔹 /unban یا «آنبن» - آنبن کردن کاربر\n"
            "🔹 /pin یا «پین» - پین کردن پیام\n"
            "🔹 /unpin یا «برداشتن پین» - برداشتن پین",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "dash_settings":
        settings = db.get_settings(chat_id)
        locked = "🔒 قفل" if settings.get("locked", 0) else "🔓 باز"
        
        await query.edit_message_text(
            f"⚙️ *تنظیمات گروه*\n\n"
            f"وضعیت گروه: {locked}\n\n"
            f"🔹 /setwelcome یا «تنظیم خوش‌آمدگویی»\n"
            f"🔹 /setgoodbye یا «تنظیم خداحافظی»\n"
            f"🔹 /setrules یا «تنظیم قوانین»\n"
            f"🔹 /lock یا «قفل» - قفل گروه\n"
            f"🔹 /unlock یا «باز» - باز کردن قفل",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "dash_tickets":
        stats = db.get_ticket_stats(chat_id)
        await query.edit_message_text(
            f"🎫 *مدیریت تیکت‌ها*\n\n"
            f"🟢 باز: {stats['open']}  |  🟡 در حال بررسی: {stats['in_progress']}  |  ⚪️ بسته: {stats['closed']}\n\n"
            f"🔹 /tickets یا «مدیریت تیکت» - لیست تیکت‌های باز\n"
            f"🔹 /reply یا «پاسخ» (با ریپلای) - پاسخ به تیکت\n"
            f"🔹 /close یا «بستن» - بستن تیکت",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "dash_tagall":
        from handlers.admin import tagall
        await query.edit_message_text("📣 در حال ارسال تگ به همه‌ی اعضا...")
        await tagall(update, context)
        return

    elif data == "dash_ai":
        from config import AI_ENABLED
        settings = db.get_settings(chat_id)
        ai_status = "✅ فعال" if settings.get("ai_moderation") else "❌ غیرفعال"
        configured = "✅ تنظیم شده" if AI_ENABLED else "❌ تنظیم نشده (ANTHROPIC_API_KEY خالیه)"
        await query.edit_message_text(
            f"🤖 *هوش مصنوعی*\n\n"
            f"وضعیت کلی: {configured}\n"
            f"تشخیص هوشمند فحش/توهین این گروه: {ai_status}\n\n"
            f"🔹 /aimod یا «هوش مصنوعی» - روشن/خاموش کردن تشخیص فحش هوشمند\n"
            f"🔹 /aireport - گزارش هوشمند گروه (توی پیوی برات می‌فرسته)\n"
            f"🔹 چت آزاد با AI: کافیه توی *پیوی ربات* هر چی خواستی بنویسی (شعر، سوال، هر چیزی)",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "dash_badwords":
        await query.edit_message_text(
            "🚫 *مدیریت کلمات ممنوعه*\n\n"
            "🔹 /addbadword کلمه - افزودن\n"
            "🔹 /removebadword کلمه - حذف\n"
            "🔹 /listbadwords - لیست\n"
            "🔹 /importbadwords - ایمپورت از فایل",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "dash_admins":
        await query.edit_message_text(
            "👑 *مدیریت ادمین‌ها*\n\n"
            "🔹 /addadmin - افزودن ادمین (با ریپلای)\n"
            "🔹 /removeadmin - حذف ادمین (با ریپلای)\n"
            "🔹 /setlevel - تنظیم سطح دسترسی",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "dash_stats":
        stats = db.chat_stats(chat_id)
        await query.edit_message_text(
            f"📊 *آمار و گزارشات گروه*\n\n"
            f"👥 تعداد اعضا: {stats['member_count']}\n"
            f"⭐️ مجموع امتیازات: {stats['total_points']}\n"
            f"⚠️ مجموع اخطارها: {stats['total_warns']}",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "dash_announce":
        await query.edit_message_text(
            "🔔 *ارسال اعلان به گروه*\n\n"
            "دستور زیر رو بفرستید:\n"
            "/announce متن پیام",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "dash_backup":
        await query.edit_message_text(
            "🔄 *بک‌آپ و بازیابی*\n\n"
            "🔹 /backup - گرفتن بک‌آپ\n"
            "🔹 /restore - بازیابی بک‌آپ\n"
            "🔹 /backups - لیست بک‌آپ‌ها",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "dash_back":
        await query.edit_message_text(
            "🛡️ *داشبورد مدیریت گروه*\n\n"
            "از دکمه‌های زیر استفاده کنید:",
            reply_markup=get_main_dashboard(),
            parse_mode="Markdown"
        )
    
    elif data == "dash_close":
        await query.edit_message_text("❌ پنل مدیریت بسته شد.")


def register_dashboard_handlers(app):
    """ثبت هندلرهای داشبورد (نکته: main.py فعلاً این تابع رو صدا نمی‌زنه و
    دستورات panel/dashboard رو مستقیم رجیستر می‌کنه - این تابع برای استفاده‌ی
    احتمالی جداگانه نگه داشته شده)."""
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("panel", dashboard))
    app.add_handler(CallbackQueryHandler(dashboard_callback, pattern="^dash_"))