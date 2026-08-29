"""
کلاینت سبک برای پرسیدن وضعیت لایسنس از ربات مرکزی HEXIRON SALES.
جایگزین سیستم فروش داخلی قدیمی شده - گارد دیگه خودش اشتراک نمی‌فروشه،
فقط از ربات مرکزی می‌پرسه «این گروه برای محصول گارد لایسنس فعال داره یا نه؟»

طراحی fail-safe: اگه ربات مرکزی/شبکه در دسترس نبود، آخرین جواب شناخته‌شده
(کش شده تا ۱۰ دقیقه) رو برمی‌گردونه؛ اگه هیچ کشی هم نبود، fail-open (اجازه بده)
تا یه قطعی موقت روی ربات مرکزی، خدمات مشتریای واقعی رو قطع نکنه.
"""
import logging
import time

import httpx

from config import CENTRAL_API_URL, CENTRAL_API_KEY, PRODUCT_ID

logger = logging.getLogger(__name__)

_CACHE_TTL = 120          # چند ثانیه یه جواب موفق رو کش کنیم (کاهش بار روی API مرکزی)
_STALE_FALLBACK_TTL = 600  # اگه API در دسترس نبود، تا چند ثانیه از کش قدیمی استفاده کنیم
_cache: dict[str, tuple[float, bool]] = {}  # group_id -> (زمان, active)


async def is_group_licensed(group_id) -> bool:
    group_id = str(group_id)
    now = time.time()

    cached = _cache.get(group_id)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{CENTRAL_API_URL}/api/v1/license",
                params={"product": PRODUCT_ID, "group_id": group_id},
                headers={"X-API-Key": CENTRAL_API_KEY},
            )
        if resp.status_code == 200:
            active = bool(resp.json().get("active"))
            _cache[group_id] = (now, active)
            return active
        logger.warning(f"license API returned {resp.status_code} for group {group_id}")
    except Exception as e:
        logger.warning(f"license API unreachable for group {group_id}: {e}")

    # API در دسترس نبود - اگه کش قدیمی‌تر (تا ۱۰ دقیقه) داریم ازش استفاده کن
    if cached and (now - cached[0]) < _STALE_FALLBACK_TTL:
        logger.warning(f"using stale cached license status for group {group_id}")
        return cached[1]

    # هیچ اطلاعاتی نداریم - fail-open تا مشتری واقعی قطع نشه
    logger.error(f"no cached license info for group {group_id} and API unreachable - failing open")
    return True
