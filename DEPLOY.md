# راهنمای دقیق آپلود روی VPS

## چرا خیلی از امکانات کار نمی‌کرد؟ (ریشه‌ی اصلی مشکل)

فایلی که آپلود کرده بودی، یه ابزار دیگه `database.py` رو کامل بازنویسی کرده بود:
اسم تقریباً همه‌ی توابع عوض شده بود (مثلاً `list_badwords` شده بود `get_badwords`،
`set_setting` شده بود `update_settings`، و توابعی مثل `is_group_subscribed` و
`seed_default_group_content` که کل هندلرها (پنل ادمین، فیلتر فحش، خوش‌آمدگویی، گیت
اشتراک گروه) بهشون نیاز داشتن **اصلاً وجود نداشتن**).

نتیجه: هر پیامی توی هر گروهی می‌رسید، همون اول (`enforce_subscription_gate`) با
خطای `AttributeError` کرش می‌کرد چون `db.is_group_subscribed` وجود نداشت — یعنی
عملاً کل بخش گروه‌ها از کار افتاده بود، ولی چون خطاها فقط توی لاگ سرور ثبت می‌شدن
(نه توی چت)، از بیرون فقط «کار نمی‌کنه» دیده می‌شد.

**راه‌حل:** `database.py`، `main.py`، تمام فایل‌های `handlers/` و `utils/helpers.py`
+ `utils/ratelimit.py` + `utils/role_filters.py` رو با نسخه‌ی کاملاً تست‌شده (که در
طول این گفتگو مرحله‌به‌مرحله ساختیم و هر بار کامپایل/تست شد) جایگزین کردم.
`config.py`، `utils/permissions.py`، `utils/crypto.py` و `badwords.txt` شما دست‌نخورده
موندن چون سالم و سازگار بودن.

## مرحله ۱: بک‌آپ بگیر (قبل از هر کاری)
```bash
cd ~/telegram_guard_bot   # یا هرجا که پروژه‌ست
mkdir -p backups
cp guardbot.db "backups/before_new_deploy_$(date +%Y%m%d_%H%M%S).db" 2>/dev/null || true
```

## مرحله ۲: ربات رو متوقف کن
```bash
# اگه با systemd اجرا می‌شه:
sudo systemctl stop guardbot
# یا اگه دستی/با screen و tmux اجرا می‌شه، همون پروسه رو Ctrl+C کن
```

## مرحله ۳: فایل جدید رو آپلود و جایگزین کن
فایل zip رو روی سرور آپلود کن (با scp/sftp یا پنل فایل‌منیجر سرورت)، extract کن، و
این فایل‌ها/پوشه‌ها رو با همینی که توی zip هست **جایگزین** کن (نه اضافه):
- `main.py`
- `database.py`
- کل پوشه‌ی `handlers/` (همه‌ی فایل‌های داخلش عوض بشن)
- از پوشه‌ی `utils/`: فقط `helpers.py`، `ratelimit.py`، `role_filters.py`
  (این سه‌تا رو عوض کن؛ `permissions.py`، `crypto.py`، `decorators.py`، `__init__.py`
  رو دست نزن، چون دست‌نخورده و سازگارن)
- `requirements.txt`

**این‌ها رو دست نزن / جایگزین نکن:**
- `.env` (توکن و تنظیمات واقعیت توشه)
- `config.py` (سالم بود، عوض نشده)
- `guardbot.db` (دیتابیس واقعیت — هیچ‌وقت این فایل رو از zip جایگزین نکن)
- پوشه‌های `backups/`, `screenshots/`, `whispers/`, `playlists/`, `audio_temp/`

فایل‌های جدید (اضافه، نه جایگزین) که این‌بار همراه zip اومدن:
- `.env.example`
- `.gitignore`
- `scripts/backup.sh`, `scripts/restore.sh`, `scripts/guardbot.service.example`
- `DEPLOY.md`, `AUDIT.md` (همین فایل‌ها)

## مرحله ۴: نصب پکیج‌ها
```bash
source venv/bin/activate   # اگه از venv استفاده می‌کنی
pip install -r requirements.txt --upgrade
```
نکته‌ی مهم: `requirements.txt` جدید شامل `python-telegram-bot[job-queue]` هست
(قبلاً بدون `[job-queue]` بود که باعث می‌شد پنل ادمین توی مکالمه‌های طولانی گیر کنه).

## مرحله ۵: اجرا کن و تست کن
```bash
python main.py
```
لاگ استارتاپ رو نگاه کن — نباید هیچ `ModuleNotFoundError` یا `AttributeError` ببینی.
اگه دیدی، همون خط خطا رو کامل برام بفرست.

تست‌های پیشنهادی به ترتیب:
1. ربات رو به یه گروه تستی اضافه کن → باید خودش پیام «ربات فعال شد» + دکمه‌های
   مدیریت رو بفرسته (یعنی `seed_default_group_content` کار کرده).
2. یه ممبر تستی وارد گروه بشه → باید پیام خوش‌آمدگویی + قوانین رو ببینه.
3. یه کلمه‌ی ممنوعه (یکی از نمونه‌های پیش‌فرض مثل «عوضی») رو تنها بفرست → باید
   حذف بشه. همون کلمه رو وسط یه کلمه‌ی دیگه بفرست → نباید حذف بشه.
4. توی پیوی ربات `/adminpanel` بزن → پنل فروش باید باز بشه.
5. توی گروه، ادمین `/start` بزنه → باید کیبورد کامل مدیریت گروه رو ببینه.

## مرحله ۶: با systemd دائمی‌اش کن (پیشنهادی برای تجاری شدن)
```bash
sudo cp scripts/guardbot.service.example /etc/systemd/system/guardbot.service
sudo nano /etc/systemd/system/guardbot.service   # مسیر/یوزر رو با مقدار واقعیت جایگزین کن
sudo systemctl daemon-reload
sudo systemctl enable guardbot
sudo systemctl start guardbot
sudo journalctl -u guardbot -f     # دیدن لاگ زنده
```

## بک‌آپ دوره‌ای
```bash
chmod +x scripts/backup.sh scripts/restore.sh
./scripts/backup.sh
```
برای بک‌آپ خودکار روزانه، این خط رو به `crontab -e` اضافه کن:
```
0 3 * * * cd /home/guardbot/telegram_guard_bot && ./scripts/backup.sh >> /var/log/guardbot_backup.log 2>&1
```

## اگه بعد از این مراحل هم خطا داشتی
عین قبل: کل متن ترمینال رو کپی کن، دقیقاً بگو کدوم مرحله رو انجام دادی، و برام بفرست.
