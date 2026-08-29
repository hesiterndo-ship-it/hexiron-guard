"""
Lightweight persistence layer built on sqlite3.
"""
import sqlite3
import time
import json
from contextlib import contextmanager
from pathlib import Path

from config import DB_PATH

SCHEMA = """
-- جدول کاربران
CREATE TABLE IF NOT EXISTS users (
    chat_id     INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    username    TEXT,
    first_name  TEXT,
    points      INTEGER DEFAULT 0,
    warns       INTEGER DEFAULT 0,
    joined_at   INTEGER,
    PRIMARY KEY (chat_id, user_id)
);

-- جدول تنظیمات گروه
CREATE TABLE IF NOT EXISTS settings (
    chat_id      INTEGER PRIMARY KEY,
    welcome_text TEXT,
    goodbye_text TEXT,
    rules_text   TEXT,
    locked       INTEGER DEFAULT 0,
    slow_mode    INTEGER DEFAULT 0,
    slow_delay   INTEGER DEFAULT 5,
    force_channels TEXT,
    join_limit   INTEGER DEFAULT 0,
    security_enabled INTEGER DEFAULT 1
);

-- جدول کلمات ممنوعه
CREATE TABLE IF NOT EXISTS badwords (
    chat_id INTEGER NOT NULL,
    word    TEXT NOT NULL,
    PRIMARY KEY (chat_id, word)
);

-- جدول ادمین‌ها با سطح دسترسی
CREATE TABLE IF NOT EXISTS admins (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    level   TEXT DEFAULT 'admin',
    PRIMARY KEY (chat_id, user_id)
);

-- جدول تیکت‌های پشتیبانی
CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    subject     TEXT NOT NULL,
    message     TEXT NOT NULL,
    priority    TEXT DEFAULT 'medium',
    status      TEXT DEFAULT 'open',
    replies     TEXT,
    created_at  INTEGER,
    closed_at   INTEGER
);

-- جدول مسابقات
CREATE TABLE IF NOT EXISTS contests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    status      TEXT DEFAULT 'active',
    start_at    INTEGER,
    end_at      INTEGER,
    winner_id   INTEGER,
    prize       INTEGER DEFAULT 0,
    created_at  INTEGER
);

-- جدول شرکت‌کنندگان در مسابقات
CREATE TABLE IF NOT EXISTS contest_participants (
    contest_id  INTEGER NOT NULL,
    chat_id     INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    score       INTEGER DEFAULT 0,
    PRIMARY KEY (contest_id, user_id)
);

-- جدول واکنش‌ها
CREATE TABLE IF NOT EXISTS reactions (
    chat_id INTEGER NOT NULL,
    word    TEXT NOT NULL,
    reply   TEXT NOT NULL,
    PRIMARY KEY (chat_id, word)
);

-- ==========================================
-- جداول سیستم فروش اشتراک (Subscription Sales System)
-- این جداول فقط توی چت خصوصی با خودِ ربات استفاده می‌شن (نه توی گروه‌ها)
-- و کاملاً مستقل از جداول بالان
-- ==========================================

-- کاربرانی که مشترک هستن (خریدار/مدیر یک گروه)
CREATE TABLE IF NOT EXISTS users_with_subscription (
    user_id             INTEGER PRIMARY KEY,
    username            TEXT,
    first_name          TEXT,
    phone               TEXT,
    group_id            TEXT,
    subscription_type   TEXT,
    subscription_start  INTEGER,
    subscription_end    INTEGER,
    is_active           INTEGER DEFAULT 0,
    created_at          INTEGER
);

-- تنظیمات قابلیت‌های هر گروه مشتری (روشن/خاموش)
CREATE TABLE IF NOT EXISTS group_settings (
    group_id        TEXT PRIMARY KEY,
    antispam        INTEGER DEFAULT 1,
    badword_filter  INTEGER DEFAULT 1,
    ticket_system   INTEGER DEFAULT 1,
    force_subscribe INTEGER DEFAULT 0,
    contest_system  INTEGER DEFAULT 1,
    poll_system     INTEGER DEFAULT 1,
    admin_panel     INTEGER DEFAULT 1,
    user_id         INTEGER
);

-- پکیج‌های اشتراک
CREATE TABLE IF NOT EXISTS plans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    duration_days INTEGER NOT NULL,
    price         INTEGER NOT NULL,
    is_active     INTEGER DEFAULT 1
);

-- تراکنش‌های خرید
CREATE TABLE IF NOT EXISTS transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    plan_id       INTEGER NOT NULL,
    group_id      TEXT,
    amount        INTEGER NOT NULL,
    status        TEXT DEFAULT 'pending',
    screenshot    TEXT,
    admin_note    TEXT,
    created_at    INTEGER,
    approved_at   INTEGER
);

-- شماره کارت‌های دریافت وجه (شماره کارت رمزنگاری‌شده ذخیره می‌شه)
CREATE TABLE IF NOT EXISTS cards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    card_number TEXT NOT NULL,
    bank_name   TEXT,
    owner_name  TEXT,
    is_active   INTEGER DEFAULT 1
);

-- ادمین‌های پنل فروش (جدا از ادمین‌های گروه‌ها)
CREATE TABLE IF NOT EXISTS admins_panel (
    user_id     INTEGER PRIMARY KEY,
    level       TEXT DEFAULT 'sales_admin',
    permissions TEXT,
    added_by    INTEGER
);

-- لاگ فعالیت‌های ادمین (فاز امنیت)
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id  INTEGER NOT NULL,
    action    TEXT NOT NULL,
    detail    TEXT,
    ts        INTEGER
);

-- فعالیت روزانه‌ی هر گروه (برای آمار «پیام‌های امروز» در پنل کاربر)
CREATE TABLE IF NOT EXISTS daily_activity (
    chat_id  INTEGER NOT NULL,
    day      TEXT NOT NULL,
    messages INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, day)
);

-- کدهای تخفیف
CREATE TABLE IF NOT EXISTS discount_codes (
    code       TEXT PRIMARY KEY,
    percent    INTEGER NOT NULL,
    is_active  INTEGER DEFAULT 1,
    created_by INTEGER,
    used_count INTEGER DEFAULT 0,
    created_at INTEGER
);

-- محتوای صفحه‌ی فروش (راهنمای خرید، تبلیغ متنی/ویدیویی) - کلید ثابت، مقدار قابل ویرایش
CREATE TABLE IF NOT EXISTS sales_content (
    key          TEXT PRIMARY KEY,
    content_type TEXT,
    text         TEXT,
    file_id      TEXT,
    updated_by   INTEGER,
    updated_at   INTEGER
);

-- اطلاعات تماس پشتیبانی که توی صفحه‌ی فروش نشون داده میشه
CREATE TABLE IF NOT EXISTS support_info (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    phone       TEXT,
    telegram_id TEXT,
    updated_at  INTEGER
);
"""


@contextmanager
def get_conn():
    """اتصال امن به SQLite - با WAL برای هم‌زمانی بهتر، busy_timeout برای جلوگیری
    از خطای 'database is locked'، و rollback خودکار اگه وسط تراکنش خطا بیفته."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _add_column_if_missing(conn, table: str, column: str, coltype: str):
    """برای دیتابیس‌هایی که از قبل ساخته شدن - ستون جدید رو بدون پاک کردن داده اضافه می‌کنه."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def init_db():
    Path(DB_PATH).touch(exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)

        # مهاجرت ستون‌های جدید برای دیتابیس‌هایی که از نسخه‌های قبلی آپدیت شدن
        _add_column_if_missing(conn, "transactions", "approved_by", "INTEGER")
        _add_column_if_missing(conn, "settings", "ai_moderation", "INTEGER DEFAULT 0")
        _add_column_if_missing(conn, "settings", "trusted_bots", "TEXT DEFAULT ''")
        _add_column_if_missing(conn, "transactions", "discount_code", "TEXT")
        _add_column_if_missing(conn, "transactions", "original_amount", "INTEGER")
        _add_column_if_missing(conn, "users_with_subscription", "group_link", "TEXT")
        _add_column_if_missing(conn, "discount_codes", "valid_days", "INTEGER")
        _add_column_if_missing(conn, "discount_codes", "expires_at", "INTEGER")

        # پکیج‌های پیش‌فرض رو فقط یک‌بار (اگه جدول خالیه) اضافه کن
        count = conn.execute("SELECT COUNT(*) c FROM plans").fetchone()["c"]
        if count == 0:
            conn.executemany(
                "INSERT INTO plans (name, duration_days, price) VALUES (?, ?, ?)",
                [
                    ("1 ماهه", 30, 50000),
                    ("3 ماهه", 90, 120000),
                    ("1 ساله", 365, 350000),
                ],
            )

        # صاحب سراسری ربات (OWNER_ID از .env) رو خودکار super_admin پنل فروش کن
        from config import OWNER_ID
        if OWNER_ID:
            conn.execute(
                "INSERT OR IGNORE INTO admins_panel (user_id, level, added_by) VALUES (?, 'super_admin', 0)",
                (OWNER_ID,),
            )


# ==========================================
# بخش کاربران (Users)
# ==========================================

def upsert_user(chat_id: int, user_id: int, username: str | None, first_name: str | None):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO users (chat_id, user_id, username, first_name, joined_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name
            """,
            (chat_id, user_id, username, first_name, int(time.time())),
        )


def add_points(chat_id: int, user_id: int, amount: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET points = points + ? WHERE chat_id=? AND user_id=?",
            (amount, chat_id, user_id),
        )


def get_user(chat_id: int, user_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        ).fetchone()
        return dict(row) if row else None


def top_users(chat_id: int, limit: int = 10):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE chat_id=? ORDER BY points DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def add_warn(chat_id: int, user_id: int) -> int:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET warns = warns + 1 WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        )
        row = conn.execute(
            "SELECT warns FROM users WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        ).fetchone()
        return row["warns"] if row else 0


def remove_warn(chat_id: int, user_id: int) -> int:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET warns = MAX(warns - 1, 0) WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        )
        row = conn.execute(
            "SELECT warns FROM users WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        ).fetchone()
        return row["warns"] if row else 0


def user_rank(chat_id: int, user_id: int) -> int:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id FROM users WHERE chat_id=? ORDER BY points DESC", (chat_id,)
        ).fetchall()
        ids = [r["user_id"] for r in rows]
        return ids.index(user_id) + 1 if user_id in ids else -1


def get_users_with_warns(chat_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id, username, first_name, warns FROM users WHERE chat_id=? AND warns > 0 ORDER BY warns DESC",
            (chat_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_users(chat_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id, username, first_name, points, warns FROM users WHERE chat_id=? ORDER BY points DESC",
            (chat_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_user_by_id(chat_id: int, user_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        ).fetchone()
        return dict(row) if row else None


def find_user_by_username(chat_id: int, username: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE chat_id=? AND username LIKE ?",
            (chat_id, f"%{username}%")
        ).fetchall()
        return [dict(r) for r in rows]


# ==========================================
# بخش تنظیمات (Settings)
# ==========================================

def _ensure_settings_row(conn, chat_id: int):
    conn.execute(
        "INSERT OR IGNORE INTO settings (chat_id) VALUES (?)", (chat_id,)
    )


def get_settings(chat_id: int) -> dict:
    with get_conn() as conn:
        _ensure_settings_row(conn, chat_id)
        row = conn.execute(
            "SELECT * FROM settings WHERE chat_id=?", (chat_id,)
        ).fetchone()
        return dict(row) if row else {}


def set_setting(chat_id: int, field: str, value):
    allowed_fields = {"welcome_text", "goodbye_text", "rules_text", "locked", "slow_mode", "slow_delay", "force_channels", "join_limit", "security_enabled", "ai_moderation", "trusted_bots"}
    assert field in allowed_fields, f"فیلد {field} مجاز نیست"
    with get_conn() as conn:
        _ensure_settings_row(conn, chat_id)
        conn.execute(f"UPDATE settings SET {field}=? WHERE chat_id=?", (value, chat_id))


# ==========================================
# بخش کلمات ممنوعه (Badwords)
# ==========================================

def add_badword(chat_id: int, word: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO badwords (chat_id, word) VALUES (?, ?)",
            (chat_id, word.lower().strip()),
        )


def remove_badword(chat_id: int, word: str):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM badwords WHERE chat_id=? AND word=?",
            (chat_id, word.lower().strip()),
        )


def list_badwords(chat_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT word FROM badwords WHERE chat_id=?", (chat_id,)
        ).fetchall()
        return [r["word"] for r in rows]


# ==========================================
# محتوای پیش‌فرض گروه (برای گروه‌های تازه - وقتی ربات اضافه می‌شه خودکار ست می‌شه
# تا از همون اول آماده‌ی تست باشه؛ ادمین‌های همون گروه هر لحظه با
# /setwelcome ، /setgoodbye ، /setrules ، /addbadword و /removebadword می‌تونن عوضش کنن)
# ==========================================

DEFAULT_WELCOME_TEXT = (
    "🎉 سلام {name} عزیز، به {chat_title} خوش اومدی!\n\n"
    "📜 لطفاً قبل از هر چیز یه نگاه به قوانین گروه بندازی:\n"
    "{rules}"
)

DEFAULT_GOODBYE_TEXT = "👋 {name} از گروه خارج شد. امیدواریم دوباره ببینیمت!"

DEFAULT_RULES_TEXT = (
    "1. به بقیه‌ی اعضا با احترام رفتار کن.\n"
    "2. فحش، توهین و بی‌احترامی ممنوعه.\n"
    "3. ارسال لینک/تبلیغات بدون اجازه‌ی ادمین ممنوعه.\n"
    "4. اسپم و ارسال پیام‌های پشت سر هم ممنوعه.\n"
    "5. محتوای نامناسب (سیاسی، مذهبی حساسیت‌برانگیز، ۱۸+) ممنوعه.\n"
    "6. به دستورات ادمین‌ها توجه کن.\n\n"
    "⚠️ عدم رعایت قوانین باعث اخطار، بی‌صدا شدن یا اخراج از گروه می‌شه."
)

# نمونه‌ی کوچیک و ملایم فقط برای این‌که فیلتر از همون اول یه چیزی برای تست داشته باشه؛
# ادمین گروه می‌تونه با /addbadword کلمات خودشو اضافه کنه، یا با /importbadwords
# یه فایل badwords.txt کامل (هر کلمه یه خط) رو یک‌جا ایمپورت کنه.
DEFAULT_BADWORDS = ["احمق", "کودن", "خنگ", "عوضی", "بی‌شعور", "لعنتی"]


def seed_default_group_content(chat_id: int):
    """وقتی ربات به یه گروه جدید اضافه می‌شه صدا زده می‌شه. اگه گروه از قبل
    welcome/goodbye/rules نداشته باشه، پیش‌فرض رو ست می‌کنه؛ و اگه لیست کلمات
    ممنوعه‌ش خالیه، چندتا نمونه اضافه می‌کنه. هیچ‌وقت روی تنظیمات موجود
    (که ادمین از قبل خودش عوض کرده) رو نمی‌نویسه."""
    settings = get_settings(chat_id)
    if not settings.get("welcome_text"):
        set_setting(chat_id, "welcome_text", DEFAULT_WELCOME_TEXT)
    if not settings.get("goodbye_text"):
        set_setting(chat_id, "goodbye_text", DEFAULT_GOODBYE_TEXT)
    if not settings.get("rules_text"):
        set_setting(chat_id, "rules_text", DEFAULT_RULES_TEXT)
    if not list_badwords(chat_id):
        for word in DEFAULT_BADWORDS:
            add_badword(chat_id, word)


# ==========================================
# بخش آمار (Stats)
# ==========================================

def chat_stats(chat_id: int) -> dict:
    with get_conn() as conn:
        member_count = conn.execute(
            "SELECT COUNT(*) c FROM users WHERE chat_id=?", (chat_id,)
        ).fetchone()["c"]
        total_points = conn.execute(
            "SELECT COALESCE(SUM(points),0) s FROM users WHERE chat_id=?", (chat_id,)
        ).fetchone()["s"]
        total_warns = conn.execute(
            "SELECT COALESCE(SUM(warns),0) s FROM users WHERE chat_id=?", (chat_id,)
        ).fetchone()["s"]
        return {
            "member_count": member_count,
            "total_points": total_points,
            "total_warns": total_warns,
        }


# ==========================================
# بخش ادمین‌ها (Admins)
# ==========================================

def add_admin(chat_id: int, user_id: int, level: str = "admin"):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO admins (chat_id, user_id, level) VALUES (?, ?, ?)",
            (chat_id, user_id, level)
        )


def remove_admin(chat_id: int, user_id: int):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM admins WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )


def get_admins(chat_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM admins WHERE chat_id=?", (chat_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def is_admin_user(chat_id: int, user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM admins WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        ).fetchone()
        return row is not None


def get_admin_level(chat_id: int, user_id: int) -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT level FROM admins WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        ).fetchone()
        return row["level"] if row else "user"


# ==========================================
# بخش تیکت‌ها (Tickets)
# ==========================================

def create_ticket(chat_id: int, user_id: int, subject: str, message: str, priority: str = "medium") -> int:
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
    with get_conn() as conn:
        row = conn.execute(
            "SELECT replies FROM tickets WHERE chat_id=? AND id=?",
            (chat_id, ticket_id)
        ).fetchone()
        
        if row and row["replies"]:
            replies = json.loads(row["replies"])
        else:
            replies = []
        
        replies.append({
            "admin_id": admin_id,
            "reply": reply,
            "time": int(time.time())
        })
        
        conn.execute(
            "UPDATE tickets SET replies=?, status='in_progress' WHERE chat_id=? AND id=?",
            (json.dumps(replies), chat_id, ticket_id)
        )


def close_ticket(chat_id: int, ticket_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE tickets SET status='closed', closed_at=? WHERE chat_id=? AND id=?",
            (int(time.time()), chat_id, ticket_id)
        )


def get_ticket_stats(chat_id: int) -> dict:
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


# ==========================================
# بخش مسابقات (Contests)
# ==========================================

def create_contest(chat_id: int, name: str, contest_type: str, duration: int, prize: int = 0) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO contests (chat_id, name, type, status, start_at, end_at, prize, created_at)
            VALUES (?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (chat_id, name, contest_type, int(time.time()), int(time.time()) + duration, prize, int(time.time()))
        )
        return cursor.lastrowid


def get_active_contest(chat_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM contests 
            WHERE chat_id=? AND status='active' 
            ORDER BY created_at DESC LIMIT 1
            """,
            (chat_id,)
        ).fetchone()
        return dict(row) if row else None


def add_contest_participant(contest_id: int, chat_id: int, user_id: int):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO contest_participants (contest_id, chat_id, user_id)
            VALUES (?, ?, ?)
            """,
            (contest_id, chat_id, user_id)
        )


def update_contest_score(contest_id: int, user_id: int, points: int):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE contest_participants 
            SET score = score + ? 
            WHERE contest_id=? AND user_id=?
            """,
            (points, contest_id, user_id)
        )


def get_contest_winners(contest_id: int, limit: int = 10) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT cp.*, u.first_name, u.username 
            FROM contest_participants cp
            LEFT JOIN users u ON cp.user_id = u.user_id AND cp.chat_id = u.chat_id
            WHERE cp.contest_id=?
            ORDER BY cp.score DESC 
            LIMIT ?
            """,
            (contest_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


# ==========================================
# بخش واکنش‌ها (Reactions)
# ==========================================

def add_reaction(chat_id: int, word: str, reply: str):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO reactions (chat_id, word, reply)
            VALUES (?, ?, ?)
            """,
            (chat_id, word.lower().strip(), reply)
        )


def remove_reaction(chat_id: int, word: str):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM reactions WHERE chat_id=? AND word=?",
            (chat_id, word.lower().strip())
        )


def list_reactions(chat_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT word, reply FROM reactions WHERE chat_id=? ORDER BY word",
            (chat_id,)
        ).fetchall()
        return [dict(r) for r in rows]

# ==========================================
# بخش سیستم فروش اشتراک (Subscription Sales System)
# ==========================================

# ----- users_with_subscription -----

def get_subscription(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users_with_subscription WHERE user_id=?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def get_subscription_by_group(group_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users_with_subscription WHERE group_id=? ORDER BY subscription_end DESC LIMIT 1",
            (str(group_id),),
        ).fetchone()
        return dict(row) if row else None


def is_group_subscribed(group_id: int | str) -> bool:
    """بررسی می‌کنه این گروه (بر اساس chat_id) الان اشتراک فعال و منقضی‌نشده داره یا نه.
    برای گیت کردن خدمات گروه‌هایی که اشتراک ندارن استفاده می‌شه."""
    sub = get_subscription_by_group(group_id)
    if not sub or not sub.get("is_active"):
        return False
    end = sub.get("subscription_end")
    if not end:
        return False
    return end > int(time.time())


def upsert_subscription_contact(user_id: int, username: str | None, first_name: str | None,
                                 phone: str | None = None, group_id: str | None = None,
                                 group_link: str | None = None):
    """اطلاعات پایه‌ی کاربر (قبل از تایید تراکنش) رو ثبت/به‌روزرسانی می‌کنه."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT user_id FROM users_with_subscription WHERE user_id=?", (user_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE users_with_subscription
                   SET username=?, first_name=?,
                       phone=COALESCE(?, phone),
                       group_id=COALESCE(?, group_id),
                       group_link=COALESCE(?, group_link)
                   WHERE user_id=?""",
                (username, first_name, phone, group_id, group_link, user_id),
            )
        else:
            conn.execute(
                """INSERT INTO users_with_subscription
                   (user_id, username, first_name, phone, group_id, group_link, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
                (user_id, username, first_name, phone, group_id, group_link, int(time.time())),
            )


def activate_subscription(user_id: int, group_id: str, subscription_type: str, duration_days: int):
    """بعد از تایید تراکنش، اشتراک رو فعال/تمدید می‌کنه."""
    now = int(time.time())
    with get_conn() as conn:
        current = conn.execute(
            "SELECT subscription_end, is_active FROM users_with_subscription WHERE user_id=?",
            (user_id,),
        ).fetchone()

        # اگه اشتراک قبلی هنوز فعاله، از تاریخ پایانش تمدید کن؛ وگرنه از همین الان
        if current and current["is_active"] and current["subscription_end"] and current["subscription_end"] > now:
            start = current["subscription_end"]
        else:
            start = now
        end = start + duration_days * 86400

        conn.execute(
            """UPDATE users_with_subscription
               SET group_id=?, subscription_type=?, subscription_start=?,
                   subscription_end=?, is_active=1
               WHERE user_id=?""",
            (group_id, subscription_type, start, end, user_id),
        )
        return end


def deactivate_subscription(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE users_with_subscription SET is_active=0 WHERE user_id=?", (user_id,))


def get_all_subscriptions() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM users_with_subscription ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


# ----- group_settings -----

DEFAULT_FEATURE_FIELDS = [
    "antispam", "badword_filter", "ticket_system",
    "force_subscribe", "contest_system", "poll_system", "admin_panel",
]


def ensure_group_settings(group_id: str, user_id: int | None = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO group_settings (group_id, user_id) VALUES (?, ?)",
            (str(group_id), user_id),
        )


def get_group_settings(group_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM group_settings WHERE group_id=?", (str(group_id),)
        ).fetchone()
        return dict(row) if row else None


def toggle_group_setting(group_id: str, field: str) -> int:
    if field not in DEFAULT_FEATURE_FIELDS:
        raise ValueError(f"Unknown feature field: {field}")
    ensure_group_settings(group_id)
    with get_conn() as conn:
        current = conn.execute(
            f"SELECT {field} FROM group_settings WHERE group_id=?", (str(group_id),)
        ).fetchone()[field]
        new_val = 0 if current else 1
        conn.execute(
            f"UPDATE group_settings SET {field}=? WHERE group_id=?",
            (new_val, str(group_id)),
        )
        return new_val


def is_feature_enabled(group_id, feature: str) -> bool:
    """
    اگه گروه هنوز هیچ ردیف تنظیماتی نداره (یعنی هنوز وارد چرخه‌ی فروش نشده)
    قابلیت رو فعال فرض می‌کنیم تا رفتار گروه‌های فعلی نشکنه.
    """
    if feature not in DEFAULT_FEATURE_FIELDS:
        return True
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {feature} FROM group_settings WHERE group_id=?", (str(group_id),)
        ).fetchone()
        if row is None:
            return True
        return bool(row[feature])


# ----- plans -----

def get_active_plans() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM plans WHERE is_active=1 ORDER BY duration_days"
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_plans() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM plans ORDER BY duration_days").fetchall()
        return [dict(r) for r in rows]


def get_plan(plan_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        return dict(row) if row else None


def update_plan_price(plan_id: int, price: int):
    with get_conn() as conn:
        conn.execute("UPDATE plans SET price=? WHERE id=?", (price, plan_id))


# ----- transactions -----

def create_transaction(user_id: int, plan_id: int, group_id: str, amount: int, screenshot: str | None,
                        discount_code: str | None = None, original_amount: int | None = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO transactions
               (user_id, plan_id, group_id, amount, status, screenshot, discount_code, original_amount, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
            (user_id, plan_id, group_id, amount, screenshot, discount_code,
             original_amount if original_amount is not None else amount, int(time.time())),
        )
        return cur.lastrowid


def get_transaction(tx_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
        return dict(row) if row else None


def get_pending_transactions() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE status='pending' ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]


def set_transaction_status(tx_id: int, status: str, admin_note: str | None = None, approved_by: int | None = None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE transactions SET status=?, admin_note=?, approved_at=?, approved_by=? WHERE id=?",
            (status, admin_note, int(time.time()), approved_by, tx_id),
        )


def get_sales_report() -> dict:
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM transactions WHERE status='approved'"
        ).fetchone()
        per_plan = conn.execute(
            """SELECT p.name AS plan_name, COUNT(*) AS cnt, COALESCE(SUM(t.amount),0) AS revenue
               FROM transactions t JOIN plans p ON p.id = t.plan_id
               WHERE t.status='approved'
               GROUP BY t.plan_id"""
        ).fetchall()
        per_admin = conn.execute(
            """SELECT t.approved_by AS admin_id, COUNT(*) AS cnt, COALESCE(SUM(t.amount),0) AS revenue
               FROM transactions t
               WHERE t.status='approved' AND t.approved_by IS NOT NULL
               GROUP BY t.approved_by
               ORDER BY revenue DESC"""
        ).fetchall()
        return {
            "total_count": total["c"],
            "total_revenue": total["s"],
            "per_plan": [dict(r) for r in per_plan],
            "per_admin": [dict(r) for r in per_admin],
        }


# ----- cards -----

def add_card(card_number: str, bank_name: str, owner_name: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO cards (card_number, bank_name, owner_name) VALUES (?, ?, ?)",
            (card_number, bank_name, owner_name),
        )
        return cur.lastrowid


def remove_card(card_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM cards WHERE id=?", (card_id,))


def get_active_cards() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM cards WHERE is_active=1").fetchall()
        return [dict(r) for r in rows]


def get_all_cards() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM cards ORDER BY id").fetchall()
        return [dict(r) for r in rows]


# ----- admins_panel -----

def add_panel_admin(user_id: int, level: str, added_by: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO admins_panel (user_id, level, added_by) VALUES (?, ?, ?)",
            (user_id, level, added_by),
        )


def remove_panel_admin(user_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM admins_panel WHERE user_id=?", (user_id,))


def get_panel_admin(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM admins_panel WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_panel_admins() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM admins_panel ORDER BY user_id").fetchall()
        return [dict(r) for r in rows]


def is_panel_admin(user_id: int) -> bool:
    return get_panel_admin(user_id) is not None


# ----- admin_audit_log -----

def log_admin_action(admin_id: int, action: str, detail: str = ""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO admin_audit_log (admin_id, action, detail, ts) VALUES (?, ?, ?, ?)",
            (admin_id, action, detail, int(time.time())),
        )


def get_recent_audit_log(limit: int = 50) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM admin_audit_log ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ----- daily_activity (برای آمار پنل کاربر) -----

def _today_str() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def increment_daily_activity(chat_id: int):
    day = _today_str()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO daily_activity (chat_id, day, messages) VALUES (?, ?, 1)
               ON CONFLICT(chat_id, day) DO UPDATE SET messages = messages + 1""",
            (chat_id, day),
        )


def get_today_message_count(chat_id: int) -> int:
    day = _today_str()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT messages FROM daily_activity WHERE chat_id=? AND day=?", (chat_id, day)
        ).fetchone()
        return row["messages"] if row else 0


def get_new_users_today(chat_id: int) -> int:
    start_of_day = int(time.mktime(time.strptime(_today_str(), "%Y-%m-%d")))
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) c FROM users WHERE chat_id=? AND joined_at >= ?",
            (chat_id, start_of_day),
        ).fetchone()
        return row["c"]


# ----- discount_codes -----

def create_discount_code(code: str, percent: int, created_by: int, valid_days: int | None = None) -> bool:
    """کد جدید می‌سازه. اگه کد از قبل وجود داشته باشه False برمی‌گردونه.
    valid_days: چند روز این کد اعتبار داره (None یعنی بدون انقضا/نامحدود)."""
    code = code.strip().upper()
    now = int(time.time())
    expires_at = now + valid_days * 86400 if valid_days else None
    with get_conn() as conn:
        existing = conn.execute("SELECT code FROM discount_codes WHERE code=?", (code,)).fetchone()
        if existing:
            return False
        conn.execute(
            """INSERT INTO discount_codes (code, percent, created_by, created_at, valid_days, expires_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (code, percent, created_by, now, valid_days, expires_at),
        )
        return True


def is_discount_code_valid(discount: dict) -> bool:
    """چک می‌کنه کد تخفیف هم فعال باشه و هم (اگه اعتبار زمانی داره) منقضی نشده باشه."""
    if not discount or not discount.get("is_active"):
        return False
    expires_at = discount.get("expires_at")
    if expires_at and expires_at < int(time.time()):
        return False
    return True


def get_discount_code(code: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM discount_codes WHERE code=?", (code.strip().upper(),)
        ).fetchone()
        return dict(row) if row else None


def get_all_discount_codes() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM discount_codes ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def deactivate_discount_code(code: str):
    with get_conn() as conn:
        conn.execute("UPDATE discount_codes SET is_active=0 WHERE code=?", (code.strip().upper(),))


def increment_discount_code_usage(code: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE discount_codes SET used_count = used_count + 1 WHERE code=?",
            (code.strip().upper(),),
        )


# ----- sales_content (راهنمای خرید / تبلیغ متنی و ویدیویی صفحه‌ی فروش) -----

def set_sales_content(key: str, content_type: str, text: str | None, file_id: str | None, updated_by: int):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO sales_content (key, content_type, text, file_id, updated_by, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                   content_type=excluded.content_type, text=excluded.text,
                   file_id=excluded.file_id, updated_by=excluded.updated_by, updated_at=excluded.updated_at""",
            (key, content_type, text, file_id, updated_by, int(time.time())),
        )


def get_sales_content(key: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM sales_content WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None


def delete_sales_content(key: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM sales_content WHERE key=?", (key,))


# ----- support_info (شماره تماس/آیدی پشتیبانی که توی صفحه فروش نشون داده میشه) -----

def set_support_info(phone: str | None, telegram_id: str | None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO support_info (id, phone, telegram_id, updated_at) VALUES (1, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   phone=COALESCE(excluded.phone, support_info.phone),
                   telegram_id=COALESCE(excluded.telegram_id, support_info.telegram_id),
                   updated_at=excluded.updated_at""",
            (phone, telegram_id, int(time.time())),
        )


def get_support_info() -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM support_info WHERE id=1").fetchone()
        return dict(row) if row else None