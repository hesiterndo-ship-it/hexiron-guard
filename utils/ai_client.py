"""
لایه‌ی نازک روی Anthropic API برای سه تا کاربرد:
  1. ai_chat        -> چت آزاد با کاربر (شعر، سوال، هر چیزی) - پیوی ربات
  2. ai_check_toxic  -> تشخیص هوشمند فحش/توهین (فراتر از لیست کلمات ثابت)
  3. ai_group_report -> خلاصه‌ی هوشمند از وضعیت گروه برای مالک/ادمین

اگه ANTHROPIC_API_KEY توی .env ست نشده باشه، همه‌ی این توابع پیام خطای
واضح برمی‌گردونن (نه Exception خام) تا بقیه‌ی ربات کرش نکنه.
"""
import json
import logging

from config import ANTHROPIC_API_KEY, AI_CHAT_MODEL, AI_FAST_MODEL, AI_ENABLED

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """کلاینت رو فقط یک‌بار و فقط وقتی لازم شد می‌سازه (lazy init)."""
    global _client
    if _client is None and AI_ENABLED:
        from anthropic import AsyncAnthropic
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


NOT_CONFIGURED_MSG = (
    "🤖 قابلیت هوش مصنوعی هنوز روی این ربات فعال نشده.\n"
    "ادمین ربات باید ANTHROPIC_API_KEY رو توی فایل .env تنظیم کنه."
)

CHAT_SYSTEM_PROMPT = (
    "تو یک دستیار هوش مصنوعی فارسی‌زبان هستی که داخل یک ربات تلگرام گروه فعالیت می‌کنی. "
    "خودت رو 'HEXIRON AI' معرفی کن اگه کسی پرسید کی هستی. "
    "همیشه به فارسی و خیلی محاوره‌ای و دوستانه جواب بده، مگر اینکه کاربر زبان دیگه‌ای استفاده کنه. "
    "می‌تونی شعر بگی، داستان بنویسی، سوال جواب بدی، کمک به تکالیف/برنامه‌نویسی بدی و هر کار متنی دیگه‌ای انجام بدی. "
    "جواب‌ها رو کوتاه و مفید نگه دار مگر اینکه کاربر توضیح مفصل بخواد."
)


async def ai_chat(user_message: str, history: list | None = None) -> str:
    """چت آزاد. history اختیاریه: لیستی از {'role': 'user'|'assistant', 'content': str}."""
    client = _get_client()
    if client is None:
        return NOT_CONFIGURED_MSG

    messages = list(history) if history else []
    messages.append({"role": "user", "content": user_message})

    try:
        resp = await client.messages.create(
            model=AI_CHAT_MODEL,
            max_tokens=1024,
            system=CHAT_SYSTEM_PROMPT,
            messages=messages,
        )
        return "".join(block.text for block in resp.content if block.type == "text").strip() or "..."
    except Exception as e:
        logger.error(f"ai_chat failed: {e}")
        return "😕 مشکلی توی ارتباط با هوش مصنوعی پیش اومد. یه بار دیگه امتحان کن."


TOXIC_SYSTEM_PROMPT = (
    "تو یک سیستم تشخیص فحش/توهین/بی‌ادبی برای یک گروه تلگرامی فارسی‌زبان هستی. "
    "فقط و فقط یک JSON خام (بدون توضیح اضافه، بدون markdown fence) با این شکل دقیق برگردون:\n"
    '{"toxic": true|false, "reason": "دلیل کوتاه فارسی یا خالی"}\n'
    "toxic=true فقط وقتی که پیام واقعاً حاوی فحش، توهین مستقیم به یک نفر، تهدید یا نفرت‌پراکنی باشه. "
    "شوخی‌های عادی، انتقاد محترمانه، و بحث معمولی toxic نیستن."
)


async def ai_check_toxic(text: str) -> tuple[bool, str]:
    """برمی‌گردونه (is_toxic, reason). اگه AI فعال نباشه یا خطا بخوره، (False, '') برمی‌گردونه
    تا هیچ‌وقت به‌خاطر این لایه‌ی اضافه، پیام‌های سالم به اشتباه حذف نشن (fail-open)."""
    client = _get_client()
    if client is None:
        return False, ""
    if not text or len(text.strip()) < 2:
        return False, ""

    try:
        resp = await client.messages.create(
            model=AI_FAST_MODEL,
            max_tokens=150,
            system=TOXIC_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text[:2000]}],
        )
        raw = "".join(block.text for block in resp.content if block.type == "text").strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)
        return bool(data.get("toxic")), str(data.get("reason") or "")
    except Exception as e:
        logger.warning(f"ai_check_toxic failed (fail-open, message allowed): {e}")
        return False, ""


async def ai_group_report(raw_stats: dict) -> str:
    """یه خلاصه‌ی خوانا و فارسی از یه دیکشنری آمار خام گروه می‌سازه."""
    client = _get_client()
    if client is None:
        return NOT_CONFIGURED_MSG

    prompt = (
        "این آمار خام یک گروه تلگرامیه. یک گزارش کوتاه، خوانا و فارسی برای مالک گروه بنویس "
        "(چند خط، با ایموجی مناسب، بدون تیتر اضافی، لحن دوستانه و حرفه‌ای):\n\n"
        f"{json.dumps(raw_stats, ensure_ascii=False, indent=2)}"
    )
    try:
        resp = await client.messages.create(
            model=AI_FAST_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in resp.content if block.type == "text").strip()
    except Exception as e:
        logger.error(f"ai_group_report failed: {e}")
        return "😕 مشکلی توی ساخت گزارش هوشمند پیش اومد."
