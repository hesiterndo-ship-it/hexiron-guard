"""
Central configuration loaded from environment variables (.env).

Security notes:
- Never hard-code secrets in this file.
- Keep the real .env file outside version control.
- Production payment/database secrets must be persistent.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

# Load .env from the project directory.
load_dotenv(BASE_DIR / ".env")


def _str_env(name: str, default: str = "") -> str:
    """Read a string environment variable safely."""
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip()


def _int_env(name: str, default: int) -> int:
    """Read an integer environment variable safely."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _positive_int_env(
    name: str,
    default: int,
    minimum: int = 1,
) -> int:
    """Read an integer and enforce a minimum value."""
    return max(minimum, _int_env(name, default))


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

BOT_TOKEN = _str_env("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not configured. "
        "Create a .env file and set BOT_TOKEN."
    )


# ---------------------------------------------------------------------------
# Owner / administration
# ---------------------------------------------------------------------------

OWNER_ID = _int_env("OWNER_ID", 0)

if OWNER_ID < 0:
    OWNER_ID = 0


# ---------------------------------------------------------------------------
# Proxy
# ---------------------------------------------------------------------------

# Optional examples:
#
# PROXY_URL=socks5://127.0.0.1:10808
# PROXY_URL=http://127.0.0.1:10809
#
# Leave empty when no proxy is required.

PROXY_URL = _str_env("PROXY_URL")


# ---------------------------------------------------------------------------
# Anti-spam / flood protection
# ---------------------------------------------------------------------------

FLOOD_MAX_MESSAGES = _positive_int_env(
    "FLOOD_MAX_MESSAGES",
    6,
    minimum=1,
)

FLOOD_WINDOW_SECONDS = _positive_int_env(
    "FLOOD_WINDOW_SECONDS",
    8,
    minimum=1,
)

FLOOD_MUTE_MINUTES = _positive_int_env(
    "FLOOD_MUTE_MINUTES",
    10,
    minimum=1,
)


# ---------------------------------------------------------------------------
# Points / activity
# ---------------------------------------------------------------------------

POINTS_PER_MESSAGE = max(
    0,
    _int_env("POINTS_PER_MESSAGE", 1),
)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

# The path can be absolute or relative.
#
# Example:
# DB_PATH=guardbot.db
#
# For production you can use:
# DB_PATH=data/guardbot.db

DB_PATH_RAW = _str_env("DB_PATH", "guardbot.db")

DB_PATH = Path(DB_PATH_RAW)

if not DB_PATH.is_absolute():
    DB_PATH = BASE_DIR / DB_PATH

# Make sure the parent directory exists.
DB_PATH.parent.mkdir(
    parents=True,
    exist_ok=True,
)


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

BACKUP_DIR_RAW = _str_env(
    "BACKUP_DIR",
    "backups",
)

BACKUP_DIR = Path(BACKUP_DIR_RAW)

if not BACKUP_DIR.is_absolute():
    BACKUP_DIR = BASE_DIR / BACKUP_DIR

BACKUP_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ---------------------------------------------------------------------------
# Payment / sales system
# ---------------------------------------------------------------------------

# IMPORTANT:
# These settings belong to the sales system.
# Do not remove them even if the guard/security part of the bot is modified.

SCREENSHOTS_DIR_RAW = _str_env(
    "SCREENSHOTS_DIR",
    "screenshots",
)

SCREENSHOTS_DIR = Path(SCREENSHOTS_DIR_RAW)

if not SCREENSHOTS_DIR.is_absolute():
    SCREENSHOTS_DIR = BASE_DIR / SCREENSHOTS_DIR

SCREENSHOTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ---------------------------------------------------------------------------
# Card encryption
# ---------------------------------------------------------------------------

# Persistent Fernet key used by the sales/payment system.
#
# IMPORTANT:
# NEVER generate a new key automatically on every startup.
#
# If the key changes, previously encrypted card data may become impossible
# to decrypt.
#
# Generate one once and store it in .env:
#
# CARD_ENCRYPTION_KEY=...
#
# Do NOT commit the key to GitHub or include it in a public ZIP.

CARD_ENCRYPTION_KEY = _str_env(
    "CARD_ENCRYPTION_KEY",
)


# ---------------------------------------------------------------------------
# Sales admin panel
# ---------------------------------------------------------------------------

# Additional PIN for the sales/admin panel.
#
# Keep this separate from Telegram OWNER_ID authentication.

ADMIN_PANEL_PIN = _str_env(
    "ADMIN_PANEL_PIN",
)


# ---------------------------------------------------------------------------
# Admin panel session
# ---------------------------------------------------------------------------

ADMIN_PANEL_SESSION_MINUTES = _positive_int_env(
    "ADMIN_PANEL_SESSION_MINUTES",
    30,
    minimum=1,
)


# ---------------------------------------------------------------------------
# Runtime / logging
# ---------------------------------------------------------------------------

LOG_LEVEL = _str_env(
    "LOG_LEVEL",
    "INFO",
).upper()

ALLOWED_LOG_LEVELS = {
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
}

if LOG_LEVEL not in ALLOWED_LOG_LEVELS:
    LOG_LEVEL = "INFO"


# ---------------------------------------------------------------------------
# Telegram request limits
# ---------------------------------------------------------------------------

# Maximum number of characters accepted for user-generated text that the
# bot processes as a moderation message.
#
# This prevents unnecessarily large payloads from reaching moderation logic.

MAX_MESSAGE_TEXT_LENGTH = _positive_int_env(
    "MAX_MESSAGE_TEXT_LENGTH",
    4096,
    minimum=100,
)


# ---------------------------------------------------------------------------
# Security defaults
# ---------------------------------------------------------------------------

# Whether development/debug information may be exposed in logs.
#
# Keep this FALSE in production.

DEBUG = _str_env(
    "DEBUG",
    "false",
).lower() in {
    "1",
    "true",
    "yes",
    "on",
}


# Never print secrets from this module.
#
# The following values intentionally do NOT have print/log statements:
#
# BOT_TOKEN
# CARD_ENCRYPTION_KEY
# ADMIN_PANEL_PIN


# ---------------------------------------------------------------------------
# اتصال به ربات فروش مرکزی (HEXIRON SALES)
# ---------------------------------------------------------------------------
# این ربات دیگه خودش اشتراک نمی‌فروشه - فقط از ربات مرکزی می‌پرسه که آیا این
# گروه لایسنس فعال داره یا نه. این آدرس باید دقیقاً همون آدرسی باشه که ربات
# مرکزی روش دیپلوی شده (توی لیارا، آدرس داخلی/خارجی سرویس مرکزی رو بذار)،
# و CENTRAL_API_KEY هم باید دقیقاً همون مقدار API_KEY که توی .env ربات مرکزی
# گذاشتی باشه.
CENTRAL_API_URL = _str_env("CENTRAL_API_URL", "http://localhost:8080")
CENTRAL_API_KEY = _str_env("CENTRAL_API_KEY")
if not CENTRAL_API_KEY:
    raise RuntimeError(
        "CENTRAL_API_KEY تنظیم نشده. این باید دقیقاً همون API_KEY که توی .env "
        "ربات فروش مرکزی گذاشتی باشه."
    )

# آیدی این محصول توی ربات مرکزی (باید دقیقاً با آیدی محصول توی دیتابیس مرکزی یکی باشه)
PRODUCT_ID = _str_env("PRODUCT_ID", "guard")

# یوزرنیم ربات فروش مرکزی، برای راهنمایی کاربرا به سمت خرید/تمدید
CENTRAL_BOT_USERNAME = _str_env("CENTRAL_BOT_USERNAME", "")


# ---------------------------------------------------------------------------
# هوش مصنوعی (چت آزاد، تشخیص توهین/فحش، گزارش هوشمند)
# ---------------------------------------------------------------------------

# کلید API آنتروپیک (Claude). اگه خالی باشه، همه‌ی قابلیت‌های AI خودکار غیرفعال
# می‌مونن (بدون کرش کردن ربات) - فقط لازمه یه پیام راهنما به کاربر نشون بدیم.
#
# ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_API_KEY = _str_env("ANTHROPIC_API_KEY")

# مدل استفاده‌شده برای چت آزاد (کیفیت بالاتر، هزینه بیشتر)
AI_CHAT_MODEL = _str_env("AI_CHAT_MODEL", "claude-sonnet-5")

# مدل استفاده‌شده برای تشخیص توهین/فحش و خلاصه‌سازی گزارش (سریع‌تر و ارزون‌تر)
AI_FAST_MODEL = _str_env("AI_FAST_MODEL", "claude-haiku-4-5-20251001")

AI_ENABLED = bool(ANTHROPIC_API_KEY)

# محدودیت نرخ چت آزاد در پیوی (جلوگیری از هزینه‌ی زیاد/سواستفاده)
AI_CHAT_RATE_LIMIT_MAX = _positive_int_env("AI_CHAT_RATE_LIMIT_MAX", 12, minimum=1)
AI_CHAT_RATE_LIMIT_WINDOW = _positive_int_env("AI_CHAT_RATE_LIMIT_WINDOW", 60, minimum=10)

#