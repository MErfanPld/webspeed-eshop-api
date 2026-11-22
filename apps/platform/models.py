from django.db import models
from django.utils import timezone


class Plan(models.Model):
    """A subscription plan shown on the landing page."""

    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=60)
    tagline = models.CharField(max_length=160, blank=True)
    price_monthly = models.PositiveBigIntegerField(default=0)  # Toman
    price_yearly = models.PositiveBigIntegerField(default=0)  # Toman
    features = models.JSONField(default=list, blank=True)  # ["..."] shown as a checklist
    max_products = models.PositiveIntegerField(null=True, blank=True)  # null = unlimited
    max_members = models.PositiveIntegerField(null=True, blank=True)
    custom_domain = models.BooleanField(default=False)
    highlighted = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    sort = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort", "price_monthly"]

    def __str__(self):
        return self.name


class Subscription(models.Model):
    """A store's plan. Trial first; the platform admin extends `paid_until`."""

    class Status(models.TextChoices):
        TRIAL = "trial", "دوره آزمایشی"
        ACTIVE = "active", "فعال"
        SUSPENDED = "suspended", "معلق"

    store = models.OneToOneField("stores.Store", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TRIAL)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    paid_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.store} · {self.plan}"

    @property
    def ends_at(self):
        return self.paid_until if self.status == self.Status.ACTIVE else self.trial_ends_at

    @property
    def is_active(self) -> bool:
        if self.status == self.Status.SUSPENDED:
            return False
        end = self.ends_at
        return end is None or end >= timezone.now()


# --- Landing site content (managed in /django-admin) ------------------------------------
ICON_CHOICES = [
    (x, x)
    for x in (
        "MousePointerClick", "Globe", "CreditCard", "Percent", "MessageSquare", "Users", "Palette", "BarChart3",
        "ShieldCheck", "Store", "LayoutTemplate", "Smartphone", "Rocket", "Truck", "Search", "Zap", "Package",
        "Headphones", "Lock", "Sparkles", "PenTool", "Image", "Settings", "CheckCircle2",
    )
]


def landing_upload(instance, filename):
    import os
    import uuid

    ext = os.path.splitext(filename)[1].lower()[:8]
    return f"platform/{instance.__class__.__name__.lower()}/{uuid.uuid4().hex}{ext}"


def validate_video(f):
    from django.core.exceptions import ValidationError

    if not f.name.lower().endswith((".mp4", ".webm")):
        raise ValidationError("فقط فایل MP4 یا WEBM")


def validate_image(f):
    from django.core.exceptions import ValidationError

    if not f.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        raise ValidationError("فقط تصویر PNG، JPG، WEBP یا GIF")


class LandingSettings(models.Model):  # noqa: DJ008
    """Single row: texts, video and contact details of the landing site."""

    hero_badge = models.CharField("برچسب بالای عنوان", max_length=120, default="۱۴ روز رایگان · بدون نیاز به کارت بانکی")
    hero_title = models.CharField("عنوان اصلی", max_length=160, default="فروشگاه اینترنتی خودتان را")
    hero_highlight = models.CharField("بخش رنگی عنوان", max_length=80, default="در چند دقیقه")
    hero_title_end = models.CharField("ادامه عنوان", max_length=80, default="بسازید")
    hero_subtitle = models.TextField(
        "توضیح زیر عنوان",
        default="آدرس اختصاصی، صفحه‌ساز کشیدنی، پرداخت آنلاین، کد تخفیف و پنل مدیریت کامل — همه در یک جا، بدون یک خط کد.",
    )
    cta_primary = models.CharField("متن دکمه اصلی", max_length=60, default="ساخت فروشگاه رایگان")
    cta_secondary = models.CharField("متن دکمه دوم", max_length=60, default="تماشای ویدیو معرفی")
    show_stats = models.BooleanField("نمایش آمار واقعی پلتفرم", default=True)

    video_title = models.CharField("عنوان بخش ویدیو", max_length=120, default="وب‌اسپید را در ۲ دقیقه ببینید")
    video_text = models.TextField("توضیح بخش ویدیو", blank=True, default="از ثبت‌نام تا اولین سفارش: ساخت صفحه با کشیدن و رها کردن، افزودن محصول و دریافت پرداخت.")
    video_url = models.URLField(
        "لینک ویدیو (آپارات / یوتیوب / فایل mp4)", blank=True,
        help_text="مثلاً https://www.aparat.com/v/xxxxx یا https://youtu.be/xxxxx — یا به‌جای لینک، فایل آپلود کنید",
    )
    video_file = models.FileField("فایل ویدیو (mp4/webm)", upload_to=landing_upload, blank=True, validators=[validate_video])
    video_poster = models.FileField("تصویر پیش‌نمایش ویدیو", upload_to=landing_upload, blank=True, validators=[validate_image])

    support_phone = models.CharField("تلفن پشتیبانی", max_length=40, blank=True)
    support_email = models.EmailField("ایمیل پشتیبانی", blank=True)
    support_hours = models.CharField("ساعات پاسخ‌گویی", max_length=80, blank=True, default="شنبه تا پنجشنبه، ۹ تا ۱۸")
    instagram = models.CharField("اینستاگرام (بدون @)", max_length=60, blank=True)
    telegram = models.CharField("تلگرام (بدون @)", max_length=60, blank=True)
    enamad_html = models.TextField(
        "کد نماد اعتماد (اینماد)", blank=True,
        help_text="فقط کدی که از enamad.ir دریافت کرده‌اید؛ در فوتر نمایش داده می‌شود",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تنظیمات سایت معرفی"
        verbose_name_plural = "تنظیمات سایت معرفی"

    def __str__(self):
        return "تنظیمات سایت معرفی"

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "LandingSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class _Ordered(models.Model):
    sort = models.PositiveIntegerField("ترتیب", default=0)
    active = models.BooleanField("فعال", default=True)

    class Meta:
        abstract = True
        ordering = ["sort", "id"]


class LandingFeature(_Ordered):
    icon = models.CharField("آیکون", max_length=40, choices=ICON_CHOICES, default="Sparkles")
    title = models.CharField("عنوان", max_length=80)
    text = models.CharField("توضیح", max_length=300)

    class Meta(_Ordered.Meta):
        verbose_name = "امکان"
        verbose_name_plural = "امکانات (سایت معرفی)"

    def __str__(self):
        return self.title


class RoadmapStep(_Ordered):
    """«نقشه ساخت سایت»: steps from sign-up to the first sale."""

    icon = models.CharField("آیکون", max_length=40, choices=ICON_CHOICES, default="CheckCircle2")
    when = models.CharField("زمان", max_length=40, help_text="مثلاً «دقیقه اول» یا «روز اول»")
    title = models.CharField("عنوان", max_length=80)
    text = models.CharField("توضیح", max_length=300)

    class Meta(_Ordered.Meta):
        verbose_name = "مرحله نقشه ساخت"
        verbose_name_plural = "نقشه ساخت سایت"

    def __str__(self):
        return self.title


class FaqItem(_Ordered):
    question = models.CharField("سؤال", max_length=200)
    answer = models.TextField("پاسخ")

    class Meta(_Ordered.Meta):
        verbose_name = "سؤال متداول"
        verbose_name_plural = "سؤالات متداول"

    def __str__(self):
        return self.question


class Testimonial(_Ordered):
    """Real customer quotes only — the section is hidden while empty."""

    name = models.CharField("نام", max_length=80)
    role = models.CharField("سمت / فروشگاه", max_length=120, blank=True)
    text = models.TextField("متن نظر")
    rating = models.PositiveSmallIntegerField("امتیاز (۱ تا ۵)", default=5)
    avatar = models.FileField("تصویر", upload_to=landing_upload, blank=True, validators=[validate_image])
    store_url = models.URLField("لینک فروشگاه", blank=True)

    class Meta(_Ordered.Meta):
        verbose_name = "نظر مشتری"
        verbose_name_plural = "نظرات مشتریان (سایت معرفی)"

    def __str__(self):
        return self.name


class Article(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PUBLISHED = "published", "منتشرشده"

    title = models.CharField("عنوان", max_length=160)
    slug = models.SlugField("آدرس (انگلیسی)", max_length=120, unique=True, allow_unicode=True)
    excerpt = models.CharField("خلاصه", max_length=300)
    body = models.TextField(
        "متن",
        help_text="پاراگراف‌ها را با یک خط خالی جدا کنید. «## » برای تیتر، «- » برای فهرست، **متن** برای پررنگ.",
    )
    cover = models.FileField("تصویر کاور", upload_to=landing_upload, blank=True, validators=[validate_image])
    category = models.CharField("دسته", max_length=60, blank=True, default="آموزش")
    author = models.CharField("نویسنده", max_length=80, default="تیم وب‌اسپید")
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField("تاریخ انتشار", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "مقاله"
        verbose_name_plural = "مقالات (وبلاگ)"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        from django.utils import timezone

        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def read_minutes(self) -> int:
        return max(1, round(len(self.body.split()) / 200))
