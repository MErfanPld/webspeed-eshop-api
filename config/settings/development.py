"""
Django development settings for WebSpeed E-Shop API.
"""
from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

# More permissive CORS in development (still controlled by env)
# Do not force CORS_ALLOW_ALL_ORIGINS = True; use .env
