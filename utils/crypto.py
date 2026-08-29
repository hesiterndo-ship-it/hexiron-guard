"""
رمزنگاری شماره کارت‌ها با کتابخانه‌ی cryptography (Fernet - AES متقارن).

⚠️ برای اجرای production یک‌بار این فایل رو مستقیم اجرا کن تا یک کلید بسازه:
    python -m utils.crypto
و مقدار چاپ‌شده رو توی .env به‌عنوان CARD_ENCRYPTION_KEY قرار بده.
اگه این متغیر ست نشه، یک کلید تصادفیِ فقط-برای-همین-اجرا ساخته میشه که با
هر بار ری‌استارت عوض میشه و کارت‌های قبلاً ذخیره‌شده دیگه رمزگشایی نمیشن.
"""
import logging
from cryptography.fernet import Fernet, InvalidToken

from config import CARD_ENCRYPTION_KEY

logger = logging.getLogger(__name__)

if CARD_ENCRYPTION_KEY:
    _key = CARD_ENCRYPTION_KEY.encode()
else:
    logger.warning(
        "CARD_ENCRYPTION_KEY توی .env ست نشده! یک کلید موقت ساخته شد که با ری‌استارت عوض میشه. "
        "برای production حتماً یک کلید ثابت بساز (python -m utils.crypto) و توی .env بذار."
    )
    _key = Fernet.generate_key()

_fernet = Fernet(_key)


def encrypt_card(card_number: str) -> str:
    """شماره کارت رو رمزنگاری می‌کنه (خروجی متن قابل‌ذخیره توی دیتابیس)."""
    return _fernet.encrypt(card_number.encode()).decode()


def decrypt_card(token: str) -> str:
    """شماره کارت رمزنگاری‌شده رو برمی‌گردونه. اگه کلید عوض شده باشه یا داده خراب باشه، خطای واضح می‌ده."""
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return "⚠️ خطا در رمزگشایی (کلید عوض شده؟)"


if __name__ == "__main__":
    print("یک کلید جدید برای CARD_ENCRYPTION_KEY:")
    print(Fernet.generate_key().decode())