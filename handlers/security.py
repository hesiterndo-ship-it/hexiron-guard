"""
سیستم امنیت پیشرفته
"""
import logging
import time
from datetime import datetime, timedelta
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, ApplicationHandlerStop
from telegram.error import BadRequest

import database as db
from utils.permissions import require_admin, is_admin
from utils.helpers import escape_markdown

logger = logging.getLogger(__name__)

# ردیابی ورود کاربران
join_tracker = {}


async def setjoinlimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم محدودیت ورود کاربران جدید"""
    if not await require_admin(update, context):
        return
    
    chat_id = update.effective_chat.id
    
    if not context.args:
        settings = db.get_settings(chat_id)
        limit = settings.get('join_limit', 0)
        if limit > 0:
            await update.effective_message.reply_text(
                f"🔒 محدودیت ورود فعلی: {limit} کاربر در ساعت\n"
                f"برای تغییر: `/setjoinlimit تعداد`\n"
                f"برای غیرفعال: `/setjoinlimit 0`"
            )
        else:
            await update.effective_message.reply_text(
                "🔒 *تنظیم محدودیت ورود*\n\n"
                "استفاده: `/setjoinlimit تعداد`\n"
                "مثال: `/setjoinlimit 10` (حداکثر ۱۰ کاربر در ساعت)\n"
                "برای غیرفعال: `/setjoinlimit 0`"
            )
        return
    
    try:
        limit = int(context.args[0])
        if limit < 0:
            await update.effective_message.reply_text("❌ تعداد باید مثبت باشد!")
            return
        
        db.set_setting(chat_id, 'join_limit', limit)
        
        if limit == 0:
            await update.effective_message.reply_text("✅ محدودیت ورود غیرفعال شد.")
        else:
            await update.effective_message.reply_text(
                f"✅ محدودیت ورود تنظیم شد: {limit} کاربر در ساعت"
            )
    except ValueError:
        await update.effective_message.reply_text("❌ لطفاً یک عدد وارد کنید!")


async def check_join_security(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بررسی امنیتی ورود کاربران جدید"""
    chat_id = update.effective_chat.id
    
    # دریافت تنظیمات
    settings = db.get_settings(chat_id)
    join_limit = settings.get('join_limit', 0)
    
    if join_limit == 0:
        return
    
    current_hour = time.strftime("%Y%m%d%H")
    key = f"{chat_id}_{current_hour}"
    
    # به‌روزرسانی تعداد ورودها
    if key not in join_tracker:
        join_tracker[key] = 0
    
    join_tracker[key] += 1
    
    # بررسی محدودیت
    if join_tracker[key] > join_limit:
        # کاربر جدید رو اخراج کن
        for member in update.message.new_chat_members:
            try:
                await context.bot.ban_chat_member(chat_id, member.id)
                await context.bot.unban_chat_member(chat_id, member.id)
                logger.info(f"کاربر {member.id} به دلیل محدودیت ورود اخراج شد")
            except Exception as e:
                logger.error(f"خطا در اخراج کاربر: {e}")
        
        await update.effective_message.reply_text(
            f"⚠️ *هشدار امنیتی!*\n\n"
            f"تعداد ورودی‌ها از حد مجاز ({join_limit} کاربر در ساعت) بیشتر شد.\n"
            f"کاربر(های) جدید به طور خودکار اخراج شدند.\n\n"
            f"برای تغییر محدودیت: `/setjoinlimit تعداد`",
            parse_mode="Markdown"
        )
        
        # پاک کردن ترکر برای جلوگیری از اسپم
        join_tracker[key] = 0

        # کاربری که به‌خاطر فلود ورود اخراج شده نباید پیام خوش‌آمدگویی هم بگیره
        raise ApplicationHandlerStop


async def trustbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اضافه کردن یک بات به لیست بات‌های مورد اعتماد، تا هنگام ورود اخراج نشه.
    استفاده: /trustbot @botusername  یا  /trustbot <آیدی عددی بات>"""
    if not await require_admin(update, context):
        return

    if not context.args:
        await update.effective_message.reply_text(
            "استفاده: `/trustbot @botusername` یا `/trustbot آیدی_عددی_بات`\n\n"
            "بعد از این‌کار می‌تونی اون بات رو به گروه اضافه کنی بدون این‌که سیستم امنیتی اخراجش کنه.",
            parse_mode="Markdown",
        )
        return

    chat_id = update.effective_chat.id
    entry = context.args[0].strip().lstrip("@").lower()
    settings = db.get_settings(chat_id)
    current = [b for b in (settings.get("trusted_bots") or "").split() if b]
    if entry in current:
        await update.effective_message.reply_text("✅ این بات از قبل توی لیست مورد اعتماده.")
        return

    current.append(entry)
    db.set_setting(chat_id, "trusted_bots", " ".join(current))
    await update.effective_message.reply_text(
        f"✅ بات `{entry}` به لیست بات‌های مورد اعتماد اضافه شد. حالا می‌تونی اضافه‌ش کنی به گروه.",
        parse_mode="Markdown",
    )


async def untrustbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف یک بات از لیست بات‌های مورد اعتماد."""
    if not await require_admin(update, context):
        return

    if not context.args:
        await update.effective_message.reply_text("استفاده: `/untrustbot @botusername`", parse_mode="Markdown")
        return

    chat_id = update.effective_chat.id
    entry = context.args[0].strip().lstrip("@").lower()
    settings = db.get_settings(chat_id)
    current = [b for b in (settings.get("trusted_bots") or "").split() if b]
    if entry not in current:
        await update.effective_message.reply_text("❌ این بات توی لیست نبود.")
        return

    current.remove(entry)
    db.set_setting(chat_id, "trusted_bots", " ".join(current))
    await update.effective_message.reply_text(f"✅ بات `{entry}` از لیست مورد اعتماد حذف شد.", parse_mode="Markdown")


async def trustedbots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست بات‌های مورد اعتماد این گروه رو نشون می‌ده."""
    if not await require_admin(update, context):
        return

    chat_id = update.effective_chat.id
    settings = db.get_settings(chat_id)
    current = [b for b in (settings.get("trusted_bots") or "").split() if b]
    if not current:
        await update.effective_message.reply_text(
            "📋 هیچ باتی توی لیست مورد اعتماد نیست.\nبرای اضافه کردن: `/trustbot @botusername`",
            parse_mode="Markdown",
        )
        return
    await update.effective_message.reply_text("🤖 بات‌های مورد اعتماد:\n" + "\n".join(f"@{b}" for b in current))


async def check_bot_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تشخیص و حذف بات‌ها هنگام ورود"""
    chat_id = update.effective_chat.id
    
    # دریافت تنظیمات
    settings = db.get_settings(chat_id)
    if not settings.get('security_enabled', 1):
        return

    trusted = {b for b in (settings.get("trusted_bots") or "").split() if b}
    
    for member in update.message.new_chat_members:
        if member.is_bot:
            username = (member.username or "").lower()
            if username in trusted or str(member.id) in trusted:
                continue  # بات مورد اعتماد - دست نزن
            try:
                # اخراج بات
                await context.bot.ban_chat_member(chat_id, member.id)
                await context.bot.unban_chat_member(chat_id, member.id)
                
                await update.effective_message.reply_text(
                    f"🤖 *بات شناسایی و حذف شد!*\n\n"
                    f"نام: {escape_markdown(member.first_name)}\n"
                    f"آیدی: `{member.id}`\n\n"
                    f"⚠️ ورود بات‌ها در این گروه ممنوع است.",
                    parse_mode="Markdown"
                )
                logger.info(f"بات {member.id} به طور خودکار حذف شد")
            except ApplicationHandlerStop:
                raise
            except Exception as e:
                logger.error(f"خطا در حذف بات: {e}")
            else:
                # کاربری که بات تشخیص داده و اخراج شده نباید پیام خوش‌آمدگویی هم بگیره
                raise ApplicationHandlerStop


async def security(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فعال/غیرفعال کردن حالت امنیت"""
    if not await require_admin(update, context):
        return
    
    chat_id = update.effective_chat.id
    
    if not context.args:
        settings = db.get_settings(chat_id)
        status = "فعال" if settings.get('security_enabled', 1) else "غیرفعال"
        await update.effective_message.reply_text(
            f"🔒 *وضعیت امنیت: {status}*\n\n"
            f"برای فعال: `/security on`\n"
            f"برای غیرفعال: `/security off`"
        )
        return
    
    if context.args[0].lower() == 'on':
        db.set_setting(chat_id, 'security_enabled', 1)
        await update.effective_message.reply_text("✅ حالت امنیت فعال شد.")
    elif context.args[0].lower() == 'off':
        db.set_setting(chat_id, 'security_enabled', 0)
        await update.effective_message.reply_text("✅ حالت امنیت غیرفعال شد.")
    else:
        await update.effective_message.reply_text("❌ استفاده: `/security on/off`")


async def securityreport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """گزارش امنیتی گروه"""
    if not await require_admin(update, context):
        return
    
    chat_id = update.effective_chat.id
    
    # آمار کلی
    stats = db.chat_stats(chat_id)
    
    # تعداد ورودهای امروز
    today = time.strftime("%Y%m%d")
    today_joins = 0
    for key, count in join_tracker.items():
        if key.startswith(f"{chat_id}_{today}"):
            today_joins += count
    
    # دریافت تنظیمات امنیتی
    settings = db.get_settings(chat_id)
    join_limit = settings.get('join_limit', 0)
    security_enabled = settings.get('security_enabled', 1)
    
    text = (
        f"🔒 *گزارش امنیتی*\n\n"
        f"👥 کل اعضا: {stats.get('member_count', 0)}\n"
        f"📥 ورودی‌های امروز: {today_joins}\n"
        f"🔢 محدودیت ورود: {join_limit if join_limit > 0 else 'غیرفعال'} کاربر در ساعت\n"
        f"🔐 حالت امنیت: {'فعال' if security_enabled else 'غیرفعال'}\n\n"
        f"*توصیه‌های امنیتی:*\n"
    )
    
    if join_limit == 0:
        text += "⚠️ محدودیت ورود فعال نیست!\n"
    elif today_joins > join_limit * 0.8:
        text += "⚠️ نزدیک به محدودیت ورود هستید!\n"
    
    if not security_enabled:
        text += "⚠️ حالت امنیت غیرفعال است!\n"
    
    text += (
        f"\nبرای تغییر محدودیت: `/setjoinlimit تعداد`\n"
        f"برای تغییر حالت امنیت: `/security on/off`"
    )
    
    await update.effective_message.reply_text(text, parse_mode="Markdown")


def register_security_handlers(app):
    """ثبت هندلرهای امنیتی"""
    app.add_handler(CommandHandler("setjoinlimit", setjoinlimit))
    app.add_handler(CommandHandler("security", security))
    app.add_handler(CommandHandler("securityreport", securityreport))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, check_join_security), group=10)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, check_bot_entry), group=11)