"""
سیستم نجوا (Whisper) - ارسال ویس خصوصی
"""
import os
import time
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ChatAction
import database as db
from utils.helpers import escape_markdown

WHISPER_DIR = "whispers"

if not os.path.exists(WHISPER_DIR):
    os.makedirs(WHISPER_DIR)


async def whisper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not update.effective_message.reply_to_message:
        await update.effective_message.reply_text(
            "🔇 *سیستم نجوا*\n\n"
            "روی یک ویس ریپلای کنید و /whisper @username بفرستید.\n\n"
            "مثال: روی ویس ریپلای کنید و بفرستید:\n"
            "`/whisper @Ali_Reza`",
            parse_mode="Markdown"
        )
        return
    
    if not context.args:
        await update.effective_message.reply_text(
            "❗️ نام کاربر را وارد کنید:\n"
            "/whisper @username"
        )
        return
    
    voice = update.effective_message.reply_to_message.voice
    if not voice:
        await update.effective_message.reply_text("❌ لطفاً روی یک ویس ریپلای کنید!")
        return
    
    target_username = context.args[0].replace('@', '')
    
    target_id = None
    try:
        users = db.find_user_by_username(chat_id, target_username)
        if users:
            target_id = users[0]['user_id']
        else:
            await update.effective_message.reply_text(f"❌ کاربر @{target_username} پیدا نشد!")
            return
    except:
        await update.effective_message.reply_text(f"❌ کاربر @{target_username} پیدا نشد!")
        return
    
    try:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        
        voice_file = await context.bot.get_file(voice.file_id)
        file_name = f"{int(time.time())}_{user_id}_{target_id}.ogg"
        file_path = os.path.join(WHISPER_DIR, file_name)
        await voice_file.download_to_drive(file_path)
        
        with open(file_path, 'rb') as f:
            await context.bot.send_voice(
                chat_id=target_id,
                voice=f,
                caption=f"🔇 *نجوا از {escape_markdown(update.effective_user.first_name)}*",
                parse_mode="Markdown"
            )
        
        await update.effective_message.reply_text(f"✅ ویس شما به @{target_username} ارسال شد! (نجوا)")
        os.remove(file_path)
        
    except Exception as e:
        await update.effective_message.reply_text(f"❌ خطا در ارسال نجوا: {e}")


async def secret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not update.effective_message.reply_to_message:
        await update.effective_message.reply_text(
            "🔐 *نجوا با رمز*\n\n"
            "روی ویس ریپلای کنید و بفرستید:\n"
            "/secret @username رمز"
        )
        return
    
    if len(context.args) < 2:
        await update.effective_message.reply_text("❗️ استفاده: /secret @username رمز")
        return
    
    target_username = context.args[0].replace('@', '')
    password = context.args[1]
    
    voice = update.effective_message.reply_to_message.voice
    if not voice:
        await update.effective_message.reply_text("❌ روی ویس ریپلای کنید!")
        return
    
    users = db.find_user_by_username(chat_id, target_username)
    if not users:
        await update.effective_message.reply_text(f"❌ کاربر @{target_username} پیدا نشد!")
        return
    
    target_id = users[0]['user_id']
    
    try:
        voice_file = await context.bot.get_file(voice.file_id)
        file_name = f"secret_{int(time.time())}_{user_id}_{target_id}.ogg"
        file_path = os.path.join(WHISPER_DIR, file_name)
        await voice_file.download_to_drive(file_path)
        
        with open(file_path, 'rb') as f:
            await context.bot.send_voice(
                chat_id=target_id,
                voice=f,
                caption=f"🔐 *نجوا با رمز از {escape_markdown(update.effective_user.first_name)}*\nرمز: `{password}`",
                parse_mode="Markdown"
            )
        
        await update.effective_message.reply_text(f"✅ نجوا با رمز به @{target_username} ارسال شد!")
        os.remove(file_path)
        
    except Exception as e:
        await update.effective_message.reply_text(f"❌ خطا: {e}")


async def mywhispers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "📋 *تاریخچه نجواها*\n\n"
        "نجواهایی که دریافت کردید:\n"
        "🔹 هنوز نجوایی دریافت نشده است.",
        parse_mode="Markdown"
    )


def register_whisper_handlers(app):
    app.add_handler(CommandHandler("whisper", whisper))
    app.add_handler(CommandHandler("secret", secret))
    app.add_handler(CommandHandler("mywhispers", mywhispers))