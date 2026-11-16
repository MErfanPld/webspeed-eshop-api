"""Development settings."""
from .base import *  # noqa: F401, F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "web"])
JWT_COOKIE_SECURE = env.bool("JWT_COOKIE_SECURE", default=False)
OTP_DEV_RETURN_CODE = env.bool("OTP_DEV_RETURN_CODE", default=True)

# `runserver` handles every request in a new thread; persistent connections
# would leak one idle PostgreSQL connection per thread ("too many clients").
from .base import DATABASES  # noqa: E402

DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=0)
