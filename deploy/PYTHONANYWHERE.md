# API روی PythonAnywhere + فرانت روی Vercel

این راهنما برای آدرس `https://webspeedapi.pythonanywhere.com` نوشته شده است (نام کاربری PythonAnywhere: `webspeedapi`). اگر نام کاربری شما فرق دارد، در همه مسیرها عوضش کنید.

## محدودیت‌های PythonAnywhere
| مورد | وضعیت | راه‌حل در این پروژه |
|---|---|---|
| Redis | وجود ندارد | `REDIS_URL=` را خالی بگذارید؛ کش و محدودیت درخواست‌ها و کد ورود در دیتابیس ذخیره می‌شوند |
| PostgreSQL | فقط پلن پولی | SQLite (ساده‌ترین) یا MySQL پلن رایگان؛ هر دو تست شده‌اند |
| Celery worker | ندارد | پیش‌فرض `CELERY_TASK_ALWAYS_EAGER=True` است و کارها همان لحظه اجرا می‌شوند |
| MinIO / S3 | ندارد | `STORAGE_BACKEND=local`؛ فایل‌ها روی دیسک و از طریق Static files سرو می‌شوند |
| اینترنت خروجی (پلن رایگان) | فقط سایت‌های لیست سفید | پیامک (کاوه‌نگار) و درگاه (زرین‌پال) ممکن است در پلن رایگان مسدود باشند |
| زیردامنه برای هر فروشگاه | به Vercel مربوط است | پایین‌تر، بخش «دامنه» |

## ۱. کد و virtualenv
در Bash console ِ PythonAnywhere:

```bash
git clone https://github.com/MErfanPld/webspeed-eshop-api.git ~/webspeed-eshop-api
```

```bash
cd ~/webspeed-eshop-api && mkvirtualenv --python=python3.13 webspeed
```

```bash
pip install -r requirements/production.txt
```

## ۲. فایل `~/webspeed-eshop-api/.env`

```dotenv
DJANGO_SETTINGS_MODULE=config.settings.pythonanywhere
SECRET_KEY=<خروجی: python -c "import secrets; print(secrets.token_urlsafe(64))">
DEBUG=False
ALLOWED_HOSTS=webspeedapi.pythonanywhere.com
DATABASE_URL=sqlite:////home/webspeedapi/webspeed-eshop-api/var/db.sqlite3
REDIS_URL=
STORAGE_BACKEND=local
MEDIA_ROOT=/home/webspeedapi/webspeed-eshop-api/var/media
# آدرس فرانت روی Vercel (با https و بدون / آخر)
CORS_ALLOWED_ORIGINS=https://YOUR-APP.vercel.app
CSRF_TRUSTED_ORIGINS=https://YOUR-APP.vercel.app,https://webspeedapi.pythonanywhere.com
FRONTEND_URL=https://YOUR-APP.vercel.app
API_PUBLIC_URL=https://webspeedapi.pythonanywhere.com
# درخواست‌ها از طریق Vercel می‌رسند؛ بدون این، محدودیت درخواست برای همه کاربران مشترک می‌شود
TRUST_PROXY_HEADERS=True
ADMIN_EMAIL=you@example.com
ADMIN_PASSWORD=<رمز قوی>
SMS_BACKEND=console
PAYMENT_PROVIDER=mock
# فقط اگر دامنه دارید (بخش «دامنه»)؛ وگرنه خالی بگذارید
PLATFORM_DOMAIN=
```

> در production کد ورود مشتری (OTP) در پاسخ API برنمی‌گردد. با `SMS_BACKEND=console` کدها فقط در **Server log** ِ PythonAnywhere (تب Web) دیده می‌شوند. برای مشتری واقعی، پنل پیامک لازم است.

## ۳. دیتابیس و داده اولیه

```bash
cd ~/webspeed-eshop-api && mkdir -p var/media
```

```bash
set -a && source .env && set +a && python manage.py migrate
```

```bash
set -a && source .env && set +a && python manage.py createcachetable && python manage.py seed && python manage.py collectstatic --noinput
```

```bash
set -a && source .env && set +a && python manage.py createsuperuser
```

## ۴. تب Web
- **Virtualenv:** `/home/webspeedapi/.virtualenvs/webspeed`
- **Source code:** `/home/webspeedapi/webspeed-eshop-api`
- **WSGI configuration file:** همه محتوا را با این جایگزین کنید. `.env` خودکار خوانده می‌شود و تنظیمات مخصوص PythonAnywhere (`config/settings/pythonanywhere.py`) پیش‌فرض‌های بدون Redis، فایل محلی و SQLite را دارد:

```python
import os
import sys

PROJECT_PATH = "/home/webspeedapi/webspeed-eshop-api"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.pythonanywhere"

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
```

- **Static files:**

| URL | Directory |
|---|---|
| `/static/` | `/home/webspeedapi/webspeed-eshop-api/staticfiles` |
| `/media/` | `/home/webspeedapi/webspeed-eshop-api/var/media/public` |

- **Force HTTPS:** روشن.
- **Reload** بزنید و `https://webspeedapi.pythonanywhere.com/api/v1/health` را باز کنید؛ باید `{"status": "ok", ...}` برگرداند.

رسیدهای پرداخت در `var/media/private` می‌مانند و عمداً در Static files **نیستند**؛ فقط از طریق لینک امضاشده کوتاه‌مدت باز می‌شوند.

## ۵. Vercel
فایل `.env.vercel.example` در ریپوی فرانت را در Vercel وارد کنید (Settings → Environment Variables) و دوباره دیپلوی کنید. آدرس نهایی Vercel را در `CORS_ALLOWED_ORIGINS`، `CSRF_TRUSTED_ORIGINS` و `FRONTEND_URL` ِ `.env` بالا بگذارید و Reload کنید.

## ۶. دامنه و زیردامنه فروشگاه‌ها
- **بدون دامنه (فقط `xxx.vercel.app`):** `PLATFORM_DOMAIN` را در هر دو طرف خالی بگذارید. یک فروشگاه اصلی روی آدرس Vercel کار می‌کند و سایت معرفی در `/platform` است. Vercel روی `vercel.app` زیردامنه wildcard نمی‌دهد.
- **با دامنه (مثلاً `webspeed.ir`):** دامنه و `*.webspeed.ir` را در Vercel اضافه کنید. wildcard در Vercel نیاز دارد nameserverهای دامنه روی Vercel باشد. سپس `PLATFORM_DOMAIN=webspeed.ir` را در هر دو طرف بگذارید و در `.env` ِ API `CORS_ALLOWED_ORIGINS=https://webspeed.ir` را تنظیم کنید؛ همه زیردامنه‌ها خودکار مجاز می‌شوند.

## به‌روزرسانی

```bash
cd ~/webspeed-eshop-api && git pull && workon webspeed && pip install -r requirements/production.txt
```

```bash
set -a && source .env && set +a && python manage.py migrate && python manage.py collectstatic --noinput
```

سپس در تب Web روی Reload بزنید.
