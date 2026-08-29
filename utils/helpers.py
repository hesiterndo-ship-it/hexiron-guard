"""
توابع کمکی عمومی
"""
import re
import time
from typing import Optional
from telegram import Update, User
from telegram.ext import ContextTypes


def extract_target_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """استخراج آیدی کاربر هدف از ریپلای یا آرگومان‌ها"""
    message = update.effective_message
    
    if message.reply_to_message:
        return message.reply_to_message.from_user.id
    
    if context.args:
        try:
            return int(context.args[0])
        except ValueError:
            pass
    
    return None


def get_user_display_name(user: User) -> str:
    """دریافت نام نمایشی کاربر"""
    if user.first_name:
        return user.first_name
    if user.username:
        return f"@{user.username}"
    return str(user.id)


def is_private_chat(update: Update) -> bool:
    """بررسی چت خصوصی"""
    return update.effective_chat.type == "private"


def is_group_chat(update: Update) -> bool:
    """بررسی چت گروهی"""
    return update.effective_chat.type in ["group", "supergroup"]


_MARKDOWN_SPECIAL_CHARS = r"_*`["


def escape_markdown(text) -> str:
    """فرار دادن کاراکترهای خاص Markdown (نسخه‌ی قدیمی/legacy که تلگرام با parse_mode='Markdown'
    استفاده می‌کنه) تا متن‌های دینامیک (یوزرنیم، نام، لینک گروه، سطح دسترسی و ...) باعث
    خطای 'Can't parse entities' نشن. اگه متن None باشه، یک em dash برمی‌گردونه.
    """
    if text is None:
        return "—"
    text = str(text)
    for ch in _MARKDOWN_SPECIAL_CHARS:
        text = text.replace(ch, "\\" + ch)
    return text