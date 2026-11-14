"""
Django base settings for WebSpeed E-Shop API.
All environment-specific values come from environment variables (see .env.example).
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.core",
    "apps.users",
    "apps.authentication",
    "apps.stores",
    "apps.pages",
    "apps.catalog",
    "apps.media",
    "apps.customers",
    "apps.orders",
    "apps.stats",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database (PostgreSQL) ---------------------------------------------------
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://{u}:{p}@{h}:{port}/{db}".format(
            u=env("POSTGRES_USER", default="webspeed"),
            p=env("POSTGRES_PASSWORD", default="webspeed"),
            h=env("POSTGRES_HOST", default="db"),
            port=env("POSTGRES_PORT", default="5432"),
            db=env("POSTGRES_DB", default="webspeed"),
        ),
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

# --- Cache (Redis) — also backs rate limiting --------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://redis:6379/0"),
        "KEY_PREFIX": "ws",
        "TIMEOUT": 300,
    }
}

# --- Auth --------------------------------------------------------------------
AUTH_USER_MODEL = "users.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# JWT cookies let the existing frontend repository work with credentials
# "same-origin" and no Authorization header. Cookie-authenticated unsafe
# requests are protected by an Origin check (apps.core.authentication).
JWT_COOKIE_ACCESS = "ws_access"
JWT_COOKIE_REFRESH = "ws_refresh"
JWT_COOKIE_SECURE = env.bool("JWT_COOKIE_SECURE", default=not DEBUG)
JWT_COOKIE_SAMESITE = env("JWT_COOKIE_SAMESITE", default="Lax")
JWT_COOKIE_DOMAIN = env("JWT_COOKIE_DOMAIN", default=None)
STORE_COOKIE = "ws_store"

# --- i18n --------------------------------------------------------------------
LANGUAGE_CODE = "fa"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static & files ----------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "var" / "media")))
MEDIA_URL = "/media/"

# Storage backend: "s3" (MinIO / S3) or "local" (filesystem)
STORAGE_BACKEND = env("STORAGE_BACKEND", default="s3")
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default="http://minio:9000")
S3_PUBLIC_URL = env("S3_PUBLIC_URL", default="")
S3_ACCESS_KEY = env("S3_ACCESS_KEY", default="")
S3_SECRET_KEY = env("S3_SECRET_KEY", default="")
S3_PUBLIC_BUCKET = env("S3_PUBLIC_BUCKET", default="webspeed-media")
S3_PRIVATE_BUCKET = env("S3_PRIVATE_BUCKET", default="webspeed-private")
S3_REGION = env("S3_REGION", default="us-east-1")
PRIVATE_URL_EXPIRE_SECONDS = env.int("PRIVATE_URL_EXPIRE_SECONDS", default=300)
# Browser-reachable S3 endpoint used to sign private URLs when it differs from
# the internal one (e.g. internal http://minio:9000 vs http://localhost:9000)
S3_BROWSER_ENDPOINT_URL = env("S3_BROWSER_ENDPOINT_URL", default="")

if STORAGE_BACKEND == "s3":
    _s3 = {
        "access_key": S3_ACCESS_KEY,
        "secret_key": S3_SECRET_KEY,
        "endpoint_url": S3_ENDPOINT_URL,
        "region_name": S3_REGION,
        "signature_version": "s3v4",
        "addressing_style": "path",
        "file_overwrite": False,
    }
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                **_s3,
                "bucket_name": S3_PUBLIC_BUCKET,
                "querystring_auth": False,
                # Public URL of the bucket, e.g. https://cdn.example.com/webspeed-media
                "custom_domain": S3_PUBLIC_URL.split("://", 1)[-1] or None,
                "url_protocol": "https:" if S3_PUBLIC_URL.startswith("https") else "http:",
            },
        },
        "private": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                **_s3,
                "bucket_name": S3_PRIVATE_BUCKET,
                "querystring_auth": True,
                "querystring_expire": PRIVATE_URL_EXPIRE_SECONDS,
                "default_acl": "private",
            },
        },
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(MEDIA_ROOT / "public"), "base_url": MEDIA_URL},
        },
        "private": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(MEDIA_ROOT / "private"), "base_url": None},
        },
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF ---------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.core.authentication.JWTHeaderOrCookieAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "WebSpeed E-Shop API",
    "DESCRIPTION": "Multi-store e-commerce + page builder API. Errors: {error, details} (Persian).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
}

# --- CORS (explicit origins only, never allow-all) ---------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "origin",
    "x-store-id",
    "x-store-host",
]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=CORS_ALLOWED_ORIGINS)

# --- WebSpeed ----------------------------------------------------------------
DEFAULT_STORE_SLUG = env("DEFAULT_STORE_SLUG", default="")
ADMIN_EMAIL = env("ADMIN_EMAIL", default="admin@webspeed.local")
ADMIN_PASSWORD = env("ADMIN_PASSWORD", default="")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# Trust X-Forwarded-For / X-Store-Host only behind a known proxy (frontend server)
TRUST_PROXY_HEADERS = env.bool("TRUST_PROXY_HEADERS", default=False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
APPEND_SLASH = False
