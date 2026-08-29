"""
سیستم تیکت پشتیبانی
"""
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import database as db
from utils.permissions import is_admin, require_admin, has_permission
from utils.helpers import escape_markdown

logger = logging.getLogger(__name__)

PRIORITY_EMOJIS = {
    "low": "🟢",
    "medium": "🟡",
    "high": "🔴",
    "critical": "🔥"
}

PRIORITY_NAMES = {
    "low": "کم",
    "medium": "متوسط",
    "high": "بالا",
    "critical": "بحرانی"
}

STATUS_NAMES = {
    "open": "🟢 باز",
    "in_progress": "🟡 در حال بررسی",
    "closed": "🔴 بسته شده"
}


def get_priority_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🟢 کم", callback_data="priority_low"),
            InlineKeyboardButton("🟡 متوسط", callback_data="priority_medium"),
        ],
        [
            InlineKeyboardButton("🔴 بالا", callback_data="priority_high"),
            InlineKeyboardButton("🔥 بحرانی", callback_data="priority_critical"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if update.effective_chat.type != "private" and not db.is_feature_enabled(chat_id, "ticket_system"):
        await update.effective_message.reply_text("⛔️ سیستم تیکت برای این گروه غیرفعال شده.")
        return
    
    if update.effective_chat.type == "private":
        await update.effective_message.reply_text(
            "📝 *ارسال تیکت*\n\n"
            "لطفاً موضوع تیکت و پیام خود را بنویسید:\n"
            "/ticket موضوع|پیام\n\n"
            "مثال: `/ticket مشکل دسترسی|سلام، من نمی‌تونم پیام بفرستم!`",
            parse_mode="Markdown"
        )
        return
    
    if not context.args:
        await update.effective_message.reply_text(
            "📝 *ارسال تیکت*\n\n"
            "لطفاً موضوع و پیام خود را بنویسید:\n"
            "/ticket موضوع|پیام\n\n"
            "مثال: `/ticket مشکل دسترسی|سلام، من نمی‌تونم پیام بفرستم!`",
            parse_mode="Markdown"
        )
        return
    
    ticket_text = " ".join(context.args)
    if "|" not in ticket_text:
        await update.effective_message.reply_text(
            "❌ فرمت اشتباه!\n"
            "استفاده: `/ticket موضوع|پیام`"
        )
        return
    
    subject, message = ticket_text.split("|", 1)
    subject = subject.strip()
    message = message.strip()
    
    if not subject or not message:
        await update.effective_message.reply_text("❌ موضوع و پیام نمی‌توانند خالی باشند!")
        return
    
    context.user_data['ticket_subject'] = subject
    context.user_data['ticket_message'] = message
    
    await update.effective_message.reply_text(
        f"📝 *موضوع:* {escape_markdown(subject)}\n"
        f"📄 *پیام:* {escape_markdown(message[:100])}{'...' if len(message) > 100 else ''}\n\n"
        "🔹 اولویت تیکت را انتخاب کنید:",
        reply_markup=get_priority_keyboard(),
        parse_mode="Markdown"
    )


async def ticket_priority_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    priority = query.data.replace("priority_", "")
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    subject = context.user_data.get('ticket_subject', 'بدون موضوع')
    message = context.user_data.get('ticket_message', 'بدون پیام')
    
    ticket_id = db.create_ticket(chat_id, user_id, subject, message, priority)
    
    await query.edit_message_text(
        f"✅ *تیکت شما با موفقیت ثبت شد!*\n\n"
        f"🆔 شماره تیکت: `{ticket_id}`\n"
        f"📝 موضوع: {escape_markdown(subject)}\n"
        f"🔰 اولویت: {PRIORITY_EMOJIS[priority]} {PRIORITY_NAMES[priority]}\n\n"
        f"ادمین‌ها به زودی پاسخ خواهند داد.\n"
        f"برای مشاهده تیکت‌های خود: /mytickets",
        parse_mode="Markdown"
    )
    
    admins = db.get_admins(chat_id)
    if admins:
        try:
            for admin in admins[:3]:
                try:
                    await context.bot.send_message(
                        admin['user_id'],
                        f"🆕 *تیکت جدید!*\n\n"
                        f"🆔 شماره: `{ticket_id}`\n"
                        f"👤 کاربر: {escape_markdown(update.effective_user.first_name)}\n"
                        f"📝 موضوع: {escape_markdown(subject)}\n"
                        f"🔰 اولویت: {PRIORITY_EMOJIS[priority]} {PRIORITY_NAMES[priority]}\n\n"
                        f"برای پاسخ: /reply {ticket_id} متن",
                        parse_mode="Markdown"
                    )
                except:
                    pass
        except:
            pass


async def mytickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    tickets = db.get_user_tickets(chat_id, user_id)
    
    if not tickets:
        await update.effective_message.reply_text("📭 شما هیچ تیکتی ندارید.")
        return
    
    text = "📋 *لیست تیکت‌های شما:*\n\n"
    for t in tickets[:10]:
        status = STATUS_NAMES.get(t['status'], t['status'])
        priority_emoji = PRIORITY_EMOJIS.get(t['priority'], '🔵')
        text += f"🆔 `{t['id']}` - {priority_emoji} {escape_markdown(t['subject'][:30])}\n"
        text += f"   وضعیت: {status}\n\n"
    
    if len(tickets) > 10:
        text += f"... و {len(tickets)-10} تیکت دیگر"
    
    text += "\nبرای مشاهده جزئیات: /ticketinfo [ID]"
    
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def ticketinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.effective_message.reply_text("❗️ شماره تیکت را وارد کنید: /ticketinfo [ID]")
        return
    
    try:
        ticket_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ شماره تیکت نامعتبر!")
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    ticket = db.get_ticket(chat_id, ticket_id)
    
    if not ticket:
        await update.effective_message.reply_text("❌ تیکت پیدا نشد!")
        return
    
    if ticket['user_id'] != user_id and not await is_admin(update, context):
        await update.effective_message.reply_text("⛔️ شما دسترسی به این تیکت ندارید.")
        return
    
    text = f"📋 *جزئیات تیکت #{ticket_id}*\n\n"
    text += f"📝 موضوع: {escape_markdown(ticket['subject'])}\n"
    text += f"📄 پیام: {escape_markdown(ticket['message'])}\n"
    text += f"🔰 اولویت: {PRIORITY_EMOJIS.get(ticket['priority'], '🟡')} {PRIORITY_NAMES.get(ticket['priority'], 'متوسط')}\n"
    text += f"📊 وضعیت: {STATUS_NAMES.get(ticket['status'], ticket['status'])}\n"
    
    if ticket.get('replies'):
        try:
            replies = json.loads(ticket['replies'])
            if replies:
                text += f"\n💬 *پاسخ‌ها:*\n"
                for reply in replies[-5:]:
                    admin_name = f"ادمین {reply['admin_id']}"
                    text += f"• {admin_name}: {escape_markdown(reply['reply'][:50])}...\n"
        except:
            pass
    
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(update, context):
        await update.effective_message.reply_text("⛔️ فقط ادمین‌ها می‌توانند به تیکت‌ها پاسخ دهند.")
        return
    
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "❗️ استفاده: /reply [ID] [متن]\n"
            "مثال: `/reply 5 مشکل شما برطرف شد`"
        )
        return
    
    try:
        ticket_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ شماره تیکت نامعتبر!")
        return
    
    reply_text = " ".join(context.args[1:])
    
    if not reply_text:
        await update.effective_message.reply_text("❌ متن پاسخ نمی‌تواند خالی باشد!")
        return
    
    ticket = db.get_ticket(chat_id, ticket_id)
    if not ticket:
        await update.effective_message.reply_text("❌ تیکت پیدا نشد!")
        return
    
    if ticket['status'] == 'closed':
        await update.effective_message.reply_text("❌ این تیکت قبلاً بسته شده است.")
        return
    
    db.add_ticket_reply(chat_id, ticket_id, user_id, reply_text)
    
    await update.effective_message.reply_text(f"✅ پاسخ شما به تیکت #{ticket_id} ثبت شد.")
    
    try:
        await context.bot.send_message(
            ticket['user_id'],
            f"💬 *پاسخ به تیکت #{ticket_id}*\n\n"
            f"📝 موضوع: {escape_markdown(ticket['subject'])}\n"
            f"📄 پاسخ: {escape_markdown(reply_text)}\n\n"
            f"برای مشاهده جزئیات: /ticketinfo {ticket_id}",
            parse_mode="Markdown"
        )
    except:
        pass


async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not context.args:
        await update.effective_message.reply_text("❗️ شماره تیکت را وارد کنید: /close [ID]")
        return
    
    try:
        ticket_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ شماره تیکت نامعتبر!")
        return
    
    ticket = db.get_ticket(chat_id, ticket_id)
    
    if not ticket:
        await update.effective_message.reply_text("❌ تیکت پیدا نشد!")
        return
    
    if ticket['user_id'] != user_id and not await is_admin(update, context):
        await update.effective_message.reply_text("⛔️ شما دسترسی به این تیکت ندارید.")
        return
    
    if ticket['status'] == 'closed':
        await update.effective_message.reply_text("❌ این تیکت قبلاً بسته شده است.")
        return
    
    db.close_ticket(chat_id, ticket_id)
    await update.effective_message.reply_text(f"✅ تیکت #{ticket_id} بسته شد.")


async def tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(update, context):
        await update.effective_message.reply_text("⛔️ فقط ادمین‌ها دسترسی دارند.")
        return
    
    tickets_list = db.get_all_tickets(chat_id)
    stats = db.get_ticket_stats(chat_id)
    
    if not tickets_list:
        await update.effective_message.reply_text("📭 هیچ تیکتی ثبت نشده است.")
        return
    
    text = "🎫 *مدیریت تیکت‌ها*\n\n"
    text += f"📊 آمار: 🟢 {stats['open']} باز | 🟡 {stats['in_progress']} در حال بررسی | 🔴 {stats['closed']} بسته\n\n"
    
    for t in tickets_list[:10]:
        status_emoji = "🟢" if t['status'] == 'open' else "🟡" if t['status'] == 'in_progress' else "🔴"
        priority_emoji = PRIORITY_EMOJIS.get(t['priority'], '🔵')
        name = escape_markdown(t.get('first_name', f"کاربر {t['user_id']}"))[:15]
        
        text += f"🆔 `{t['id']}` - {priority_emoji} {escape_markdown(t['subject'][:25])}\n"
        text += f"   👤 {name} | {status_emoji} {STATUS_NAMES.get(t['status'], t['status'])}\n\n"
    
    if len(tickets_list) > 10:
        text += f"... و {len(tickets_list)-10} تیکت دیگر\n"
    
    text += "\n📝 برای پاسخ: /reply [ID] [متن]"
    
    await update.effective_message.reply_text(text, parse_mode="Markdown")


def register_ticket_handlers(app):
    app.add_handler(CommandHandler("ticket", ticket))
    app.add_handler(CommandHandler("mytickets", mytickets))
    app.add_handler(CommandHandler("ticketinfo", ticketinfo))
    app.add_handler(CommandHandler("reply", reply))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("tickets", tickets))
    app.add_handler(CallbackQueryHandler(ticket_priority_callback, pattern="^priority_"))