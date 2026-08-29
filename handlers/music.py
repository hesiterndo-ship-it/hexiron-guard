"""
سیستم پخش موزیک و پلی‌لیست

نکته‌ی مهم فنی: Bot API تلگرام امکان join شدن به voice chat گروه یا استریم
زنده‌ی صدا رو نداره (این فقط با MTProto/userbot و کتابخونه‌هایی مثل
PyTgCalls ممکنه). بنابراین "پخش" در این ماژول یعنی: آهنگ رو پیدا/دانلود می‌کنیم
و به‌صورت فایل صوتی (voice message) توی خود گروه ارسال می‌کنیم - که تنها روش
واقعی و قابل‌اجرا روی سرور (بدون کارت صدا) با یک بات معمولیه.
"""
import logging
import os
import uuid
import asyncio
from collections import OrderedDict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, CommandHandler
from telegram.constants import ChatAction
import yt_dlp
from pydub import AudioSegment

logger = logging.getLogger(__name__)

MUSIC_DIR = "music"
PLAYLISTS_DIR = "playlists"
DEFAULT_PLAYLIST = "علاقه‌مندی‌ها"

# سایت‌هایی که برای جست‌وجوی خودکار (وقتی کاربر فقط اسم آهنگ رو می‌ده، نه لینک)
# به ترتیب امتحان می‌شن. yt_dlp این extractorها رو built-in پشتیبانی می‌کنه.
SEARCH_ENGINES = ["ytsearch1:", "scsearch1:"]  # یوتیوب، بعد ساندکلاود

if not os.path.exists(MUSIC_DIR):
    os.makedirs(MUSIC_DIR)
if not os.path.exists(PLAYLISTS_DIR):
    os.makedirs(PLAYLISTS_DIR)

# رجیستری کوتاه برای دکمه‌ی «افزودن به پلی‌لیست» زیر هر آهنگ ارسالی
# (callback_data تلگرام حداکثر ۶۴ بایته، پس مسیر فایل رو مستقیم توش نمی‌ذاریم)
_track_registry: "OrderedDict[str, dict]" = OrderedDict()
_TRACK_REGISTRY_MAX = 1000


def _register_track(file_path: str, title: str) -> str:
    short_id = uuid.uuid4().hex[:10]
    _track_registry[short_id] = {"path": file_path, "title": title}
    if len(_track_registry) > _TRACK_REGISTRY_MAX:
        _track_registry.popitem(last=False)
    return short_id

# وضعیت پخش به ازای هر گروه به‌صورت جداگانه نگه‌داری می‌شه
# (قبلاً یک state سراسری بود که باعث می‌شد گروه‌های مختلف رو صفِ پخش هم اثر بذارن)
_chat_states: dict[int, dict] = {}


def _get_state(chat_id: int) -> dict:
    if chat_id not in _chat_states:
        _chat_states[chat_id] = {
            "queue": [],       # لیست (مسیر فایل، عنوان) هایی که در صف هستن
            "sending": False,  # آیا در حال حاضر یک تسک پخش صف در حال اجراست
            "paused": False,
            "loop": False,
            "volume": 0.5,     # 0.0 - 1.0
            "current": None,
            "last_by_user": {},  # user_id -> {"path":, "title":}  (آخرین آهنگی که هرکاربر پلی کرده)
        }
    return _chat_states[chat_id]


def _apply_volume(file_path: str, volume: float) -> str:
    """
    با pydub بلندی صدای فایل رو تنظیم می‌کنه و یک فایل موقت خروجی می‌ده.
    این کار فقط export می‌کنه (نیازی به کارت صدا/پخش محلی نداره).
    اگه ffmpeg روی سرور نصب نباشه، این تابع خطا می‌ده و باید فایل اصلی
    بدون تغییر ارسال بشه.
    """
    audio = AudioSegment.from_file(file_path)
    # volume=0.5 یعنی بدون تغییر؛ کمتر از اون کاهش صدا و بیشتر افزایش صدا
    gain_db = (volume - 0.5) * 20
    audio = audio + gain_db
    out_path = os.path.join(MUSIC_DIR, f"_tmp_vol_{os.path.basename(file_path)}")
    audio.export(out_path, format="mp3")
    return out_path


def _download_from_url(url: str) -> tuple[str, str]:
    """یک لینک مستقیم (یوتیوب، ساندکلاود و هر سایتی که yt_dlp پشتیبانی می‌کنه) رو دانلود می‌کنه."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(MUSIC_DIR, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_name = ydl.prepare_filename(info)
        file_name = os.path.splitext(file_name)[0] + ".mp3"
        title = info.get("title", os.path.splitext(os.path.basename(file_name))[0])
        return file_name, title


def _search_and_download(query: str) -> tuple[str, str]:
    """
    اسم آهنگ رو به ترتیب توی چند سایت آنلاین (SEARCH_ENGINES) جست‌وجو می‌کنه
    و بهترین نتیجه‌ی اولی که پیدا بشه رو دانلود می‌کنه.
    """
    last_error = None
    for prefix in SEARCH_ENGINES:
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': os.path.join(MUSIC_DIR, '%(title)s.%(ext)s'),
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(f"{prefix}{query}", download=True)
                if result and result.get("entries"):
                    info = result["entries"][0]
                else:
                    info = result
                if not info:
                    continue
                file_name = ydl.prepare_filename(info)
                file_name = os.path.splitext(file_name)[0] + ".mp3"
                title = info.get("title", query)
                return file_name, title
        except Exception as e:
            logger.warning(f"Search via {prefix!r} failed for {query!r}: {e}")
            last_error = e
            continue
    raise last_error or RuntimeError("هیچ نتیجه‌ای پیدا نشد")


async def _send_next(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """یک آهنگ از صف رو به‌عنوان فایل صوتی ارسال می‌کنه و بعدش خودش رو برای بعدی صدا می‌زنه."""
    state = _get_state(chat_id)

    if state["sending"]:
        return  # یک تسک ارسال از قبل در حال اجراست

    state["sending"] = True
    try:
        while state["queue"] and not state["paused"]:
            item = state["queue"][0]
            file_path = item["path"]
            title = item.get("title") or os.path.splitext(os.path.basename(file_path))[0]
            state["current"] = item

            send_path = file_path
            try:
                if state["volume"] != 0.5:
                    send_path = _apply_volume(file_path, state["volume"])
            except Exception as e:
                logger.warning(f"Volume adjustment failed, sending original file: {e}")
                send_path = file_path

            short_id = _register_track(file_path, title)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("❤️ افزودن به پلی‌لیست من", callback_data=f"musicfav_{short_id}")
            ]])

            try:
                await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_VOICE)
                with open(send_path, "rb") as f:
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=f,
                        title=title,
                        caption=f"🎵 {title}",
                        reply_markup=keyboard,
                    )
            except Exception as e:
                logger.error(f"Error sending audio: {e}")
                await context.bot.send_message(chat_id, f"❌ خطا در ارسال آهنگ: {e}")
            finally:
                if send_path != file_path and os.path.exists(send_path):
                    try:
                        os.remove(send_path)
                    except OSError:
                        pass

            if state["loop"]:
                # آهنگ فعلی رو به انتهای صف برمی‌گردونیم تا تکرار بشه
                state["queue"].append(state["queue"].pop(0))
            else:
                state["queue"].pop(0)

            # یک وقفه‌ی کوچیک بین آهنگ‌ها تا اسپم نشه
            await asyncio.sleep(1)

        state["current"] = None
    finally:
        state["sending"] = False


async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """افزودن آهنگ به صف پخش گروه"""
    chat_id = update.effective_chat.id
    state = _get_state(chat_id)

    if not context.args:
        await update.effective_message.reply_text(
            "🎵 *پخش موزیک*\n\n"
            "/play [نام آهنگ یا لینک]\n\n"
            "مثال: /play Shadmehr\n"
            "مثال: /play https://www.youtube.com/watch?v=...\n\n"
            "اگه فقط اسم آهنگ رو بدی، اول توی کتابخانه‌ی محلی گروه می‌گرده،\n"
            "و اگه پیدا نشد خودش از یوتیوب و ساندکلاود جست‌وجو و دانلود می‌کنه.\n\n"
            "بعد از پخش هر آهنگ، با زدن دکمه‌ی ❤️ زیرش می‌تونی به پلی‌لیست خودت اضافه‌اش کنی.",
            parse_mode="Markdown"
        )
        return

    query = " ".join(context.args)
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)

    try:
        file_path = None
        title = None

        if query.startswith("http"):
            # لینک مستقیم (یوتیوب، ساندکلاود، یا هر سایتی که yt_dlp پشتیبانی کنه)
            await update.effective_message.reply_text("⏳ در حال دانلود آهنگ...")
            file_path, title = _download_from_url(query)
        else:
            # اول توی کتابخانه‌ی محلی گروه بگرد
            music_files = [f for f in os.listdir(MUSIC_DIR) if f.endswith(('.mp3', '.wav', '.m4a'))]
            found = [f for f in music_files if query.lower() in f.lower()]

            if found:
                file_path = os.path.join(MUSIC_DIR, found[0])
                title = os.path.splitext(found[0])[0]
            else:
                # اگه محلی نبود، خودکار از چند سایت آنلاین (یوتیوب، ساندکلاود) بگرد
                await update.effective_message.reply_text("🔎 در کتابخانه‌ی محلی نبود، در حال جست‌وجوی آنلاین...")
                try:
                    file_path, title = _search_and_download(query)
                except Exception:
                    await update.effective_message.reply_text(
                        f"❌ آهنگ '{query}' نه در کتابخانه‌ی محلی و نه آنلاین پیدا نشد.\n\n"
                        f"یه اسم دیگه امتحان کن یا مستقیم لینک بده:\n"
                        f"/play https://www.youtube.com/watch?v=..."
                    )
                    return

        await update.effective_message.reply_text(
            f"✅ آهنگ *{title}* به صف پخش اضافه شد!",
            parse_mode="Markdown"
        )
        state["queue"].append({"path": file_path, "title": title})
        state["last_by_user"][user_id] = {"path": file_path, "title": title}

        state["paused"] = False
        if not state["sending"]:
            asyncio.create_task(_send_next(context, chat_id))

    except Exception as e:
        logger.error(f"Error in /play: {e}")
        await update.effective_message.reply_text(f"❌ خطا: {str(e)[:200]}")


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """توقف موقت صف پخش (بعد از ارسال آهنگ فعلی، آهنگ بعدی ارسال نمیشه تا /resume)"""
    state = _get_state(update.effective_chat.id)
    if state["queue"] or state["current"]:
        state["paused"] = True
        await update.effective_message.reply_text("⏸️ صف پخش موقتاً متوقف شد. برای ادامه: /resume")
    else:
        await update.effective_message.reply_text("❌ صف پخشی وجود نداره.")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ادامه‌ی صف پخش"""
    chat_id = update.effective_chat.id
    state = _get_state(chat_id)
    if state["paused"]:
        state["paused"] = False
        await update.effective_message.reply_text("▶️ صف پخش ادامه پیدا کرد.")
        if not state["sending"]:
            asyncio.create_task(_send_next(context, chat_id))
    else:
        await update.effective_message.reply_text("❌ صف پخشی متوقف‌شده وجود نداره.")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """توقف کامل و پاک کردن صف پخش"""
    state = _get_state(update.effective_chat.id)
    if state["queue"] or state["current"]:
        state["queue"] = []
        state["paused"] = False
        state["current"] = None
        await update.effective_message.reply_text("⏹️ پخش متوقف شد و صف پاک شد.")
    else:
        await update.effective_message.reply_text("❌ صف پخشی وجود نداره.")


async def skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رد کردن آهنگ فعلی و رفتن به بعدی"""
    chat_id = update.effective_chat.id
    state = _get_state(chat_id)
    if state["queue"]:
        state["queue"].pop(0)
        await update.effective_message.reply_text("⏭️ به آهنگ بعدی رفتیم.")
        if state["queue"] and not state["sending"]:
            asyncio.create_task(_send_next(context, chat_id))
    else:
        await update.effective_message.reply_text("❌ صف پخش خالیه.")


async def loop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فعال/غیرفعال کردن حالت تکرار صف"""
    state = _get_state(update.effective_chat.id)
    state["loop"] = not state["loop"]
    status = "فعال" if state["loop"] else "غیرفعال"
    await update.effective_message.reply_text(f"🔄 حالت تکرار: {status}")


async def volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم بلندی صدای فایل‌های بعدی"""
    state = _get_state(update.effective_chat.id)
    if not context.args:
        await update.effective_message.reply_text(
            f"🔊 صدای فعلی: {int(state['volume'] * 100)}%\n"
            "برای تغییر: /volume [0-100]"
        )
        return

    try:
        vol = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ عدد معتبر وارد کنید.")
        return

    if 0 <= vol <= 100:
        state["volume"] = vol / 100
        await update.effective_message.reply_text(f"🔊 صدا به {vol}% تغییر یافت (روی آهنگ‌های بعدی اعمال میشه).")
    else:
        await update.effective_message.reply_text("❌ عدد بین 0 تا 100 وارد کنید.")


def _save_song_to_playlist(chat_id: int, user_id: int, playlist_name: str, file_path: str) -> str:
    """اسم فایل رو (نه مسیر کامل) توی پلی‌لیست متنی کاربر ذخیره می‌کنه. اگه از قبل توی همون
    پلی‌لیست بود، دوباره اضافه نمی‌کنه."""
    song_basename = os.path.basename(file_path)
    playlist_path = os.path.join(PLAYLISTS_DIR, f"{chat_id}_{user_id}_{playlist_name}.txt")

    existing = []
    if os.path.exists(playlist_path):
        with open(playlist_path, 'r', encoding='utf-8') as f:
            existing = f.read().splitlines()

    if song_basename not in existing:
        with open(playlist_path, 'a', encoding='utf-8') as f:
            f.write(f"{song_basename}\n")

    return song_basename


async def addtoplaylist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    افزودن به پلی‌لیست شخصی. دو روش:
    - /addtoplaylist [نام]              -> آخرین آهنگی که خودتون با /play پخش کردید رو ذخیره می‌کنه
    - /addtoplaylist [نام] [آهنگ محلی]  -> یه آهنگ مشخص از کتابخانه‌ی محلی رو جست‌وجو و ذخیره می‌کنه
    """
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    state = _get_state(chat_id)

    if not context.args:
        await update.effective_message.reply_text(
            "📝 *افزودن به پلی‌لیست*\n\n"
            "بعد از `/play`، فقط بزن:\n"
            "`/addtoplaylist [نام پلی‌لیست]`\n"
            "و آخرین آهنگی که پخش کردی ذخیره میشه.\n\n"
            "یا برای انتخاب مستقیم از کتابخانه‌ی محلی:\n"
            "`/addtoplaylist [نام] [آهنگ]`\n\n"
            "مثال: `/addtoplaylist موردعلاقه`\n"
            "مثال: `/addtoplaylist موردعلاقه Shadmehr`",
            parse_mode="Markdown"
        )
        return

    playlist_name = context.args[0]

    if len(context.args) == 1:
        # همون آهنگی که کاربر آخرین بار /play کرده رو ذخیره کن
        last = state["last_by_user"].get(user_id)
        if not last:
            await update.effective_message.reply_text(
                "❌ هنوز آهنگی با /play پخش نکردی که ذخیره‌اش کنم.\n"
                "اول `/play [اسم آهنگ]` بزن، بعد `/addtoplaylist [نام]`."
            )
            return
        try:
            _save_song_to_playlist(chat_id, user_id, playlist_name, last["path"])
            await update.effective_message.reply_text(
                f"✅ آهنگ *{last['title']}* به پلی‌لیست *{playlist_name}* اضافه شد!",
                parse_mode="Markdown"
            )
        except OSError as e:
            await update.effective_message.reply_text(f"❌ خطا: {e}")
        return

    # فرم قدیمی: جست‌وجوی مستقیم توی کتابخانه‌ی محلی
    song_name = " ".join(context.args[1:])
    music_files = [f for f in os.listdir(MUSIC_DIR) if f.endswith(('.mp3', '.wav', '.m4a'))]
    found = [f for f in music_files if song_name.lower() in f.lower()]

    if not found:
        await update.effective_message.reply_text(f"❌ آهنگ '{song_name}' پیدا نشد!")
        return

    try:
        _save_song_to_playlist(chat_id, user_id, playlist_name, found[0])
        await update.effective_message.reply_text(
            f"✅ آهنگ *{found[0]}* به پلی‌لیست *{playlist_name}* اضافه شد!",
            parse_mode="Markdown"
        )
    except OSError as e:
        await update.effective_message.reply_text(f"❌ خطا: {e}")


async def music_fav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دکمه‌ی ❤️ زیر هر آهنگ ارسالی - همون آهنگ رو به پلی‌لیست پیش‌فرض کاربری که دکمه رو زده اضافه می‌کنه."""
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = update.effective_chat.id

    short_id = query.data.split("_", 1)[1] if "_" in query.data else ""
    entry = _track_registry.get(short_id)

    if not entry:
        await query.answer("⌛️ این آهنگ منقضی شده، دوباره /play بزن.", show_alert=True)
        return

    try:
        _save_song_to_playlist(chat_id, user_id, DEFAULT_PLAYLIST, entry["path"])
        await query.answer(f"❤️ به پلی‌لیست «{DEFAULT_PLAYLIST}» اضافه شد!")
    except OSError as e:
        await query.answer(f"❌ خطا: {e}", show_alert=True)


async def myplaylists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده پلی‌لیست‌های شخصی"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        files = [f for f in os.listdir(PLAYLISTS_DIR) if f.startswith(f"{chat_id}_{user_id}_")]

        if not files:
            await update.effective_message.reply_text(
                "📭 پلی‌لیستی ایجاد نکردید.\n"
                "با /addtoplaylist پلی‌لیست بسازید."
            )
            return

        text = "🎵 *پلی‌لیست‌های من:*\n\n"
        for f in files:
            name = f[len(f"{chat_id}_{user_id}_"):-len(".txt")]
            with open(os.path.join(PLAYLISTS_DIR, f), 'r', encoding='utf-8') as pf:
                songs = pf.read().splitlines()
            text += f"📁 *{name}* - {len(songs)} آهنگ\n"

        await update.effective_message.reply_text(text, parse_mode="Markdown")
    except OSError as e:
        await update.effective_message.reply_text(f"❌ خطا: {e}")


async def playlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """افزودن یک پلی‌لیست کامل به صف پخش"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    state = _get_state(chat_id)

    if not context.args:
        await update.effective_message.reply_text(
            "/playlist [نام]\n"
            "مثال: /playlist موردعلاقه"
        )
        return

    playlist_name = context.args[0]
    playlist_path = os.path.join(PLAYLISTS_DIR, f"{chat_id}_{user_id}_{playlist_name}.txt")

    if not os.path.exists(playlist_path):
        await update.effective_message.reply_text(f"❌ پلی‌لیست '{playlist_name}' پیدا نشد!")
        return

    with open(playlist_path, 'r', encoding='utf-8') as f:
        songs = f.read().splitlines()

    if not songs:
        await update.effective_message.reply_text(f"📭 پلی‌لیست '{playlist_name}' خالی است!")
        return

    added = 0
    for song in songs:
        file_path = os.path.join(MUSIC_DIR, song)
        if os.path.exists(file_path):
            state["queue"].append({"path": file_path, "title": os.path.splitext(song)[0]})
            added += 1

    await update.effective_message.reply_text(
        f"🎵 {added} آهنگ از پلی‌لیست '{playlist_name}' به صف پخش اضافه شد!"
    )

    state["paused"] = False
    if not state["sending"]:
        asyncio.create_task(_send_next(context, chat_id))


def register_music_handlers(app):
    """ثبت هندلرهای موزیک"""
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("skip", skip))
    app.add_handler(CommandHandler("loop", loop))
    app.add_handler(CommandHandler("volume", volume))
    app.add_handler(CommandHandler("addtoplaylist", addtoplaylist))
    app.add_handler(CommandHandler("myplaylists", myplaylists))
    app.add_handler(CommandHandler("playlist", playlist))
    app.add_handler(CallbackQueryHandler(music_fav_callback, pattern="^musicfav_"))