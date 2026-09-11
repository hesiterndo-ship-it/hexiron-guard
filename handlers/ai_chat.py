"""
هوش مصنوعی (Hexi):
  - چت آزاد توی پیوی ربات (متن یا ویس) - فقط برای اعضای واقعیِ گروه‌ها.
  - پاسخ داخل گروه وقتی با «Hexi»/«هگزی» صدا زده بشه (متن)، یا وقتی روی پیام
    خودِ Hexi ویس ریپلای بشه.
  - /aireport - گزارش هوشمند از وضعیت گروه، برای ادمین/مالک گروه، توی پیوی.

کنترل هزینه: سهمیه‌ی روزانه‌ی پیام (AI_DAILY_MESSAGE_LIMIT) + rate-limit دقیقه‌ای،
مشترک بین متن/ویس و بین پیوی/گروه - برای هر کاربر یکی حساب می‌شه.
"""
import logging
import os
import base64
import time as _time

from telegram import Update
from telegram.ext import ContextTypes, filters, CommandHandler, MessageHandler

import database as db
from config import AI_ENABLED, AI_CHAT_RATE_LIMIT_MAX, AI_CHAT_RATE_LIMIT_WINDOW, AI_DAILY_MESSAGE_LIMIT
from utils.ai_client import ai_chat, ai_vision, ai_group_report, NOT_CONFIGURED_MSG, GROUP_CHAT_SYSTEM_PROMPT
from utils.ratelimit import is_rate_limited
from utils.permissions import require_admin
from handlers.voicetotext import transcribe_voice_file, synthesize_speech_to_file

logger = logging.getLogger(__name__)

# تاریخچه‌ی مکالمه در حافظه (نه دیتابیس) - هر پردازش ری‌استارت بشه پاک می‌شه.
_MAX_HISTORY = 10
_chat_history: dict[int, list] = {}          # کلید: user_id (پیوی)
_group_chat_history: dict[str, list] = {}    # کلید: f"{chat_id}:{user_id}" (گروه)


def _today() -> str:
    return _time.strftime("%Y-%m-%d", _time.gmtime())


def _check_quota_and_rate(user_id: int) -> str | None:
    """فقط سهمیه‌ی روزانه + rate-limit رو چک می‌کنه (نه عضویت گروه - اون جدا و
    فقط برای پیویه). خروجی None یعنی مجازه، وگرنه متن پیامِ محدودیت."""
    today = _today()
    used = db.get_ai_daily_usage(user_id, today)
    if used >= AI_DAILY_MESSAGE_LIMIT:
        return f"📊 سهمیه‌ی امروزت ({AI_DAILY_MESSAGE_LIMIT} پیام) تموم شده. فردا دوباره امتحان کن."
    if is_rate_limited(f"aichat_{user_id}", max_attempts=AI_CHAT_RATE_LIMIT_MAX,
                        window_seconds=AI_CHAT_RATE_LIMIT_WINDOW):
        return "⏳ یکم آروم‌تر! چند لحظه صبر کن و دوباره امتحان کن."
    return None


async def _run_hexi(user, question: str, history_store: dict, history_key, system_prompt: str) -> str:
    """تماس اصلی با AI + مدیریت تاریخچه‌ی کوتاه‌مدت + حافظه‌ی بلندمدت + افزایش
    شمارنده‌ی سهمیه. فرض می‌کنه _check_quota_and_rate از قبل چک شده. خروجی: متن پاسخ."""
    history = history_store.get(history_key, [])
    existing_memory = db.get_user_memory(user.id)
    reply, new_memory = await ai_chat(question, history=history, system_prompt=system_prompt,
                                       user_memory=existing_memory)
    if new_memory:
        db.set_user_memory(user.id, new_memory)
    history = history + [{"role": "user", "content": question}, {"role": "assistant", "content": reply}]
    history_store[history_key] = history[-_MAX_HISTORY * 2:]
    db.increment_ai_daily_usage(user.id, _today())
    return reply


async def _maybe_reply_with_voice(update: Update, context: ContextTypes.DEFAULT_TYPE, reply_text: str):
    """اگه پیام ورودی ویس بود، پاسخ رو هم به‌صورت ویس (علاوه بر متن) می‌فرسته.
    اگه ساخت ویس شکست خورد، فقط لاگ می‌کنه - جلوی پاسخ متنی رو نمی‌گیره."""
    try:
        path = synthesize_speech_to_file(reply_text)
    except Exception:
        logger.exception("synthesize_speech_to_file failed - فقط پاسخ متنی فرستاده می‌شه")
        return
    try:
        with open(path, "rb") as f:
            await context.bot.send_voice(chat_id=update.effective_chat.id, voice=f)
    except Exception:
        logger.exception("ارسال ویس پاسخ Hexi شکست خورد")
    finally:
        if os.path.exists(path):
            os.remove(path)


async def ai_private_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """fallback برای پیام‌های متنیِ خصوصی که هیچ هندلر دیگه‌ای قبولشون نکرده."""
    if not AI_ENABLED:
        return

    user = update.effective_user
    text = update.effective_message.text
    if not text:
        return

    if not db.is_known_group_member(user.id):
        await update.effective_message.reply_text(
            "🔒 این قابلیت فقط برای اعضای گروه‌هایی هست که این ربات توشونه.\n"
            "اگه عضو یکی از اون گروه‌هایی، یه پیام توی خودِ گروه بفرست (حتی یه سلام)، بعد دوباره اینجا امتحان کن."
        )
        return

    block_msg = _check_quota_and_rate(user.id)
    if block_msg:
        await update.effective_message.reply_text(block_msg)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await _run_hexi(user, text, _chat_history, user.id, system_prompt=None)
    await update.effective_message.reply_text(reply)


def _private_prompt():
    return None


async def ai_private_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیوی: وقتی کاربر به‌جای متن، ویس می‌فرسته."""
    if not AI_ENABLED:
        return
    user = update.effective_user
    voice = update.effective_message.voice
    if not voice:
        return

    if not db.is_known_group_member(user.id):
        await update.effective_message.reply_text(
            "🔒 این قابلیت فقط برای اعضای گروه‌هایی هست که این ربات توشونه."
        )
        return

    block_msg = _check_quota_and_rate(user.id)
    if block_msg:
        await update.effective_message.reply_text(block_msg)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    text = await transcribe_voice_file(context, voice)
    if not text:
        await update.effective_message.reply_text("🎙 نتونستم صداتو تشخیص بدم. یه‌بار دیگه و واضح‌تر بگو.")
        return

    reply = await _run_hexi(user, text, _chat_history, user.id, system_prompt=_private_prompt())
    await update.effective_message.reply_text(f"🎙 شنیدم: «{text}»\n\n{reply}")
    await _maybe_reply_with_voice(update, context, reply)


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


# اسم‌هایی که با هرکدوم شروع بشه، یعنی پیام خطاب به Hexi ـه. عمداً محدود و
# دقیق نگه‌داشته شده (نه با NLU/تشخیص هوشمند نیت) تا با چت عادی گروه تداخل نداشته باشه.
_HEXI_TRIGGERS = ("hexi", "هگزی", "هکسی")


def _strip_hexi_trigger(text: str) -> str | None:
    """اگه پیام با یکی از اسم‌های Hexi شروع بشه (و بعدش حرف دیگه‌ای نچسبیده باشه -
    یعنی «Hexinator» یا «هگزی‌جون» رو قبول نمی‌کنه، فقط خودِ اسم تنها)، بقیه‌ی متن
    (بعد از حذف اسم و علائم نگارشی مثل ، یا :) رو برمی‌گردونه. وگرنه None."""
    stripped = text.strip()
    lower = stripped.lower()
    for trigger in _HEXI_TRIGGERS:
        if not lower.startswith(trigger):
            continue
        next_char = stripped[len(trigger):len(trigger) + 1]
        if next_char and (next_char.isalnum() or next_char == "‌"):
            continue
        rest = stripped[len(trigger):].lstrip(" ,،:؛-").strip()
        return rest
    return None


async def hexi_group_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی داخل گروه با «Hexi»/«هگزی» صداش بزنن (متن)، جواب می‌ده. برای پیام‌هایی
    که خطاب به Hexi نیستن، بی‌صدا هیچ کاری نمی‌کنه (نه تماس با AI، نه هزینه)."""
    message = update.effective_message
    if not message or not message.text:
        return

    question = _strip_hexi_trigger(message.text)
    if question is None:
        return

    if not AI_ENABLED:
        return

    user = update.effective_user
    block_msg = _check_quota_and_rate(user.id)
    if block_msg:
        if "سهمیه" in block_msg:
            await message.reply_text(f"📊 {user.first_name} سهمیه‌ی امروزت تموم شده. فردا دوباره صدام کن.")
        return  # برای rate-limit توی گروه بی‌سروصدا نادیده می‌گیریم، پیام اسپم می‌شه

    if not question:
        question = "سلام! چیزی نگفتی، چیکار می‌تونم برات بکنم؟"

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    key = f"{update.effective_chat.id}:{user.id}"
    user_prompt = f"[کاربر: {user.first_name or user.username or 'کاربر'}] {question}"
    reply = await _run_hexi(user, user_prompt, _group_chat_history, key, system_prompt=GROUP_CHAT_SYSTEM_PROMPT)
    await message.reply_text(reply)


async def hexi_group_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """توی گروه، وقتی یه ویس رو مستقیم روی پیام خودِ Hexi ریپلای کنن (چون گفتن
    «Hexi» با صدا قابل‌اعتماد تشخیص داده نمی‌شه، این معادلِ صدازدنِ Hexi با ویس‌ه)."""
    message = update.effective_message
    if not message or not message.voice:
        return
    reply_to = message.reply_to_message
    if not reply_to or not reply_to.from_user or reply_to.from_user.id != context.bot.id:
        return  # این ویس خطاب به Hexi نبود (ریپلای به پیام یه آدم دیگه بوده)

    if not AI_ENABLED:
        return

    user = update.effective_user
    block_msg = _check_quota_and_rate(user.id)
    if block_msg:
        if "سهمیه" in block_msg:
            await message.reply_text(f"📊 {user.first_name} سهمیه‌ی امروزت تموم شده.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    text = await transcribe_voice_file(context, message.voice)
    if not text:
        await message.reply_text("🎙 نتونستم صداتو تشخیص بدم.")
        return

    key = f"{update.effective_chat.id}:{user.id}"
    user_prompt = f"[کاربر: {user.first_name or user.username or 'کاربر'}] {text}"
    reply = await _run_hexi(user, user_prompt, _group_chat_history, key, system_prompt=GROUP_CHAT_SYSTEM_PROMPT)
    await message.reply_text(f"🎙 شنیدم: «{text}»\n\n{reply}")
    await _maybe_reply_with_voice(update, context, reply)


async def _download_photo_base64(context, photo) -> str:
    """بزرگ‌ترین سایز عکس رو دانلود می‌کنه و base64ِ محتواش رو برمی‌گردونه."""
    tg_file = await context.bot.get_file(photo.file_id)
    file_bytes = await tg_file.download_as_bytearray()
    return base64.b64encode(bytes(file_bytes)).decode("ascii")


async def ai_private_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیوی: کاربر یه عکس برای Hexi می‌فرسته تا تحلیلش کنه/نظر بده - فقط تحلیل،
    هیچ‌وقت عکس نمی‌سازه. عمداً وارد حافظه‌ی مکالمه نمی‌شه (base64 عکس خیلی بزرگه
    و اگه بمونه، هزینه‌ی همه‌ی پیام‌های بعدی رو منفجر می‌کنه)."""
    if not AI_ENABLED:
        return
    user = update.effective_user
    photos = update.effective_message.photo
    if not photos:
        return

    if not db.is_known_group_member(user.id):
        await update.effective_message.reply_text(
            "🔒 این قابلیت فقط برای اعضای گروه‌هایی هست که این ربات توشونه."
        )
        return

    block_msg = _check_quota_and_rate(user.id)
    if block_msg:
        await update.effective_message.reply_text(block_msg)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    image_b64 = await _download_photo_base64(context, photos[-1])
    question = update.effective_message.caption or ""
    reply = await ai_vision(question, image_b64)
    db.increment_ai_daily_usage(user.id, _today())
    await update.effective_message.reply_text(reply)


async def hexi_group_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """توی گروه، وقتی یه عکس رو با ریپلای به پیام خودِ Hexi بفرستن (همون قرارداد
    ویس رو برای عکس هم رعایت می‌کنیم)، یا مستقیم با کپشنی که با Hexi/هگزی شروع بشه."""
    message = update.effective_message
    if not message or not message.photo:
        return

    reply_to = message.reply_to_message
    addressed_via_reply = bool(reply_to and reply_to.from_user and reply_to.from_user.id == context.bot.id)
    caption_question = _strip_hexi_trigger(message.caption) if message.caption else None
    if not addressed_via_reply and caption_question is None:
        return  # این عکس خطاب به Hexi نبود

    if not AI_ENABLED:
        return

    user = update.effective_user
    block_msg = _check_quota_and_rate(user.id)
    if block_msg:
        if "سهمیه" in block_msg:
            await message.reply_text(f"📊 {user.first_name} سهمیه‌ی امروزت تموم شده.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    image_b64 = await _download_photo_base64(context, message.photo[-1])
    question = caption_question or ""
    reply = await ai_vision(question, image_b64, system_prompt=GROUP_CHAT_SYSTEM_PROMPT)
    db.increment_ai_daily_usage(user.id, _today())
    await message.reply_text(reply)


def register_ai_handlers(app):
    app.add_handler(CommandHandler("aireport", aireport_cmd, filters=filters.ChatType.GROUPS))

    # صدازدن Hexi داخل گروه (متن) - group=7: بعد از فیلترهای مدیریتی، ولی چون
    # فقط پیام‌های واقعاً خطاب‌به‌Hexi رو پردازش می‌کنه، برای ۹۹٪ پیام‌های گروه
    # هیچ هزینه/تاخیری نداره.
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, hexi_group_trigger),
        group=7,
    )
    # ویس داخل گروه، فقط وقتی ریپلای به خودِ Hexi باشه
    app.add_handler(
        MessageHandler(filters.VOICE & filters.ChatType.GROUPS, hexi_group_voice),
        group=7,
    )
    # عکس داخل گروه (ریپلای به Hexi، یا کپشنی که با Hexi/هگزی شروع بشه)
    app.add_handler(
        MessageHandler(filters.PHOTO & filters.ChatType.GROUPS, hexi_group_photo),
        group=7,
    )

    # پیوی: متن (fallback، آخرین هندلر متنی)، ویس، و عکس
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        ai_private_chat,
    ))
    app.add_handler(MessageHandler(filters.VOICE & filters.ChatType.PRIVATE, ai_private_voice))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, ai_private_photo))
