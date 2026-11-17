import django.db.models.deletion
from django.db import migrations, models

PLANS = [
    {
        "slug": "starter", "name": "پایه", "sort": 1, "tagline": "برای شروع فروش آنلاین",
        "price_monthly": 290000, "price_yearly": 2900000, "max_products": 100, "max_members": 1,
        "features": ["تا ۱۰۰ محصول", "زیردامنه اختصاصی", "صفحه‌ساز کامل", "پرداخت کارت‌به‌کارت و آنلاین",
                     "کد تخفیف", "پشتیبانی تیکتی"],
    },
    {
        "slug": "pro", "name": "حرفه‌ای", "sort": 2, "highlighted": True, "tagline": "محبوب‌ترین برای کسب‌وکارهای در حال رشد",
        "price_monthly": 690000, "price_yearly": 6900000, "max_products": 2000, "max_members": 5,
        "custom_domain": True,
        "features": ["تا ۲٬۰۰۰ محصول", "دامنه اختصاصی", "۵ عضو تیم", "نظرات و برندها",
                     "گزارش فعالیت", "پیامک وضعیت سفارش", "پشتیبانی تلفنی"],
    },
    {
        "slug": "business", "name": "سازمانی", "sort": 3, "tagline": "بدون محدودیت برای فروشگاه‌های بزرگ",
        "price_monthly": 1490000, "price_yearly": 14900000, "custom_domain": True,
        "features": ["محصول نامحدود", "عضو تیم نامحدود", "دامنه اختصاصی", "اولویت پشتیبانی",
                     "مشاوره راه‌اندازی", "همه امکانات پلن حرفه‌ای"],
    },
]


def seed_plans(apps, schema_editor):
    Plan = apps.get_model("platform", "Plan")
    for p in PLANS:
        Plan.objects.update_or_create(slug=p["slug"], defaults=p)


class Migration(migrations.Migration):
    initial = True
    dependencies = [("stores", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Plan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=40, unique=True)),
                ("name", models.CharField(max_length=60)),
                ("tagline", models.CharField(blank=True, max_length=160)),
                ("price_monthly", models.PositiveBigIntegerField(default=0)),
                ("price_yearly", models.PositiveBigIntegerField(default=0)),
                ("features", models.JSONField(blank=True, default=list)),
                ("max_products", models.PositiveIntegerField(blank=True, null=True)),
                ("max_members", models.PositiveIntegerField(blank=True, null=True)),
                ("custom_domain", models.BooleanField(default=False)),
                ("highlighted", models.BooleanField(default=False)),
                ("active", models.BooleanField(default=True)),
                ("sort", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ["sort", "price_monthly"]},
        ),
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("trial", "دوره آزمایشی"), ("active", "فعال"), ("suspended", "معلق")], default="trial", max_length=10)),
                ("trial_ends_at", models.DateTimeField(blank=True, null=True)),
                ("paid_until", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscriptions", to="platform.plan")),
                ("store", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="subscription", to="stores.store")),
            ],
        ),
        migrations.RunPython(seed_plans, migrations.RunPython.noop),
    ]
