"""
دکوریتورهای سفارشی
"""
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

from .permissions import is_admin
from .helpers import is_group_chat, is_private_chat


def admin_only(func):
    """فقط ادمین‌ها"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not await is_admin(update, context):
            await update.effective_message.reply_text("⛔️ شما دسترسی ادمین ندارید.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def group_only(func):
    """فقط در گروه‌ها"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not is_group_chat(update):
            await update.effective_message.reply_text("این دستور فقط در گروه‌ها قابل استفاده است.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def private_only(func):
    """فقط در چت خصوصی"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not is_private_chat(update):
            await update.effective_message.reply_text("این دستور فقط در چت خصوصی قابل استفاده است.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper
    # ========== توابع تیکت ==========

def create_ticket(chat_id: int, user_id: int, subject: str, message: str, priority: str = "medium") -> int:
    """ایجاد تیکت جدید"""
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tickets (chat_id, user_id, subject, message, priority, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?)
            """,
            (chat_id, user_id, subject, message, priority, int(time.time()))
        )
        return cursor.lastrowid


def get_user_tickets(chat_id: int, user_id: int) -> list:
    """دریافت تیکت‌های یک کاربر"""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tickets 
            WHERE chat_id=? AND user_id=? 
            ORDER BY created_at DESC
            """,
            (chat_id, user_id)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_tickets(chat_id: int) -> list:
    """دریافت همه تیکت‌های یک گروه"""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT t.*, u.first_name, u.username 
            FROM tickets t
            LEFT JOIN users u ON t.user_id = u.user_id AND t.chat_id = u.chat_id
            WHERE t.chat_id=? 
            ORDER BY 
                CASE t.priority 
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    WHEN 'low' THEN 4
                END,
                t.created_at ASC
            """,
            (chat_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_ticket(chat_id: int, ticket_id: int) -> dict:
    """دریافت اطلاعات یک تیکت"""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT t.*, u.first_name, u.username 
            FROM tickets t
            LEFT JOIN users u ON t.user_id = u.user_id AND t.chat_id = u.chat_id
            WHERE t.chat_id=? AND t.id=?
            """,
            (chat_id, ticket_id)
        ).fetchone()
        return dict(row) if row else None


def add_ticket_reply(chat_id: int, ticket_id: int, admin_id: int, reply: str):
    """افزودن پاسخ به تیکت"""
    with get_conn() as conn:
        # دریافت پاسخ‌های قبلی
        row = conn.execute(
            "SELECT replies FROM tickets WHERE chat_id=? AND id=?",
            (chat_id, ticket_id)
        ).fetchone()
        
        if row and row["replies"]:
            # اگر پاسخ قبلی وجود داشت
            import json
            replies = json.loads(row["replies"])
        else:
            replies = []
        
        # افزودن پاسخ جدید
        replies.append({
            "admin_id": admin_id,
            "reply": reply,
            "time": int(time.time())
        })
        
        # ذخیره در دیتابیس
        import json
        conn.execute(
            "UPDATE tickets SET replies=?, status='in_progress' WHERE chat_id=? AND id=?",
            (json.dumps(replies), chat_id, ticket_id)
        )


def close_ticket(chat_id: int, ticket_id: int):
    """بستن تیکت"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE tickets SET status='closed' WHERE chat_id=? AND id=?",
            (chat_id, ticket_id)
        )


def get_ticket_stats(chat_id: int) -> dict:
    """دریافت آمار تیکت‌ها"""
    with get_conn() as conn:
        open_tickets = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE chat_id=? AND status='open'",
            (chat_id,)
        ).fetchone()[0]
        
        in_progress = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE chat_id=? AND status='in_progress'",
            (chat_id,)
        ).fetchone()[0]
        
        closed = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE chat_id=? AND status='closed'",
            (chat_id,)
        ).fetchone()[0]
        
        total = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE chat_id=?",
            (chat_id,)
        ).fetchone()[0]
        
        return {
            "open": open_tickets,
            "in_progress": in_progress,
            "closed": closed,
            "total": total
        }