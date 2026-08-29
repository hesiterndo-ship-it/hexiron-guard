"""
سیستم واکنش به کلمات کلیدی
"""
import logging
import re
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

import database as db
from utils.permissions import require_admin, is_admin

logger = logging.getLogger(__name__)


async def addreaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """افزودن واکنش جدید"""
    if not await require_admin(update, context):
        return
    
    chat_id = update.effective_chat.id
    
    if len(context.args) < 1:
        await update.effective_message.reply_text(
            "🤖 *افزودن واکنش*\n\n"
            "استفاده: `/addreaction کلمه|پاسخ`\n\n"
            "مثال: `/addreaction سلام|سلام علیکم`\n"
            "مثال: `/addreaction خداحافظ|به امید دیدار`\n\n"
            "برای مشاهده لیست: /listreactions",
            parse_mode="Markdown"
        )
        return
    
    reaction_text = " ".join(context.args)
    
    if "|" not in reaction_text:
        await update.effective_message.reply_text(
            "❌ فرمت اشتباه!\n"
            "استفاده: `/addreaction کلمه|پاسخ`"
        )
        return
    
    word, reply = reaction_text.split("|", 1)
    word = word.strip().lower()
    reply = reply.strip()
    
    if not word or not reply:
        await update.effective_message.reply_text("❌ کلمه و پاسخ نمی‌توانند خالی باشند!")
        return
    
    db.add_reaction(chat_id, word, reply)
    
    await update.effective_message.reply_text(
        f"✅ واکنش جدید اضافه شد!\n\n"
        f"🔹 کلمه: `{word}`\n"
        f"🔹 پاسخ: {reply[:50]}{'...' if len(reply) > 50 else ''}",
        parse_mode="Markdown"
    )


async def removereaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف واکنش"""
    if not await require_admin(update, context):
        return
    
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.effective_message.reply_text(
            "❌ کلمه مورد نظر را وارد کنید:\n"
            "/removereaction کلمه"
        )
        return
    
    word = " ".join(context.args).strip().lower()
    
    db.remove_reaction(chat_id, word)
    
    await update.effective_message.reply_text(
        f"✅ واکنش کلمه `{word}` حذف شد.",
        parse_mode="Markdown"
    )


async def listreactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست واکنش‌ها"""
    chat_id = update.effective_chat.id
    
    reactions = db.list_reactions(chat_id)
    
    if not reactions:
        await update.effective_message.reply_text(
            "📭 لیست واکنش‌ها خالی است.\n\n"
            "برای افزودن: `/addreaction کلمه|پاسخ`"
        )
        return
    
    text = "🤖 *لیست واکنش‌ها:*\n\n"
    for r in reactions[:20]:
        text += f"🔹 `{r['word']}` → {r['reply'][:30]}{'...' if len(r['reply']) > 30 else ''}\n"
    
    if len(reactions) > 20:
        text += f"\n... و {len(reactions)-20} واکنش دیگر"
    
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def check_reactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بررسی خودکار واکنش‌ها"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message = update.effective_message
    
    if not message or not message.text:
        return
    
    # ادمین‌ها رو نادیده بگیر
    if await is_admin(update, context, user_id):
        return
    
    # دریافت لیست واکنش‌ها
    reactions = db.list_reactions(chat_id)
    if not reactions:
        return
    
    text = message.text.lower()
    
    for r in reactions:
        if r['word'].lower() in text:
            await message.reply_text(r['reply'])
            break


def register_reaction_handlers(app):
    """ثبت هندلرهای واکنش"""
    app.add_handler(CommandHandler("addreaction", addreaction))
    app.add_handler(CommandHandler("removereaction", removereaction))
    app.add_handler(CommandHandler("listreactions", listreactions))