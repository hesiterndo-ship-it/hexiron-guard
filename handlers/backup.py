"""
Production-grade SQLite backup / restore system.

این فایل فقط مسئول بک‌آپ و بازیابی دیتابیس است.
منطق فروش و پرداخت در این فایل وجود ندارد و نباید اضافه شود.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from config import DB_PATH
from utils.permissions import require_admin
from utils.helpers import escape_markdown


logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURATION
# ============================================================

BACKUP_DIR = Path("backups")

MAX_BACKUPS = 7

BACKUP_NAME_RE = re.compile(
    r"^guardbot_backup_\d{8}_\d{6}\.db$"
)

PRE_RESTORE_NAME_RE = re.compile(
    r"^guardbot_pre_restore_\d{8}_\d{6}\.db$"
)


# ============================================================
# PATH HELPERS
# ============================================================

def ensure_backup_dir() -> Path:
    """
    Create backup directory if necessary.
    """

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    return BACKUP_DIR


def get_db_path() -> Path:
    """
    Return database path as Path.
    """

    return Path(DB_PATH)


def get_backup_filename() -> str:
    """
    Generate a safe backup filename.
    """

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    return (
        f"guardbot_backup_{timestamp}.db"
    )


def get_pre_restore_filename() -> str:
    """
    Generate a backup filename used immediately
    before restoring another database.
    """

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    return (
        f"guardbot_pre_restore_{timestamp}.db"
    )


# ============================================================
# SQLITE VALIDATION
# ============================================================

def sqlite_integrity_check(
    database_path: Path,
) -> bool:
    """
    Validate SQLite database integrity.

    Returns True only when SQLite reports 'ok'.
    """

    if not database_path.is_file():
        return False

    connection = None

    try:
        connection = sqlite3.connect(
            f"file:{database_path.resolve()}?mode=ro",
            uri=True,
            timeout=10,
        )

        row = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()

        return bool(
            row
            and row[0] == "ok"
        )

    except sqlite3.Error:
        logger.exception(
            "SQLite integrity check failed."
        )
        return False

    finally:
        if connection is not None:
            connection.close()


def sqlite_quick_check(
    database_path: Path,
) -> bool:
    """
    Faster SQLite validation.
    """

    if not database_path.is_file():
        return False

    connection = None

    try:
        connection = sqlite3.connect(
            f"file:{database_path.resolve()}?mode=ro",
            uri=True,
            timeout=10,
        )

        row = connection.execute(
            "PRAGMA quick_check"
        ).fetchone()

        return bool(
            row
            and row[0] == "ok"
        )

    except sqlite3.Error:
        logger.exception(
            "SQLite quick check failed."
        )
        return False

    finally:
        if connection is not None:
            connection.close()


# ============================================================
# BACKUP CREATION
# ============================================================

def create_sqlite_backup(
    source_path: Path,
    destination_path: Path,
) -> None:
    """
    Create a consistent SQLite backup using SQLite's
    online backup API instead of copying the live file directly.
    """

    source = None
    destination = None

    try:
        source = sqlite3.connect(
            str(source_path),
            timeout=30,
        )

        destination = sqlite3.connect(
            str(destination_path),
            timeout=30,
        )

        with destination:
            source.backup(
                destination,
                pages=100,
                sleep=0.05,
            )

    finally:
        if source is not None:
            source.close()

        if destination is not None:
            destination.close()


def create_backup(
    *,
    prefix: str = "normal",
) -> Path:
    """
    Create and validate a database backup.

    prefix:
        normal       -> normal user-requested backup
        pre_restore  -> safety snapshot before restore
    """

    ensure_backup_dir()

    source_path = get_db_path()

    if not source_path.is_file():
        raise FileNotFoundError(
            "Database file does not exist."
        )

    if prefix == "pre_restore":
        filename = get_pre_restore_filename()
    else:
        filename = get_backup_filename()

    destination_path = (
        BACKUP_DIR / filename
    )

    temp_path = (
        BACKUP_DIR
        / f".{filename}.tmp"
    )

    try:
        create_sqlite_backup(
            source_path,
            temp_path,
        )

        if not sqlite_integrity_check(
            temp_path
        ):
            raise RuntimeError(
                "Created backup failed integrity check."
            )

        os.replace(
            temp_path,
            destination_path,
        )

        return destination_path

    except Exception:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            logger.exception(
                "Unable to remove temporary backup."
            )

        raise


# ============================================================
# BACKUP LIST
# ============================================================

def list_backups(
    include_pre_restore: bool = False,
) -> list[dict]:
    """
    Return available backups sorted newest first.
    """

    ensure_backup_dir()

    result = []

    for path in BACKUP_DIR.iterdir():

        if not path.is_file():
            continue

        filename = path.name

        normal = bool(
            BACKUP_NAME_RE.fullmatch(
                filename
            )
        )

        pre_restore = bool(
            PRE_RESTORE_NAME_RE.fullmatch(
                filename
            )
        )

        if not normal and not (
            include_pre_restore
            and pre_restore
        ):
            continue

        try:
            stat = path.stat()

            result.append(
                {
                    "name": filename,
                    "path": path,
                    "size": stat.st_size,
                    "date": datetime.fromtimestamp(
                        stat.st_mtime
                    ).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "mtime": stat.st_mtime,
                    "pre_restore": pre_restore,
                }
            )

        except OSError:
            logger.exception(
                "Unable to inspect backup: %s",
                filename,
            )

    return sorted(
        result,
        key=lambda item: item["mtime"],
        reverse=True,
    )


# ============================================================
# BACKUP RETENTION
# ============================================================

def cleanup_old_backups() -> None:
    """
    Keep only MAX_BACKUPS normal backups.

    Pre-restore safety snapshots are NOT counted here.
    """

    backups = list_backups(
        include_pre_restore=False
    )

    for backup in backups[MAX_BACKUPS:]:
        path = backup["path"]

        try:
            path.unlink()

            logger.info(
                "Old backup deleted: %s",
                backup["name"],
            )

        except OSError:
            logger.exception(
                "Unable to delete old backup: %s",
                backup["name"],
            )


# ============================================================
# USER COMMAND: /backup
# ============================================================

async def backup(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    Manually create a database backup.
    """

    if not await require_admin(
        update,
        context,
    ):
        return

    message = update.effective_message

    if message is None:
        return

    try:
        backup_path = create_backup()

        cleanup_old_backups()

        size_kb = (
            backup_path.stat().st_size
            / 1024
        )

        await message.reply_text(
            "✅ *بک‌آپ با موفقیت ایجاد شد!*\n\n"
            f"📁 نام: `{escape_markdown(backup_path.name)}`\n"
            f"📦 حجم: `{size_kb:.1f} KB`\n"
            f"📅 زمان: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
            "🔐 فایل قبل از ثبت، Integrity Check شده است.",
            parse_mode="Markdown",
        )

    except FileNotFoundError:
        await message.reply_text(
            "❌ فایل دیتابیس پیدا نشد."
        )

    except Exception:
        logger.exception(
            "Manual database backup failed."
        )

        await message.reply_text(
            "❌ گرفتن بک‌آپ با خطا مواجه شد.\n"
            "جزئیات فنی در لاگ ثبت شده است."
        )


# ============================================================
# RESTORE HELPERS
# ============================================================

def validate_backup_filename(
    filename: str,
) -> bool:
    """
    Only allow generated backup filenames.
    """

    return bool(
        BACKUP_NAME_RE.fullmatch(
            filename
        )
    )


def resolve_backup_path(
    filename: str,
) -> Path | None:
    """
    Safely resolve a backup path.

    Prevents path traversal.
    """

    if not validate_backup_filename(
        filename
    ):
        return None

    root = (
        BACKUP_DIR
        .resolve()
    )

    candidate = (
        BACKUP_DIR / filename
    ).resolve()

    try:
        candidate.relative_to(root)
    except ValueError:
        return None

    if not candidate.is_file():
        return None

    return candidate


# ============================================================
# USER COMMAND: /restore
# ============================================================

async def restore(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    Restore a validated SQLite backup.

    Usage:
        /restore
        /restore guardbot_backup_YYYYMMDD_HHMMSS.db
    """

    if not await require_admin(
        update,
        context,
    ):
        return

    message = update.effective_message

    if message is None:
        return

    # --------------------------------------------------------
    # SHOW AVAILABLE BACKUPS
    # --------------------------------------------------------

    if not context.args:

        backups = list_backups()

        if not backups:
            await message.reply_text(
                "📭 هیچ بک‌آپ سالمی موجود نیست."
            )
            return

        text = (
            "📋 *بک‌آپ‌های موجود:*\n\n"
        )

        for index, item in enumerate(
            backups[:10],
            1,
        ):
            text += (
                f"{index}. "
                f"`{escape_markdown(item['name'])}`\n"
                f"   📅 {item['date']}\n"
                f"   📦 {item['size'] / 1024:.1f} KB\n\n"
            )

        text += (
            "برای بازیابی:\n"
            "`/restore نام_فایل`"
        )

        await message.reply_text(
            text,
            parse_mode="Markdown",
        )

        return

    # --------------------------------------------------------
    # VALIDATE ARGUMENT COUNT
    # --------------------------------------------------------

    if len(context.args) != 1:
        await message.reply_text(
            "❌ فرمت صحیح:\n"
            "`/restore guardbot_backup_YYYYMMDD_HHMMSS.db`",
            parse_mode="Markdown",
        )
        return

    backup_name = os.path.basename(
        context.args[0]
    )

    backup_path = resolve_backup_path(
        backup_name
    )

    if backup_path is None:
        await message.reply_text(
            "❌ فایل بک‌آپ نامعتبر یا پیدا نشد."
        )
        return

    # --------------------------------------------------------
    # VALIDATE SQLITE
    # --------------------------------------------------------

    await message.reply_text(
        "🔍 در حال بررسی سلامت بک‌آپ..."
    )

    if not sqlite_integrity_check(
        backup_path
    ):
        await message.reply_text(
            "❌ این بک‌آپ سالم نیست و بازیابی نشد."
        )
        return

    # --------------------------------------------------------
    # CREATE SAFETY BACKUP
    # --------------------------------------------------------

    try:
        current_database = get_db_path()

        if current_database.is_file():

            safety_backup = create_backup(
                prefix="pre_restore"
            )

            logger.info(
                "Pre-restore safety backup created: %s",
                safety_backup.name,
            )

    except Exception:
        logger.exception(
            "Unable to create pre-restore safety backup."
        )

        await message.reply_text(
            "❌ قبل از بازیابی نتوانستم از دیتابیس فعلی "
            "بک‌آپ ایمنی بگیرم؛ عملیات متوقف شد."
        )

        return

    # --------------------------------------------------------
    # RESTORE ATOMICALLY
    # --------------------------------------------------------

    database_path = get_db_path()

    database_parent = (
        database_path.parent
    )

    database_parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_restore = None

    try:

        with tempfile.NamedTemporaryFile(
            prefix=".guardbot_restore_",
            suffix=".db",
            dir=str(database_parent),
            delete=False,
        ) as temp_file:

            temp_restore = Path(
                temp_file.name
            )

        # Copy backup into a temporary file.
        shutil.copy2(
            backup_path,
            temp_restore,
        )

        # Verify copied file once more.
        if not sqlite_integrity_check(
            temp_restore
        ):
            raise RuntimeError(
                "Temporary restored database failed integrity check."
            )

        # Atomic replacement.
        os.replace(
            temp_restore,
            database_path,
        )

        temp_restore = None

        await message.reply_text(
            "✅ *بازیابی با موفقیت انجام شد!*\n\n"
            f"📁 فایل: `{escape_markdown(backup_name)}`\n"
            f"📅 زمان: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
            "⚠️ برای اطمینان از بازشدن اتصال‌های دیتابیس، "
            "ربات را ری‌استارت کن.",
            parse_mode="Markdown",
        )

    except Exception:
        logger.exception(
            "Database restore failed."
        )

        if temp_restore is not None:
            try:
                temp_restore.unlink(
                    missing_ok=True
                )
            except OSError:
                logger.exception(
                    "Unable to remove restore temp file."
                )

        await message.reply_text(
            "❌ بازیابی انجام نشد.\n"
            "دیتابیس فعلی دست‌نخورده باقی مانده است.\n"
            "جزئیات فنی در لاگ ثبت شده."
        )


# ============================================================
# USER COMMAND: /backups
# ============================================================

async def backups_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    List database backups.
    """

    if not await require_admin(
        update,
        context,
    ):
        return

    message = update.effective_message

    if message is None:
        return

    backups = list_backups()

    if not backups:
        await message.reply_text(
            "📭 هیچ بک‌آپی موجود نیست."
        )
        return

    total_size = sum(
        item["size"]
        for item in backups
    )

    total_size_mb = (
        total_size
        / (1024 * 1024)
    )

    text = (
        "💾 *مدیریت بک‌آپ*\n\n"
        f"📊 تعداد: `{len(backups)}`\n"
        f"📦 حجم کل: `{total_size_mb:.2f} MB`\n\n"
    )

    for item in backups[:10]:

        size_kb = (
            item["size"]
            / 1024
        )

        text += (
            f"📁 `{escape_markdown(item['name'])}`\n"
            f"   📅 {item['date']}\n"
            f"   📦 {size_kb:.1f} KB\n\n"
        )

    if len(backups) > 10:
        text += (
            f"... و {len(backups) - 10} بک‌آپ دیگر\n\n"
        )

    text += (
        "دستورها:\n"
        "`/backup` — گرفتن بک‌آپ\n"
        "`/restore` — نمایش بک‌آپ‌ها\n"
        "`/restore نام_فایل` — بازیابی"
    )

    await message.reply_text(
        text,
        parse_mode="Markdown",
    )


# ============================================================
# AUTOMATIC BACKUP
# ============================================================

def auto_backup() -> None:
    """
    Create an automatic backup.

    This function is intentionally synchronous because it may
    also be called from a scheduler/job worker.
    """

    try:

        backup_path = create_backup()

        cleanup_old_backups()

        logger.info(
            "Automatic database backup created: %s",
            backup_path.name,
        )

    except FileNotFoundError:

        logger.warning(
            "Automatic backup skipped: database does not exist."
        )

    except Exception:

        logger.exception(
            "Automatic database backup failed."
        )


# ============================================================
# HANDLER REGISTRATION
# ============================================================

def register_backup_handlers(app):
    """
    Register backup-related commands.
    """

    app.add_handler(
        CommandHandler(
            "backup",
            backup,
        )
    )

    app.add_handler(
        CommandHandler(
            "restore",
            restore,
        )
    )

    app.add_handler(
        CommandHandler(
            "backups",
            backups_list,
        )
    )