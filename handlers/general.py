"""General, non-admin commands available to everyone."""
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

import database as db

HELP_TEXT = """
🛡️ *راهنمای کامل ربات گارد گروه*

📌 *دستورات عمومی (بدون اسلش)*
start - شروع کار با ربات
help - همین راهنما
rules - قوانین گروه
stats - آمار کلی گروه
mylevel - امتیاز و رتبه من
top - برترین‌های گروه
panel - پنل مدیریت

👑 *دستورات ادمین (مدیریت کاربران)*
warn - اخطار به کاربر (با ریپلای)
unwarn - حذف اخطار (با ریپلای)
mute - بی‌صدا کردن کاربر (با ریپلای)
unmute - باز کردن صدای کاربر (با ریپلای)
kick - اخراج کاربر (با ریپلای)
ban - بن کردن کاربر (با ریپلای)
unban - آنبن کردن کاربر (با ریپلای)

🔧 *دستورات ادمین (مدیریت گروه)*
lock - قفل کردن گروه
unlock - باز کردن قفل گروه
pin - پین کردن پیام (با ریپلای)
unpin - برداشتن پین
setwelcome - تنظیم پیام خوش‌آمدگویی
setgoodbye - تنظیم پیام خداحافظی
setrules - تنظیم قوانین گروه

🚫 *مدیریت کلمات ممنوعه*
addbadword - افزودن کلمه ممنوعه
removebadword - حذف کلمه ممنوعه
listbadwords - لیست کلمات ممنوعه
importbadwords - ایمپورت از فایل

👑 *مدیریت ادمین‌ها*
addadmin - افزودن ادمین (با ریپلای)
removeadmin - حذف ادمین (با ریپلای)
setlevel - تنظیم سطح دسترسی
mypermissions - مشاهده دسترسی‌های من

🎫 *سیستم تیکت*
ticket - ارسال تیکت جدید
mytickets - مشاهده تیکت‌های من
ticketinfo - جزئیات تیکت
reply - پاسخ به تیکت (ادمین)
close - بستن تیکت
tickets - مدیریت تیکت‌ها (ادمین)

📢 *عضویت اجباری*
setforce - تنظیم کانال اجباری
forcestatus - وضعیت عضویت من

🤖 *واکنش‌ها*
addreaction - افزودن واکنش به کلمه
removereaction - حذف واکنش
listreactions - لیست واکنش‌ها

📊 *گزارشات*
dailyreport - گزارش روزانه (ادمین)
weeklyreport - گزارش هفتگی (ادمین)
monthlyreport - گزارش ماهانه (ادمین)
userreport - گزارش کاربر (ادمین)

💾 *بک‌آپ*
backup - گرفتن بک‌آپ (ادمین)
restore - بازیابی بک‌آپ (ادمین)
backups - لیست بک‌آپ‌ها (ادمین)

🔒 *امنیت*
setjoinlimit - محدودیت ورود کاربران (ادمین)
security - فعال/غیرفعال کردن امنیت (ادمین)
securityreport - گزارش امنیتی (ادمین)

📝 *نظرسنجی*
poll - ایجاد نظرسنجی (ادمین)
pollresults - نتایج نظرسنجی
closepoll - بستن نظرسنجی (ادمین)

🤖 *هوش مصنوعی*
(توی پیوی ربات، هر پیام متنی رو مستقیم بفرست) - چت آزاد با AI
aimod - روشن/خاموش کردن تشخیص هوشمند فحش (ادمین، توی گروه)
aireport - گزارش هوشمند گروه، ارسال به پیوی (ادمین، توی گروه)
tagall - تگ کردن همه‌ی اعضای شناخته‌شده (ادمین، توی گروه)

💡 *نکته:* برای استفاده از دستورات، فقط کافیست نام دستور را تایپ کنید (بدون نیاز به /)
"""


def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📊 آمار گروه"), KeyboardButton("🏅 برترین‌ها")],
        [KeyboardButton("⭐️ امتیاز من"), KeyboardButton("📜 قوانین")],
        [KeyboardButton("🛡️ پنل مدیریت"), KeyboardButton("📋 راهنما")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def groupid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(f"🆔 آیدی این گروه:\n`{update.effective_chat.id}`", parse_mode="Markdown")


async def private_start_redirect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """این ربات (گارد) دیگه خودش فروش نداره. کاربری که توی پیوی این ربات
    /start یا /shop بزنه، به ربات فروش مرکزی هدایت می‌شه."""
    from config import CENTRAL_BOT_USERNAME
    if CENTRAL_BOT_USERNAME:
        await update.effective_message.reply_text(
            "🛡️ این ربات فقط توی گروه کار می‌کنه.\n\n"
            f"برای خرید/تمدید لایسنس یا مدیریت اشتراک گروهت، برو به @{CENTRAL_BOT_USERNAME} و /shop رو بزن.\n\n"
            "برای گرفتن آیدی گروه: ربات رو به گروهت اضافه کن و توی خودِ گروه /groupid رو بزن."
        )
    else:
        await update.effective_message.reply_text("🛡️ این ربات فقط توی گروه کار می‌کنه.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    db.upsert_user(chat_id, user_id, update.effective_user.username, update.effective_user.first_name)
    
    from utils.permissions import is_admin
    is_admin_user = await is_admin(update, context, user_id)
    
    keyboard = get_main_keyboard()
    if is_admin_user:
        text = (
            "🛡️ سلام ادمین عزیز! 👋\n\n"
            "همه‌ی ابزارهای مدیریت گروه (اخطار، بی‌صدا، اخراج، بن، قفل/باز، تنظیمات، "
            "کلمات ممنوعه، گزارش‌ها، بک‌آپ، تیکت‌ها و ...) الان همه توی یه پنل جمع شدن.\n"
            "برای باز کردنش دستور /panel رو بزن یا از دکمه‌ی «🛡️ پنل مدیریت» پایین استفاده کن."
        )
    else:
        text = "👋 سلام!\n\nاز دکمه‌های زیر استفاده کنید:"
    
    await update.effective_message.reply_text(
        text,
        reply_markup=keyboard
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_markdown(HELP_TEXT)


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    settings = db.get_settings(chat_id)
    text = settings.get("rules_text") or "قانونی برای این گروه تنظیم نشده است."
    await update.effective_message.reply_text(f"📜 قوانین گروه:\n\n{text}")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    s = db.chat_stats(chat_id)
    await update.effective_message.reply_text(
        "📊 آمار گروه:\n"
        f"👥 تعداد اعضای ثبت‌شده: {s['member_count']}\n"
        f"⭐️ مجموع امتیازها: {s['total_points']}\n"
        f"⚠️ مجموع اخطارها: {s['total_warns']}"
    )


async def mylevel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user = db.get_user(chat_id, user_id)
    if not user:
        await update.effective_message.reply_text("هنوز اطلاعاتی از شما ثبت نشده. یک پیام بفرستید تا ثبت شوید.")
        return
    rank = db.user_rank(chat_id, user_id)
    await update.effective_message.reply_text(
        f"⭐️ امتیاز شما: {user['points']}\n"
        f"🏅 رتبه شما: {rank}\n"
        f"⚠️ اخطارها: {user['warns']}"
    )


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rows = db.top_users(chat_id, limit=10)
    if not rows:
        await update.effective_message.reply_text("هنوز آماری ثبت نشده است.")
        return
    lines = ["🏆 برترین‌های گروه:"]
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows, start=1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        name = r["first_name"] or r["username"] or str(r["user_id"])
        lines.append(f"{medal} {name} — {r['points']} امتیاز")
    await update.effective_message.reply_text("\n".join(lines))


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)