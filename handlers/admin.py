"""
Admin-only moderation and configuration commands.
"""
from datetime import timedelta
import logging
import os
import json
from typing import Optional

from telegram import ChatPermissions, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from utils.permissions import require_admin, get_user_level, require_level
from utils.helpers import extract_target_user_id, escape_markdown

logger = logging.getLogger(__name__)

FULL_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_invite_users=True,
    can_pin_messages=False,
    can_change_info=False,
)


def _get_reason(context) -> str:
    return " ".join(context.args) if context.args else "بدون دلیل ذکر شده"


async def _resolve_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = extract_target_user_id(update, context)
    if target is None:
        await update.effective_message.reply_text(
            "❗️ روی پیام کاربر مورد نظر ریپلای کنید و دوباره دستور را بزنید."
        )
        return None
    if target == context.bot.id:
        await update.effective_message.reply_text(
            "🤖 نمی‌تونی خودِ ربات رو بن/اخراج/بی‌صدا کنی."
        )
        return None
    return target


# ===== دستورات اصلی ادمین =====

async def tagall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تگ کردن همه‌ی کاربرانی که ربات ازشون توی این گروه پیام دیده (جدول users)."""
    if not await require_admin(update, context):
        return

    chat = update.effective_chat
    if chat.type == "private":
        return

    users = db.get_all_users(chat.id)
    if not users:
        await update.effective_message.reply_text("😕 هنوز هیچ کاربری توی دیتابیس این گروه ثبت نشده.")
        return

    reason = _get_reason(context)
    header = f"📣 {escape_markdown(reason)}\n\n" if context.args else "📣 توجه اعضای گروه:\n\n"

    CHUNK_SIZE = 30  # هر پیام حداکثر ۳۰ نفر - جلوگیری از رد شدن از سقف کاراکتر تلگرام
    mentions = []
    for u in users:
        uid = u["user_id"]
        name = escape_markdown(u.get("first_name") or u.get("username") or str(uid))
        mentions.append(f"[{name}](tg://user?id={uid})")

    for i in range(0, len(mentions), CHUNK_SIZE):
        chunk = mentions[i:i + CHUNK_SIZE]
        text = header if i == 0 else ""
        text += " ".join(chunk)
        try:
            await context.bot.send_message(chat.id, text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"tagall chunk failed: {e}")


async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = await _resolve_target(update, context)
    if target is None:
        return
    reason = _get_reason(context)
    count = db.add_warn(update.effective_chat.id, target)
    await update.effective_message.reply_text(
        f"⚠️ اخطار ثبت شد ({count} اخطار). دلیل: {reason}"
    )


async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = await _resolve_target(update, context)
    if target is None:
        return
    count = db.remove_warn(update.effective_chat.id, target)
    await update.effective_message.reply_text(f"✅ یک اخطار حذف شد ({count} اخطار باقی مانده).")


async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = await _resolve_target(update, context)
    if target is None:
        return
    minutes = 10
    if context.args:
        try:
            minutes = int(context.args[0])
        except ValueError:
            pass
    until = update.effective_message.date + timedelta(minutes=minutes)
    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        target,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=until,
    )
    await update.effective_message.reply_text(f"🔇 کاربر به مدت {minutes} دقیقه بی‌صدا شد.")


async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = await _resolve_target(update, context)
    if target is None:
        return
    await context.bot.restrict_chat_member(
        update.effective_chat.id, target, permissions=FULL_PERMISSIONS
    )
    await update.effective_message.reply_text("🔊 صدای کاربر باز شد.")


async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = await _resolve_target(update, context)
    if target is None:
        return
    chat_id = update.effective_chat.id
    await context.bot.ban_chat_member(chat_id, target)
    await context.bot.unban_chat_member(chat_id, target)
    await update.effective_message.reply_text("👢 کاربر از گروه اخراج شد.")


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = await _resolve_target(update, context)
    if target is None:
        return
    reason = _get_reason(context)
    await context.bot.ban_chat_member(update.effective_chat.id, target)
    await update.effective_message.reply_text(f"⛔️ کاربر بن شد. دلیل: {reason}")


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = await _resolve_target(update, context)
    if target is None:
        return
    await context.bot.unban_chat_member(update.effective_chat.id, target)
    await update.effective_message.reply_text("✅ کاربر آنبن شد.")


async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    db.set_setting(update.effective_chat.id, "locked", 1)
    await update.effective_message.reply_text("🔒 گروه قفل شد. فقط ادمین‌ها می‌توانند پیام بفرستند.")


async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    db.set_setting(update.effective_chat.id, "locked", 0)
    await update.effective_message.reply_text("🔓 قفل گروه برداشته شد.")


async def aimod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """روشن/خاموش کردن تشخیص هوشمند فحش/توهین با AI (علاوه بر لیست کلمات ممنوعه)."""
    if not await require_admin(update, context):
        return

    from config import AI_ENABLED
    if not AI_ENABLED:
        await update.effective_message.reply_text(
            "🤖 قابلیت هوش مصنوعی هنوز روی این ربات فعال نشده (ANTHROPIC_API_KEY ست نشده)."
        )
        return

    chat_id = update.effective_chat.id
    settings = db.get_settings(chat_id)
    new_val = 0 if settings.get("ai_moderation") else 1
    db.set_setting(chat_id, "ai_moderation", new_val)
    if new_val:
        await update.effective_message.reply_text(
            "✅ تشخیص هوشمند فحش/توهین فعال شد. از این به بعد، حتی جمله‌هایی که توی لیست کلمات ممنوعه نیستن "
            "ولی توهین‌آمیزن هم شناسایی می‌شن."
        )
    else:
        await update.effective_message.reply_text("❌ تشخیص هوشمند فحش/توهین غیرفعال شد.")


async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not update.effective_message.reply_to_message:
        await update.effective_message.reply_text("❗️ روی پیامی که می‌خواهید پین شود ریپلای کنید.")
        return
    await context.bot.pin_chat_message(
        update.effective_chat.id, update.effective_message.reply_to_message.message_id
    )
    await update.effective_message.reply_text("📌 پیام پین شد.")


async def unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    await context.bot.unpin_all_chat_messages(update.effective_chat.id)
    await update.effective_message.reply_text("📌 پین‌ها برداشته شدند.")


async def setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    text = update.effective_message.text.partition(" ")[2].strip()
    if not text:
        await update.effective_message.reply_text(
            "استفاده: /setwelcome متن خوش‌آمدگویی\n"
            "می‌توانید از {name} و {chat_title} استفاده کنید."
        )
        return
    db.set_setting(update.effective_chat.id, "welcome_text", text)
    await update.effective_message.reply_text("✅ پیام خوش‌آمدگویی تنظیم شد.")


async def setgoodbye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    text = update.effective_message.text.partition(" ")[2].strip()
    if not text:
        await update.effective_message.reply_text("استفاده: /setgoodbye متن خداحافظی")
        return
    db.set_setting(update.effective_chat.id, "goodbye_text", text)
    await update.effective_message.reply_text("✅ پیام خداحافظی تنظیم شد.")


async def setrules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    text = update.effective_message.text.partition(" ")[2].strip()
    if not text:
        await update.effective_message.reply_text("استفاده: /setrules متن قوانین")
        return
    db.set_setting(update.effective_chat.id, "rules_text", text)
    await update.effective_message.reply_text("✅ قوانین گروه ثبت شد.")


async def addbadword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not context.args:
        await update.effective_message.reply_text("استفاده: /addbadword کلمه")
        return
    word = " ".join(context.args)
    db.add_badword(update.effective_chat.id, word)
    await update.effective_message.reply_text(f"✅ «{word}» به لیست کلمات ممنوعه اضافه شد.")


async def removebadword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not context.args:
        await update.effective_message.reply_text("استفاده: /removebadword کلمه")
        return
    word = " ".join(context.args)
    db.remove_badword(update.effective_chat.id, word)
    await update.effective_message.reply_text(f"✅ «{word}» از لیست کلمات ممنوعه حذف شد.")


async def listbadwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    words = db.list_badwords(update.effective_chat.id)
    if not words:
        await update.effective_message.reply_text("لیست کلمات ممنوعه خالی است.")
        return
    await update.effective_message.reply_text("🚫 کلمات ممنوعه:\n" + "\n".join(words))


# ========== مدیریت ادمین‌ها ==========

async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """افزودن ادمین به دیتابیس (فقط ادمین‌های تلگرام می‌تونن استفاده کنن)"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ["administrator", "creator"]:
            await update.effective_message.reply_text("⛔️ فقط ادمین‌های تلگرام می‌تونند از این دستور استفاده کنند.")
            return
    except Exception as e:
        await update.effective_message.reply_text(f"⚠️ خطا در بررسی دسترسی شما: {e}")
        return
    
    target = None
    if update.effective_message.reply_to_message:
        target = update.effective_message.reply_to_message.from_user.id
    elif context.args:
        try:
            target = int(context.args[0])
        except ValueError:
            await update.effective_message.reply_text("⚠️ لطفاً آیدی عددی را وارد کنید یا روی پیام کاربر ریپلای کنید.")
            return
    
    if target is None:
        await update.effective_message.reply_text(
            "❗️ روی پیام کاربری که می‌خواهید ادمین کنید ریپلای کنید.\n"
            "یا: /addadmin 123456789"
        )
        return
    
    db.add_admin(chat_id, target, "admin")
    
    try:
        user = await context.bot.get_chat_member(chat_id, target)
        name = user.user.first_name or user.user.username or str(target)
    except:
        name = str(target)
    
    await update.effective_message.reply_text(f"✅ کاربر {name} به لیست ادمین‌ها اضافه شد.")


async def removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف ادمین از دیتابیس"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ["administrator", "creator"]:
            await update.effective_message.reply_text("⛔️ فقط ادمین‌های تلگرام می‌تونند از این دستور استفاده کنند.")
            return
    except Exception as e:
        await update.effective_message.reply_text(f"⚠️ خطا در بررسی دسترسی شما: {e}")
        return
    
    target = None
    if update.effective_message.reply_to_message:
        target = update.effective_message.reply_to_message.from_user.id
    elif context.args:
        try:
            target = int(context.args[0])
        except ValueError:
            await update.effective_message.reply_text("⚠️ لطفاً آیدی عددی را وارد کنید یا روی پیام کاربر ریپلای کنید.")
            return
    
    if target is None:
        await update.effective_message.reply_text(
            "❗️ روی پیام کاربری که می‌خواهید از ادمینی حذف کنید ریپلای کنید.\n"
            "یا: /removeadmin 123456789"
        )
        return
    
    db.remove_admin(chat_id, target)
    
    try:
        user = await context.bot.get_chat_member(chat_id, target)
        name = user.user.first_name or user.user.username or str(target)
    except:
        name = str(target)
    
    await update.effective_message.reply_text(f"✅ کاربر {name} از لیست ادمین‌ها حذف شد.")


async def setlevel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم سطح دسترسی کاربر (فقط Owner)"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # فقط Owner می‌تونه سطح رو تغییر بده
    if not await require_level(update, context, "owner"):
        return
    
    # بررسی آرگومان‌ها
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "👑 *تنظیم سطح دسترسی*\n\n"
            "استفاده: `/setlevel @username سطح`\n\n"
            "سطوح قابل استفاده:\n"
            "• `owner` - صاحب ربات (دسترسی کامل)\n"
            "• `super_admin` - ادمین ارشد\n"
            "• `admin` - ادمین عادی\n"
            "• `mod` - ناظر (دسترسی محدود)\n"
            "• `user` - کاربر عادی\n\n"
            "مثال: `/setlevel @AdminUser super_admin`",
            parse_mode="Markdown"
        )
        return
    
    # پیدا کردن کاربر هدف
    target_username = context.args[0].replace('@', '')
    level = context.args[1].lower()
    
    # بررسی معتبر بودن سطح
    if level not in ["owner", "super_admin", "admin", "mod", "user"]:
        await update.effective_message.reply_text(
            "❌ سطح نامعتبر!\n"
            "سطوح قابل استفاده: owner, super_admin, admin, mod, user"
        )
        return
    
    # پیدا کردن کاربر از دیتابیس یا تلگرام
    target_id = None
    
    # اگر ریپلای شده بود
    if update.effective_message.reply_to_message:
        target_id = update.effective_message.reply_to_message.from_user.id
    else:
        # جستجو در دیتابیس با یوزرنیم
        users = db.find_user_by_username(chat_id, target_username)
        if users:
            target_id = users[0]['user_id']
    
    if not target_id:
        await update.effective_message.reply_text(
            f"❌ کاربر @{target_username} پیدا نشد.\n"
            "مطمئن شوید کاربر در گروه عضو است یا روی پیامش ریپلای کنید."
        )
        return
    
    # اگر سطح user بود، از دیتابیس حذفش کن
    if level == "user":
        db.remove_admin(chat_id, target_id)
        await update.effective_message.reply_text(
            f"✅ سطح دسترسی کاربر @{escape_markdown(target_username)} به **user** تغییر یافت.",
            parse_mode="Markdown"
        )
    else:
        db.add_admin(chat_id, target_id, level)
        await update.effective_message.reply_text(
            f"✅ سطح دسترسی کاربر @{escape_markdown(target_username)} به **{escape_markdown(level)}** تغییر یافت.",
            parse_mode="Markdown"
        )


async def mypermissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش سطح دسترسی خود"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    level = get_user_level(chat_id, user_id)
    level_names = {
        "owner": "👑 صاحب ربات (دسترسی کامل)",
        "super_admin": "⭐️ ادمین ارشد",
        "admin": "🛡️ ادمین",
        "mod": "🔰 ناظر",
        "user": "👤 کاربر عادی"
    }
    
    # دریافت اطلاعات کاربر
    user = await context.bot.get_chat_member(chat_id, user_id)
    name = user.user.first_name or user.user.username or str(user_id)
    
    # دریافت تعداد دستورات قابل استفاده
    if level == "owner":
        commands = "همه دستورات"
    elif level == "super_admin":
        commands = "همه دستورات (به جز مدیریت Owner)"
    elif level == "admin":
        commands = "warn, mute, ban, kick, lock, pin, setwelcome, addbadword"
    elif level == "mod":
        commands = "warn, mute, kick, pin"
    else:
        commands = "فقط دستورات عمومی (start, help, stats, mylevel, top)"
    
    await update.effective_message.reply_text(
        f"👤 *اطلاعات دسترسی شما*\n\n"
        f"نام: {escape_markdown(name)}\n"
        f"سطح: {level_names.get(level, 'ناشناخته')}\n"
        f"دستورات قابل استفاده: {commands}\n\n"
        f"برای مشاهده لیست کامل دستورات: /help",
        parse_mode="Markdown"
    )


# ========== IMPORT BADWORDS ==========

async def quicksetup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """راه‌اندازی سریع گروه جدید: قوانین + خوش‌آمدگویی + خداحافظی + کلمات ممنوعه رو
    یک‌جا از فایل‌های آماده (welcome_template.txt, goodbye_template.txt, rules_template.txt,
    badwords.txt - همه توی ریشه‌ی پروژه) روی گروه فعلی اعمال می‌کنه، تا لازم نباشه هر بار
    برای هر گروه جدید دستی تایپ بشه. فایل‌ها رو خودت با ویرایشگر متن روی سرور می‌تونی عوض کنی."""
    if not await require_admin(update, context):
        return

    chat_id = update.effective_chat.id
    base_dir = os.path.join(os.path.dirname(__file__), '..')
    applied, skipped = [], []

    template_map = [
        ("welcome_template.txt", "welcome_text", "خوش‌آمدگویی"),
        ("goodbye_template.txt", "goodbye_text", "خداحافظی"),
        ("rules_template.txt", "rules_text", "قوانین"),
    ]
    for filename, field, label in template_map:
        path = os.path.join(base_dir, filename)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if content:
                db.set_setting(chat_id, field, content)
                applied.append(label)
                continue
        skipped.append(label)

    # کلمات ممنوعه از همون badwords.txt که /importbadwords هم استفاده می‌کنه
    badwords_path = os.path.join(base_dir, 'badwords.txt')
    badword_count = 0
    if os.path.exists(badwords_path):
        with open(badwords_path, 'r', encoding='utf-8') as f:
            for word in f.read().splitlines():
                word = word.strip()
                if word and not word.startswith('#'):
                    db.add_badword(chat_id, word)
                    badword_count += 1
        applied.append(f"کلمات ممنوعه ({badword_count} کلمه)")
    else:
        skipped.append("کلمات ممنوعه")

    db.log_admin_action(update.effective_user.id, "quicksetup", f"chat={chat_id} applied={applied}")

    text = "⚡️ *راه‌اندازی سریع گروه*\n\n"
    if applied:
        text += "✅ اعمال شد: " + "، ".join(applied) + "\n"
    if skipped:
        text += "⚠️ فایل پیدا نشد یا خالی بود: " + "، ".join(skipped) + "\n"
        text += "\nبرای این موارد، یا فایل‌های *_template.txt رو توی ریشه‌ی پروژه بساز، یا دستی با /setwelcome و امثالش تنظیم کن."
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def import_badwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وارد کردن کلمات ممنوعه از فایل badwords.txt"""
    if not await require_admin(update, context):
        return
    
    chat_id = update.effective_chat.id
    try:
        file_path = os.path.join(os.path.dirname(__file__), '..', 'badwords.txt')
        
        # بررسی وجود فایل
        if not os.path.exists(file_path):
            await update.effective_message.reply_text(
                f"⚠️ فایل badwords.txt پیدا نشد!\n"
                f"لطفاً فایل رو در مسیر زیر ایجاد کنید:\n"
                f"{os.path.abspath(file_path)}"
            )
            return
        
        with open(file_path, 'r', encoding='utf-8') as f:
            words = f.read().splitlines()
        
        count = 0
        for word in words:
            word = word.strip()
            if word and not word.startswith('#'):
                db.add_badword(chat_id, word)
                count += 1
        
        await update.effective_message.reply_text(
            f"✅ {count} کلمه از فایل badwords.txt به لیست ممنوعه اضافه شد.\n\n"
            f"برای دیدن لیست: /listbadwords"
        )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ خطا در ایمپورت کلمات: {e}")


# ========== LIST ADMINS ==========

async def listadmins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست ادمین‌های گروه"""
    chat_id = update.effective_chat.id
    
    # بررسی دسترسی: فقط اعضای گروه می‌تونند ببینند
    try:
        member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
        if member.status == "left":
            await update.effective_message.reply_text("⚠️ شما عضو این گروه نیستید.")
            return
    except Exception as e:
        await update.effective_message.reply_text(f"⚠️ خطا در بررسی عضویت: {e}")
        return
    
    admins = db.get_admins(chat_id)
    
    if not admins:
        await update.effective_message.reply_text("👑 لیست ادمین‌ها خالی است.")
        return
    
    admin_list = []
    level_emojis = {
        "owner": "👑",
        "super_admin": "⭐️",
        "admin": "🛡️",
        "mod": "🔰"
    }
    
    for admin in admins:
        user_id = admin['user_id']
        level = admin.get('level', 'admin')
        
        # تلاش برای دریافت اطلاعات کاربر از تلگرام
        try:
            user = await context.bot.get_chat_member(chat_id, user_id)
            name = user.user.first_name or user.user.username or str(user_id)
            if user.user.username:
                name = f"{name} (@{user.user.username})"
        except:
            name = f"User {user_id}"
        
        emoji = level_emojis.get(level, "🔹")
        admin_list.append(f"{emoji} {name} - سطح: `{level}`")
    
    # اضافه کردن ادمین‌های تلگرام که در دیتابیس نیستند
    try:
        chat_admins = await context.bot.get_chat_administrators(chat_id)
        for admin in chat_admins:
            user_id = admin.user.id
            # اگر کاربر در دیتابیس نیست ولی ادمین تلگرام است
            if not db.is_admin_user(chat_id, user_id):
                name = admin.user.first_name or admin.user.username or str(user_id)
                if admin.user.username:
                    name = f"{name} (@{admin.user.username})"
                admin_list.append(f"🤖 {name} - سطح: `telegram_admin`")
    except:
        pass
    
    if not admin_list:
        await update.effective_message.reply_text("👑 هیچ ادمینی پیدا نشد.")
        return
    
    message = "👑 *لیست ادمین‌های گروه:*\n\n"
    message += "\n".join(admin_list)
    
    # اگر لیست طولانی بود، به چند بخش تقسیم کن
    if len(message) > 4000:
        parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for part in parts:
            await update.effective_message.reply_text(part, parse_mode="Markdown")
    else:
        await update.effective_message.reply_text(message, parse_mode="Markdown")


# ========== توابع کمکی برای compatibility ==========

async def get_admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تابع کمکی برای نمایش لیست ادمین‌ها (alias)"""
    await listadmins(update, context)