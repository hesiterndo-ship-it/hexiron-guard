"""
سیستم تبدیل صدا به متن (Voice to Text)
"""
import os
import time
import speech_recognition as sr
from pydub import AudioSegment
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ChatAction

AUDIO_DIR = "audio_temp"
if not os.path.exists(AUDIO_DIR):
    os.makedirs(AUDIO_DIR)


async def voicetotext(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبدیل ویس به متن"""
    chat_id = update.effective_chat.id
    
    if not update.effective_message.reply_to_message:
        await update.effective_message.reply_text(
            "🗣️ *تبدیل صدا به متن*\n\n"
            "روی یک ویس ریپلای کنید و /voicetotext بفرستید.",
            parse_mode="Markdown"
        )
        return
    
    voice = update.effective_message.reply_to_message.voice
    if not voice:
        await update.effective_message.reply_text("❌ لطفاً روی یک ویس ریپلای کنید!")
        return
    
    try:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        
        voice_file = await context.bot.get_file(voice.file_id)
        ogg_path = os.path.join(AUDIO_DIR, f"voice_{int(time.time())}.ogg")
        await voice_file.download_to_drive(ogg_path)
        
        wav_path = ogg_path.replace('.ogg', '.wav')
        audio = AudioSegment.from_ogg(ogg_path)
        audio.export(wav_path, format="wav")
        
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            
        try:
            text = recognizer.recognize_google(audio_data, language='fa-IR')
            await update.effective_message.reply_text(
                f"📝 *متن تشخیص داده شده:*\n\n{text}\n\n🔊 زبان: فارسی",
                parse_mode="Markdown"
            )
        except sr.UnknownValueError:
            try:
                text = recognizer.recognize_google(audio_data, language='en-US')
                await update.effective_message.reply_text(
                    f"📝 *متن تشخیص داده شده (انگلیسی):*\n\n{text}",
                    parse_mode="Markdown"
                )
            except:
                await update.effective_message.reply_text(
                    "❌ متاسفانه نتوانستم متن را تشخیص دهم.\n"
                    "لطفاً واضح‌تر صحبت کنید یا از ویس کوتاه‌تر استفاده کنید."
                )
        except Exception as e:
            await update.effective_message.reply_text(f"❌ خطا: {e}")
        
        os.remove(ogg_path)
        if os.path.exists(wav_path):
            os.remove(wav_path)
            
    except Exception as e:
        await update.effective_message.reply_text(f"❌ خطا: {e}")


async def texttovoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبدیل متن به صدا"""
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.effective_message.reply_text(
            "🔊 *تبدیل متن به صدا*\n\n"
            "/texttovoice متن\n\n"
            "مثال: /texttovoice سلام خوبی؟"
        )
        return
    
    text = " ".join(context.args)
    
    if len(text) > 500:
        await update.effective_message.reply_text("❌ متن طولانی است! حداکثر ۵۰۰ کاراکتر.")
        return
    
    try:
        from gtts import gTTS
        import tempfile
        
        await context.bot.send_chat_action(chat_id, ChatAction.RECORD_VOICE)
        
        tts = gTTS(text=text, lang='fa', slow=False)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
            tts.save(tmp.name)
            
            with open(tmp.name, 'rb') as audio_file:
                await context.bot.send_voice(
                    chat_id=chat_id,
                    voice=audio_file,
                    caption=f"🔊 تبدیل متن به صدا:\n\n{text[:100]}{'...' if len(text)>100 else ''}"
                )
            
            os.unlink(tmp.name)
            
    except Exception as e:
        await update.effective_message.reply_text(f"❌ خطا در تبدیل متن به صدا: {e}")


def register_voicetotext_handlers(app):
    """ثبت هندلرهای تبدیل صدا"""
    app.add_handler(CommandHandler("voicetotext", voicetotext))
    app.add_handler(CommandHandler("texttovoice", texttovoice))