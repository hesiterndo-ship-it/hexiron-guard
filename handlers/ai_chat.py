"""
هوش مصنوعی:
  - چت آزاد توی پیوی ربات (شعر، سوال، هر چیزی) - fallback، فقط وقتی هیچ
    مکالمه/دستور دیگه‌ای اون پیام رو نگرفته باشه. فقط برای اعضای واقعیِ گروه‌ها
    (کسی که تا حالا توی هیچ گروهی که ربات توشه دیده نشده باشه، جواب نمی‌گیره).
  - /aireport - گزارش هوشمند از وضعیت گروه، برای ادمین/مالک گروه، توی پیوی.
"""
import logging
import time as _time

from telegram import Update
from telegram.ext import ContextTypes, filters, CommandHandler, MessageHandler

import database as db
from config import AI_ENABLED, AI_CHAT_RATE_LIMIT_MAX, AI_CHAT_RATE_LIMIT_WINDOW, AI_DAILY_MESSAGE_LIMIT
from utils.ai_client import ai_chat, ai_group_report, NOT_CONFIGURED_MSG
from utils.ratelimit import is_rate_limited
from utils.permissions import require_admin

logger = logging.getLogger(__name__)

# تاریخچه‌ی ساده‌ی مکالمه در حافظه (نه دیتابیس) - هر پردازش ری‌استارت بشه پاک می‌شه.
# هر کاربر حداکثر آخرین ۱۰ پیام رو برای حفظ context نگه می‌داره.
_MAX_HISTORY = 10
_chat_history: dict[int, list] = {}


def _today() -> str:
    return _time.strftime("%Y-%m-%d", _time.gmtime())


async def ai_private_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """fallback برای پیام‌های متنیِ خصوصی که هیچ هندلر دیگه‌ای قبولشون نکرده."""
    if not AI_ENABLED:
        return  # اگه AI خاموشه، اصلاً وارد نشو - بذار پیام بی‌جواب بمونه به‌جای گیج‌کردن کاربر

    user = update.effective_user
    text = update.effective_message.text
    if not text:
        return

    # فقط اعضای واقعیِ حداقل یه گروه که ربات توشه اجازه‌ی چت با AI رو دارن -
    # این هم برای کنترل هزینه‌ست و هم برای اینکه چت آزاد رایگان به کل عموم مردم درز نکنه.
    if not db.is_known_group_member(user.id):
        await update.effective_message.reply_text(
            "🔒 این قابلیت فقط برای اعضای گروه‌هایی هست که این ربات توشونه.\n"
            "اگه عضو یکی از اون گروه‌هایی، یه پیام توی خودِ گروه بفرست (حتی یه سلام)، بعد دوباره اینجا امتحان کن."
        )
        return

    today = _today()
    used = db.get_ai_daily_usage(user.id, today)
    if used >= AI_DAILY_MESSAGE_LIMIT:
        await update.effective_message.reply_text(
            f"📊 سهمیه‌ی امروزت ({AI_DAILY_MESSAGE_LIMIT} پیام) تموم شده. فردا دوباره امتحان کن."
        )
        return

    if is_rate_limited(f"aichat_{user.id}", max_attempts=AI_CHAT_RATE_LIMIT_MAX,
                        window_seconds=AI_CHAT_RATE_LIMIT_WINDOW):
        await update.effective_message.reply_text(
            "⏳ یکم آروم‌تر! چند لحظه صبر کن و دوباره امتحان کن."
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    history = _chat_history.get(user.id, [])
    reply = await ai_chat(text, history=history)

    history = history + [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
    _chat_history[user.id] = history[-_MAX_HISTORY * 2:]

    db.increment_ai_daily_usage(user.id, today)
    await update.effective_message.reply_text(reply)


async def aireport_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/aireport - فقط توی گروه، فقط ادمین. گزارش هوشمند رو توی پیوی خودِ ادمین می‌فرسته."""
    chat = update.effective_chat
    if chat.type == "private":
        await update.effective_message.reply_text("این دستور رو باید داخل گروه بزنی.")
        return

    if not await require_admin(update, context):
        return

    if not AI_ENABLED:
        await update.effective_message.reply_text(NOT_CONFIGURED_MSG)
        return

    await update.effective_message.reply_text("⏳ در حال ساخت گزارش هوشمند... نتیجه رو توی پیوی برات می‌فرستم.")

    stats = db.chat_stats(chat.id)
    warns = db.get_users_with_warns(chat.id)
    tickets = db.get_ticket_stats(chat.id)
    settings = db.get_settings(chat.id)

    raw = {
        "نام گروه": chat.title,
        "تعداد اعضای ثبت‌شده": stats["member_count"],
        "مجموع امتیازها": stats["total_points"],
        "مجموع اخطارها": stats["total_warns"],
        "کاربران با اخطار فعال": [
            {"نام": w.get("first_name") or w.get("username") or w["user_id"], "تعداد اخطار": w["warns"]}
            for w in warns[:15]
        ],
        "وضعیت تیکت‌ها": tickets,
        "قفل بودن گروه": bool(settings.get("locked")),
    }

    report_text = await ai_group_report(raw)

    user_id = update.effective_user.id
    try:
        await context.bot.send_message(
            user_id,
            f"📊 *گزارش هوشمند گروه «{chat.title}»*\n\n{report_text}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning(f"Could not DM AI report to {user_id}: {e}")
        await update.effective_message.reply_text(
            "❗️ نتونستم توی پیوی برات پیام بفرستم. اول یه‌بار /start رو توی پیوی ربات بزن، بعد دوباره امتحان کن."
        )


def register_ai_handlers(app):
    app.add_handler(CommandHandler("aireport", aireport_cmd, filters=filters.ChatType.GROUPS))
    # این باید آخرین هندلر متنیِ پیوی توی همین گروه (group=0) باشه، تا فقط وقتی
    # هیچ مکالمه/دستور دیگه‌ای (شاپ، پنل کاربر، پنل ادمین، ...) پیام رو نگرفت، اجرا بشه.
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        ai_private_chat,
    ))
