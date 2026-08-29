"""Handles new members joining/leaving, and awards points per message."""
from telegram import Update
from telegram.ext import ContextTypes

import database as db
from config import POINTS_PER_MESSAGE

DEFAULT_WELCOME = "🎉 خوش آمدی {name} عزیز به گروه {chat_title}!"
DEFAULT_GOODBYE = "👋 {name} از گروه خارج شد."


def _safe_template(template: str, name: str, chat_title: str) -> str:
    """جایگزینی امنِ {name} و {chat_title} بدون استفاده از str.format - چون اگه ادمین یه
    آکولاد اضافه/اشتباه توی متن سفارشی بذاره، str.format() کرش می‌کنه و کل پیام
    اصلاً ارسال نمیشه. این تابع هیچ‌وقت کرش نمی‌کنه."""
    try:
        return template.replace("{name}", name).replace("{chat_title}", chat_title)
    except Exception:
        return DEFAULT_WELCOME.replace("{name}", name).replace("{chat_title}", chat_title)


async def greet_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    settings = db.get_settings(chat.id)
    template = settings.get("welcome_text") or DEFAULT_WELCOME

    for member in update.message.new_chat_members:
        db.upsert_user(chat.id, member.id, member.username, member.first_name)
        name = member.first_name or member.username or "کاربر"
        text = _safe_template(template, name=name, chat_title=chat.title or "")
        await update.effective_message.reply_text(text)


async def farewell_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    left = update.message.left_chat_member
    if left is None:
        return
    settings = db.get_settings(chat.id)
    template = settings.get("goodbye_text") or DEFAULT_GOODBYE
    name = left.first_name or left.username or "کاربر"
    text = _safe_template(template, name=name, chat_title=chat.title or "")
    await update.effective_message.reply_text(text)


async def track_message_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Awards points for regular text messages. Registered as a low-priority
    handler group so anti-spam handlers run first and can delete/skip abusive
    messages before points are awarded."""
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if message is None or user is None or chat is None or chat.type == "private":
        return
    db.upsert_user(chat.id, user.id, user.username, user.first_name)
    db.add_points(chat.id, user.id, POINTS_PER_MESSAGE)
    db.increment_daily_activity(chat.id)