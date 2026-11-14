"""
Customer authentication with one-time codes (OTP) sent to the mobile number.

- Codes: 6 digits, stored only as a salted hash in Redis, valid 2 minutes,
  max 5 wrong attempts, then a new code must be requested.
- Rate limits: 3 codes per phone / 10 min, 10 per IP / 10 min.
- Session: signed, httpOnly `ws_customer` cookie bound to the store (30 days).
- SMS delivery: settings.SMS_BACKEND ("console" logs the code for
  development; plug a provider into `send_sms`).
"""
import hashlib
import hmac
import logging
import secrets

from django.conf import settings
from django.core import signing
from django.core.cache import cache

from apps.core import ratelimit
from apps.core.errors import ApiError, bad_request

logger = logging.getLogger(__name__)

CODE_TTL = 120
MAX_ATTEMPTS = 5
SESSION_COOKIE = "ws_customer"
SESSION_SALT = "ws.customer"
SESSION_MAX_AGE = 30 * 24 * 3600


def _key(store_id, phone) -> str:
    return f"otp:{store_id}:{phone}"


def _hash(code: str, phone: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def send_sms(phone: str, message: str) -> None:
    backend = settings.SMS_BACKEND
    if backend == "console":
        # Development only: the code is visible in the API log
        logger.warning("SMS to %s: %s", phone, message)
        return
    raise ApiError("ارسال پیامک پیکربندی نشده است", 503)


def request_code(request, store, phone: str) -> str:
    ratelimit.enforce(f"otp-phone:{store.id}:{phone}", 3, 600, "درخواست کد زیاد بود؛ {minutes} دقیقه دیگر دوباره تلاش کنید.")
    ratelimit.enforce(f"otp-ip:{ratelimit.client_ip(request)}", 10, 600, "درخواست کد زیاد بود؛ {minutes} دقیقه دیگر دوباره تلاش کنید.")
    code = f"{secrets.randbelow(10**6):06d}"
    cache.set(_key(store.id, phone), {"h": _hash(code, phone), "a": 0}, timeout=CODE_TTL)
    send_sms(phone, f"کد ورود به {store.name}: {code}")
    return code


def verify_code(store, phone: str, code: str) -> None:
    key = _key(store.id, phone)
    data = cache.get(key)
    if not data:
        raise bad_request("کد منقضی شده است؛ دوباره درخواست کنید")
    if data["a"] >= MAX_ATTEMPTS:
        cache.delete(key)
        raise bad_request("تلاش‌های ناموفق زیاد بود؛ کد جدید درخواست کنید")
    if not hmac.compare_digest(data["h"], _hash(code, phone)):
        data["a"] += 1
        cache.set(key, data, timeout=CODE_TTL)
        raise bad_request("کد واردشده اشتباه است")
    cache.delete(key)


def make_session(customer) -> str:
    return signing.dumps({"c": customer.id, "s": str(customer.store_id)}, salt=SESSION_SALT)


def read_session(request):
    raw = request.COOKIES.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        return signing.loads(raw, salt=SESSION_SALT, max_age=SESSION_MAX_AGE)
    except signing.BadSignature:
        return None


def set_session_cookie(response, token: str):
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=settings.JWT_COOKIE_SECURE,
        samesite=settings.JWT_COOKIE_SAMESITE,
        domain=settings.JWT_COOKIE_DOMAIN,
        path="/",
    )


def clear_session_cookie(response):
    response.delete_cookie(SESSION_COOKIE, path="/", domain=settings.JWT_COOKIE_DOMAIN, samesite=settings.JWT_COOKIE_SAMESITE)
