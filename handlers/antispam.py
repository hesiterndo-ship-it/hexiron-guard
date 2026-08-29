"""
Phase 1 anti-spam:
  - banned word filter (per-chat, admin-managed list)
  - basic link filter (blocks links from non-admins)
  - flood control (too many messages in a short window -> temporary mute)
  - group lock (when locked, only admins can send messages)

This runs in an earlier handler group than point-tracking, and raises
ApplicationHandlerStop when it takes action so a deleted/punished message
never earns points or reaches other handlers.
"""
import re
import time
from collections import defaultdict, deque

from telegram import ChatPermissions, Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

import database as db
from config import FLOOD_MAX_MESSAGES, FLOOD_MUTE_MINUTES, FLOOD_WINDOW_SECONDS, CENTRAL_BOT_USERNAME
from utils.license_client import is_group_licensed
from utils.permissions import is_admin

LINK_PATTERN = re.compile(r"(https?://|t\.me/|www\.)", re.IGNORECASE)

# نگاشت کاراکترهای عربی به معادل فارسی‌شون، برای اینکه فیلتر کلمات ممنوعه فرقی
# بین «كتاب» (عربی) و «کتاب» (فارسی) نذاره - خیلی از کیبوردها این دوتا رو قاطی می‌کنن.
_ARABIC_TO_PERSIAN = str.maketrans({
    "ك": "ک", "ي": "ی", "ة": "ه", "ۀ": "ه",
    "أ": "ا", "إ": "ا", "آ": "ا", "ؤ": "و", "ئ": "ی",
})
# نیم‌فاصله و کاراکترهای صفر-عرض که معمولاً وسط کلمه اومده و نباید مانع تشخیص بشه
_ZERO_WIDTH_CHARS = str.maketrans({"\u200c": "", "\u200b": "", "\u200f": "", "\u200e": ""})


def _normalize_for_badword_match(text: str) -> str:
    """متن رو برای مقایسه‌ی یکنواخت آماده می‌کنه: حروف عربی -> فارسی، حذف نیم‌فاصله/کاراکتر
    صفر-عرض، و lower کردن حروف لاتین. این باعث می‌شه یک کلمه‌ی ممنوعه با نوشتار متفاوت
    (عربی/فارسی) هم شناسایی بشه."""
    text = text.translate(_ARABIC_TO_PERSIAN).translate(_ZERO_WIDTH_CHARS)
    return text.lower()

# in-memory flood tracker: {(chat_id, user_id): deque[timestamps]}
_recent_messages: dict[tuple[int, int], deque] = defaultdict(
    lambda: deque(maxlen=FLOOD_MAX_MESSAGES + 5)
)

# آخرین باری که به هر گروه پیام «اشتراک ندارید» فرستاده شده (برای جلوگیری از اسپم شدن پیام)
_last_sub_notice: dict[int, float] = {}

# دستوراتی که حتی بدون اشتراک هم باید کار کنن (برای این‌که گروه بتونه اشتراک بخره)
ALWAYS_ALLOWED_COMMANDS = {"/start", "/groupid"}


async def enforce_subscription_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اگه گروه لایسنس فعال نداشته باشه (طبق ربات مرکزی فروش)، هیچ خدمتی
    (به‌جز /start و /groupid) اجرا نمی‌شه. این باید زودتر از همه‌ی هندلرهای
    دیگه ثبت بشه (group=-10 توی main.py)."""
    chat = update.effective_chat
    message = update.effective_message
    if chat is None or chat.type == "private":
        return
    if await is_group_licensed(chat.id):
        return

    text = (message.text if message else "") or ""
    if text.startswith("/"):
        command = text.strip().split()[0].split("@")[0].lower()
        if command in ALWAYS_ALLOWED_COMMANDS:
            return

    now = time.time()
    last = _last_sub_notice.get(chat.id, 0)
    if now - last > 600:  # حداکثر هر ۱۰ دقیقه یک‌بار پیام بده تا اسپم نشه
        _last_sub_notice[chat.id] = now
        buy_hint = f"@{CENTRAL_BOT_USERNAME}" if CENTRAL_BOT_USERNAME else "ربات فروش"
        try:
            await chat.send_message(
                "🚫 این گروه لایسنس فعال نداره و خدمات ربات غیرفعاله.\n"
                f"برای خرید/تمدید: توی پیوی {buy_hint} بزن /shop و با /groupid (همین‌جا) آیدی گروه رو بگیر."
            )
        except Exception:
            pass
    raise ApplicationHandlerStop


async def _delete_and_warn(update: Update, reason: str):
    message = update.effective_message
    try:
        await message.delete()
    except Exception:
        pass  # bot may lack delete rights; fail open rather than crash
    warns = db.add_warn(update.effective_chat.id, update.effective_user.id)
    name = update.effective_user.first_name or update.effective_user.username or "کاربر"
    await update.effective_chat.send_message(
        f"🚫 پیام {name} حذف شد. دلیل: {reason}\n⚠️ تعداد اخطارها: {warns}"
    )


async def enforce_group_lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or chat.type == "private":
        return
    if not db.is_feature_enabled(chat.id, "antispam"):
        return
    settings = db.get_settings(chat.id)
    if not settings.get("locked"):
        return
    if await is_admin(update, context):
        return
    await _delete_and_warn(update, "گروه در حالت قفل است")
    raise ApplicationHandlerStop


async def filter_badwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat.type == "private":
        return
    # هم متن پیام معمولی و هم کپشن عکس/ویدیو رو چک کن - قبلاً فقط message.text
    # چک می‌شد و فحش داخل کپشن عکس اصلاً فیلتر نمی‌شد.
    raw_text = message.text or message.caption or ""
    if not raw_text:
        return
    if not db.is_feature_enabled(chat.id, "badword_filter"):
        return
    if await is_admin(update, context):
        return

    normalized_text = _normalize_for_badword_match(raw_text)
    for word in db.list_badwords(chat.id):
        if not word:
            continue
        normalized_word = _normalize_for_badword_match(word)
        if not normalized_word:
            continue
        # به‌جای substring ساده (که مثلاً کلمه‌ی «کص» رو وسط «تخصص» هم پیدا می‌کرد)،
        # از یک الگوی مرزِ-کلمه استفاده می‌کنیم تا فقط خودِ کلمه رو بگیره.
        pattern = re.compile(
            r"(?<![^\W\d_])" + re.escape(normalized_word) + r"(?![^\W\d_])",
            re.UNICODE,
        )
        if pattern.search(normalized_text):
            await _delete_and_warn(update, f"استفاده از کلمه ممنوعه")
            raise ApplicationHandlerStop

    # ===== لایه‌ی اضافه: تشخیص هوشمند با AI (اختیاری، فقط اگه ادمین گروه فعالش کرده باشه) =====
    # این جدا از لیست کلمات ممنوعه‌ست: جمله‌هایی رو می‌گیره که فحش رکیک ندارن ولی
    # توهین‌آمیزن. fail-open هست یعنی اگه AI خطا بده یا کند باشه، پیام حذف نمی‌شه.
    settings = db.get_settings(chat.id)
    if settings.get("ai_moderation"):
        from config import AI_ENABLED
        if AI_ENABLED:
            from utils.ai_client import ai_check_toxic
            is_toxic, reason = await ai_check_toxic(raw_text)
            if is_toxic:
                await _delete_and_warn(update, f"محتوای توهین‌آمیز (تشخیص AI): {reason}" if reason else "محتوای توهین‌آمیز (تشخیص AI)")
                raise ApplicationHandlerStop


async def filter_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    if message is None or not message.text or chat.type == "private":
        return
    if not db.is_feature_enabled(chat.id, "antispam"):
        return
    if await is_admin(update, context):
        return
    if LINK_PATTERN.search(message.text):
        await _delete_and_warn(update, "ارسال لینک بدون اجازه")
        raise ApplicationHandlerStop


async def flood_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if message is None or user is None or chat is None or chat.type == "private":
        return
    if not db.is_feature_enabled(chat.id, "antispam"):
        return
    if await is_admin(update, context):
        return

    key = (chat.id, user.id)
    now = time.time()
    dq = _recent_messages[key]
    dq.append(now)
    while dq and now - dq[0] > FLOOD_WINDOW_SECONDS:
        dq.popleft()

    if len(dq) >= FLOOD_MAX_MESSAGES:
        dq.clear()
        until = int(time.time() + FLOOD_MUTE_MINUTES * 60)
        try:
            await context.bot.restrict_chat_member(
                chat.id,
                user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
            name = user.first_name or user.username or "کاربر"
            await chat.send_message(
                f"🔇 {name} به دلیل ارسال پیام زیاد در زمان کوتاه، "
                f"به مدت {FLOOD_MUTE_MINUTES} دقیقه بی‌صدا شد."
            )
        except Exception:
            pass
        raise ApplicationHandlerStop