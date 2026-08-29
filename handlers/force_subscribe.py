"""
سیستم عضویت اجباری در کانال‌ها
"""
import logging
from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes, CommandHandler
from telegram.error import BadRequest

import database as db
from utils.permissions import require_admin, is_admin

logger = logging.getLogger(__name__)


async def setforce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم کانال‌های اجباری"""
    if not await require_admin(update, context):
        return
    
    chat_id = update.effective_chat.id
    
    if not context.args:
        # نمایش کانال‌های فعلی
        settings = db.get_settings(chat_id)
        channels = settings.get('force_channels', '')
        if channels:
            await update.effective_message.reply_text(
                f"📢 *کانال‌های اجباری فعلی:*\n\n{channels}\n\n"
                f"برای تغییر: /setforce @channel1 @channel2"
            )
        else:
            await update.effective_message.reply_text(
                "📢 *تنظیم کانال‌های اجباری*\n\n"
                "استفاده: `/setforce @channel1 @channel2`\n\n"
                "مثال: `/setforce @my_channel @my_second_channel`\n\n"
                "برای غیرفعال کردن: `/setforce off`"
            )
        return
    
    # غیرفعال کردن
    if context.args[0].lower() == 'off':
        db.set_setting(chat_id, 'force_channels', '')
        await update.effective_message.reply_text("✅ عضویت اجباری غیرفعال شد.")
        return
    
    # تنظیم کانال‌ها
    channels = ' '.join(context.args)
    db.set_setting(chat_id, 'force_channels', channels)
    await update.effective_message.reply_text(
        f"✅ کانال‌های اجباری تنظیم شد:\n\n{channels}\n\n"
        f"کاربران برای ارسال پیام باید عضو این کانال‌ها باشند."
    )


async def removeforce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف یک کانال خاص از لیست عضویت اجباری، بدون پاک کردن بقیه.
    استفاده: /removeforce @channel"""
    if not await require_admin(update, context):
        return

    chat_id = update.effective_chat.id
    if not context.args:
        await update.effective_message.reply_text("استفاده: `/removeforce @channel`", parse_mode="Markdown")
        return

    target = context.args[0].strip()
    settings = db.get_settings(chat_id)
    current = settings.get('force_channels', '') or ''
    channels = [c for c in current.split() if c.lower() != target.lower()]

    if len(channels) == len(current.split()):
        await update.effective_message.reply_text(f"❌ کانال {target} توی لیست نبود.")
        return

    db.set_setting(chat_id, 'force_channels', ' '.join(channels))
    if channels:
        await update.effective_message.reply_text(f"✅ کانال {target} حذف شد.\n\nکانال‌های باقی‌مانده:\n{' '.join(channels)}")
    else:
        await update.effective_message.reply_text(f"✅ کانال {target} حذف شد و دیگه کانالی توی لیست نمونده (عضویت اجباری غیرفعال شد).")


async def forcelinks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لینک دعوت هر کانال اجباریِ این گروه رو برمی‌گردونه."""
    if not await require_admin(update, context):
        return

    chat_id = update.effective_chat.id
    settings = db.get_settings(chat_id)
    channels = (settings.get('force_channels', '') or '').split()
    if not channels:
        await update.effective_message.reply_text("📢 هیچ کانال اجباری‌ای برای این گروه تنظیم نشده.")
        return

    lines = ["🔗 *لینک کانال‌های اجباری:*\n"]
    for channel in channels:
        try:
            link = await context.bot.export_chat_invite_link(channel)
        except Exception:
            # اگه ربات ادمین کانال نباشه export_chat_invite_link خطا می‌ده -
            # برای کانال‌های عمومی (@username) لینک t.me هم همیشه معتبره
            if channel.startswith('@'):
                link = f"https://t.me/{channel[1:]}"
            else:
                link = "⚠️ در دسترس نیست (ربات ادمین کانال نیست)"
        lines.append(f"📢 {channel}: {link}")

    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")


async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بررسی خودکار عضویت کاربران"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # اگه از پنل کاربر این قابلیت خاموش شده باشه، ردش کن
    if not db.is_feature_enabled(chat_id, "force_subscribe"):
        return
    
    # اگر ادمین است، نادیده بگیر
    if await is_admin(update, context, user_id):
        return
    
    # دریافت کانال‌های اجباری
    settings = db.get_settings(chat_id)
    channels = settings.get('force_channels', '')
    
    if not channels:
        return
    
    # چک کردن عضویت در هر کانال
    for channel in channels.split():
        channel = channel.strip()
        if not channel.startswith('@'):
            continue
        
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status in ['left', 'kicked']:
                # کاربر عضو نیست
                await update.effective_message.delete()
                await update.effective_message.reply_text(
                    f"⛔️ برای ارسال پیام در این گروه، ابتدا در کانال زیر عضو شوید:\n\n"
                    f"📢 {channel}\n\n"
                    f"سپس دوباره پیام خود را ارسال کنید."
                )
                # جلوی هندلرهای بعدی (فیلتر کلمات/لینک/فلاد/امتیازدهی) رو بگیر
                # چون پیام همین الان حذف شد و نباید دوباره پردازش بشه.
                raise ApplicationHandlerStop
        except BadRequest:
            # کانال وجود ندارد یا ربات عضو نیست
            await update.effective_message.reply_text(
                f"⚠️ ربات به کانال {channel} دسترسی ندارد.\n"
                f"لطفاً ربات را به عنوان ادمین به کانال اضافه کنید."
            )
            return
        except Exception as e:
            logger.error(f"Error checking membership: {e}")
            return


async def force_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش وضعیت عضویت اجباری"""
    chat_id = update.effective_chat.id
    settings = db.get_settings(chat_id)
    channels = settings.get('force_channels', '')
    
    if not channels:
        await update.effective_message.reply_text("📢 عضویت اجباری غیرفعال است.")
        return
    
    # چک کردن عضویت کاربر
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or update.effective_user.username or 'کاربر'
    
    text = f"📢 *وضعیت عضویت اجباری*\n\n"
    text += f"👤 {user_name}\n\n"
    
    all_member = True
    for channel in channels.split():
        channel = channel.strip()
        if not channel.startswith('@'):
            continue
        
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status in ['left', 'kicked']:
                text += f"❌ {channel}: عضو نیستید\n"
                all_member = False
            else:
                text += f"✅ {channel}: عضو هستید\n"
        except:
            text += f"❓ {channel}: وضعیت نامشخص\n"
            all_member = False
    
    if all_member:
        text += f"\n✅ شما در همه کانال‌ها عضو هستید!"
    else:
        text += f"\n⛔️ لطفاً در کانال‌های بالا عضو شوید."
    
    await update.effective_message.reply_text(text, parse_mode="Markdown")


def register_force_handlers(app):
    """ثبت هندلرهای عضویت اجباری"""
    app.add_handler(CommandHandler("setforce", setforce))
    app.add_handler(CommandHandler("removeforce", removeforce))
    app.add_handler(CommandHandler("forcelinks", forcelinks))
    app.add_handler(CommandHandler("forcestatus", force_status))