"""
سیستم گزارش‌گیری پیشرفته
"""
import logging
import time
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import database as db
from utils.permissions import require_admin, is_admin
from utils.helpers import escape_markdown

logger = logging.getLogger(__name__)


def format_time(timestamp):
    if not timestamp:
        return "نامشخص"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def get_time_range(period: str):
    now = int(time.time())
    if period == "daily":
        start = now - 86400
    elif period == "weekly":
        start = now - 604800
    elif period == "monthly":
        start = now - 2592000
    else:
        start = 0
    return start, now


async def dailyreport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(update, context, user_id):
        await update.effective_message.reply_text("⛔️ فقط ادمین‌ها دسترسی دارند.")
        return
    
    start, end = get_time_range("daily")
    report = generate_report(chat_id, start, end)
    
    await update.effective_message.reply_text(
        f"📊 *گزارش روزانه*\n"
        f"📅 تاریخ: {datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"{report}",
        parse_mode="Markdown"
    )


async def weeklyreport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(update, context, user_id):
        await update.effective_message.reply_text("⛔️ فقط ادمین‌ها دسترسی دارند.")
        return
    
    start, end = get_time_range("weekly")
    report = generate_report(chat_id, start, end)
    
    await update.effective_message.reply_text(
        f"📊 *گزارش هفتگی*\n"
        f"📅 از {datetime.fromtimestamp(start).strftime('%Y-%m-%d')} تا {datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"{report}",
        parse_mode="Markdown"
    )


async def monthlyreport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(update, context, user_id):
        await update.effective_message.reply_text("⛔️ فقط ادمین‌ها دسترسی دارند.")
        return
    
    start, end = get_time_range("monthly")
    report = generate_report(chat_id, start, end)
    
    await update.effective_message.reply_text(
        f"📊 *گزارش ماهانه*\n"
        f"📅 از {datetime.fromtimestamp(start).strftime('%Y-%m-%d')} تا {datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"{report}",
        parse_mode="Markdown"
    )


async def userreport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(update, context, user_id):
        await update.effective_message.reply_text("⛔️ فقط ادمین‌ها دسترسی دارند.")
        return
    
    target_id = None
    target_name = "نامشخص"
    
    if update.effective_message.reply_to_message:
        target_id = update.effective_message.reply_to_message.from_user.id
        target_name = update.effective_message.reply_to_message.from_user.first_name or "کاربر"
    elif context.args:
        username = context.args[0].replace('@', '')
        users = db.find_user_by_username(chat_id, username)
        if users:
            target_id = users[0]['user_id']
            target_name = users[0].get('first_name', username)
        else:
            await update.effective_message.reply_text(
                f"❌ کاربر @{username} پیدا نشد."
            )
            return
    else:
        await update.effective_message.reply_text(
            "❗️ روی پیام کاربر ریپلای کنید یا /userreport @username"
        )
        return
    
    user_data = db.get_user_by_id(chat_id, target_id)
    if not user_data:
        await update.effective_message.reply_text("❌ کاربر در دیتابیس ثبت نشده است.")
        return
    
    rank = db.user_rank(chat_id, target_id)
    
    text = (
        f"👤 *گزارش کاربر*\n\n"
        f"نام: {escape_markdown(user_data.get('first_name', 'نامشخص'))}\n"
        f"یوزرنیم: @{escape_markdown(user_data.get('username', 'ندارد'))}\n"
        f"آیدی: `{target_id}`\n"
        f"تاریخ عضویت: {format_time(user_data.get('joined_at'))}\n\n"
        f"⭐️ امتیاز: {user_data.get('points', 0)}\n"
        f"🏅 رتبه: {rank if rank > 0 else 'ثبت نشده'}\n"
        f"⚠️ اخطارها: {user_data.get('warns', 0)}\n"
    )
    
    await update.effective_message.reply_text(text, parse_mode="Markdown")


def generate_report(chat_id: int, start_time: int, end_time: int) -> str:
    stats = db.chat_stats(chat_id)
    
    with db.get_conn() as conn:
        new_users = conn.execute(
            "SELECT COUNT(*) FROM users WHERE chat_id=? AND joined_at BETWEEN ? AND ?",
            (chat_id, start_time, end_time)
        ).fetchone()[0]
        
        new_warns = conn.execute(
            "SELECT COUNT(*) FROM users WHERE chat_id=? AND warns > 0 AND joined_at BETWEEN ? AND ?",
            (chat_id, start_time, end_time)
        ).fetchone()[0]
    
    text = (
        f"📊 *آمار کلی*\n"
        f"👥 کل اعضا: {stats.get('member_count', 0)}\n"
        f"🆕 کاربران جدید: {new_users}\n"
        f"⭐️ مجموع امتیازات: {stats.get('total_points', 0)}\n"
        f"⚠️ مجموع اخطارها: {stats.get('total_warns', 0)}\n"
        f"🆕 اخطارهای جدید: {new_warns}\n\n"
        f"🏅 *۵ کاربر برتر:*\n"
    )
    
    top = db.top_users(chat_id, 5)
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, user in enumerate(top):
        name = escape_markdown(user.get('first_name', 'کاربر'))[:15]
        text += f"{medals[i]} {name} — {user.get('points', 0)} امتیاز\n"
    
    return text


def register_report_handlers(app):
    app.add_handler(CommandHandler("dailyreport", dailyreport))
    app.add_handler(CommandHandler("weeklyreport", weeklyreport))
    app.add_handler(CommandHandler("monthlyreport", monthlyreport))
    app.add_handler(CommandHandler("userreport", userreport))