"""
PythonAnywhere: production settings for a host without Redis, Postgres,
MinIO or a Celery worker. Values come from .env (read by base.py); these are
only safe defaults when a variable is missing. See deploy/PYTHONANYWHERE.md.

WSGI file:  os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.pythonanywhere"
"""
import os

# Defaults must be in place before base.py reads them
os.environ.setdefault("REDIS_URL", "")  # no Redis: database cache (run createcachetable)
os.environ.setdefault("STORAGE_BACKEND", "local")  # files on disk, /media/ via the Static files tab
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "True")  # no worker: run tasks inline
os.environ.setdefault("TRUST_PROXY_HEADERS", "True")  # PythonAnywhere (and Vercel) proxy requests

from .base import BASE_DIR, DATABASES, env  # noqa: E402
from .production import *  # noqa: E402, F401, F403

# SQLite next to the code unless DATABASE_URL says otherwise
if not env("DATABASE_URL", default=""):
    DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": str(BASE_DIR / "var" / "db.sqlite3")}
