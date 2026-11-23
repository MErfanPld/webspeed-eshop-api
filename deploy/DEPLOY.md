# راه‌اندازی روی سرور (چندفروشگاهی روی زیردامنه‌ها)

نتیجه نهایی (به‌جای `webspeed.ir` دامنه خودتان را بگذارید):

| آدرس | چه چیزی |
|---|---|
| `webspeed.ir` و `www.webspeed.ir` | سایت معرفی، تعرفه‌ها و ثبت‌نام (`/signup`) |
| `panel.webspeed.ir/admin` | پنل مرکزی؛ هر کاربر همه فروشگاه‌های خودش را می‌بیند. کاربر superuser بخش «مدیریت پلتفرم» را هم دارد |
| `shop1.webspeed.ir` | فروشگاه shop1 |
| `shop1.webspeed.ir/admin` | پنل همان فروشگاه؛ فقط تیم shop1 وارد می‌شوند و فقط داده shop1 را می‌بینند |
| `media.webspeed.ir` | تصاویر محصولات (MinIO) |
| دامنه شخصی مشتری، مثل `myshop.com` | همان فروشگاه (پلن‌های حرفه‌ای و سازمانی) |

جداسازی فروشگاه‌ها:
- هر درخواست بر اساس نام دامنه به یک فروشگاه وصل می‌شود.
- زیردامنه‌ای که فروشگاه ندارد، یا زیردامنه رزرو (`www`، `panel`، `api` و…)، **هیچ‌وقت** فروشگاه دیگری را نشان نمی‌دهد و فقط «فروشگاهی در این آدرس وجود ندارد» می‌آید.
- کوکی‌های ورود مخصوص هر زیردامنه‌اند (`JWT_COOKIE_DOMAIN` را خالی بگذارید).
- پنل هر زیردامنه به همان فروشگاه قفل است.
- این‌ها در `tests/test_platform.py` تست شده‌اند.

## ۱. پیش‌نیازها
- یک سرور Ubuntu 22.04 یا 24.04 با حداقل ۲ CPU، ۴ گیگ RAM و ۴۰ گیگ دیسک
- Docker و Docker Compose v2.24 یا بالاتر:

  ```bash
  curl -fsSL https://get.docker.com | sh
  ```

- Nginx و certbot روی خود سرور:

  ```bash
  sudo apt install -y nginx certbot
  ```

## ۲. DNS
در پنل DNS دامنه دو رکورد بسازید:

| نوع | نام | مقدار |
|---|---|---|
| A | `@` | IP سرور |
| A | `*` | IP سرور |

رکورد wildcard (`*`) باعث می‌شود هر فروشگاه جدید بدون کار اضافه کار کند.

## ۳. کد
هر دو ریپو باید کنار هم باشند:

```bash
mkdir -p /srv/webspeed && cd /srv/webspeed
```

```bash
git clone git@github.com:MErfanPld/webspeed-eshop-api.git
```

```bash
git clone git@github.com:MErfanPld/webspeed-eshop.git
```

```bash
cd webspeed-eshop-api && cp .env.example .env
```

## ۴. تنظیم `.env` در پوشه API
مهم‌ترین مقادیر (بقیه در `.env.example` توضیح داده شده):

```dotenv
SECRET_KEY=<خروجی: python3 -c "import secrets; print(secrets.token_urlsafe(64))">
DEBUG=False
PLATFORM_DOMAIN=webspeed.ir
PANEL_SUBDOMAIN=panel
TRIAL_DAYS=14
ALLOWED_HOSTS=web,localhost,127.0.0.1,panel.webspeed.ir
CORS_ALLOWED_ORIGINS=https://webspeed.ir
CSRF_TRUSTED_ORIGINS=https://webspeed.ir,https://panel.webspeed.ir
FRONTEND_URL=https://panel.webspeed.ir
API_PUBLIC_URL=https://panel.webspeed.ir
JWT_COOKIE_SECURE=True
POSTGRES_PASSWORD=<رمز قوی>
DATABASE_URL=postgres://webspeed:<همان رمز>@db:5432/webspeed
REDIS_URL=redis://redis:6379/0
S3_ACCESS_KEY=<کلید>
S3_SECRET_KEY=<رمز قوی>
S3_PUBLIC_URL=https://media.webspeed.ir/webspeed-media
S3_BROWSER_ENDPOINT_URL=https://media.webspeed.ir
ADMIN_EMAIL=you@example.com
ADMIN_PASSWORD=<رمز قوی>
# سرویس‌های پولی (بعد از خرید):
SMS_BACKEND=console
PAYMENT_PROVIDER=mock
```

توضیح چند مقدار:
- **زیردامنه‌ها در CORS:** همه زیردامنه‌های `PLATFORM_DOMAIN` خودکار مجاز هستند و فقط دامنه اصلی را در `CORS_ALLOWED_ORIGINS` بنویسید.
- **`API_PUBLIC_URL`:** آدرسی است که درگاه پرداخت به آن برمی‌گردد. چون Next.js مسیر `/api/v1` را به API می‌فرستد، آدرس پنل کافی است.
- **`PAYMENT_PROVIDER=mock`:** درگاه آزمایشی است و در production نباید بماند. بعد از گرفتن مرچنت، `zarinpal` بگذارید.

## ۵. اجرا

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

این دستور Postgres، Redis، MinIO، API، worker و فرانت را بالا می‌آورد. migrate و داده اولیه خودکار اجرا می‌شوند. سرویس‌ها فقط روی `127.0.0.1` در دسترس‌اند.

برای ساختن مدیر پلتفرم (برای بخش «مدیریت پلتفرم» در پنل مرکزی):

```bash
docker compose exec web python manage.py createsuperuser
```

## ۶. گواهی SSL wildcard
گواهی `*.webspeed.ir` فقط با چالش DNS صادر می‌شود:

```bash
sudo certbot certonly --manual --preferred-challenges dns -d webspeed.ir -d '*.webspeed.ir'
```

certbot یک رکورد TXT می‌دهد؛ آن را در DNS بگذارید و Enter بزنید.

برای تمدید خودکار، از افزونه DNS سرویس‌دهنده‌تان استفاده کنید؛ مثلاً برای Cloudflare: `python3-certbot-dns-cloudflare`.

## ۷. Nginx

```bash
sudo cp deploy/nginx/webspeed.conf /etc/nginx/sites-available/webspeed.conf
```

```bash
sudo sed -i 's/webspeed\.ir/YOUR-DOMAIN/g' /etc/nginx/sites-available/webspeed.conf
```

```bash
sudo ln -s /etc/nginx/sites-available/webspeed.conf /etc/nginx/sites-enabled/
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## ۸. بررسی
- `https://webspeed.ir` باید صفحه معرفی و تعرفه‌ها را نشان دهد.
- از `https://webspeed.ir/signup` یک فروشگاه با زیردامنه `test1` بسازید و `https://test1.webspeed.ir/admin` را باز کنید.
- `https://chizi-nist.webspeed.ir` باید «فروشگاهی در این آدرس وجود ندارد» را نشان دهد.
- `https://panel.webspeed.ir/admin` را با حساب superuser باز کنید و به «مدیریت پلتفرم» بروید.

## ۹. مدیریت محتوای سایت معرفی
همه محتوای `webspeed.ir` از **`https://panel.webspeed.ir/django-admin`** (با حساب superuser) مدیریت می‌شود و تغییرات حداکثر ظرف یک دقیقه روی سایت دیده می‌شوند:

| بخش در django-admin | چه چیزی |
|---|---|
| تنظیمات سایت معرفی | متن‌های بخش اول، ویدیو معرفی (لینک آپارات یا یوتیوب، یا آپلود mp4)، تماس و پشتیبانی، کد اینماد |
| امکانات | کارت‌های امکانات (آیکون، عنوان، متن، ترتیب، فعال/غیرفعال) |
| نقشه ساخت سایت | مراحل از ثبت‌نام تا اولین فروش |
| سؤالات متداول | پرسش و پاسخ‌ها |
| نظرات مشتریان | فقط نظرات **واقعی** مشتری‌ها را وارد کنید؛ تا خالی است، این بخش نمایش داده نمی‌شود |
| مقالات (وبلاگ) | مقاله با کاور؛ در متن `## ` برای تیتر، `- ` برای فهرست و `**متن**` برای پررنگ |
| پلن‌ها / اشتراک‌ها | قیمت و امکانات پلن‌ها |

آمار بخش اول (تعداد فروشگاه، محصول و سفارش) **واقعی** است و از دیتابیس خوانده می‌شود. با «نمایش آمار واقعی پلتفرم» می‌توانید آن را خاموش کنید.

## ۱۰. مدیریت اشتراک‌ها
در «مدیریت پلتفرم» برای هر فروشگاه پلن، وضعیت (آزمایشی، فعال، معلق) و «اعتبار تا» را تعیین کنید.

فروشگاه منقضی یا معلق برای بازدیدکننده بسته می‌شود، ولی پنلش باز می‌ماند تا مالک تمدید کند. داده‌ها هیچ‌وقت حذف نمی‌شوند.

پرداخت آنلاین اشتراک هنوز پیاده نشده است. تا آن زمان، پس از دریافت مبلغ، اعتبار را دستی تمدید کنید.

## ۱۱. دامنه شخصی یک فروشگاه
۱. صاحب فروشگاه در «تنظیمات فروشگاه» دامنه را وارد می‌کند (مثل `myshop.com`).
۲. رکورد A آن دامنه را به IP سرور اشاره دهد.
۳. برای آن دامنه گواهی بگیرید:

   ```bash
   sudo certbot certonly --webroot -w /var/www/certbot -d myshop.com
   ```

۴. بلوک نمونه انتهای `webspeed.conf` را برای این دامنه کپی کنید و Nginx را reload کنید.

## ۱۲. پشتیبان‌گیری
بکاپ روزانه دیتابیس (مثلاً در cron):

```bash
docker compose exec -T db pg_dump -U webspeed -Fc webspeed > /srv/backups/db-$(date +%F).dump
```

از volume ‏`minio_data` (تصاویر و رسیدها) هم بکاپ بگیرید و چند نسخه آخر را خارج از سرور نگه دارید.

## ۱۳. به‌روزرسانی

```bash
cd /srv/webspeed/webspeed-eshop && git pull
```

```bash
cd ../webspeed-eshop-api && git pull
```

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## پیوست: فرانت روی Vercel
اگر فرانت را روی Vercel و API را روی سرور خودتان می‌گذارید:

۱. **متغیرها:** فایل `.env.vercel.example` (در ریپوی فرانت) را در Vercel وارد کنید (Settings → Environment Variables → Import) و سپس دیپلوی کنید. `API_INTERNAL_URL` و `MEDIA_PUBLIC_URLS` هنگام بیلد خوانده می‌شوند؛ بعد از هر تغییرشان دوباره دیپلوی کنید.

۲. **دامنه‌ها در Vercel:** `webspeed.ir` و `*.webspeed.ir` را به پروژه اضافه کنید. دامنه wildcard در Vercel فقط وقتی کار می‌کند که nameserverهای دامنه روی Vercel باشند. در آن صورت رکوردهای `api` و `media` را در DNS ِ Vercel به IP سرور خودتان بدهید.

۳. **API روی سرور:** بلوک `api.webspeed.ir` در `deploy/nginx/webspeed.conf` را فعال کنید و در `.env` ِ API بگذارید:

   ```dotenv
   ALLOWED_HOSTS=web,localhost,127.0.0.1,api.webspeed.ir,panel.webspeed.ir
   TRUST_PROXY_HEADERS=True
   API_PUBLIC_URL=https://api.webspeed.ir
   ```

   بدون `TRUST_PROXY_HEADERS=True` همه درخواست‌ها با IP ِ Vercel می‌رسند و محدودیت تعداد درخواست (ورود، کد پیامکی، ثبت سفارش) برای همه کاربران مشترک می‌شود.

۴. **پنل جنگو** در این حالت روی `https://api.webspeed.ir/django-admin` است. `https://api.webspeed.ir` را به `CSRF_TRUSTED_ORIGINS` اضافه کنید.
