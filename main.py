"""
Telegram Guard Bot - Entry point
"""
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, ApplicationHandlerStop

import database as db
from utils.ffmpeg_setup import ensure_ffmpeg
from config import BOT_TOKEN, PROXY_URL
from handlers import admin, antispam, general, welcome, dashboard, ticket, force_subscribe, reactions, reports, backup, security, polls, whisper, voicetotext, invite_links, ai_chat

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ensure_ffmpeg()
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
    app.add_handler(CommandHandler("aiwelcome", admin.aiwelcome))
    app.add_handler(CommandHandler("aitest", admin.aitest))
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

    # ===== لینک دعوت با تگ =====
    invite_links.register_invite_link_handlers(app)
    
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
    app.add_handler(CommandHandler("grouplink", general.grouplink_cmd, filters=filters.ChatType.GROUPS))
    
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
    # ===== هوش مصنوعی: /aireport + چت آزاد در پیوی (باید همین‌جا، آخر همه‌ی
    # هندلرهای group=0 پیوی ثبت بشه، چون طراحیش fallback ـه: فقط وقتی هیچ
    # مکالمه/دستور دیگه‌ای (شاپ، پنل کاربر/ادمین، تیکت) پیام رو نگرفت، اجرا می‌شه) =====
    ai_chat.register_ai_handlers(app)

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
        raise ApplicationHandlerStop
    elif text_lower in ["help", "راهنما"]:
        await general.help_cmd(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["rules", "قوانین"]:
        await general.rules(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["stats", "آمار"]:
        await general.stats(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["mylevel", "امتیاز"]:
        await general.mylevel(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["top", "برترین"]:
        await general.top(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["menu", "منو"]:
        await general.menu(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["panel", "پنل"]:
        await dashboard.dashboard(update, context)
        raise ApplicationHandlerStop
    
    # ===== دستورات ادمین (مدیریت کاربران) =====
    elif text_lower in ["warn", "اخطار"]:
        await admin.warn(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["unwarn", "حذف اخطار"]:
        await admin.unwarn(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["mute", "بی صدا"]:
        await admin.mute(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["unmute", "باز کردن صدا"]:
        await admin.unmute(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["kick", "اخراج"]:
        await admin.kick(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["ban", "بن"]:
        await admin.ban(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["unban", "آنبن"]:
        await admin.unban(update, context)
        raise ApplicationHandlerStop
    
    # ===== دستورات ادمین (مدیریت گروه) =====
    elif text_lower in ["lock", "قفل"]:
        await admin.lock(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["unlock", "باز کردن"]:
        await admin.unlock(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["pin", "پین"]:
        await admin.pin(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["unpin", "برداشتن پین"]:
        await admin.unpin(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["setwelcome", "خوش آمدگویی"]:
        await admin.setwelcome(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["setgoodbye", "خداحافظی"]:
        await admin.setgoodbye(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["setrules", "قوانین جدید"]:
        await admin.setrules(update, context)
        raise ApplicationHandlerStop
    
    # ===== مدیریت کلمات ممنوعه =====
    elif text_lower in ["addbadword", "افزودن کلمه"]:
        await admin.addbadword(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["removebadword", "حذف کلمه"]:
        await admin.removebadword(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["listbadwords", "لیست کلمات"]:
        await admin.listbadwords(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["importbadwords", "ایمپورت"]:
        await admin.import_badwords(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["quicksetup", "نصب سریع", "راه اندازی سریع", "راه‌اندازی سریع"]:
        await admin.quicksetup(update, context)
        raise ApplicationHandlerStop
    
    # ===== مدیریت ادمین‌ها =====
    elif text_lower in ["addadmin", "افزودن ادمین"]:
        await admin.addadmin(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["removeadmin", "حذف ادمین"]:
        await admin.removeadmin(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["setlevel", "تنظیم سطح"]:
        await admin.setlevel(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["mypermissions", "دسترسی من"]:
        await admin.mypermissions(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["tagall", "تگ", "تگ همه", "تگ کردن همه"]:
        await admin.tagall(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["aimod", "هوش مصنوعی", "تشخیص هوشمند"]:
        await admin.aimod(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["aiwelcome", "خوش آمدگویی هوشمند", "خوشامدگویی هوشمند"]:
        await admin.aiwelcome(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["aitest", "تست هوش مصنوعی", "تست اتصال هوش مصنوعی"]:
        await admin.aitest(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["trustbot", "اعتماد به بات"]:
        await security.trustbot(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["untrustbot", "حذف اعتماد بات"]:
        await security.untrustbot(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["trustedbots", "بات های مورد اعتماد", "بات‌های مورد اعتماد"]:
        await security.trustedbots(update, context)
        raise ApplicationHandlerStop
    
    # ===== تیکت =====
    elif text_lower in ["ticket", "تیکت"]:
        await ticket.ticket(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["mytickets", "تیکت های من"]:
        await ticket.mytickets(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["ticketinfo", "جزئیات تیکت"]:
        await ticket.ticketinfo(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["reply", "پاسخ"]:
        await ticket.reply(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["close", "بستن"]:
        await ticket.close(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["tickets", "مدیریت تیکت"]:
        await ticket.tickets(update, context)
        raise ApplicationHandlerStop
    
    # ===== عضویت اجباری =====
    elif text_lower in ["setforce", "کانال اجباری"]:
        await force_subscribe.setforce(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["removeforce", "حذف کانال اجباری"]:
        await force_subscribe.removeforce(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["forcelinks", "لینک کانال ها", "لینک کانال‌ها"]:
        await force_subscribe.forcelinks(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["forcestatus", "وضعیت عضویت"]:
        await force_subscribe.force_status(update, context)
        raise ApplicationHandlerStop
    
    
    # ===== واکنش‌ها =====
    elif text_lower in ["addreaction", "افزودن واکنش"]:
        await reactions.addreaction(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["removereaction", "حذف واکنش"]:
        await reactions.removereaction(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["listreactions", "لیست واکنش"]:
        await reactions.listreactions(update, context)
        raise ApplicationHandlerStop
    
    # ===== گزارشات =====
    elif text_lower in ["dailyreport", "گزارش روزانه"]:
        await reports.dailyreport(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["weeklyreport", "گزارش هفتگی"]:
        await reports.weeklyreport(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["monthlyreport", "گزارش ماهانه"]:
        await reports.monthlyreport(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["userreport", "گزارش کاربر"]:
        await reports.userreport(update, context)
        raise ApplicationHandlerStop
    
    # ===== بک‌آپ =====
    elif text_lower in ["backup", "بکاپ"]:
        await backup.backup(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["restore", "بازیابی"]:
        await backup.restore(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["backups", "لیست بکاپ"]:
        await backup.backups_list(update, context)
        raise ApplicationHandlerStop
    
    # ===== امنیت =====
    elif text_lower in ["setjoinlimit", "محدودیت ورود"]:
        await security.setjoinlimit(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["security", "امنیت"]:
        await security.security(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["securityreport", "گزارش امنیتی"]:
        await security.securityreport(update, context)
        raise ApplicationHandlerStop
    
    # ===== نظرسنجی =====
    elif text_lower in ["poll", "نظرسنجی"]:
        await polls.poll(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["pollresults", "نتایج نظرسنجی"]:
        await polls.poll_results(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["closepoll", "بستن نظرسنجی"]:
        await polls.close_poll(update, context)
        raise ApplicationHandlerStop
    
    # ===== سیستم نجوا (Whisper) =====
    elif text_lower in ["whisper", "نجوا"]:
        await whisper.whisper(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["secret", "رمزی"]:
        await whisper.secret(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["mywhispers", "نجواهای من"]:
        await whisper.mywhispers(update, context)
        raise ApplicationHandlerStop
    
    # ===== تبدیل صدا به متن =====
    elif text_lower in ["voicetotext", "صدا به متن"]:
        await voicetotext.voicetotext(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["texttovoice", "متن به صدا"]:
        await voicetotext.texttovoice(update, context)
        raise ApplicationHandlerStop

    # ===== لینک دعوت با تگ =====
    elif text_lower in ["newlink", "لینک جدید", "ساخت لینک"]:
        await invite_links.newlink(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["links", "لینک ها", "لینک‌ها", "لیست لینک"]:
        await invite_links.links_list(update, context)
        raise ApplicationHandlerStop
    elif text_lower in ["revokelink", "حذف لینک", "غیرفعال کردن لینک"]:
        await invite_links.revoke_link(update, context)
        raise ApplicationHandlerStop

    # ===== دکمه‌های کیبورد =====
    elif text == "📊 آمار گروه":
        await general.stats(update, context)
        raise ApplicationHandlerStop
    elif text == "🏅 برترین‌ها":
        await general.top(update, context)
        raise ApplicationHandlerStop
    elif text == "⭐️ امتیاز من":
        await general.mylevel(update, context)
        raise ApplicationHandlerStop
    elif text == "📜 قوانین":
        await general.rules(update, context)
        raise ApplicationHandlerStop
    elif text == "📋 راهنما":
        await general.help_cmd(update, context)
        raise ApplicationHandlerStop
    elif text == "🛡️ پنل مدیریت":
        await dashboard.dashboard(update, context)
        raise ApplicationHandlerStop
    elif text == "⚠️ اخطار":
        await admin.warn(update, context)
        raise ApplicationHandlerStop
    elif text == "🔇 بی‌صدا":
        await admin.mute(update, context)
        raise ApplicationHandlerStop
    elif text == "👢 اخراج":
        await admin.kick(update, context)
        raise ApplicationHandlerStop
    elif text == "⛔️ بن":
        await admin.ban(update, context)
        raise ApplicationHandlerStop
    elif text == "🔓 آنبن":
        await admin.unban(update, context)
        raise ApplicationHandlerStop
    elif text == "🔒 قفل":
        await admin.lock(update, context)
        raise ApplicationHandlerStop
    elif text == "🔓 باز":
        await admin.unlock(update, context)
        raise ApplicationHandlerStop
    elif text == "🛡 امنیت":
        await security.security(update, context)
        raise ApplicationHandlerStop
    elif text == "👑 لیست ادمین‌ها":
        await admin.listadmins(update, context)
        raise ApplicationHandlerStop
    elif text == "📌 پین":
        await admin.pin(update, context)
        raise ApplicationHandlerStop
    elif text == "📌 برداشتن پین":
        await admin.unpin(update, context)
        raise ApplicationHandlerStop
    elif text == "📝 تنظیم خوش‌آمدگویی":
        await admin.setwelcome(update, context)
        raise ApplicationHandlerStop
    elif text == "📝 تنظیم خداحافظی":
        await admin.setgoodbye(update, context)
        raise ApplicationHandlerStop
    elif text == "📜 تنظیم قوانین":
        await admin.setrules(update, context)
        raise ApplicationHandlerStop
    elif text == "🚫 کلمات ممنوعه":
        await admin.listbadwords(update, context)
        raise ApplicationHandlerStop
    elif text == "📊 گزارش روزانه":
        await reports.dailyreport(update, context)
        raise ApplicationHandlerStop
    elif text == "📊 گزارش هفتگی":
        await reports.weeklyreport(update, context)
        raise ApplicationHandlerStop
    elif text == "🔄 بک‌آپ":
        await backup.backup(update, context)
        raise ApplicationHandlerStop
    elif text == "🎫 تیکت":
        await ticket.ticket(update, context)
        raise ApplicationHandlerStop
    elif text == "🔙 منوی اصلی":
        await general.start(update, context)
        raise ApplicationHandlerStop
    elif text == "❌ بستن منو":
        from telegram import ReplyKeyboardRemove
        await update.effective_message.reply_text("❌ منو بسته شد.", reply_markup=ReplyKeyboardRemove())
        raise ApplicationHandlerStop


def main():
    db.init_db()
    app = build_application()
    logger.info("🤖 Bot starting (polling mode)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()