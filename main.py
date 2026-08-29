"""
Telegram Guard Bot - Entry point
"""
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

import database as db
from config import BOT_TOKEN, PROXY_URL
from handlers import admin, antispam, general, welcome, dashboard, ticket, force_subscribe, reactions, reports, backup, security, polls, whisper, voicetotext

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def build_application() -> Application:
    builder = Application.builder().token(BOT_TOKEN)
    
    if PROXY_URL and PROXY_URL.strip():
        logger.info(f"Using proxy: {PROXY_URL}")
        builder = builder.proxy(PROXY_URL).get_updates_proxy(PROXY_URL)
    else:
        logger.info("No proxy configured, using direct connection.")
    
    app = builder.build()
    
    # ===== گیت اشتراک گروه (باید همیشه اولین هندلر باشه، قبل از هر دستور دیگه) =====
    # اگه گروه اشتراک فعال نداره، هیچ خدمتی (به‌جز /start و /groupid) اجرا نمی‌شه.
    app.add_handler(
        MessageHandler(filters.ALL & filters.ChatType.GROUPS, antispam.enforce_subscription_gate),
        group=-10,
    )
    
    # ===== ثبت هندلرها (با اسلش) =====
    
    # دستورات عمومی
    app.add_handler(CommandHandler("start", general.start, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("menu", general.menu))
    app.add_handler(CommandHandler("help", general.help_cmd))
    app.add_handler(CommandHandler("rules", general.rules))
    app.add_handler(CommandHandler("stats", general.stats))
    app.add_handler(CommandHandler("mylevel", general.mylevel))
    app.add_handler(CommandHandler("top", general.top))
    
    # دستورات ادمین
    app.add_handler(CommandHandler("warn", admin.warn))
    app.add_handler(CommandHandler("unwarn", admin.unwarn))
    app.add_handler(CommandHandler("mute", admin.mute))
    app.add_handler(CommandHandler("unmute", admin.unmute))
    app.add_handler(CommandHandler("kick", admin.kick))
    app.add_handler(CommandHandler("ban", admin.ban))
    app.add_handler(CommandHandler("unban", admin.unban))
    app.add_handler(CommandHandler("lock", admin.lock))
    app.add_handler(CommandHandler("unlock", admin.unlock))
    app.add_handler(CommandHandler("aimod", admin.aimod))
    app.add_handler(CommandHandler("trustbot", security.trustbot))
    app.add_handler(CommandHandler("untrustbot", security.untrustbot))
    app.add_handler(CommandHandler("trustedbots", security.trustedbots))
    app.add_handler(CommandHandler("pin", admin.pin))
    app.add_handler(CommandHandler("unpin", admin.unpin))
    app.add_handler(CommandHandler("setwelcome", admin.setwelcome))
    app.add_handler(CommandHandler("setgoodbye", admin.setgoodbye))
    app.add_handler(CommandHandler("setrules", admin.setrules))
    app.add_handler(CommandHandler("addbadword", admin.addbadword))
    app.add_handler(CommandHandler("removebadword", admin.removebadword))
    app.add_handler(CommandHandler("listbadwords", admin.listbadwords))
    app.add_handler(CommandHandler("importbadwords", admin.import_badwords))
    app.add_handler(CommandHandler("quicksetup", admin.quicksetup))
    
    # مدیریت ادمین‌ها
    app.add_handler(CommandHandler("addadmin", admin.addadmin))
    app.add_handler(CommandHandler("removeadmin", admin.removeadmin))
    app.add_handler(CommandHandler("setlevel", admin.setlevel))
    app.add_handler(CommandHandler("mypermissions", admin.mypermissions))
    app.add_handler(CommandHandler("listadmins", admin.listadmins))
    app.add_handler(CommandHandler("tagall", admin.tagall))
    
    # ===== تیکت =====
    ticket.register_ticket_handlers(app)
    
    # ===== عضویت اجباری =====
    force_subscribe.register_force_handlers(app)
    
    # ===== واکنش‌ها =====
    reactions.register_reaction_handlers(app)
    
    # ===== گزارش‌ها =====
    reports.register_report_handlers(app)
    
    # ===== بک‌آپ =====
    backup.register_backup_handlers(app)
    
    # ===== امنیت =====
    security.register_security_handlers(app)
    
    # ===== نظرسنجی =====
    polls.register_poll_handlers(app)
    
    # ===== سیستم نجوا (Whisper) =====
    whisper.register_whisper_handlers(app)
    
    # ===== تبدیل صدا به متن =====
    voicetotext.register_voicetotext_handlers(app)
    
    # پنل مدیریت
    app.add_handler(CommandHandler("panel", dashboard.dashboard))
    app.add_handler(CommandHandler("dashboard", dashboard.dashboard))
    app.add_handler(CallbackQueryHandler(dashboard.dashboard_callback, pattern="^dash_"))
    app.add_handler(CallbackQueryHandler(dashboard.dashboard_callback, pattern="^users_"))
    app.add_handler(CallbackQueryHandler(dashboard.dashboard_callback, pattern="^badword_"))
    app.add_handler(CallbackQueryHandler(dashboard.dashboard_callback, pattern="^admin_"))
    app.add_handler(CallbackQueryHandler(dashboard.dashboard_callback, pattern="^set_"))
    
    # ===== سیستم فروش اشتراک (فقط چت خصوصی، جدا از قابلیت‌های گروه) =====
    # ===== سیستم فروش قدیمی حذف شد - فروش/تمدید حالا توی ربات مرکزی HEXIRON SALES انجام می‌شه =====
    app.add_handler(CommandHandler("start", general.private_start_redirect, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("shop", general.private_start_redirect, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("groupid", general.groupid_cmd, filters=filters.ChatType.GROUPS))
    
    # رویدادهای عضویت
    # نکته: check_join_security و check_bot_entry (توی security.py) هم روی همین
    # فیلتر (NEW_CHAT_MEMBERS) ثبت می‌شن؛ group=12 عمداً بعد از اوناست (group=10, 11)
    # تا اول امنیت/ضدفلود چک بشه، بعد خوش‌آمدگویی نشون داده بشه.
    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome.greet_new_members), group=12
    )
    app.add_handler(
        MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, welcome.farewell_member)
    )
    
    # ===== فیلترهای پیام =====
    text_filter = filters.TEXT & ~filters.COMMAND
    # فیلتر فحش باید کپشن عکس/ویدیو رو هم بگیره، نه فقط پیام متنی خالص
    badword_filter_scope = (filters.TEXT & ~filters.COMMAND) | (filters.CAPTION & ~filters.COMMAND)
    
    # فیلتر واکنش‌ها (group 0) - فقط توی گروه، نه پیوی (وگرنه هر پیام پیویِ
    # بی‌صاحب رو می‌بلعه و اجازه نمی‌ده هندلرهای دیگه‌ی همون گروه اجرا بشن)
    app.add_handler(MessageHandler(text_filter & filters.ChatType.GROUPS, reactions.check_reactions), group=0)
    
    # فیلتر عضویت اجباری (group 1)
    app.add_handler(MessageHandler(text_filter, force_subscribe.check_membership), group=1)
    
    # فیلتر قفل گروه (group 2)
    app.add_handler(MessageHandler(text_filter, antispam.enforce_group_lock), group=2)
    
    # ===== فیلتر کلمات ممنوعه (group 3) - این باید کار کند! =====
    app.add_handler(MessageHandler(badword_filter_scope, antispam.filter_badwords), group=3)
    
    # فیلتر لینک (group 4)
    app.add_handler(MessageHandler(text_filter, antispam.filter_links), group=4)
    
    # فیلتر ضد فلود (group 5)
    app.add_handler(MessageHandler(text_filter, antispam.flood_control), group=5)
    
    # ردیابی امتیاز (group 6)
    app.add_handler(MessageHandler(text_filter, welcome.track_message_points), group=6)
    
    # ===== پردازش دستورات بدون اسلش =====
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, handle_text_commands), group=-1)
    
    # ===== ثبت کامل خطاها توی ترمینال (به‌جای بی‌صدا خوردنشون) =====
    app.add_error_handler(on_error)
    
    if app.job_queue is None:
        logger.warning(
            "⚠️ JobQueue فعال نیست (پکیج APScheduler نصب نشده). "
            "conversation_timeout ها (مثلاً تایم‌اوت پنل ادمین) کار نمی‌کنن و کاربر ممکنه "
            "توی یه مکالمه گیر بمونه. برای رفع: 'pip install \"python-telegram-bot[job-queue]\"' "
            "رو توی venv اجرا کن."
        )
    
    return app


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """هندلر سراسری خطا - جای اینکه خطاها بی‌صدا قورت داده بشن، کامل با traceback لاگ می‌شن."""
    logger.error("خطای پردازش‌نشده در هندلر:", exc_info=context.error)


async def handle_text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش دستورات بدون اسلش و دکمه‌های کیبورد"""
    text = update.effective_message.text.strip()
    
    # اگه پیام با / شروع شد، نادیده بگیر
    if text.startswith('/'):
        return
    
    text_lower = text.lower()
    
    # ===== دستورات عمومی =====
    if text_lower in ["start", "شروع"]:
        await general.start(update, context)
        return
    elif text_lower in ["help", "راهنما"]:
        await general.help_cmd(update, context)
        return
    elif text_lower in ["rules", "قوانین"]:
        await general.rules(update, context)
        return
    elif text_lower in ["stats", "آمار"]:
        await general.stats(update, context)
        return
    elif text_lower in ["mylevel", "امتیاز"]:
        await general.mylevel(update, context)
        return
    elif text_lower in ["top", "برترین"]:
        await general.top(update, context)
        return
    elif text_lower in ["menu", "منو"]:
        await general.menu(update, context)
        return
    elif text_lower in ["panel", "پنل"]:
        await dashboard.dashboard(update, context)
        return
    
    # ===== دستورات ادمین (مدیریت کاربران) =====
    elif text_lower in ["warn", "اخطار"]:
        await admin.warn(update, context)
        return
    elif text_lower in ["unwarn", "حذف اخطار"]:
        await admin.unwarn(update, context)
        return
    elif text_lower in ["mute", "بی صدا"]:
        await admin.mute(update, context)
        return
    elif text_lower in ["unmute", "باز کردن صدا"]:
        await admin.unmute(update, context)
        return
    elif text_lower in ["kick", "اخراج"]:
        await admin.kick(update, context)
        return
    elif text_lower in ["ban", "بن"]:
        await admin.ban(update, context)
        return
    elif text_lower in ["unban", "آنبن"]:
        await admin.unban(update, context)
        return
    
    # ===== دستورات ادمین (مدیریت گروه) =====
    elif text_lower in ["lock", "قفل"]:
        await admin.lock(update, context)
        return
    elif text_lower in ["unlock", "باز کردن"]:
        await admin.unlock(update, context)
        return
    elif text_lower in ["pin", "پین"]:
        await admin.pin(update, context)
        return
    elif text_lower in ["unpin", "برداشتن پین"]:
        await admin.unpin(update, context)
        return
    elif text_lower in ["setwelcome", "خوش آمدگویی"]:
        await admin.setwelcome(update, context)
        return
    elif text_lower in ["setgoodbye", "خداحافظی"]:
        await admin.setgoodbye(update, context)
        return
    elif text_lower in ["setrules", "قوانین جدید"]:
        await admin.setrules(update, context)
        return
    
    # ===== مدیریت کلمات ممنوعه =====
    elif text_lower in ["addbadword", "افزودن کلمه"]:
        await admin.addbadword(update, context)
        return
    elif text_lower in ["removebadword", "حذف کلمه"]:
        await admin.removebadword(update, context)
        return
    elif text_lower in ["listbadwords", "لیست کلمات"]:
        await admin.listbadwords(update, context)
        return
    elif text_lower in ["importbadwords", "ایمپورت"]:
        await admin.import_badwords(update, context)
        return
    elif text_lower in ["quicksetup", "نصب سریع", "راه اندازی سریع", "راه‌اندازی سریع"]:
        await admin.quicksetup(update, context)
        return
    
    # ===== مدیریت ادمین‌ها =====
    elif text_lower in ["addadmin", "افزودن ادمین"]:
        await admin.addadmin(update, context)
        return
    elif text_lower in ["removeadmin", "حذف ادمین"]:
        await admin.removeadmin(update, context)
        return
    elif text_lower in ["setlevel", "تنظیم سطح"]:
        await admin.setlevel(update, context)
        return
    elif text_lower in ["mypermissions", "دسترسی من"]:
        await admin.mypermissions(update, context)
        return
    elif text_lower in ["tagall", "تگ", "تگ همه", "تگ کردن همه"]:
        await admin.tagall(update, context)
        return
    elif text_lower in ["aimod", "هوش مصنوعی", "تشخیص هوشمند"]:
        await admin.aimod(update, context)
        return
    elif text_lower in ["trustbot", "اعتماد به بات"]:
        await security.trustbot(update, context)
        return
    elif text_lower in ["untrustbot", "حذف اعتماد بات"]:
        await security.untrustbot(update, context)
        return
    elif text_lower in ["trustedbots", "بات های مورد اعتماد", "بات‌های مورد اعتماد"]:
        await security.trustedbots(update, context)
        return
    
    # ===== تیکت =====
    elif text_lower in ["ticket", "تیکت"]:
        await ticket.ticket(update, context)
        return
    elif text_lower in ["mytickets", "تیکت های من"]:
        await ticket.mytickets(update, context)
        return
    elif text_lower in ["ticketinfo", "جزئیات تیکت"]:
        await ticket.ticketinfo(update, context)
        return
    elif text_lower in ["reply", "پاسخ"]:
        await ticket.reply(update, context)
        return
    elif text_lower in ["close", "بستن"]:
        await ticket.close(update, context)
        return
    elif text_lower in ["tickets", "مدیریت تیکت"]:
        await ticket.tickets(update, context)
        return
    
    # ===== عضویت اجباری =====
    elif text_lower in ["setforce", "کانال اجباری"]:
        await force_subscribe.setforce(update, context)
        return
    elif text_lower in ["removeforce", "حذف کانال اجباری"]:
        await force_subscribe.removeforce(update, context)
        return
    elif text_lower in ["forcelinks", "لینک کانال ها", "لینک کانال‌ها"]:
        await force_subscribe.forcelinks(update, context)
        return
    elif text_lower in ["forcestatus", "وضعیت عضویت"]:
        await force_subscribe.force_status(update, context)
        return
    
    
    # ===== واکنش‌ها =====
    elif text_lower in ["addreaction", "افزودن واکنش"]:
        await reactions.addreaction(update, context)
        return
    elif text_lower in ["removereaction", "حذف واکنش"]:
        await reactions.removereaction(update, context)
        return
    elif text_lower in ["listreactions", "لیست واکنش"]:
        await reactions.listreactions(update, context)
        return
    
    # ===== گزارشات =====
    elif text_lower in ["dailyreport", "گزارش روزانه"]:
        await reports.dailyreport(update, context)
        return
    elif text_lower in ["weeklyreport", "گزارش هفتگی"]:
        await reports.weeklyreport(update, context)
        return
    elif text_lower in ["monthlyreport", "گزارش ماهانه"]:
        await reports.monthlyreport(update, context)
        return
    elif text_lower in ["userreport", "گزارش کاربر"]:
        await reports.userreport(update, context)
        return
    
    # ===== بک‌آپ =====
    elif text_lower in ["backup", "بکاپ"]:
        await backup.backup(update, context)
        return
    elif text_lower in ["restore", "بازیابی"]:
        await backup.restore(update, context)
        return
    elif text_lower in ["backups", "لیست بکاپ"]:
        await backup.backups_list(update, context)
        return
    
    # ===== امنیت =====
    elif text_lower in ["setjoinlimit", "محدودیت ورود"]:
        await security.setjoinlimit(update, context)
        return
    elif text_lower in ["security", "امنیت"]:
        await security.security(update, context)
        return
    elif text_lower in ["securityreport", "گزارش امنیتی"]:
        await security.securityreport(update, context)
        return
    
    # ===== نظرسنجی =====
    elif text_lower in ["poll", "نظرسنجی"]:
        await polls.poll(update, context)
        return
    elif text_lower in ["pollresults", "نتایج نظرسنجی"]:
        await polls.poll_results(update, context)
        return
    elif text_lower in ["closepoll", "بستن نظرسنجی"]:
        await polls.close_poll(update, context)
        return
    
    # ===== سیستم نجوا (Whisper) =====
    elif text_lower in ["whisper", "نجوا"]:
        await whisper.whisper(update, context)
        return
    elif text_lower in ["secret", "رمزی"]:
        await whisper.secret(update, context)
        return
    elif text_lower in ["mywhispers", "نجواهای من"]:
        await whisper.mywhispers(update, context)
        return
    
    # ===== تبدیل صدا به متن =====
    elif text_lower in ["voicetotext", "صدا به متن"]:
        await voicetotext.voicetotext(update, context)
        return
    elif text_lower in ["texttovoice", "متن به صدا"]:
        await voicetotext.texttovoice(update, context)
        return
    
    # ===== دکمه‌های کیبورد =====
    elif text == "📊 آمار گروه":
        await general.stats(update, context)
    elif text == "🏅 برترین‌ها":
        await general.top(update, context)
    elif text == "⭐️ امتیاز من":
        await general.mylevel(update, context)
    elif text == "📜 قوانین":
        await general.rules(update, context)
    elif text == "📋 راهنما":
        await general.help_cmd(update, context)
    elif text == "🛡️ پنل مدیریت":
        await dashboard.dashboard(update, context)
    elif text == "⚠️ اخطار":
        await admin.warn(update, context)
    elif text == "🔇 بی‌صدا":
        await admin.mute(update, context)
    elif text == "👢 اخراج":
        await admin.kick(update, context)
    elif text == "⛔️ بن":
        await admin.ban(update, context)
    elif text == "🔓 آنبن":
        await admin.unban(update, context)
    elif text == "🔒 قفل":
        await admin.lock(update, context)
    elif text == "🔓 باز":
        await admin.unlock(update, context)
    elif text == "🛡 امنیت":
        await security.security(update, context)
    elif text == "👑 لیست ادمین‌ها":
        await admin.listadmins(update, context)
    elif text == "📌 پین":
        await admin.pin(update, context)
    elif text == "📌 برداشتن پین":
        await admin.unpin(update, context)
    elif text == "📝 تنظیم خوش‌آمدگویی":
        await admin.setwelcome(update, context)
    elif text == "📝 تنظیم خداحافظی":
        await admin.setgoodbye(update, context)
    elif text == "📜 تنظیم قوانین":
        await admin.setrules(update, context)
    elif text == "🚫 کلمات ممنوعه":
        await admin.listbadwords(update, context)
    elif text == "📊 گزارش روزانه":
        await reports.dailyreport(update, context)
    elif text == "📊 گزارش هفتگی":
        await reports.weeklyreport(update, context)
    elif text == "🔄 بک‌آپ":
        await backup.backup(update, context)
    elif text == "🎫 تیکت":
        await ticket.ticket(update, context)
    elif text == "🔙 منوی اصلی":
        await general.start(update, context)
    elif text == "❌ بستن منو":
        from telegram import ReplyKeyboardRemove
        await update.effective_message.reply_text("❌ منو بسته شد.", reply_markup=ReplyKeyboardRemove())


def main():
    db.init_db()
    app = build_application()
    logger.info("🤖 Bot starting (polling mode)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()