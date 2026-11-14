"""Test settings: local storage, in-memory cache, fast hashing."""
import tempfile
from pathlib import Path

from .base import *  # noqa: F401, F403

DEBUG = False
ALLOWED_HOSTS = ["*"]
CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
JWT_COOKIE_SECURE = False

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="ws-test-media-"))
STORAGE_BACKEND = "local"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": str(MEDIA_ROOT / "public"), "base_url": "/media/"},
    },
    "private": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": str(MEDIA_ROOT / "private"), "base_url": None},
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
