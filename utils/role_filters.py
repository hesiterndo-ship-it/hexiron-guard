"""
فیلترهای نقش‌ها برای python-telegram-bot
"""
import database as db
from config import OWNER_ID
from telegram.ext import filters


class _PanelAdmin(filters.UpdateFilter):
    """فیلتری که فقط کاربرانی که ادمین پنل هستند یا OWNER_ID را قبول می‌کند"""

    def filter(self, update):
        user = update.effective_user
        if not user:
            return False

        user_id = user.id

        # OWNER_ID همیشه دسترسی دارد
        if user_id == OWNER_ID:
            return True

        # بررسی در دیتابیس
        return db.is_panel_admin(user_id)


class _ActiveSubscriber(filters.UpdateFilter):
    """فیلتری که فقط کاربرانی با اشتراک فعال را قبول می‌کند"""

    def filter(self, update):
        user = update.effective_user
        if not user:
            return False

        sub = db.get_subscription(user.id)
        if not sub:
            return False

        if not sub.get("is_active"):
            return False

        end = sub.get("subscription_end")
        if not end:
            return False

        import time
        return end > int(time.time())


# ایجاد نمونه‌های فیلتر برای استفاده
IS_PANEL_ADMIN = _PanelAdmin()
IS_ACTIVE_SUBSCRIBER = _ActiveSubscriber()
