"""Small diagnostic for the sales/admin panel database.

Run from the project root with the same environment as the bot:
    python check_admin.py
"""
import sqlite3

from config import DB_PATH, OWNER_ID


def main() -> None:
    print("=" * 50)
    print("🔍 بررسی ادمین‌های پنل")
    print("=" * 50)
    print(f"Database: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='admins_panel'"
        )
        if not cursor.fetchone():
            print("⚠️ جدول admins_panel وجود ندارد؛ ایجاد می‌شود.")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS admins_panel (
                    user_id INTEGER PRIMARY KEY,
                    level TEXT DEFAULT 'sales_admin',
                    permissions TEXT,
                    added_by INTEGER
                )
                """
            )
            conn.commit()
            print("✅ جدول admins_panel ساخته شد.")

        cursor.execute("SELECT user_id, level FROM admins_panel ORDER BY user_id")
        admins = cursor.fetchall()
        if admins:
            print("\n📋 ادمین‌های فعلی:")
            for user_id, level in admins:
                print(f"  🆔 {user_id} - سطح: {level}")
        else:
            print("\n📭 هیچ ادمینی در دیتابیس ثبت نشده است.")

        if OWNER_ID > 0:
            print(f"\n👤 OWNER_ID: {OWNER_ID}")
            cursor.execute(
                """
                INSERT INTO admins_panel (user_id, level, added_by)
                VALUES (?, 'super_admin', 0)
                ON CONFLICT(user_id) DO UPDATE SET level='super_admin'
                """,
                (OWNER_ID,),
            )
            conn.commit()
            print(f"✅ OWNER_ID {OWNER_ID} به‌عنوان super_admin ثبت شد.")
        else:
            print("\n⚠️ OWNER_ID در محیط تنظیم نشده یا صفر است.")

        cursor.execute("SELECT user_id, level FROM admins_panel ORDER BY user_id")
        print("\n📋 فهرست نهایی:")
        for user_id, level in cursor.fetchall():
            print(f"  🆔 {user_id} - سطح: {level}")
        print("\n✅ بررسی با موفقیت انجام شد.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
