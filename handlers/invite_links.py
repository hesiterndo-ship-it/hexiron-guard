"""
لینک دعوت با تگ (برچسب) - برای اینکه بدونی هر عضو از کدوم کمپین/منبع جوین شده.

دستورات (فقط ادمین، فقط داخل گروه):
  /newlink <تگ>            -> لینک دائمی با این تگ می‌سازه
  /newlink <تگ> once        -> لینک یک‌بارمصرف (فقط یک نفر می‌تونه باهاش جوین بشه)
  /links                    -> لیست همه‌ی تگ‌ها و تعداد جوینِ هرکدوم
  /revokelink <تگ>          -> لینک رو غیرفعال می‌کنه (کسی دیگه نمی‌تونه باهاش جوین بشه)

ردیابی جوین: تلگرام موقع عضویت یک کاربر، خودِ لینکی که باهاش اومده رو توی آپدیت
chat_member برمی‌گردونه (update.chat_member.invite_link.invite_link). اون رو با
جدول invite_links مطابقت می‌دیم و شمارنده‌ی همون تگ رو زیاد می‌کنیم.
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, ChatMemberHandler, filters

import database as db
from utils.permissions import require_admin

logger = logging.getLogger(__name__)


async def newlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    chat_id = update.effective_chat.id

    if not context.args:
        await update.effective_message.reply_text(
            "🔗 *ساخت لینک دعوت با تگ*\n\n"
            "استفاده: `/newlink تگ` (لینک دائمی)\n"
            "یا: `/newlink تگ once` (لینک یک‌بارمصرف)\n\n"
            "مثال: `/newlink اینستاگرام`",
            parse_mode="Markdown",
        )
        return

    once = context.args[-1].lower() in ("once", "یکبار", "یک‌بار")
    tag = " ".join(context.args[:-1]) if once else " ".join(context.args)
    tag = tag.strip()
    if not tag:
        await update.effective_message.reply_text("❌ تگ نمی‌تونه خالی باشه.")
        return

    existing = db.get_invite_link_by_tag(chat_id, tag)
    if existing:
        await update.effective_message.reply_text(
            f"⚠️ لینکی با تگ «{tag}» از قبل هست:\n{existing['invite_link']}\n\n"
            f"اگه می‌خوای یکی جدید بسازی، اول `/revokelink {tag}` رو بزن."
        )
        return

    try:
        result = await context.bot.create_chat_invite_link(
            chat_id=chat_id,
            name=tag[:32],  # محدودیت تلگرام برای اسم لینک
            member_limit=1 if once else None,
        )
    except Exception as e:
        logger.exception("ساخت لینک دعوت شکست خورد")
        await update.effective_message.reply_text(
            f"❌ ساخت لینک ممکن نشد ({e}).\nمطمئن شو ربات توی این گروه ادمین با دسترسی «دعوت کاربران» هست."
        )
        return

    db.create_invite_link_record(chat_id, tag, result.invite_link, not once, 1 if once else None,
                                  update.effective_user.id)
    kind = "یک‌بارمصرف" if once else "دائمی"
    await update.effective_message.reply_text(
        f"✅ لینک {kind} با تگ «{tag}» ساخته شد:\n{result.invite_link}\n\n"
        f"با `/links` می‌تونی هر وقت خواستی ببینی چند نفر ازش جوین شدن."
    )


async def links_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    chat_id = update.effective_chat.id
    links = db.get_invite_links_for_chat(chat_id)
    if not links:
        await update.effective_message.reply_text("هنوز هیچ لینک تگ‌داری نساختی. با `/newlink تگ` بساز.")
        return

    lines = ["🔗 *لینک‌های دعوت این گروه:*\n"]
    for link in links:
        kind = "یک‌بارمصرف" if link["member_limit"] else "دائمی"
        lines.append(f"🏷 *{link['tag']}* ({kind}) — {link['join_count']} جوین\n`{link['invite_link']}`\n")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")


async def revoke_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    chat_id = update.effective_chat.id
    if not context.args:
        await update.effective_message.reply_text("استفاده: `/revokelink تگ`", parse_mode="Markdown")
        return
    tag = " ".join(context.args).strip()
    link = db.get_invite_link_by_tag(chat_id, tag)
    if not link:
        await update.effective_message.reply_text(f"❌ لینکی با تگ «{tag}» پیدا نشد.")
        return
    try:
        await context.bot.revoke_chat_invite_link(chat_id, link["invite_link"])
    except Exception:
        logger.warning("revoke_chat_invite_link failed (ممکنه از قبل باطل شده باشه)")
    db.revoke_invite_link_record(link["id"])
    await update.effective_message.reply_text(f"✅ لینک «{tag}» غیرفعال شد.")


async def track_invite_link_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """با هر تغییر وضعیت عضویت (chat_member update) صدا زده می‌شه. فقط وقتی که
    کاربر تازه عضو شده و از طریق یکی از لینک‌های تگ‌دار ما اومده، شمارنده رو زیاد می‌کنه."""
    cmu = update.chat_member
    if not cmu:
        return
    old_status = cmu.old_chat_member.status
    new_status = cmu.new_chat_member.status
    became_member = old_status not in ("member", "administrator", "creator") and new_status in ("member",)
    if not became_member or not cmu.invite_link:
        return

    link = db.get_invite_link_by_url(cmu.invite_link.invite_link)
    if not link:
        return  # عضو از یه لینک دیگه (نه لینک‌های تگ‌دار ما) اومده

    user = cmu.new_chat_member.user
    db.record_invite_link_join(link["id"], user.id, user.username)
    logger.info(f"کاربر {user.id} از طریق تگ «{link['tag']}» جوین شد")


def register_invite_link_handlers(app):
    app.add_handler(CommandHandler("newlink", newlink, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("links", links_list, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("revokelink", revoke_link, filters=filters.ChatType.GROUPS))
    app.add_handler(ChatMemberHandler(track_invite_link_join, ChatMemberHandler.CHAT_MEMBER))
