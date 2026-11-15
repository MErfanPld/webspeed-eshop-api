"""Production settings."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403
from .base import CORS_ALLOWED_ORIGINS, SECRET_KEY, SIMPLE_JWT, SMS_BACKEND, env

DEBUG = False

if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("change-me"):
    raise ImproperlyConfigured("SECRET_KEY must be a random string of at least 50 characters.")
if len(SIMPLE_JWT["SIGNING_KEY"]) < 32:
    raise ImproperlyConfigured("JWT signing key (JWT_SIGNING_KEY or SECRET_KEY) must be at least 32 characters.")
if not CORS_ALLOWED_ORIGINS:
    raise ImproperlyConfigured("CORS_ALLOWED_ORIGINS must list the frontend origin(s).")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
JWT_COOKIE_SECURE = True
OTP_DEV_RETURN_CODE = False
if SMS_BACKEND == "console":
    import warnings

    warnings.warn("SMS_BACKEND=console: customer OTP codes are only logged, not sent.", stacklevel=1)
