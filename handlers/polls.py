"""
سیستم نظرسنجی و رای‌گیری
"""
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import database as db
from utils.permissions import require_admin, is_admin
from utils.helpers import escape_markdown

logger = logging.getLogger(__name__)

active_polls = {}


async def poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not db.is_feature_enabled(chat_id, "poll_system"):
        await update.effective_message.reply_text("⛔️ سیستم نظرسنجی برای این گروه غیرفعال شده.")
        return
    
    if not await is_admin(update, context, user_id):
        await update.effective_message.reply_text("⛔️ فقط ادمین‌ها می‌توانند نظرسنجی ایجاد کنند.")
        return
    
    if not context.args:
        await update.effective_message.reply_text(
            "📝 *ایجاد نظرسنجی*\n\n"
            "استفاده: `/poll سوال|گزینه1|گزینه2|...`\n\n"
            "مثال: `/poll رنگ مورد علاقه شما چیست؟|آبی|سبز|قرمز|زرد`\n\n"
            "برای نظرسنجی ناشناس:\n"
            "`/poll anonymous سوال|گزینه1|گزینه2|...`",
            parse_mode="Markdown"
        )
        return
    
    poll_text = " ".join(context.args)
    is_anonymous = False
    
    if poll_text.startswith("anonymous "):
        is_anonymous = True
        poll_text = poll_text.replace("anonymous ", "")
    
    if "|" not in poll_text:
        await update.effective_message.reply_text(
            "❌ فرمت اشتباه!\n"
            "استفاده: `/poll سوال|گزینه1|گزینه2|...`"
        )
        return
    
    parts = poll_text.split("|")
    question = parts[0].strip()
    options = [opt.strip() for opt in parts[1:] if opt.strip()]
    
    if len(options) < 2:
        await update.effective_message.reply_text("❌ حداقل ۲ گزینه وارد کنید!")
        return
    
    if len(options) > 10:
        await update.effective_message.reply_text("❌ حداکثر ۱۰ گزینه مجاز است!")
        return
    
    poll_id = int(time.time())
    poll_data = {
        "id": poll_id,
        "chat_id": chat_id,
        "user_id": user_id,
        "question": question,
        "options": options,
        "votes": {opt: [] for opt in options},
        "anonymous": is_anonymous,
        "created_at": time.time(),
        "active": True,
        "message_id": None
    }
    
    active_polls[poll_id] = poll_data
    
    keyboard = []
    for i, option in enumerate(options):
        keyboard.append([
            InlineKeyboardButton(f"📊 {option}", callback_data=f"vote_{poll_id}_{i}")
        ])
    keyboard.append([
        InlineKeyboardButton("📊 مشاهده نتایج", callback_data=f"poll_results_{poll_id}"),
        InlineKeyboardButton("❌ بستن نظرسنجی", callback_data=f"poll_close_{poll_id}")
    ])
    
    msg = await update.effective_message.reply_text(
        f"📊 *نظرسنجی جدید*\n\n"
        f"❓ {escape_markdown(question)}\n\n"
        f"🔹 روی گزینه مورد نظر کلیک کنید.\n"
        f"🔹 {len(options)} گزینه\n"
        f"🔹 {'🔒 ناشناس' if is_anonymous else '👤 عمومی'}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    
    poll_data["message_id"] = msg.message_id


async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    data = query.data
    
    parts = data.split("_")
    if len(parts) != 3:
        return
    
    poll_id = int(parts[1])
    option_index = int(parts[2])
    
    if poll_id not in active_polls:
        await query.edit_message_text("❌ این نظرسنجی وجود ندارد یا بسته شده است.")
        return
    
    poll = active_polls[poll_id]
    
    if not poll["active"]:
        await query.edit_message_text("❌ این نظرسنجی بسته شده است.")
        return
    
    if chat_id != poll["chat_id"]:
        await query.answer("⛔️ شما نمی‌توانید در این نظرسنجی رای دهید!")
        return
    
    for opt in poll["options"]:
        if user_id in poll["votes"][opt]:
            poll["votes"][opt].remove(user_id)
    
    selected_option = poll["options"][option_index]
    poll["votes"][selected_option].append(user_id)
    
    total_votes = sum(len(v) for v in poll["votes"].values())
    
    if poll["anonymous"]:
        await query.answer(f"✅ رای شما ثبت شد!")
    else:
        await query.answer(f"✅ شما به «{selected_option}» رای دادید!")
    
    await update_poll_message(query, poll_id)


async def update_poll_message(query, poll_id):
    if poll_id not in active_polls:
        return
    
    poll = active_polls[poll_id]
    total_votes = sum(len(v) for v in poll["votes"].values())
    
    text = f"📊 *نظرسنجی*\n\n"
    text += f"❓ {escape_markdown(poll['question'])}\n\n"
    
    for opt in poll["options"]:
        votes = len(poll["votes"][opt])
        percentage = (votes / total_votes * 100) if total_votes > 0 else 0
        bar = "█" * int(percentage / 5) + "░" * (20 - int(percentage / 5))
        text += f"• {escape_markdown(opt)}:\n"
        text += f"  {bar} {percentage:.1f}% ({votes} رای)\n\n"
    
    text += f"📊 مجموع رای‌ها: {total_votes}"
    if poll["anonymous"]:
        text += "\n🔒 ناشناس"
    
    if not poll["active"]:
        text += "\n\n🔴 *این نظرسنجی بسته شده است.*"
    
    keyboard = [
        [InlineKeyboardButton("🔄 به‌روزرسانی", callback_data=f"poll_refresh_{poll_id}")]
    ]
    
    try:
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error updating poll: {e}")


async def poll_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.effective_message.reply_text(
            "❌ شماره نظرسنجی را وارد کنید:\n"
            "/pollresults [ID]"
        )
        return
    
    try:
        poll_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ شماره نامعتبر!")
        return
    
    if poll_id not in active_polls:
        await update.effective_message.reply_text("❌ نظرسنجی وجود ندارد!")
        return
    
    poll = active_polls[poll_id]
    if chat_id != poll["chat_id"]:
        await update.effective_message.reply_text("⛔️ شما دسترسی به این نظرسنجی ندارید!")
        return
    
    total_votes = sum(len(v) for v in poll["votes"].values())
    
    text = f"📊 *نتایج نظرسنجی*\n\n"
    text += f"❓ {escape_markdown(poll['question'])}\n\n"
    
    if total_votes == 0:
        text += "📭 هنوز رای‌ای ثبت نشده است."
    else:
        for opt in poll["options"]:
            votes = len(poll["votes"][opt])
            percentage = (votes / total_votes) * 100 if total_votes > 0 else 0
            bar = "█" * int(percentage / 5) + "░" * (20 - int(percentage / 5))
            text += f"• {escape_markdown(opt)}:\n"
            text += f"  {bar} {percentage:.1f}% ({votes} رای)\n\n"
        
        text += f"\n📊 مجموع رای‌ها: {total_votes}"
        if poll["anonymous"]:
            text += "\n🔒 این نظرسنجی ناشناس است."
    
    if not poll["active"]:
        text += "\n\n🔴 *این نظرسنجی بسته شده است.*"
    
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def close_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(update, context, user_id):
        await update.effective_message.reply_text("⛔️ فقط ادمین‌ها می‌توانند نظرسنجی را ببندند.")
        return
    
    if not context.args:
        await update.effective_message.reply_text(
            "❌ شماره نظرسنجی را وارد کنید:\n"
            "/closepoll [ID]"
        )
        return
    
    try:
        poll_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ شماره نامعتبر!")
        return
    
    if poll_id not in active_polls:
        await update.effective_message.reply_text("❌ نظرسنجی وجود ندارد!")
        return
    
    poll = active_polls[poll_id]
    if chat_id != poll["chat_id"]:
        await update.effective_message.reply_text("⛔️ شما دسترسی به این نظرسنجی ندارید!")
        return
    
    poll["active"] = False
    
    await update.effective_message.reply_text(
        f"✅ نظرسنجی «{poll['question']}» بسته شد.\n"
        f"برای مشاهده نتایج: /pollresults {poll_id}"
    )


async def poll_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("vote_"):
        await vote_callback(update, context)
    elif data.startswith("poll_results_"):
        poll_id = int(data.split("_")[2])
        await show_poll_results(update, poll_id, edit=True)
    elif data.startswith("poll_close_"):
        poll_id = int(data.split("_")[2])
        await close_poll_callback(update, poll_id)
    elif data.startswith("poll_refresh_"):
        poll_id = int(data.split("_")[2])
        await query.answer("🔄 به‌روزرسانی شد!")
        await update_poll_message(query, poll_id)


async def show_poll_results(update, poll_id, edit=False):
    if poll_id not in active_polls:
        await update.effective_message.reply_text("❌ نظرسنجی وجود ندارد!")
        return
    
    poll = active_polls[poll_id]
    total_votes = sum(len(v) for v in poll["votes"].values())
    
    text = f"📊 *نتایج نظرسنجی*\n\n"
    text += f"❓ {escape_markdown(poll['question'])}\n\n"
    
    if total_votes == 0:
        text += "📭 هنوز رای‌ای ثبت نشده است."
    else:
        for opt in poll["options"]:
            votes = len(poll["votes"][opt])
            percentage = (votes / total_votes) * 100 if total_votes > 0 else 0
            bar = "█" * int(percentage / 5) + "░" * (20 - int(percentage / 5))
            text += f"• {escape_markdown(opt)}:\n"
            text += f"  {bar} {percentage:.1f}% ({votes} رای)\n\n"
        
        text += f"\n📊 مجموع رای‌ها: {total_votes}"
        if poll["anonymous"]:
            text += "\n🔒 این نظرسنجی ناشناس است."
    
    if not poll["active"]:
        text += "\n\n🔴 *این نظرسنجی بسته شده است.*"
    
    if edit:
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown"
        )
        await update.callback_query.answer()
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown")


async def close_poll_callback(update, poll_id):
    query = update.callback_query
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if poll_id not in active_polls:
        await query.answer("❌ نظرسنجی وجود ندارد!")
        return
    
    poll = active_polls[poll_id]
    
    if not await is_admin(update, None, user_id):
        await query.answer("⛔️ فقط ادمین‌ها می‌توانند نظرسنجی را ببندند!")
        return
    
    if chat_id != poll["chat_id"]:
        await query.answer("⛔️ شما دسترسی به این نظرسنجی ندارید!")
        return
    
    poll["active"] = False
    await query.answer("✅ نظرسنجی بسته شد!")
    await update_poll_message(query, poll_id)


def register_poll_handlers(app):
    app.add_handler(CommandHandler("poll", poll))
    app.add_handler(CommandHandler("pollresults", poll_results))
    app.add_handler(CommandHandler("closepoll", close_poll))
    app.add_handler(CallbackQueryHandler(poll_callback_handler, pattern="^(vote_|poll_results_|poll_close_|poll_refresh_)"))