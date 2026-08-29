"""
ابزارهای Rate Limiting برای جلوگیری از حملات brute-force
"""
import time
from collections import defaultdict

# ذخیره تعداد تلاش‌ها
_attempts = defaultdict(list)


def is_rate_limited(key: str, max_attempts: int = 5, window_seconds: int = 300) -> bool:
    """
    بررسی می‌کند آیا کلید مورد نظر از حد مجاز عبور کرده است یا خیر.
    
    Args:
        key: کلید شناسایی (مثلاً adminpin_123456789)
        max_attempts: حداکثر تعداد تلاش مجاز در بازه زمانی
        window_seconds: بازه زمانی به ثانیه
    
    Returns:
        True اگر محدودیت اعمال شده باشد، False اگر هنوز مجاز است
    """
    now = time.time()
    
    # پاک کردن تلاش‌های قدیمی
    _attempts[key] = [t for t in _attempts[key] if now - t < window_seconds]
    
    # بررسی تعداد تلاش‌ها
    if len(_attempts[key]) >= max_attempts:
        return True
    
    # ثبت تلاش جدید
    _attempts[key].append(now)
    return False


def reset_rate_limit(key: str):
    """ریست کردن محدودیت برای یک کلید خاص"""
    if key in _attempts:
        del _attempts[key]