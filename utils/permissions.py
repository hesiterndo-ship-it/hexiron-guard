"""
مدیریت دسترسی‌ها و سطوح کاربری
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes

import database as db
from config import OWNER_ID

logger = logging.getLogger(__name__)

# سطوح دسترسی با اعداد (هر عدد بالاتر = دسترسی بیشتر)
LEVELS = {
    "owner": 5,
    "super_admin": 4,
    "admin": 3,
    "mod": 2,
    "user": 1
}


async def sync_admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> None:
    """
    وضعیت ادمین تلگرام کاربر رو با جدول admins توی دیتابیس هماهنگ می‌کنه.
    این تابع رو قبل از هر چک دسترسیِ سطح‌بندی‌شده (has_permission/get_user_level)
    صدا بزنید، وگرنه کاربری که هنوز هیچ دستور ادمینی نزده (و بنابراین توی دیتابیس
    ثبت نشده) به اشتباه سطح "user" می‌گیره، حتی اگه واقعاً سازنده/ادمین گروه باشه.
    """
    if user_id is None:
        user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if OWNER_ID and user_id == OWNER_ID:
        try:
            db.add_admin(chat_id, user_id, "owner")
        except Exception:
            pass
        return

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status == "creator":
            db.add_admin(chat_id, user_id, "owner")
        elif member.status == "administrator":
            # اگه از قبل توی دیتابیس سطح بالاتری داره (مثلاً super_admin) دست نمی‌زنیم
            if not db.is_admin_user(chat_id, user_id):
                db.add_admin(chat_id, user_id, "admin")
    except Exception as e:
        logger.error(f"Error syncing admin status: {e}")


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> bool:
    """بررسی ادمین بودن کاربر (هم تلگرام، هم دیتابیس، هم OWNER_ID سراسری)"""
    if user_id is None:
        user_id = update.effective_user.id
    
    chat_id = update.effective_chat.id
    
    # اگر کاربر ربات هست
    if user_id == context.bot.id:
        return True

    # صاحب سراسری ربات (از .env) همیشه توی همه گروه‌ها دسترسی کامل داره
    if OWNER_ID and user_id == OWNER_ID:
        try:
            db.add_admin(chat_id, user_id, "owner")
        except Exception:
            pass
        return True
    
    # اول: بررسی ادمین تلگرام
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ["administrator", "creator"]:
            # اگر ادمین تلگرام بود، توی دیتابیس هم ثبتش کن
            try:
                if member.status == "creator":
                    db.add_admin(chat_id, user_id, "owner")
                else:
                    db.add_admin(chat_id, user_id, "admin")
            except Exception as e:
                logger.error(f"Error syncing telegram admin to db: {e}")
            return True
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
    
    # دوم: بررسی ادمین دیتابیس
    try:
        return db.is_admin_user(chat_id, user_id)
    except Exception as e:
        logger.error(f"Error checking db admin: {e}")
        return False


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """بررسی و درخواست دسترسی ادمین"""
    is_admin_user = await is_admin(update, context)
    if not is_admin_user:
        await update.effective_message.reply_text(
            "⛔️ شما دسترسی ادمین ندارید.\n\n"
            "🔹 اگر ادمین گروه هستید، مطمئن شوید ربات را به عنوان ادمین گروه اضافه کرده‌اید.\n"
            "🔹 سپس دوباره /panel را امتحان کنید."
        )
        return False
    return True


def get_user_level(chat_id: int, user_id: int) -> str:
    """دریافت سطح دسترسی کاربر"""
    if OWNER_ID and user_id == OWNER_ID:
        return "owner"
    try:
        level = db.get_admin_level(chat_id, user_id)
        if not level:
            return "user"
        return level
    except Exception as e:
        logger.error(f"Error reading admin level: {e}")
        return "user"


def get_user_level_number(chat_id: int, user_id: int) -> int:
    """دریافت عدد سطح دسترسی کاربر"""
    level = get_user_level(chat_id, user_id)
    return LEVELS.get(level, 1)


def has_permission(chat_id: int, user_id: int, required_level: str) -> bool:
    """بررسی آیا کاربر دسترسی لازم را دارد"""
    user_level_num = get_user_level_number(chat_id, user_id)
    required_level_num = LEVELS.get(required_level, 1)
    return user_level_num >= required_level_num


async def require_level(update: Update, context: ContextTypes.DEFAULT_TYPE, required_level: str) -> bool:
    """بررسی دسترسی بر اساس سطح"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # قبل از چک، وضعیت ادمین تلگرام رو با دیتابیس هماهنگ کن، وگرنه سازنده/ادمینی
    # که هنوز هیچ دستوری نزده به اشتباه "user" شناخته میشه.
    await sync_admin_status(update, context, user_id)

    if has_permission(chat_id, user_id, required_level):
        return True
    
    await update.effective_message.reply_text(
        f"⛔️ شما دسترسی لازم را ندارید.\n"
        f"سطح مورد نیاز: {required_level}\n"
        f"سطح شما: {get_user_level(chat_id, user_id)}"
    )
    return False