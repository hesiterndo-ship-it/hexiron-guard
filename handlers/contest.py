"""
سیستم مسابقات و چالش‌ها
"""
import logging
import time
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import database as db
from utils.permissions import require_admin, is_admin
from utils.helpers import escape_markdown

logger = logging.getLogger(__name__)

CONTEST_TYPES = {
    "messages": "بیشترین پیام",
    "points": "بیشترین امتیاز",
    "nowarns": "کمترین اخطار"
}

async def newcontest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ایجاد مسابقه جدید"""
    if not await require_admin(update, context):
        return
    
    chat_id = update.effective_chat.id
    
    if not db.is_feature_enabled(chat_id, "contest_system"):
        await update.effective_message.reply_text("⛔️ سیستم مسابقات برای این گروه غیرفعال شده.")
        return
    
    # بررسی آرگومان‌ها
    if len(context.args) < 4:
        await update.effective_message.reply_text(
            "🏆 *ایجاد مسابقه جدید*\n\n"
            "استفاده: `/newcontest نام|نوع|مدت(دقیقه)|جایزه`\n\n"
            "انواع مسابقه:\n"
            "• `messages` - بیشترین پیام\n"
            "• `points` - بیشترین امتیاز\n"
            "• `nowarns` - کمترین اخطار\n\n"
            "مثال: `/newcontest مسابقه هفتگی|points|60|100`\n"
            "(مدت ۶۰ دقیقه، جایزه ۱۰۰ امتیاز)",
            parse_mode="Markdown"
        )
        return
    
    try:
        contest_data = " ".join(context.args).split("|")
        name = contest_data[0].strip()
        contest_type = contest_data[1].strip().lower()
        duration = int(contest_data[2].strip()) * 60  # تبدیل به ثانیه
        prize = int(contest_data[3].strip()) if len(contest_data) > 3 else 0
    except (ValueError, IndexError):
        await update.effective_message.reply_text(
            "❌ فرمت اشتباه!\n"
            "استفاده: `/newcontest نام|نوع|مدت(دقیقه)|جایزه`"
        )
        return
    
    # بررسی نوع مسابقه
    if contest_type not in CONTEST_TYPES:
        await update.effective_message.reply_text(
            f"❌ نوع مسابقه نامعتبر!\n"
            f"انواع مجاز: {', '.join(CONTEST_TYPES.keys())}"
        )
        return
    
    # ایجاد مسابقه
    contest_id = db.create_contest(chat_id, name, contest_type, duration, prize)
    
    # ارسال پیام به گروه
    await update.effective_message.reply_text(
        f"🏆 *مسابقه جدید شروع شد!*\n\n"
        f"📌 نام: {escape_markdown(name)}\n"
        f"📊 نوع: {CONTEST_TYPES[contest_type]}\n"
        f"⏱ مدت: {duration//60} دقیقه\n"
        f"🎁 جایزه: {prize} امتیاز\n\n"
        f"همه کاربران می‌توانند شرکت کنند!\n"
        f"برای مشاهده وضعیت: /conteststatus",
        parse_mode="Markdown"
    )


async def conteststatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش وضعیت مسابقه فعال"""
    chat_id = update.effective_chat.id
    
    contest = db.get_active_contest(chat_id)
    
    if not contest:
        await update.effective_message.reply_text("📭 در حال حاضر هیچ مسابقه‌ای فعال نیست.")
        return
    
    # محاسبه زمان باقی‌مانده
    now = int(time.time())
    remaining = contest['end_at'] - now
    if remaining < 0:
        remaining = 0
    minutes = remaining // 60
    seconds = remaining % 60
    
    # دریافت برندگان فعلی
    winners = db.get_contest_winners(contest['id'], 5)
    
    text = f"🏆 *وضعیت مسابقه*\n\n"
    text += f"📌 نام: {escape_markdown(contest['name'])}\n"
    text += f"📊 نوع: {CONTEST_TYPES.get(contest['type'], contest['type'])}\n"
    text += f"⏱ زمان باقی‌مانده: {minutes} دقیقه {seconds} ثانیه\n"
    text += f"🎁 جایزه: {contest['prize']} امتیاز\n"
    
    if winners:
        text += f"\n🏅 *۵ نفر برتر فعلی:*\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, w in enumerate(winners[:5]):
            name = escape_markdown(w.get('first_name', f"کاربر {w['user_id']}"))[:15]
            text += f"{medals[i]} {name} — {w['score']} امتیاز\n"
    else:
        text += "\n📭 هنوز کسی شرکت نکرده است!"
    
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def contestwinners(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش برندگان مسابقه"""
    chat_id = update.effective_chat.id
    
    # دریافت مسابقه قبلی (آخرین مسابقه)
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM contests WHERE chat_id=? ORDER BY created_at DESC LIMIT 1",
            (chat_id,)
        ).fetchone()
        contest = dict(row) if row else None
    
    if not contest:
        await update.effective_message.reply_text("📭 هیچ مسابقه‌ای یافت نشد.")
        return
    
    winners = db.get_contest_winners(contest['id'], 10)
    
    if not winners:
        await update.effective_message.reply_text(
            f"📭 مسابقه «{contest['name']}» هیچ شرکت‌کننده‌ای نداشت."
        )
        return
    
    text = f"🏆 *برندگان مسابقه: {escape_markdown(contest['name'])}*\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, w in enumerate(winners[:10]):
        name = escape_markdown(w.get('first_name', f"کاربر {w['user_id']}"))[:20]
        text += f"{medals[i]} {name} — {w['score']} امتیاز\n"
    
    if contest['prize'] > 0 and winners:
        text += f"\n🎁 جایزه: {contest['prize']} امتیاز به برنده تعلق گرفت!"
    
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def declarewinner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اعلام برنده مسابقه"""
    if not await require_admin(update, context):
        return
    
    chat_id = update.effective_chat.id
    
    contest = db.get_active_contest(chat_id)
    
    if not contest:
        await update.effective_message.reply_text("📭 هیچ مسابقه‌ای فعال نیست.")
        return
    
    # دریافت برندگان
    winners = db.get_contest_winners(contest['id'], 1)
    
    if not winners:
        await update.effective_message.reply_text("📭 هیچ شرکت‌کننده‌ای وجود ندارد!")
        return
    
    winner = winners[0]
    winner_id = winner['user_id']
    winner_name = winner.get('first_name', f"کاربر {winner_id}")
    score = winner['score']
    
    # اعلام برنده
    await update.effective_message.reply_text(
        f"🏆 *برنده مسابقه اعلام شد!*\n\n"
        f"📌 مسابقه: {contest['name']}\n"
        f"👑 برنده: {winner_name}\n"
        f"⭐️ امتیاز: {score}\n"
        f"🎁 جایزه: {contest['prize']} امتیاز\n\n"
        f"🎉 به {winner_name} تبریک می‌گوییم!"
    )
    
    # اضافه کردن جایزه به کاربر
    if contest['prize'] > 0:
        db.add_points(chat_id, winner_id, contest['prize'])
    
    # پایان مسابقه
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE contests SET status='finished', winner_id=? WHERE id=?",
            (winner_id, contest['id'])
        )


async def joincontest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شرکت در مسابقه"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    contest = db.get_active_contest(chat_id)
    
    if not contest:
        await update.effective_message.reply_text("📭 در حال حاضر هیچ مسابقه‌ای فعال نیست.")
        return
    
    # افزودن کاربر به مسابقه
    db.add_contest_participant(contest['id'], chat_id, user_id)
    
    await update.effective_message.reply_text(
        f"✅ شما در مسابقه «{contest['name']}» ثبت نام شدید!\n"
        f"برای مشاهده وضعیت: /conteststatus"
    )


def register_contest_handlers(app):
    """ثبت هندلرهای مسابقات"""
    app.add_handler(CommandHandler("newcontest", newcontest))
    app.add_handler(CommandHandler("conteststatus", conteststatus))
    app.add_handler(CommandHandler("contestwinners", contestwinners))
    app.add_handler(CommandHandler("declarewinner", declarewinner))
    app.add_handler(CommandHandler("joincontest", joincontest))